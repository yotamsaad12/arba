"""The professional's upload page: reached by a personal link, no account."""

import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.core.deps import DB
from app.core.storage import get_storage
from app.modules.checks.service import check_in_background
from app.modules.documents.schemas import UploadStarted, UploadTarget
from app.modules.team import service
from app.modules.team.schemas import FileOut, PublicRequestOut, PublicUpload

router = APIRouter(prefix="/public/requests/{token}", tags=["public"])


@router.get("")
async def view_request(token: str, db: DB) -> PublicRequestOut:
    """What is asked, for which project, and what was uploaded so far."""
    return await service.public_view(db, token)


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def start_upload(token: str, data: PublicUpload, db: DB) -> UploadStarted:
    document, upload = await service.start_public_upload(db, get_storage(), token, data)
    return UploadStarted(document_id=document.id, upload=UploadTarget(**upload.__dict__))


@router.post("/uploads/{document_id}/complete")
async def complete_upload(
    token: str, document_id: uuid.UUID, db: DB, background: BackgroundTasks
) -> FileOut:
    storage = get_storage()
    document = await service.complete_public_upload(db, storage, token, document_id)
    background.add_task(check_in_background, document.project_id, storage)
    return FileOut(
        id=document.id,
        file_name=document.file_name,
        created_at=document.created_at,
        check_status=document.check_status,
    )


@router.post("/done", status_code=status.HTTP_204_NO_CONTENT)
async def done(token: str, db: DB) -> None:
    """The professional uploaded everything."""
    await service.mark_done(db, token)
