import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Protocol

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import rules
from app.ai.types import Attachment, Decision, Item, RequirementInfo
from app.core.config import settings
from app.core.enums import DocumentStatus, RequirementStatus, SuggestionStatus
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import (
    AuditLog,
    Document,
    Message,
    Project,
    Requirement,
    Suggestion,
    Thread,
    User,
)
from app.modules.documents import service as documents
from app.modules.inbox import service as inbox
from app.modules.notifications import triggers
from app.modules.notifications.service import resolve_for_suggestion
from app.modules.projects.schemas import stages_of
from app.modules.requirements.service import change_status
from app.modules.suggestions.schemas import (
    AcceptAll,
    AcceptAllResult,
    AcceptResult,
    AcceptSuggestion,
    SuggestionOut,
)

log = logging.getLogger(__name__)

_READABLE = ("application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp")
_MAX_READ_BYTES = 10 * 1024 * 1024


class Classifier(Protocol):
    reads_files: bool

    async def classify(self, item: Item, requirements: list[RequirementInfo]) -> Decision: ...


class RulesClassifier:
    reads_files = False

    async def classify(self, item: Item, requirements: list[RequirementInfo]) -> Decision:
        return rules.classify(item, requirements)


class ResilientClaude:
    """Claude, falling back to the rules engine if the API is unreachable or errors."""

    reads_files = True

    def __init__(self) -> None:
        from app.ai.claude import ClaudeClassifier

        self.claude = ClaudeClassifier()

    async def classify(self, item: Item, requirements: list[RequirementInfo]) -> Decision:
        try:
            return await self.claude.classify(item, requirements)
        except anthropic.APIError as exc:
            log.warning("Claude classification failed (%s); using rules", exc)
            return rules.classify(item, requirements)


def get_classifier() -> Classifier:
    use_claude = settings.ai_provider == "claude" or (
        settings.ai_provider == "auto" and bool(os.environ.get("ANTHROPIC_API_KEY"))
    )
    return ResilientClaude() if use_claude else RulesClassifier()


async def requirement_infos(db: AsyncSession, project: Project) -> list[RequirementInfo]:
    stage_titles = {s.key: s.title for s in stages_of(project)}
    return [
        RequirementInfo(
            id=r.id,
            title=r.title,
            stage_title=stage_titles.get(r.stage, r.stage),
            authority_type=r.authority_type,
            status=r.status,
            required_documents=r.required_documents,
            order=r.order * 100 + (r.floor or 0),
        )
        for r in await db.scalars(select(Requirement).where(Requirement.project_id == project.id))
    ]


async def _attachments(storage: Storage, docs: list[Document], read: bool) -> list[Attachment]:
    out = []
    for d in docs:
        data = None
        if read and d.content_type in _READABLE and d.size_bytes <= _MAX_READ_BYTES:
            data = await storage.get(d.storage_key)
        out.append(Attachment(d.file_name, d.content_type, data))
    return out


async def _project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id).options(selectinload(Project.template))
    )
    assert project is not None
    return project


def _record(decision: Decision, **target: object) -> Suggestion:
    return Suggestion(
        **target,
        requirement_id=decision.requirement_id,
        kind=decision.kind,
        suggested_status=RequirementStatus(decision.suggested_status)
        if decision.suggested_status
        else None,
        summary=decision.summary,
        reason=decision.reason,
        confidence=decision.confidence,
        source=decision.source,
        model=decision.model,
        input_tokens=decision.input_tokens,
        output_tokens=decision.output_tokens,
    )


