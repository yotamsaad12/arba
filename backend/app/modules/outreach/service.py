"""Arba writes to the approving bodies: drafts, the person's approval, sending, and follow-ups.

Nothing reaches an authority without a person's approval. Sent mail comes from Arba with the
project inbox as Reply-To, so the answer lands in the project's conversation; the person is
copied. Bodies that take requests only through a website get the text ready to paste.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid, parseaddr

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    Channel,
    DocumentStatus,
    DraftKind,
    DraftStatus,
    MessageDirection,
    NotificationKind,
    PermitStatus,
    ProjectRole,
    ProjectStatus,
    RequirementStatus,
    Urgency,
)
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import (
    AuditLog,
    Document,
    Message,
    OutboundDraft,
    Project,
    ProjectMember,
    Requirement,
    Thread,
    User,
)
from app.email.outgoing import send as send_email
from app.email.parsing import normalize_subject
from app.modules.notifications.service import WhatsAppContent, members, notify
from app.modules.outreach import writer
from app.modules.outreach.recipients import WRITES_TO, find_recipient
from app.modules.outreach.schemas import AttachmentOut, DraftOut, DraftUpdate
from app.modules.permits.service import permit_requirement
from app.modules.requirements.service import change_status

log = logging.getLogger(__name__)

# Days without an answer before Arba drafts a reminder, and reminders before it suggests a call.
FOLLOW_UP_DAYS = 7
MAX_REMINDERS = 3
# Writing to authorities starts once the permit is checked.
_PERMIT_OK = (PermitStatus.document_checked, PermitStatus.committee_confirmed)
_OPEN = (DraftStatus.draft,)


# --- Writing --------------------------------------------------------------------------


async def _owner(db: AsyncSession, project: Project) -> User | None:
    return await db.scalar(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project.id, ProjectMember.role == ProjectRole.owner)
        .limit(1)
    )


async def _documents(
    db: AsyncSession, project: Project, requirement: Requirement
) -> list[tuple[str, Document]]:
    """The step's own documents (S1…) and the permit (P1), as the letter may attach them."""
    own = list(
        await db.scalars(
            select(Document)
            .where(
                Document.requirement_id == requirement.id, Document.status == DocumentStatus.ready
            )
            .order_by(Document.created_at.desc())
            .limit(8)
        )
    )
    out = [(f"S{i + 1}", d) for i, d in enumerate(own)]
    permit_req = await permit_requirement(db, project)
    if permit_req and permit_req.id != requirement.id:
        permit = await db.scalar(
            select(Document)
            .where(
                Document.requirement_id == permit_req.id, Document.status == DocumentStatus.ready
            )
            .order_by(Document.created_at.desc())
            .limit(1)
        )
        if permit:
            out.append(("P1", permit))
    return out


