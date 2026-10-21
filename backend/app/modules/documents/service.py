import csv
import io
import re
import uuid
import zipfile
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import DocumentSource, DocumentStatus
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import AuditLog, Document, Project, Requirement, User
from app.email.processing import document_key
from app.modules.documents.schemas import DocumentOut, UploadRequest
from app.modules.projects.schemas import stages_of

# What people upload to a building file: scans, photos, office documents and drawings.
ALLOWED_EXTENSIONS = frozenset(
    {
        "pdf", "jpg", "jpeg", "png", "heic", "heif", "webp", "gif", "tif", "tiff",
        "doc", "docx", "xls", "xlsx", "csv", "txt", "dwg", "dxf", "zip",
    }
)  # fmt: skip


def _audit(project: Project, user: User | None, action: str, doc: Document, **after: object):
    return AuditLog(
        organization_id=project.organization_id,
        project_id=project.id,
        user_id=user.id if user else None,
        action=action,
        entity="document",
        entity_id=doc.id,
        after={"file_name": doc.file_name, **{k: str(v) if v else None for k, v in after.items()}},
    )


async def ensure_requirement(
    db: AsyncSession, project: Project, requirement_id: uuid.UUID | None
) -> Requirement | None:
    if requirement_id is None:
        return None
    requirement = await db.get(Requirement, requirement_id)
    if requirement is None or requirement.project_id != project.id:
        raise not_found("requirement")
    return requirement


async def start_upload(
    db: AsyncSession, storage: Storage, project: Project, user: User, data: UploadRequest
) -> tuple[Document, object]:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if data.size_bytes > max_bytes:
        raise AppError(
            413, "file_too_large", "file is too large", {"max_mb": settings.max_upload_mb}
        )
    extension = PurePath(data.file_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(415, "file_type_not_allowed", "file type is not allowed")
    await ensure_requirement(db, project, data.requirement_id)

    document = Document(
        id=uuid.uuid4(),
        project_id=project.id,
        requirement_id=data.requirement_id,
        file_name=data.file_name,
        content_type=data.content_type,
        size_bytes=data.size_bytes,
        source=DocumentSource.upload,
        status=DocumentStatus.pending,
        uploaded_by=user.id,
    )
    document.storage_key = document_key(project.id, document.id)
    db.add(document)
    await db.commit()
    return document, storage.presign_upload(document.storage_key, data.content_type, max_bytes)


async def get_document(db: AsyncSession, project: Project, document_id: uuid.UUID) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.project_id != project.id:
        raise not_found("document")
    return document


async def complete_upload(
    db: AsyncSession, storage: Storage, project: Project, user: User, document_id: uuid.UUID
) -> Document:
    document = await get_document(db, project, document_id)
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
    db.add(
        _audit(project, user, "document.uploaded", document, requirement=document.requirement_id)
    )
    await db.commit()
    return document


async def file_document(
    db: AsyncSession,
    project: Project,
    user: User,
    document_id: uuid.UUID,
    requirement_id: uuid.UUID | None,
) -> Document:
    document = await get_document(db, project, document_id)
    await ensure_requirement(db, project, requirement_id)
    document.requirement_id = requirement_id
    db.add(_audit(project, user, "document.filed", document, requirement=requirement_id))
    await db.commit()
    return document


async def delete_document(
    db: AsyncSession, storage: Storage, project: Project, user: User, document_id: uuid.UUID
) -> None:
    document = await get_document(db, project, document_id)
    await storage.delete(document.storage_key)
    db.add(_audit(project, user, "document.deleted", document))
    await db.delete(document)
    await db.commit()


async def list_documents(
    db: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID | None = None
) -> list[tuple[Document, str | None]]:
    query = (
        select(Document, User.name)
        .outerjoin(User, User.id == Document.uploaded_by)
        .where(Document.project_id == project_id, Document.status == DocumentStatus.ready)
        .order_by(Document.created_at.desc())
    )
    if requirement_id:
        query = query.where(Document.requirement_id == requirement_id)
    return [(d, name) for d, name in await db.execute(query)]


async def document_counts(db: AsyncSession, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Document.requirement_id, func.count())
        .where(
            Document.project_id == project_id,
            Document.status == DocumentStatus.ready,
            Document.requirement_id.is_not(None),
        )
        .group_by(Document.requirement_id)
    )
    return {rid: n for rid, n in rows}


def to_out(
    storage: Storage, document: Document, uploaded_by_name: str | None = None
) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        file_name=document.file_name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        source=document.source,
        requirement_id=document.requirement_id,
        message_id=document.message_id,
        created_at=document.created_at,
        uploaded_by_name=uploaded_by_name,
        download_url=storage.presign_download(
            document.storage_key, document.file_name, document.content_type
        ),
    )


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _safe(name: str, limit: int = 80) -> str:
    cleaned = _UNSAFE.sub("_", name).strip(" .") or "_"
    return cleaned[:limit]


async def export_zip(db: AsyncSession, storage: Storage, project: Project) -> bytes:
    """The Form 4 file: one folder per stage and requirement, plus an index for Excel."""
    stage_titles = {s.key: (i + 1, s.title) for i, s in enumerate(stages_of(project))}
    requirements = {
        r.id: r
        for r in await db.scalars(select(Requirement).where(Requirement.project_id == project.id))
    }
    documents = await list_documents(db, project.id)

    buffer = io.BytesIO()
    index = io.StringIO()
    writer = csv.writer(index)
    writer.writerow(["תיקייה", "קובץ", "דרישה", "מקור", "תאריך"])
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for document, _ in sorted(documents, key=lambda d: d[0].created_at):
            requirement = (
                requirements.get(document.requirement_id) if document.requirement_id else None
            )
            if requirement:
                number, title = stage_titles.get(requirement.stage, (99, requirement.stage))
                folder = f"{number:02d} {_safe(title)}/{_safe(requirement.title)}"
            else:
                folder = "00 לא מתויק"
            name = PurePath(document.file_name)
            stem = _safe(name.stem)
            suffix = "." + _safe(name.suffix[1:], 10) if name.suffix else ""
            path = f"{folder}/{stem}{suffix}"
            n = 2
            while path in used:
                path = f"{folder}/{stem} ({n}){suffix}"
                n += 1
            used.add(path)
            archive.writestr(path, await storage.get(document.storage_key))
            writer.writerow(
                [
                    folder,
                    PurePath(path).name,
                    requirement.title if requirement else "",
                    "מייל" if document.source == DocumentSource.email else "העלאה",
                    f"{document.created_at:%d/%m/%Y}",
                ]
            )
        # BOM so Excel opens the Hebrew correctly.
        archive.writestr("index.csv", "﻿" + index.getvalue())
    return buffer.getvalue()