async def suggest_for_message(
    db: AsyncSession,
    storage: Storage,
    classifier: Classifier,
    message_id: uuid.UUID,
    *,
    scan_id: uuid.UUID | None = None,
) -> Suggestion | None:
    """Proposes where the message's conversation belongs. Mail found by a mailbox scan
    (`scan_id`) is announced once, when the scan ends, not message by message."""
    message = await db.get(Message, message_id)
    if message is None:
        return None
    thread = await db.get(Thread, message.thread_id)
    assert thread is not None
    project = await _project(db, message.project_id)
    docs = list(
        await db.scalars(
            select(Document).where(
                Document.message_id == message.id, Document.status == DocumentStatus.ready
            )
        )
    )
    item = Item(
        source="email",
        subject=message.subject,
        text=message.text_body,
        sender_email=message.from_email,
        sender_name=message.from_name,
        attachments=await _attachments(storage, docs, classifier.reads_files),
        current_requirement_id=thread.requirement_id,
    )
    decision = await classifier.classify(item, await requirement_infos(db, project))

    # One open question per conversation: the newest message decides.
    for older in await db.scalars(
        select(Suggestion).where(
            Suggestion.thread_id == thread.id, Suggestion.status == SuggestionStatus.pending
        )
    ):
        older.status = SuggestionStatus.superseded
    suggestion = _record(
        decision,
        project_id=project.id,
        thread_id=thread.id,
        message_id=message.id,
        scan_id=scan_id,
    )
    db.add(suggestion)
    await db.commit()
    if scan_id is None:
        await _announce(db, suggestion)
    return suggestion


async def suggest_for_document(
    db: AsyncSession, storage: Storage, classifier: Classifier, document_id: uuid.UUID
) -> Suggestion | None:
    document = await db.get(Document, document_id)
    if document is None or document.requirement_id is not None:
        return None
    project = await _project(db, document.project_id)
    item = Item(
        source="document",
        subject=document.file_name,
        attachments=await _attachments(storage, [document], classifier.reads_files),
    )
    decision = await classifier.classify(item, await requirement_infos(db, project))
    suggestion = _record(decision, project_id=project.id, document_id=document.id)
    db.add(suggestion)
    await db.commit()
    await _announce(db, suggestion)
    return suggestion


async def _announce(db: AsyncSession, suggestion: Suggestion) -> None:
    # The suggestion is saved either way; people can still find it in the app.
    try:
        await triggers.suggestion_created(db, suggestion)
    except Exception:
        log.exception("could not notify about suggestion %s", suggestion.id)
        await db.rollback()


async def list_pending(db: AsyncSession, project_id: uuid.UUID) -> list[SuggestionOut]:
    rows = await db.execute(
        select(Suggestion, Requirement, Thread, Document)
        .outerjoin(Requirement, Requirement.id == Suggestion.requirement_id)
        .outerjoin(Thread, Thread.id == Suggestion.thread_id)
        .outerjoin(Document, Document.id == Suggestion.document_id)
        .where(Suggestion.project_id == project_id, Suggestion.status == SuggestionStatus.pending)
        .order_by(Suggestion.created_at.desc())
    )
    items = list(rows)
    file_counts: dict[uuid.UUID, int] = {}
    thread_ids = [s.thread_id for s, *_ in items if s.thread_id]
    if thread_ids:
        counted = await db.execute(
            select(Message.thread_id, func.count(Document.id))
            .join(Document, Document.message_id == Message.id)
            .where(Message.thread_id.in_(thread_ids), Document.status == DocumentStatus.ready)
            .group_by(Message.thread_id)
        )
        file_counts = {tid: n for tid, n in counted}

    out = []
    for s, requirement, thread, document in items:
        out.append(
            SuggestionOut(
                id=s.id,
                target="thread" if s.thread_id else "document",
                thread_id=s.thread_id,
                document_id=s.document_id,
                title=thread.subject if thread else document.file_name if document else "",
                sender=(thread.counterparty_name or thread.counterparty_email) if thread else None,
                file_count=file_counts.get(s.thread_id, 0) if s.thread_id else 1,
                requirement_id=s.requirement_id,
                requirement_title=requirement.title if requirement else None,
                requirement_status=requirement.status if requirement else None,
                kind=s.kind,
                suggested_status=s.suggested_status,
                summary=s.summary,
                reason=s.reason,
                confidence=s.confidence,
                source=s.source,
                created_at=s.created_at,
            )
        )
    return out


