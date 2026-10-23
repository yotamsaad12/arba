"""Importing an authority's Form 4 list into the project's file.

The list is kept as a document (it's part of the file too), read into items, and each item
is matched to the project's existing items: the same document already on the list gets the
authority's appendix number, standard and notes; a new one becomes an item. Nothing changes
until the person approves.
"""

import re
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentSource, DocumentStatus, RequirementOrigin
from app.core.enums import RequirementStatus as S
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import (
    ChecklistImport,
    Document,
    ImportedItem,
    Project,
    Requirement,
    TemplateRequirement,
    User,
)
from app.email.processing import document_key
from app.modules.projects.schemas import RequirementCreate
from app.modules.requirements.checklist import create_item
from app.modules.requirements.list_reader import ListItem, read_list
from app.modules.requirements.schemas import ImportDecision, ImportedItemOut, ImportOut
from app.modules.requirements.service import (
    apply_automatic_statuses,
    load_graph,
    run_engine,
    sync_fulfilled,
)

# Words every item shares; they say nothing about which document it is.
_COMMON = {
    "אישור", "אשיור", "בדיקת", "בדיקה", "בדיקות", "של", "על", "ידי", "מאת", "עם", "את", "לפי",
    "טופס", "דוח", "ריכוז", "התאמת", "תקינות", "מוסמך", "מורשה", "לקבל", "קבלת", "מהעירייה",
    "המבנה", "לבדיקת", "מת", "עבור", "או", "לביצוע",
}  # fmt: skip
_COMMON_FORMS = {_c for word in _COMMON for _c in {word}}


# How the field writes the same thing differently.
_SYNONYMS = [
    ("מרחבים מוגנים", "ממד"),
    ("מרחב מוגן", "ממד"),
    ("ממדים", "ממד"),
    ("כיבוי אש", "כבאות"),
    ('משהב"ש', "משרד הבינוי"),
    ("משהבש", "משרד הבינוי"),
    ("חברת הפיתוח", "חברה מפתחת"),
    ("החברה המפתחת", "חברה מפתחת"),
    ("אינס'", "אינסטלציה"),
    ("טייח", "טיח"),
    ("ריכז", "ריכוז"),
    ("AS MADE", "עדות"),
    ("מדידה לאחר סוף העבודות", "תכנית עדות"),
    ("מהנדס חשמל", "חשמלאי"),
]


def _canonical(word: str) -> str:
    return re.sub(r"(?<=.)[וי]", "", word)


def _forms(word: str) -> set[str]:
    """The word without vav/yod (תכנית/תוכנית), and without up to three one-letter
    prefixes (ו, ה, ל, ב, מ, ש: "ולהחתים" ~ "חתום")."""
    forms = {_canonical(word)}
    while len(word) > 3 and word[0] in "והלבמש":
        word = word[1:]
        forms.add(_canonical(word))
    return forms


def _words(text: str) -> list[set[str]]:
    """The distinctive words of a title, each as its set of forms."""
    for phrase, replacement in _SYNONYMS:
        text = text.replace(phrase, replacement)
    words = []
    for raw in re.findall(r"[א-תa-zA-Z0-9]+", text.replace('"', "").replace("'", "")):
        if raw in _COMMON or len(raw) < 2:
            continue
        forms = _forms(raw)
        if not forms & _COMMON_FORMS and forms not in words:
            words.append(forms)
    return words


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    all_b = set().union(*wb)
    all_a = set().union(*wa)
    hits_a = sum(1 for forms in wa if forms & all_b)
    hits_b = sum(1 for forms in wb if forms & all_a)
    overlap = min(1.0, max(hits_a, hits_b) / min(len(wa), len(wb)))
    flat_a = " ".join(sorted(min(f) for f in wa))
    flat_b = " ".join(sorted(min(f) for f in wb))
    sequence = SequenceMatcher(None, flat_a, flat_b).ratio()
    return max(overlap * 0.9 + sequence * 0.1, sequence * 0.8)


def best_match(item: ListItem, requirements: list[Requirement]) -> Requirement | None:
    scored = []
    for r in requirements:
        score = similarity(item.title, r.title)
        if r.track == item.track:
            score += 0.1
        scored.append((score, r))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0] >= 0.62:
        return scored[0][1]
    return None


async def _form4_list_step(db: AsyncSession, project: Project) -> Requirement | None:
    return await db.scalar(
        select(Requirement)
        .join(TemplateRequirement, TemplateRequirement.id == Requirement.template_requirement_id)
        .where(Requirement.project_id == project.id, TemplateRequirement.key == "form4_list")
        .limit(1)
    )