async def create_draft(
    db: AsyncSession,
    project: Project,
    requirement: Requirement,
    kind: DraftKind = DraftKind.request,
    *,
    announce: bool = True,
) -> OutboundDraft:
    if requirement.authority_type not in WRITES_TO:
        raise AppError(422, "not_an_authority", "Arba writes only to approving bodies")
    existing = await db.scalar(
        select(OutboundDraft).where(
            OutboundDraft.requirement_id == requirement.id,
            OutboundDraft.status == DraftStatus.draft,
        )
    )
    if existing:
        return existing

    recipient = await find_recipient(db, project, requirement)
    owner = await _owner(db, project)
    documents = await _documents(db, project, requirement)
    thread = await db.scalar(
        select(Thread)
        .where(Thread.project_id == project.id, Thread.requirement_id == requirement.id)
        .order_by(Thread.last_message_at.desc())
        .limit(1)
    )
    history: list[tuple[str, date, str]] = []
    if thread:
        for m in await db.scalars(
            select(Message)
            .where(Message.thread_id == thread.id)
            .order_by(Message.sent_at.desc())
            .limit(3)
        ):
            history.insert(0, (m.direction.value, m.sent_at.date(), m.text_body))
    first_sent = await db.scalar(
        select(func.min(OutboundDraft.sent_at)).where(
            OutboundDraft.requirement_id == requirement.id,
            OutboundDraft.status == DraftStatus.sent,
        )
    )
    letter = await writer.write(
        writer.Facts(
            kind=kind,
            owner_name=owner.name if owner else "",
            address=project.address,
            locality=project.municipality,
            gush=project.gush,
            helka=project.helka,
            permit_number=project.permit_number,
            request_number=project.permit_request_number,
            requirement_title=requirement.title,
            requirement_description=requirement.description,
            required_documents=requirement.required_documents,
            authority_name=recipient.name,
            documents=[(ref, d.file_name) for ref, d in documents],
            history=history,
            first_sent=first_sent.date() if first_sent else None,
        )
    )
    by_ref = dict(documents)
    draft = OutboundDraft(
        project_id=project.id,
        requirement_id=requirement.id,
        thread_id=thread.id if thread else None,
        authority_id=recipient.authority_id,
        kind=kind,
        channel=recipient.channel,
        to_email=recipient.email,
        to_name=recipient.name,
        portal_url=recipient.portal_url,
        phone=recipient.phone,
        recipient_source=recipient.source,
        subject=letter.subject,
        body=letter.body,
        attachment_ids=[str(by_ref[r].id) for r in letter.attachment_refs if r in by_ref],
        missing_documents=letter.missing_documents,
        source=letter.source,
        model=letter.model,
    )
    db.add(draft)
    await db.commit()
    if announce:
        try:
            await _announce(db, project, requirement, draft)
        except Exception:
            log.exception("could not notify about draft %s", draft.id)
            await db.rollback()
    return draft


async def _announce(
    db: AsyncSession, project: Project, requirement: Requirement, draft: OutboundDraft
) -> None:
    what = "תזכורת" if draft.kind == DraftKind.reminder else "פנייה"
    to = draft.to_name or draft.to_email or "הגורם המאשר"
    link = f"{settings.app_url}/projects/{project.id}#drafts"
    if draft.channel == Channel.email:
        question = "לשלוח?"
        buttons = [(f"dr:{draft.id}:s", "✓ שליחה"), (f"dr:{draft.id}:e", "עריכה באפליקציה")]
        template = "arba_draft_ready"
        params = [project.name, requirement.title, f"{what} ל{to}", draft.subject]
    else:
        question = "הנוסח מוכן להדבקה באתר שלהם."
        buttons = []
        template = "arba_draft_ready_portal"
        params = [project.name, requirement.title, f"{what} ל{to}", link]
    await notify(
        db,
        await members(db, project.id, ProjectRole.manager),
        kind=NotificationKind.draft_ready,
        urgency=Urgency.urgent,
        title=f"Arba הכינה {what} ל{to} · {project.name}",
        body=f"{requirement.title}: {draft.subject}\n{question}",
        project_id=project.id,
        action_path=f"/projects/{project.id}#drafts",
        dedupe_key=f"draft:{draft.id}",
        whatsapp=WhatsAppContent(
            template=template,
            params=params,
            buttons=buttons,
            session_text=(
                f"✉️ {project.name} · {requirement.title}\n"
                f"Arba הכינה {what} ל{to}:\n{draft.subject}\n\n{question}"
            ),
        ),
    )


# --- The person decides ---------------------------------------------------------------


async def get_draft(db: AsyncSession, project: Project, draft_id: uuid.UUID) -> OutboundDraft:
    draft = await db.get(OutboundDraft, draft_id)
    if draft is None or draft.project_id != project.id:
        raise not_found("draft")
    return draft


def _open(draft: OutboundDraft) -> None:
    if draft.status != DraftStatus.draft:
        raise AppError(409, "draft_decided", "this draft was already sent or discarded")