async def pending_count(db: AsyncSession, project_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Suggestion)
            .where(
                Suggestion.project_id == project_id,
                Suggestion.status == SuggestionStatus.pending,
            )
        )
        or 0
    )


async def _pending(db: AsyncSession, project: Project, suggestion_id: uuid.UUID) -> Suggestion:
    suggestion = await db.get(Suggestion, suggestion_id)
    if suggestion is None or suggestion.project_id != project.id:
        raise not_found("suggestion")
    if suggestion.status != SuggestionStatus.pending:
        raise AppError(409, "suggestion_decided", "this suggestion was already handled")
    return suggestion


async def accept(
    db: AsyncSession,
    project: Project,
    user: User,
    suggestion_id: uuid.UUID,
    data: AcceptSuggestion,
) -> AcceptResult:
    suggestion = await _pending(db, project, suggestion_id)
    suggested = suggestion.requirement_id
    target = data.requirement_id if "requirement_id" in data.model_fields_set else suggested
    if target is None:
        raise AppError(422, "requirement_required", "choose a requirement to file under")
    new_status = suggestion.suggested_status

    # Filing also settles this suggestion (see resolve.py), as accepted or changed.
    if suggestion.thread_id:
        await inbox.file_thread(db, project, user, suggestion.thread_id, target)
    elif suggestion.document_id:
        await documents.file_document(db, project, user, suggestion.document_id, target)

    applied, error = False, None
    if data.apply_status and new_status:
        requirement = await db.get(Requirement, target)
        if requirement is not None and requirement.status == new_status:
            applied = True
        else:
            # change_status refuses before changing anything, so the filing above stands.
            try:
                await change_status(db, project, target, new_status, user)
                applied = True
            except AppError as exc:
                error = exc.code

    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="suggestion.accepted" if target == suggested else "suggestion.changed",
            entity="suggestion",
            entity_id=suggestion_id,
            after={
                "requirement": str(target),
                "status": new_status if applied else None,
                "status_error": error,
            },
        )
    )
    await db.commit()
    return AcceptResult(requirement_id=target, status_applied=applied, status_error=error)


async def accept_all(
    db: AsyncSession, project: Project, user: User, data: AcceptAll
) -> AcceptAllResult:
    """Approves every pending suggestion that names a requirement, earliest requirement first
    so that statuses can follow the dependency order."""
    query = (
        select(Suggestion.id, Suggestion.requirement_id)
        .join(Requirement, Requirement.id == Suggestion.requirement_id, isouter=True)
        .where(Suggestion.project_id == project.id, Suggestion.status == SuggestionStatus.pending)
        .order_by(Requirement.order, Requirement.floor, Suggestion.created_at)
    )
    if data.scan_id:
        query = query.where(Suggestion.scan_id == data.scan_id)
    rows = list(await db.execute(query))
    accepted = applied = left = 0
    for suggestion_id, requirement_id in rows:
        if requirement_id is None:
            left += 1
            continue
        # Filing one thread can settle another suggestion; skip ones no longer pending.
        current = await db.get(Suggestion, suggestion_id)
        if current is None or current.status != SuggestionStatus.pending:
            continue
        result = await accept(db, project, user, suggestion_id, AcceptSuggestion())
        accepted += 1
        applied += result.status_applied
    return AcceptAllResult(accepted=accepted, statuses_applied=applied, left=left)


async def dismiss(db: AsyncSession, project: Project, user: User, suggestion_id: uuid.UUID) -> None:
    suggestion = await _pending(db, project, suggestion_id)
    suggestion.status = SuggestionStatus.dismissed
    suggestion.decided_by = user.id
    suggestion.decided_at = datetime.now(UTC)
    await resolve_for_suggestion(db, suggestion.id)
    await db.commit()