async def start_import(
    db: AsyncSession,
    storage: Storage,
    project: Project,
    user: User,
    *,
    file_name: str,
    content_type: str,
    data: bytes | None = None,
    document: Document | None = None,
) -> ChecklistImport:
    """Reads a list from an upload (kept as a document under the Form 4 list step) or from a
    document already in the project (an authority's email attachment)."""
    if document is None:
        assert data is not None
        step = await _form4_list_step(db, project)
        document = Document(
            id=uuid.uuid4(),
            project_id=project.id,
            requirement_id=step.id if step else None,
            file_name=file_name,
            content_type=content_type,
            size_bytes=len(data),
            source=DocumentSource.upload,
            status=DocumentStatus.ready,
            uploaded_by=user.id,
        )
        document.storage_key = document_key(project.id, document.id)
        await storage.put(document.storage_key, data, content_type)
        db.add(document)
        await db.flush()
    else:
        data = await storage.get(document.storage_key)
        file_name, content_type = document.file_name, document.content_type

    requirements = list(
        await db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id)
            .order_by(Requirement.order, Requirement.building, Requirement.floor)
        )
    )
    # One entry per document type; copies per floor/building share a title stem.
    unique = [r for r in requirements if r.floor in (None, 1) and r.building in (None, 1)]
    refs = {f"R{i + 1}": r for i, r in enumerate(unique)}
    found = await read_list(
        file_name,
        content_type,
        data,
        [{"ref": ref, "title": r.title, "track": r.track.value} for ref, r in refs.items()],
    )
    if not found.items:
        raise AppError(422, "list_unreadable", "no items were found in this file")

    imported = ChecklistImport(
        project_id=project.id,
        user_id=user.id,
        document_id=document.id,
        file_name=file_name,
        track=found.track,
        source=found.source,
    )
    db.add(imported)
    await db.flush()
    for position, item in enumerate(found.items):
        # Lists repeat documents ("מודד לאחר סוף העבודות" three times): all merge into one.
        match = refs.get(item.match_ref or "") or best_match(item, unique)
        db.add(
            ImportedItem(
                import_id=imported.id,
                position=position,
                number=item.number,
                title=item.title,
                track=item.track,
                authority_type=item.authority_type,
                standard=item.standard,
                appendix=item.appendix,
                notes=item.notes,
                due_date=item.due_date,
                not_needed=item.not_needed,
                match_requirement_id=match.id if match else None,
            )
        )
    await db.commit()
    return imported


async def get_import(db: AsyncSession, project: Project, import_id: uuid.UUID) -> ChecklistImport:
    imported = await db.get(ChecklistImport, import_id)
    if imported is None or imported.project_id != project.id:
        raise not_found("import")
    return imported


async def import_out(db: AsyncSession, imported: ChecklistImport) -> ImportOut:
    rows = list(
        await db.execute(
            select(ImportedItem, Requirement.title)
            .outerjoin(
                Requirement,
                Requirement.id
                == func.coalesce(ImportedItem.requirement_id, ImportedItem.match_requirement_id),
            )
            .where(ImportedItem.import_id == imported.id)
            .order_by(ImportedItem.position)
        )
    )
    return ImportOut(
        id=imported.id,
        file_name=imported.file_name,
        track=imported.track,
        source=imported.source,
        applied_at=imported.applied_at,
        items=[
            ImportedItemOut(
                id=i.id,
                number=i.number,
                title=i.title,
                track=i.track,
                authority_type=i.authority_type,
                standard=i.standard,
                appendix=i.appendix,
                notes=i.notes,
                due_date=i.due_date,
                not_needed=i.not_needed,
                match_requirement_id=i.match_requirement_id,
                match_title=title,
                status=i.status,
                requirement_id=i.requirement_id,
            )
            for i, title in rows
        ],
    )


async def apply(
    db: AsyncSession,
    project: Project,
    user: User,
    import_id: uuid.UUID,
    decisions: list[ImportDecision] | None,
) -> ChecklistImport:
    """Applies the person's decisions, or Arba's proposals when none are given: merge into
    the matched item, add as a new item, or skip."""
    imported = await get_import(db, project, import_id)
    items = list(
        await db.scalars(
            select(ImportedItem)
            .where(ImportedItem.import_id == imported.id, ImportedItem.status == "proposed")
            .order_by(ImportedItem.position)
        )
    )
    chosen = {d.item_id: d for d in decisions or []}
    for item in items:
        decision = chosen.get(item.id)
        action = decision.action if decision else ("merge" if item.match_requirement_id else "add")
        if decision and decision.requirement_id:
            item.match_requirement_id = decision.requirement_id
        if action == "skip":
            item.status = "skipped"
        elif action == "merge" and item.match_requirement_id:
            await _merge(db, project, item)
        else:
            requirement = await create_item(
                db,
                project,
                user,
                RequirementCreate(
                    title=item.title,
                    track=item.track,
                    authority_type=item.authority_type,
                    documents=[item.title],
                    appendix=item.appendix,
                    standard=item.standard,
                    due_date=item.due_date,
                    notes=item.notes,
                ),
                origin=RequirementOrigin.authority_list,
                origin_ref=f"import:{imported.id}",
            )
            if item.not_needed:
                requirement.status = S.not_applicable
            item.status, item.requirement_id = "added", requirement.id
    imported.applied_at = datetime.now(UTC)
    await db.flush()
    requirements, deps = await load_graph(db, project.id)
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    sync_fulfilled(requirements)
    await db.commit()
    return imported


async def _merge(db: AsyncSession, project: Project, item: ImportedItem) -> None:
    requirement = await db.get(Requirement, item.match_requirement_id)
    if requirement is None or requirement.project_id != project.id:
        raise not_found("requirement")
    # Every copy of the step (per floor / building) carries the authority's references.
    copies = (
        list(
            await db.scalars(
                select(Requirement).where(
                    Requirement.project_id == project.id,
                    Requirement.template_requirement_id == requirement.template_requirement_id,
                )
            )
        )
        if requirement.template_requirement_id
        else [requirement]
    )
    for r in copies:
        r.appendix = item.appendix or r.appendix
        r.standard = item.standard or r.standard
        r.due_date = item.due_date or r.due_date
        if item.notes and item.notes not in (r.notes or ""):
            r.notes = f"{r.notes}\n{item.notes}" if r.notes else item.notes
        if item.not_needed and r.status not in (S.done,):
            r.status, r.status_changed_at = S.not_applicable, datetime.now(UTC)
    item.status, item.requirement_id = "merged", requirement.id
