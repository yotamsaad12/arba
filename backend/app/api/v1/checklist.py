import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.errors import AppError, not_found
from app.core.storage import get_storage
from app.db.models import ChecklistImport, Document
from app.modules.projects.service import get_project_for_user
from app.modules.requirements import list_import
from app.modules.requirements.schemas import ApplyImport, ImportFromDocument, ImportOut

router = APIRouter(prefix="/projects/{project_id}/checklist", tags=["checklist"])

# What authorities' lists come as: Excel sheets, letters (PDF), scans and photos, text.
_LIST_TYPES = {".xlsx", ".xlsm", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".txt"}


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def import_list(
    project_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> ImportOut:
    """Reads an authority's Form 4 list and proposes, item by item, where it goes. The file
    is kept in the project under the Form 4 list step."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    name = file.filename or "list"
    if PurePath(name).suffix.lower() not in _LIST_TYPES:
        raise AppError(415, "file_type_not_allowed", "send an Excel, PDF, image or text file")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            413, "file_too_large", "file is too large", {"max_mb": settings.max_upload_mb}
        )
    imported = await list_import.start_import(
        db,
        get_storage(),
        project,
        user,
        file_name=name,
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return await list_import.import_out(db, imported)


@router.post("/imports/from-document", status_code=status.HTTP_201_CREATED)
async def import_from_document(
    project_id: uuid.UUID, data: ImportFromDocument, db: DB, user: CurrentUser
) -> ImportOut:
    """Reads a list that is already in the project, e.g. an attachment of the authority's email."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    document = await db.get(Document, data.document_id)
    if document is None or document.project_id != project.id:
        raise not_found("document")
    imported = await list_import.start_import(
        db,
        get_storage(),
        project,
        user,
        file_name=document.file_name,
        content_type=document.content_type,
        document=document,
    )
    return await list_import.import_out(db, imported)


@router.get("/imports")
async def list_imports(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[ImportOut]:
    project, _ = await get_project_for_user(db, project_id, user)
    rows = await db.scalars(
        select(ChecklistImport)
        .where(ChecklistImport.project_id == project.id)
        .order_by(ChecklistImport.created_at.desc())
        .limit(10)
    )
    return [await list_import.import_out(db, i) for i in rows]


@router.get("/imports/{import_id}")
async def get_import(
    project_id: uuid.UUID, import_id: uuid.UUID, db: DB, user: CurrentUser
) -> ImportOut:
    project, _ = await get_project_for_user(db, project_id, user)
    return await list_import.import_out(db, await list_import.get_import(db, project, import_id))


@router.post("/imports/{import_id}/apply")
async def apply_import(
    project_id: uuid.UUID, import_id: uuid.UUID, data: ApplyImport, db: DB, user: CurrentUser
) -> ImportOut:
    """Applies the person's decisions (or Arba's proposals as they are)."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    imported = await list_import.apply(db, project, user, import_id, data.decisions)
    return await list_import.import_out(db, imported)