async def update_draft(
    db: AsyncSession, project: Project, draft_id: uuid.UUID, data: DraftUpdate
) -> OutboundDraft:
    draft = await get_draft(db, project, draft_id)
    _open(draft)
    if data.subject is not None:
        draft.subject = data.subject
    if data.body is not None:
        draft.body = data.body
    if "to_email" in data.model_fields_set:
        draft.to_email = str(data.to_email).lower() if data.to_email else None
        draft.recipient_source = "user"
        if draft.to_email:
            draft.channel = Channel.email
    if data.attachment_ids is not None:
        allowed = set(
            await db.scalars(
                select(Document.id).where(
                    Document.project_id == project.id,
                    Document.id.in_(data.attachment_ids),
                    Document.status == DocumentStatus.ready,
                )
            )
        )
        draft.attachment_ids = [str(i) for i in data.attachment_ids if i in allowed]
    await db.commit()
    return draft


async def send_draft(
    db: AsyncSession, storage: Storage, project: Project, user: User, draft_id: uuid.UUID
) -> OutboundDraft:
    draft = await get_draft(db, project, draft_id)
    _open(draft)
    if draft.channel != Channel.email:
        raise AppError(409, "draft_not_email", "this body takes requests on its website")
    if not draft.to_email:
        raise AppError(422, "recipient_required", "add the email address to send to")

    thread = await db.get(Thread, draft.thread_id) if draft.thread_id else None
    previous = (
        await db.scalar(
            select(Message)
            .where(Message.thread_id == thread.id)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        if thread
        else None
    )
    attachments = list(
        await db.scalars(
            select(Document).where(
                Document.project_id == project.id,
                Document.id.in_([uuid.UUID(i) for i in draft.attachment_ids]),
            )
        )
    )
    now = datetime.now(UTC)
    message_id = make_msgid(domain=settings.inbox_domain)
    email = await _email(draft, project, user, message_id, previous, attachments, storage, now)
    if not await send_email(email):
        raise AppError(409, "email_held", "outgoing mail is held back in this environment")

    if thread is None:
        thread = Thread(
            id=uuid.uuid4(),
            project_id=project.id,
            requirement_id=draft.requirement_id,
            subject=draft.subject,
            normalized_subject=normalize_subject(draft.subject),
            counterparty_email=draft.to_email,
            counterparty_name=draft.to_name,
            last_message_at=now,
        )
        db.add(thread)
        await db.flush()
    thread.last_message_at = now
    message = Message(
        id=uuid.uuid4(),
        project_id=project.id,
        thread_id=thread.id,
        direction=MessageDirection.outbound,
        from_email=parseaddr(settings.email_from)[1].lower(),
        from_name=user.name,
        to=[draft.to_email],
        cc=[user.email],
        subject=draft.subject,
        text_body=draft.body,
        rfc_message_id=message_id.strip("<>").lower(),
        in_reply_to=previous.rfc_message_id if previous else None,
        references=[*previous.references, previous.rfc_message_id] if previous else [],
        sent_at=now,
        read_at=now,
    )
    db.add(message)
    await db.flush()
    draft.status = DraftStatus.sent
    draft.sent_at = now
    draft.decided_by = user.id
    draft.thread_id = thread.id
    draft.message_id = message.id
    await _after_sending(db, project, user, draft)
    return draft


async def _email(
    draft: OutboundDraft,
    project: Project,
    user: User,
    message_id: str,
    previous: Message | None,
    attachments: list[Document],
    storage: Storage,
    now: datetime,
) -> EmailMessage:
    to, subject, cc = draft.to_email or "", draft.subject, [user.email]
    allowed = settings.email_allowed_recipients
    if allowed is not None:
        allowed_lower = {a.lower() for a in allowed}
        # Development with a real mail server: the authority never receives a test letter.
        if to.lower() not in allowed_lower:
            subject = f"[בדיקה, במקום אל {to}] {subject}"
            to = allowed[0]
        cc = [c for c in cc if c.lower() in allowed_lower and c.lower() != to.lower()]

    msg = EmailMessage()
    msg["From"] = formataddr((f"{user.name} באמצעות Arba", parseaddr(settings.email_from)[1]))
    msg["To"] = formataddr((draft.to_name or "", to)) if draft.to_name else to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Reply-To"] = project.inbox_address
    msg["Subject"] = subject
    msg["Date"] = format_datetime(now)
    msg["Message-ID"] = message_id
    if previous:
        msg["In-Reply-To"] = f"<{previous.rfc_message_id}>"
        msg["References"] = " ".join(
            f"<{r}>" for r in [*previous.references, previous.rfc_message_id]
        )
    footer = "\n\n--\nנשלח באמצעות Arba בשם בעלי הפרויקט. תשובה למייל הזה תגיע ישירות לתיק הפרויקט."
    msg.set_content(draft.body + footer)
    for document in attachments:
        maintype, _, subtype = document.content_type.partition("/")
        msg.add_attachment(
            await storage.get(document.storage_key),
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=document.file_name,
        )
    return msg


async def mark_submitted(
    db: AsyncSession, project: Project, user: User, draft_id: uuid.UUID
) -> OutboundDraft:
    """The person submitted the text on the body's website (or at the counter)."""
    draft = await get_draft(db, project, draft_id)
    _open(draft)
    draft.status = DraftStatus.sent
    draft.sent_at = datetime.now(UTC)
    draft.decided_by = user.id
    await _after_sending(db, project, user, draft)
    return draft


async def _after_sending(
    db: AsyncSession, project: Project, user: User, draft: OutboundDraft
) -> None:
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="draft.sent",
            entity="outbound_draft",
            entity_id=draft.id,
            after={"to": draft.to_email or draft.portal_url, "kind": draft.kind},
        )
    )
    await db.commit()
    requirement = await db.get(Requirement, draft.requirement_id)
    if requirement and requirement.status != RequirementStatus.waiting_for_authority:
        try:
            await change_status(
                db, project, requirement.id, RequirementStatus.waiting_for_authority, user
            )
        except AppError as exc:
            # Sent either way; the step keeps its status (e.g. earlier steps aren't done).
            log.info("draft %s sent; status unchanged (%s)", draft.id, exc.code)


