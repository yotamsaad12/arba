"""Checking documents filed under a step, and what follows from the check.

A problem is reported to the people managing the project right away. When every document a
step needs is in and checks out, Arba proposes marking the step done; the person approves
with one tap (in the app or on WhatsApp).
"""

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CheckVerdict,
    DocumentStatus,
    MessageKind,
    NotificationKind,
    ProjectRole,
    RequirementStatus,
    SuggestionStatus,
    Urgency,
)
from app.core.storage import Storage
from app.db.models import Document, Project, Requirement, Suggestion
from app.db.session import SessionLocal
from app.modules.checks import checker
from app.modules.notifications.service import members, notify

log = logging.getLogger(__name__)

# Checked in one go after a filing; the cron picks up anything left.
BATCH = 10


async def check_document(db: AsyncSession, storage: Storage, document: Document) -> None:
    requirement = (
        await db.get(Requirement, document.requirement_id) if document.requirement_id else None
    )
    project = await db.get(Project, document.project_id)
    if requirement is None or project is None or document.status != DocumentStatus.ready:
        return
    data = await storage.get(document.storage_key)
    result = await checker.check(
        document.file_name,
        document.content_type,
        data,
        checker.Facts(
            requirement_title=requirement.title,
            requirement_description=requirement.description,
            required_documents=requirement.required_documents,
            address=project.address,
            locality=project.municipality,
            gush=project.gush,
            helka=project.helka,
            permit_number=project.permit_number,
            today=date.today(),
        ),
    )
    document.check_status = result.verdict
    document.check_result = result.model_dump(mode="json")
    document.checked_at = datetime.now(UTC)
    await db.commit()

    if result.verdict == CheckVerdict.problem:
        await _report_problem(db, project, requirement, document, result)
    elif result.verdict in (CheckVerdict.ok, CheckVerdict.warning):
        await _propose_done(db, project, requirement, document)


async def _report_problem(
    db: AsyncSession,
    project: Project,
    requirement: Requirement,
    document: Document,
    result: checker.CheckResult,
) -> None:
    who = f" (הועלה על ידי {document.uploader_name})" if document.uploader_name else ""
    await notify(
        db,
        await members(db, project.id, ProjectRole.manager),
        kind=NotificationKind.document_problem,
        urgency=Urgency.urgent,
        title=f"בעיה במסמך · {project.name}",
        body=(
            f'Arba בדקה את "{document.file_name}"{who} בשלב {requirement.title}:\n'
            + "\n".join(f"• {i}" for i in (result.issues or [result.summary]))
        ),
        project_id=project.id,
        action_path=f"/projects/{project.id}?tab=all",
        dedupe_key=f"check:{document.id}",
    )


async def _propose_done(
    db: AsyncSession, project: Project, requirement: Requirement, document: Document
) -> None:
    if requirement.status in (RequirementStatus.done, RequirementStatus.not_applicable):
        return
    documents = list(
        await db.scalars(
            select(Document).where(
                Document.requirement_id == requirement.id,
                Document.status == DocumentStatus.ready,
            )
        )
    )
    if any(d.check_status == CheckVerdict.problem for d in documents):
        return
    good = [d for d in documents if d.check_status in (CheckVerdict.ok, CheckVerdict.warning)]
    covered = {s for d in good for s in (d.check_result or {}).get("satisfies", [])}
    missing = [r for r in requirement.required_documents if r not in covered]
    if missing or not good:
        return
    already = await db.scalar(
        select(Suggestion.id).where(
            Suggestion.requirement_id == requirement.id,
            Suggestion.status == SuggestionStatus.pending,
            Suggestion.suggested_status == RequirementStatus.done,
        )
    )
    if already:
        return

    from app.modules.suggestions.service import _announce

    warnings = [d for d in good if d.check_status == CheckVerdict.warning]
    reason = "כל המסמכים שהשלב דורש התקבלו ונבדקו."
    if warnings:
        reason += " שימו לב: " + "; ".join(
            str((d.check_result or {}).get("summary", "")) for d in warnings
        )
    suggestion = Suggestion(
        project_id=project.id,
        document_id=document.id,
        requirement_id=requirement.id,
        kind=MessageKind.approval,
        suggested_status=RequirementStatus.done,
        summary=f'כל המסמכים ל"{requirement.title}" נמצאים ונבדקו. אפשר לסמן את השלב כהושלם.',
        reason=reason,
        confidence=0.9 if not warnings else 0.7,
        source=str((document.check_result or {}).get("source", "rules")),
    )
    db.add(suggestion)
    await db.commit()
    await _announce(db, suggestion)


async def check_pending(
    db: AsyncSession, storage: Storage, project_id: uuid.UUID | None = None, limit: int = BATCH
) -> int:
    """Checks documents filed under a step that haven't been checked yet."""
    query = (
        select(Document)
        .where(
            Document.requirement_id.is_not(None),
            Document.status == DocumentStatus.ready,
            Document.check_status.is_(None),
        )
        .order_by(Document.created_at)
        .limit(limit)
    )
    if project_id:
        query = query.where(Document.project_id == project_id)
    count = 0
    for document in list(await db.scalars(query)):
        try:
            await check_document(db, storage, document)
            count += 1
        except Exception:
            log.exception("checking document %s failed", document.id)
            await db.rollback()
            # Don't retry forever: record that it couldn't be checked.
            stale = await db.get(Document, document.id)
            if stale is not None:
                stale.check_status = CheckVerdict.unchecked
                stale.check_result = {"summary": "הבדיקה האוטומטית נכשלה.", "issues": []}
                stale.checked_at = datetime.now(UTC)
                await db.commit()
    return count


async def check_in_background(project_id: uuid.UUID, storage: Storage) -> None:
    """After something was filed: check the project's new documents, with its own session."""
    async with SessionLocal() as db:
        await check_pending(db, storage, project_id)
