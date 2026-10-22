"""Turns a stored inbound delivery into a message in a project thread, with its attachments
filed as documents."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentSource, DocumentStatus, InboundStatus, MessageDirection
from app.core.storage import Storage
from app.db.models import Document, InboundEmail, Message, Project, Thread
from app.email.parsing import ParsedAttachment, ParsedEmail, normalize_subject, parse_postmark

log = logging.getLogger(__name__)

# Replies that lost their threading headers still join a thread with the same subject and
# sender, if it was active recently.
SUBJECT_MATCH_WINDOW = timedelta(days=90)
# Small inline images are logos and signatures, not documents.
INLINE_IMAGE_MAX_BYTES = 50_000


def raw_key(inbound_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return f"inbound/{now:%Y/%m}/{inbound_id}.json"


def document_key(project_id: uuid.UUID, document_id: uuid.UUID) -> str:
    # No file name in the key: names are user data (Hebrew, slashes, anything).
    return f"projects/{project_id}/documents/{document_id}"


async def process_inbound(
    db: AsyncSession, storage: Storage, inbound_id: uuid.UUID
) -> uuid.UUID | None:
    """Returns the id of the new message, if one was created."""
    inbound = await db.get(InboundEmail, inbound_id)
    if inbound is None or inbound.status not in (InboundStatus.received, InboundStatus.failed):
        return None
    try:
        payload = json.loads(await storage.get(inbound.raw_key))
        return await _process(db, storage, inbound, parse_postmark(payload))
    except Exception as exc:  # noqa: BLE001 - keep the delivery and record why it failed
        await db.rollback()
        inbound = await db.get(InboundEmail, inbound_id)
        if inbound is not None:
            inbound.status = InboundStatus.failed
            inbound.error = f"{type(exc).__name__}: {exc}"[:2000]
            await db.commit()
        log.exception("inbound email %s failed", inbound_id)
        return None


async def _process(
    db: AsyncSession, storage: Storage, inbound: InboundEmail, email: ParsedEmail
) -> uuid.UUID | None:
    project = await _find_project(db, email.recipients)
    inbound.processed_at = datetime.now(UTC)
    if project is None:
        inbound.status = InboundStatus.unroutable
        await db.commit()
        return None
    inbound.project_id = project.id

    message_id = await store_email(db, storage, project, email, inbound_email_id=inbound.id)
    if message_id is None:
        inbound.status = InboundStatus.duplicate
        await db.commit()
        return None
    inbound.status = InboundStatus.processed
    inbound.error = None
    await db.commit()
    return message_id


async def store_email(
    db: AsyncSession,
    storage: Storage,
    project: Project,
    email: ParsedEmail,
    *,
    direction: MessageDirection = MessageDirection.inbound,
    inbound_email_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Adds the email to its thread in the project, with its attachments as documents.
    Returns the new message's id, or None if the project already has it. Flushes, doesn't
    commit."""
    duplicate = await db.scalar(
        select(Message.id).where(
            Message.project_id == project.id, Message.rfc_message_id == email.message_id
        )
    )
    if duplicate:
        return None

    thread = await _find_thread(db, project.id, email)
    if thread is None:
        # Mail the person sent (found in their mailbox) is a conversation with its recipient.
        outbound = direction == MessageDirection.outbound and email.to
        thread = Thread(
            id=uuid.uuid4(),
            project_id=project.id,
            subject=email.subject or "(ללא נושא)",
            normalized_subject=normalize_subject(email.subject),
            counterparty_email=email.to[0] if outbound else email.from_email,
            counterparty_name=None if outbound else email.from_name,
            last_message_at=email.sent_at,
        )
        db.add(thread)
        await db.flush()
    thread.last_message_at = max(thread.last_message_at, email.sent_at)

    message = Message(
        id=uuid.uuid4(),
        project_id=project.id,
        thread_id=thread.id,
        direction=direction,
        from_email=email.from_email,
        from_name=email.from_name,
        to=email.to,
        cc=email.cc,
        subject=email.subject,
        text_body=email.text,
        rfc_message_id=email.message_id,
        in_reply_to=email.in_reply_to,
        references=email.references,
        sent_at=email.sent_at,
        inbound_email_id=inbound_email_id,
    )
    db.add(message)
    await db.flush()

    for attachment in email.attachments:
        if _is_decoration(attachment):
            continue
        document_id = uuid.uuid4()
        key = document_key(project.id, document_id)
        await storage.put(key, attachment.data, attachment.content_type)
        db.add(
            Document(
                id=document_id,
                project_id=project.id,
                # A thread already filed under a requirement files its new attachments too.
                requirement_id=thread.requirement_id,
                message_id=message.id,
                storage_key=key,
                file_name=attachment.name,
                content_type=attachment.content_type,
                size_bytes=len(attachment.data),
                source=DocumentSource.email,
                status=DocumentStatus.ready,
            )
        )

    await db.flush()
    return message.id


def _is_decoration(attachment: ParsedAttachment) -> bool:
    return (
        attachment.content_id is not None
        and attachment.content_type.startswith("image/")
        and len(attachment.data) <= INLINE_IMAGE_MAX_BYTES
    )


async def _find_project(db: AsyncSession, recipients: list[str]) -> Project | None:
    if not recipients:
        return None
    return await db.scalar(
        select(Project).where(func.lower(Project.inbox_address).in_(recipients)).limit(1)
    )


async def _find_thread(
    db: AsyncSession, project_id: uuid.UUID, email: ParsedEmail
) -> Thread | None:
    # 1. Standard threading headers.
    ids = [i for i in [email.in_reply_to, *reversed(email.references)] if i]
    if ids:
        thread_id = await db.scalar(
            select(Message.thread_id)
            .where(Message.project_id == project_id, Message.rfc_message_id.in_(ids))
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        if thread_id:
            return await db.get(Thread, thread_id)

    # 2. Same subject from the same sender, recently.
    subject = normalize_subject(email.subject)
    if not subject:
        return None
    return await db.scalar(
        select(Thread)
        .where(
            Thread.project_id == project_id,
            Thread.normalized_subject == subject,
            Thread.counterparty_email == email.from_email,
            Thread.last_message_at >= email.sent_at - SUBJECT_MATCH_WINDOW,
        )
        .order_by(Thread.last_message_at.desc())
        .limit(1)
    )