async def discard(db: AsyncSession, project: Project, user: User, draft_id: uuid.UUID) -> None:
    draft = await get_draft(db, project, draft_id)
    _open(draft)
    draft.status = DraftStatus.discarded
    draft.decided_by = user.id
    await db.commit()


async def list_open(db: AsyncSession, project: Project) -> list[DraftOut]:
    drafts = list(
        await db.scalars(
            select(OutboundDraft)
            .where(
                OutboundDraft.project_id == project.id, OutboundDraft.status == DraftStatus.draft
            )
            .order_by(OutboundDraft.created_at.desc())
        )
    )
    return [await draft_out(db, d) for d in drafts]


async def draft_out(db: AsyncSession, draft: OutboundDraft) -> DraftOut:
    requirement = await db.get(Requirement, draft.requirement_id)
    ids = [uuid.UUID(i) for i in draft.attachment_ids]
    names = {
        d.id: d.file_name for d in await db.scalars(select(Document).where(Document.id.in_(ids)))
    }
    return DraftOut(
        id=draft.id,
        requirement_id=draft.requirement_id,
        requirement_title=requirement.title if requirement else "",
        kind=draft.kind,
        channel=draft.channel,
        to_email=draft.to_email,
        to_name=draft.to_name,
        portal_url=draft.portal_url,
        phone=draft.phone,
        recipient_source=draft.recipient_source,
        subject=draft.subject,
        body=draft.body,
        attachments=[AttachmentOut(id=i, file_name=names[i]) for i in ids if i in names],
        missing_documents=draft.missing_documents,
        status=draft.status,
        source=draft.source,
        created_at=draft.created_at,
        sent_at=draft.sent_at,
    )


# --- Arba keeps things moving ---------------------------------------------------------


