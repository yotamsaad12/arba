import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.storage import get_storage
from app.modules.documents import service
from app.modules.documents.schemas import (
    DocumentOut,
    FileDocument,
    UploadRequest,
    UploadStarted,
    UploadTarget,
)
from app.modules.projects.service import get_project_for_user

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


@router.get("")
async def list_documents(
    project_id: uuid.UUID, db: DB, user: CurrentUser, requirement_id: uuid.UUID | None = None
) -> list[DocumentOut]:
    project, _ = await get_project_for_user(db, project_id, user)
    storage = get_storage()
    return [
        service.to_out(storage, d, name)
        for d, name in await service.list_documents(db, project.id, requirement_id)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def start_upload(
    project_id: uuid.UUID, data: UploadRequest, db: DB, user: CurrentUser
) -> UploadStarted:
    """Step 1 of 3: get a URL to PUT the file to. Then PUT it, then call /complete."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    document, upload = await service.start_upload(db, get_storage(), project, user, data)
    return UploadStarted(document_id=document.id, upload=UploadTarget(**upload.__dict__))


@router.post("/{document_id}/complete")
async def complete_upload(
    project_id: uuid.UUID, document_id: uuid.UUID, db: DB, user: CurrentUser
) -> DocumentOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    storage = get_storage()
    document = await service.complete_upload(db, storage, project, user, document_id)
    return service.to_out(storage, document, user.name)


@router.patch("/{document_id}")
async def file_document(
    project_id: uuid.UUID, document_id: uuid.UUID, data: FileDocument, db: DB, user: CurrentUser
) -> DocumentOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    document = await service.file_document(db, project, user, document_id, data.requirement_id)
    return service.to_out(get_storage(), document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    project_id: uuid.UUID, document_id: uuid.UUID, db: DB, user: CurrentUser
) -> None:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.delete_document(db, get_storage(), project, user, document_id)


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_documents(project_id: uuid.UUID, db: DB, user: CurrentUser) -> Response:
    """The whole document folder as a ZIP, organised by stage and requirement."""
    project, _ = await get_project_for_user(db, project_id, user)
    data = await service.export_zip(db, get_storage(), project)
    name = f"{project.name} - Arba.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"arba-{project.slug}.zip\"; filename*=UTF-8''{quote(name)}"
            )
        },
    )
