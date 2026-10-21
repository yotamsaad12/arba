import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentSource, DocumentStatus
from app.core.errors import not_found
from app.core.storage import Storage
from app.db.models import AuditLog, Document, Message, Project, Requirement, Thread, User
from app.modules.documents import service as documents
from app.modules.inbox.schemas import MessageOut, ThreadDetail, ThreadSummary
from app.modules.projects.schemas import InboxCounts

SNIPPET_LENGTH = 140


async def list_threads(db: AsyncSession, project_id: uuid.UUID) -> list[ThreadSummary]:
    stats = (
        select(
            Message.thread_id,
            func.count().label("messages"),
            func.count(case((Message.read_at.is_(None), 1))).label("unread"),
        )
        .where(Message.project_id == project_id)
        .group_by(Message.thread_id)
        .subquery()
    )
    files = (
        select(Message.thread_id, func.count(Document.id).label("files"))
        .join(Document, Document.message_id == Message.id)
        .where(Message.project_id == project_id, Document.status == DocumentStatus.ready)
        .group_by(Message.thread_id)
        .subquery()
    )
    latest = (
        select(Message.text_body)
        .where(Message.thread_id == Thread.id)
        .order_by(Message.sent_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Thread, stats.c.messages, stats.c.unread, files.c.files, Requirement.title, latest)
        .join(stats, stats.c.thread_id == Thread.id)
        .outerjoin(files, files.c.thread_id == Thread.id)
        .outerjoin(Requirement, Requirement.id == Thread.requirement_id)
        .where(Thread.project_id == project_id)
        .order_by(Thread.last_message_at.desc())
    )
    return [
        _summary(t, messages, unread, n_files or 0, title, text)
        for t, messages, unread, n_files, title, text in rows
    ]


def _summary(
    thread: Thread,
    messages: int,
    unread: int,
    attachments: int,
    requirement_title: str | None,
    last_text: str | None,
) -> ThreadSummary:
    snippet = " ".join((last_text or "").split())
    return ThreadSummary(
        id=thread.id,
        subject=thread.subject,
        counterparty_email=thread.counterparty_email,
        counterparty_name=thread.counterparty_name,
        last_message_at=thread.last_message_at,
        message_count=messages,
        unread_count=unread,
        attachment_count=attachments,
        requirement_id=thread.requirement_id,
        requirement_title=requirement_title,
        snippet=snippet[:SNIPPET_LENGTH] + ("…" if len(snippet) > SNIPPET_LENGTH else ""),
    )


async def get_thread(db: AsyncSession, project: Project, thread_id: uuid.UUID) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None or thread.project_id != project.id:
        raise not_found("thread")
    return thread


async def thread_detail(
    db: AsyncSession, storage: Storage, project: Project, thread_id: uuid.UUID
) -> ThreadDetail:
    thread = await get_thread(db, project, thread_id)
    messages = list(
        await db.scalars(
            select(Message).where(Message.thread_id == thread.id).order_by(Message.sent_at)
        )
    )
    attachments: dict[uuid.UUID, list[Document]] = {}
    for doc in await db.scalars(
        select(Document)
        .where(
            Document.message_id.in_([m.id for m in messages]),
            Document.status == DocumentStatus.ready,
        )
        .order_by(Document.created_at)
    ):
        attachments.setdefault(doc.message_id, []).append(doc)  # type: ignore[arg-type]

    requirement = (
        await db.get(Requirement, thread.requirement_id) if thread.requirement_id else None
    )
    summary = _summary(
        thread,
        len(messages),
        sum(m.read_at is None for m in messages),
        sum(len(v) for v in attachments.values()),
        requirement.title if requirement else None,
        messages[-1].text_body if messages else "",
    )
    return ThreadDetail(
        **summary.model_dump(),
        messages=[
            MessageOut(
                id=m.id,
                direction=m.direction,
                from_email=m.from_email,
                from_name=m.from_name,
                to=m.to,
                cc=m.cc,
                subject=m.subject,
                text_body=m.text_body,
                sent_at=m.sent_at,
                read_at=m.read_at,
                attachments=[documents.to_out(storage, d) for d in attachments.get(m.id, [])],
            )
            for m in messages
        ],
    )


async def mark_read(db: AsyncSession, project: Project, thread_id: uuid.UUID) -> None:
    thread = await get_thread(db, project, thread_id)
    await db.execute(
        update(Message)
        .where(Message.thread_id == thread.id, Message.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()


async def file_thread(
    db: AsyncSession,
    project: Project,
    user: User,
    thread_id: uuid.UUID,
    requirement_id: uuid.UUID | None,
) -> None:
    """Files the conversation under a requirement, and its attachments with it."""
    thread = await get_thread(db, project, thread_id)
    await documents.ensure_requirement(db, project, requirement_id)
    previous = thread.requirement_id
    thread.requirement_id = requirement_id

    # Move attachments that were unfiled or followed the thread's previous filing; leave
    # ones a person filed somewhere else on purpose.
    movable = Document.requirement_id.is_(None)
    if previous:
        movable = or_(movable, Document.requirement_id == previous)
    message_ids = select(Message.id).where(Message.thread_id == thread.id)
    await db.execute(
        update(Document)
        .where(
            Document.message_id.in_(message_ids),
            Document.source == DocumentSource.email,
            movable,
        )
        .values(requirement_id=requirement_id)
    )
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="thread.filed",
            entity="thread",
            entity_id=thread.id,
            before={"requirement": str(previous) if previous else None},
            after={"requirement": str(requirement_id) if requirement_id else None},
        )
    )
    await db.commit()


async def counts(db: AsyncSession, project_id: uuid.UUID) -> InboxCounts:
    unread = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.project_id == project_id, Message.read_at.is_(None))
    )
    unfiled = await db.scalar(
        select(func.count())
        .select_from(Thread)
        .where(Thread.project_id == project_id, Thread.requirement_id.is_(None))
    )
    return InboxCounts(unread=unread or 0, unfiled=unfiled or 0)