async def prepare_requests(db: AsyncSession, limit: int = 5) -> int:
    """Drafts the first request for authority steps that became ready. Once per step: a
    discarded draft means the person handles it another way."""
    drafted = select(OutboundDraft.requirement_id)
    filed = select(Thread.requirement_id).where(Thread.requirement_id.is_not(None))
    rows = list(
        await db.execute(
            select(Requirement, Project)
            .join(Project, Project.id == Requirement.project_id)
            .where(
                Project.status == ProjectStatus.active,
                Project.permit_status.in_(_PERMIT_OK),
                Requirement.status == RequirementStatus.ready,
                Requirement.authority_type.in_(WRITES_TO),
                Requirement.channel != Channel.in_person,
                Requirement.id.not_in(drafted),
                Requirement.id.not_in(filed),
            )
            .order_by(Requirement.order)
            .limit(limit)
        )
    )
    count = 0
    for requirement, project in rows:
        permit_req = await permit_requirement(db, project)
        if permit_req and permit_req.id == requirement.id:
            continue
        await create_draft(db, project, requirement)
        count += 1
    return count


async def prepare_reminders(db: AsyncSession, now: datetime, limit: int = 5) -> int:
    """Steps waiting on an authority that hasn't answered: a reminder draft, and after
    MAX_REMINDERS, a nudge to call."""
    due = now - timedelta(days=FOLLOW_UP_DAYS)
    last_sent = (
        select(OutboundDraft.requirement_id, func.max(OutboundDraft.sent_at).label("at"))
        .where(OutboundDraft.status == DraftStatus.sent)
        .group_by(OutboundDraft.requirement_id)
        .subquery()
    )
    rows = list(
        await db.execute(
            select(Requirement, Project, last_sent.c.at)
            .join(last_sent, last_sent.c.requirement_id == Requirement.id)
            .join(Project, Project.id == Requirement.project_id)
            .where(
                Project.status == ProjectStatus.active,
                Requirement.status == RequirementStatus.waiting_for_authority,
                last_sent.c.at <= due,
                Requirement.id.not_in(
                    select(OutboundDraft.requirement_id).where(
                        OutboundDraft.status == DraftStatus.draft
                    )
                ),
            )
            .limit(limit)
        )
    )
    count = 0
    for requirement, project, sent_at in rows:
        answered = await db.scalar(
            select(Message.id)
            .join(Thread, Thread.id == Message.thread_id)
            .where(
                Thread.requirement_id == requirement.id,
                Message.direction == MessageDirection.inbound,
                Message.sent_at > sent_at,
            )
            .limit(1)
        )
        if answered:
            continue
        reminders = await db.scalar(
            select(func.count())
            .select_from(OutboundDraft)
            .where(
                OutboundDraft.requirement_id == requirement.id,
                OutboundDraft.kind == DraftKind.reminder,
                OutboundDraft.status == DraftStatus.sent,
            )
        )
        if (reminders or 0) >= MAX_REMINDERS:
            await _suggest_call(db, project, requirement)
            continue
        await create_draft(db, project, requirement, DraftKind.reminder)
        count += 1
    return count


async def _suggest_call(db: AsyncSession, project: Project, requirement: Requirement) -> None:
    recipient = await find_recipient(db, project, requirement)
    phone = f" בטלפון {recipient.phone}" if recipient.phone else ""
    await notify(
        db,
        await members(db, project.id, ProjectRole.manager),
        kind=NotificationKind.authority_request,
        urgency=Urgency.normal,
        title=f"{recipient.name or 'הגורם המאשר'} לא עונים · {project.name}",
        body=(
            f"שלחנו {MAX_REMINDERS} תזכורות בנושא {requirement.title} ועדיין אין תשובה. "
            f"כדאי להתקשר אליהם{phone}."
        ),
        project_id=project.id,
        action_path=f"/projects/{project.id}",
        # Once per step.
        dedupe_key=f"call:{requirement.id}",
    )
