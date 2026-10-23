"""The project team, and asking its professionals for documents through a personal link.

The professional needs no account: the link shows what is asked and for which project, and
takes uploads straight into the step. Arba checks every file, tells the person who asked,
and reminds the professional while the request stays open.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    AuthorityType,
    DocumentSource,
    DocumentStatus,
    NotificationKind,
    ProjectRole,
    RequestStatus,
    Urgency,
)
from app.core.errors import AppError, not_found
from app.core.storage import PresignedUpload, Storage
from app.db.models import (
    AuditLog,
    Document,
    DocumentRequest,
    Project,
    ProjectContact,
    Requirement,
    User,
)
from app.email.outgoing import build as build_email
from app.email.outgoing import send as send_email
from app.email.processing import document_key
from app.modules.documents.service import ALLOWED_EXTENSIONS
from app.modules.notifications.service import members, notify
from app.modules.team.schemas import (
    ContactIn,
    FileOut,
    PublicRequestOut,
    PublicUpload,
    RequestCreate,
    RequestOut,
    TeamMemberOut,
)
from app.whatsapp.client import get_whatsapp
from app.whatsapp.phone import normalize_phone
from app.whatsapp.templates import DOCUMENT_REQUEST

log = logging.getLogger(__name__)

LINK_DAYS = 60
REMIND_AFTER = timedelta(days=3)
MAX_SENDS = 4  # the first request and three reminders

# People Arba writes to directly (outreach), and the homeowner: not asked through a link.
_NOT_TEAM = {
    AuthorityType.municipality,
    AuthorityType.water_corporation,
    AuthorityType.fire_department,
    AuthorityType.home_front_command,
    AuthorityType.owner,
}


# --- The team -------------------------------------------------------------------------


def contact_out(c: ProjectContact) -> TeamMemberOut:
    return TeamMemberOut(id=c.id, role=c.role, name=c.name, email=c.email, phone=c.phone)


async def list_contacts(db: AsyncSession, project: Project) -> list[TeamMemberOut]:
    rows = await db.scalars(
        select(ProjectContact)
        .where(ProjectContact.project_id == project.id)
        .order_by(ProjectContact.role, ProjectContact.name)
    )
    return [contact_out(c) for c in rows]


def _clean(data: ContactIn) -> dict[str, object]:
    phone = None
    if data.phone:
        phone = normalize_phone(data.phone)
        if phone is None:
            raise AppError(422, "invalid_phone", "not a valid phone number")
    return {
        "role": data.role,
        "name": data.name.strip(),
        "email": str(data.email).lower() if data.email else None,
        "phone": phone,
    }


async def add_contact(db: AsyncSession, project: Project, data: ContactIn) -> ProjectContact:
    contact = ProjectContact(project_id=project.id, **_clean(data))
    db.add(contact)
    await db.commit()
    return contact


async def get_contact(db: AsyncSession, project: Project, contact_id: uuid.UUID) -> ProjectContact:
    contact = await db.get(ProjectContact, contact_id)
    if contact is None or contact.project_id != project.id:
        raise not_found("contact")
    return contact


async def update_contact(
    db: AsyncSession, project: Project, contact_id: uuid.UUID, data: ContactIn
) -> ProjectContact:
    contact = await get_contact(db, project, contact_id)
    for key, value in _clean(data).items():
        setattr(contact, key, value)
    await db.commit()
    return contact


async def delete_contact(db: AsyncSession, project: Project, contact_id: uuid.UUID) -> None:
    contact = await get_contact(db, project, contact_id)
    await db.delete(contact)
    await db.commit()


# --- Requests -------------------------------------------------------------------------


def link_for(request: DocumentRequest) -> str:
    return f"{settings.app_url}/r/{request.token}"


async def create_request(
    db: AsyncSession, project: Project, user: User, data: RequestCreate
) -> tuple[DocumentRequest, list[str]]:
    requirement = await db.get(Requirement, data.requirement_id)
    if requirement is None or requirement.project_id != project.id:
        raise not_found("requirement")
    if data.contact is not None:
        if data.contact.role in _NOT_TEAM:
            raise AppError(422, "not_a_professional", "Arba writes to authorities itself")
        contact = await add_contact(db, project, data.contact)
    else:
        assert data.contact_id is not None
        contact = await get_contact(db, project, data.contact_id)

    request = DocumentRequest(
        project_id=project.id,
        requirement_id=requirement.id,
        contact_id=contact.id,
        token=secrets.token_urlsafe(24),
        documents=[d.strip() for d in data.documents if d.strip()],
        note=data.note.strip() if data.note else None,
        expires_at=datetime.now(UTC) + timedelta(days=LINK_DAYS),
        requested_by=user.id,
    )
    db.add(request)
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="document_request.created",
            entity="document_request",
            entity_id=request.id,
            after={"contact": contact.name, "documents": request.documents},
        )
    )
    await db.commit()
    sent = await send_request(db, request)
    return request, sent


async def send_request(
    db: AsyncSession, request: DocumentRequest, reminder: bool = False
) -> list[str]:
    """Emails and/or WhatsApps the link. Returns the channels that went out."""
    project = await db.get(Project, request.project_id)
    contact = await db.get(ProjectContact, request.contact_id)
    requirement = await db.get(Requirement, request.requirement_id)
    asker = await db.get(User, request.requested_by)
    assert project and contact and requirement and asker
    link = link_for(request)
    place = ", ".join(p for p in (project.address, project.municipality) if p)
    listing = "\n".join(f"• {d}" for d in request.documents)
    sent: list[str] = []

    if contact.email:
        prefix = "תזכורת: " if reminder else ""
        text = (
            f"שלום {contact.name},\n"
            f'{asker.name} מבקשים ממך מסמכים לשלב "{requirement.title}" בפרויקט {project.name}'
            f"{f' ({place})' if place else ''}:\n{listing}\n"
            + (f"\nהערה: {request.note}\n" if request.note else "")
            + "\nאפשר להעלות אותם ישירות מהקישור, בלי הרשמה ובלי סיסמה. "
            "Arba תתייק אותם בשלב הנכון ותעדכן את בעלי הפרויקט."
        )
        message = build_email(
            contact.email,
            f"{prefix}בקשה למסמכים · {project.name}",
            text,
            link,
            button="העלאת המסמכים",
            footer="קיבלת את המייל הזה כי בעלי הפרויקט ביקשו ממך מסמכים דרך Arba.",
            reply_to=asker.email,
        )
        try:
            if await send_email(message):
                sent.append("email")
        except Exception:
            log.exception("could not email document request %s", request.id)

    whatsapp = get_whatsapp()
    if contact.phone and whatsapp is not None:
        try:
            await whatsapp.send_template(
                contact.phone,
                DOCUMENT_REQUEST,
                [contact.name, asker.name, f"{project.name} · {requirement.title}", link],
            )
            sent.append("whatsapp")
        except Exception:
            log.exception("could not WhatsApp document request %s", request.id)

    if sent:
        request.sent_count += 1
        request.last_sent_at = datetime.now(UTC)
        await db.commit()
    return sent


async def get_request(db: AsyncSession, project: Project, request_id: uuid.UUID) -> DocumentRequest:
    request = await db.get(DocumentRequest, request_id)
    if request is None or request.project_id != project.id:
        raise not_found("request")
    return request


async def resend(db: AsyncSession, project: Project, request_id: uuid.UUID) -> list[str]:
    request = await get_request(db, project, request_id)
    if request.status == RequestStatus.cancelled:
        raise AppError(409, "request_cancelled", "this request was cancelled")
    if request.status == RequestStatus.fulfilled:
        request.status = RequestStatus.open
        request.fulfilled_at = None
    request.expires_at = max(request.expires_at, datetime.now(UTC) + timedelta(days=LINK_DAYS))
    await db.commit()
    return await send_request(db, request, reminder=True)


async def cancel(db: AsyncSession, project: Project, request_id: uuid.UUID) -> None:
    request = await get_request(db, project, request_id)
    request.status = RequestStatus.cancelled
    await db.commit()


async def _files(db: AsyncSession, request_id: uuid.UUID) -> list[FileOut]:
    rows = await db.scalars(
        select(Document)
        .where(Document.request_id == request_id, Document.status == DocumentStatus.ready)
        .order_by(Document.created_at)
    )
    return [
        FileOut(
            id=d.id, file_name=d.file_name, created_at=d.created_at, check_status=d.check_status
        )
        for d in rows
    ]


async def request_out(
    db: AsyncSession, request: DocumentRequest, sent_by: list[str] | None = None
) -> RequestOut:
    contact = await db.get(ProjectContact, request.contact_id)
    requirement = await db.get(Requirement, request.requirement_id)
    assert contact is not None
    return RequestOut(
        id=request.id,
        requirement_id=request.requirement_id,
        requirement_title=requirement.title if requirement else "",
        contact=contact_out(contact),
        documents=request.documents,
        note=request.note,
        status=request.status,
        link=link_for(request),
        sent_count=request.sent_count,
        last_sent_at=request.last_sent_at,
        fulfilled_at=request.fulfilled_at,
        created_at=request.created_at,
        files=await _files(db, request.id),
        sent_by=sent_by or [],
    )


async def list_requests(db: AsyncSession, project: Project) -> list[RequestOut]:
    recent = datetime.now(UTC) - timedelta(days=14)
    rows = await db.scalars(
        select(DocumentRequest)
        .where(
            DocumentRequest.project_id == project.id,
            (DocumentRequest.status == RequestStatus.open)
            | (DocumentRequest.fulfilled_at >= recent),
        )
        .order_by(DocumentRequest.created_at.desc())
    )
    return [await request_out(db, r) for r in rows]


async def remind_open(db: AsyncSession, now: datetime, limit: int = 20) -> int:
    """Open requests with no upload since the last message: send the link again."""
    rows = list(
        await db.scalars(
            select(DocumentRequest)
            .where(
                DocumentRequest.status == RequestStatus.open,
                DocumentRequest.last_sent_at <= now - REMIND_AFTER,
                DocumentRequest.sent_count < MAX_SENDS,
                DocumentRequest.expires_at > now,
            )
            .limit(limit)
        )
    )
    count = 0
    for request in rows:
        latest = await db.scalar(
            select(Document.created_at)
            .where(Document.request_id == request.id)
            .order_by(Document.created_at.desc())
            .limit(1)
        )
        if latest and request.last_sent_at and latest > request.last_sent_at:
            continue  # they're answering; no need to nag
        if await send_request(db, request, reminder=True):
            count += 1
    return count


# --- The professional's side (by link, no account) ------------------------------------


async def by_token(db: AsyncSession, token: str) -> DocumentRequest:
    request = await db.scalar(select(DocumentRequest).where(DocumentRequest.token == token))
    if request is None or request.status == RequestStatus.cancelled:
        raise AppError(404, "request_not_found", "this link is not valid")
    if request.expires_at < datetime.now(UTC):
        raise AppError(410, "request_expired", "this link has expired")
    return request


async def public_view(db: AsyncSession, token: str) -> PublicRequestOut:
    request = await by_token(db, token)
    project = await db.get(Project, request.project_id)
    contact = await db.get(ProjectContact, request.contact_id)
    requirement = await db.get(Requirement, request.requirement_id)
    asker = await db.get(User, request.requested_by)
    assert project and contact and requirement and asker
    return PublicRequestOut(
        project_name=project.name,
        place=", ".join(p for p in (project.address, project.municipality) if p),
        requested_by=asker.name,
        contact_name=contact.name,
        role=contact.role,
        requirement_title=requirement.title,
        documents=request.documents,
        note=request.note,
        status=request.status,
        expires_at=request.expires_at,
        files=await _files(db, request.id),
        max_upload_mb=settings.max_upload_mb,
    )


async def start_public_upload(
    db: AsyncSession, storage: Storage, token: str, data: PublicUpload
) -> tuple[Document, PresignedUpload]:
    request = await by_token(db, token)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if data.size_bytes > max_bytes:
        raise AppError(
            413, "file_too_large", "file is too large", {"max_mb": settings.max_upload_mb}
        )
    if PurePath(data.file_name).suffix.lower().lstrip(".") not in ALLOWED_EXTENSIONS:
        raise AppError(415, "file_type_not_allowed", "file type is not allowed")
    contact = await db.get(ProjectContact, request.contact_id)
    document = Document(
        id=uuid.uuid4(),
        project_id=request.project_id,
        requirement_id=request.requirement_id,
        request_id=request.id,
        uploader_name=contact.name if contact else None,
        file_name=data.file_name,
        content_type=data.content_type,
        size_bytes=data.size_bytes,
        source=DocumentSource.professional,
        status=DocumentStatus.pending,
    )
    document.storage_key = document_key(request.project_id, document.id)
    db.add(document)
    await db.commit()
    return document, storage.presign_upload(document.storage_key, data.content_type, max_bytes)


async def complete_public_upload(
    db: AsyncSession, storage: Storage, token: str, document_id: uuid.UUID
) -> Document:
    request = await by_token(db, token)
    document = await db.get(Document, document_id)
    if document is None or document.request_id != request.id:
        raise not_found("document")
    if document.status == DocumentStatus.ready:
        return document
    size = await storage.size(document.storage_key)
    if size is None:
        raise AppError(409, "upload_missing", "the file was not uploaded")
    if size > settings.max_upload_mb * 1024 * 1024:
        await storage.delete(document.storage_key)
        raise AppError(
            413, "file_too_large", "file is too large", {"max_mb": settings.max_upload_mb}
        )
    document.size_bytes = size
    document.status = DocumentStatus.ready
    await db.commit()
    await _tell_project(db, request, f'הועלה "{document.file_name}"', urgent=False)
    return document


async def mark_done(db: AsyncSession, token: str) -> None:
    """The professional says that's everything."""
    request = await by_token(db, token)
    if request.status == RequestStatus.fulfilled:
        return
    request.status = RequestStatus.fulfilled
    request.fulfilled_at = datetime.now(UTC)
    await db.commit()
    count = len(await _files(db, request.id))
    await _tell_project(db, request, f"סיימו להעלות ({count} קבצים). Arba בודקת אותם", urgent=True)


async def _tell_project(
    db: AsyncSession, request: DocumentRequest, what: str, urgent: bool
) -> None:
    project = await db.get(Project, request.project_id)
    contact = await db.get(ProjectContact, request.contact_id)
    requirement = await db.get(Requirement, request.requirement_id)
    if project is None or contact is None or requirement is None:
        return
    now = datetime.now(UTC)
    await notify(
        db,
        await members(db, project.id, ProjectRole.manager),
        kind=NotificationKind.document_received,
        urgency=Urgency.urgent if urgent else Urgency.normal,
        title=f"{contact.name}: {requirement.title} · {project.name}",
        body=f"{contact.name} {what}.",
        project_id=project.id,
        action_path=f"/projects/{project.id}?tab=all",
        # Many files in a row make one notification an hour, plus one when they're done.
        dedupe_key=f"request:{request.id}:{'done' if urgent else now.strftime('%Y%m%d%H')}",
    )
