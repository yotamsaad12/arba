import uuid

from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.storage import get_storage
from app.modules.inbox import service
from app.modules.inbox.schemas import FileThread, ThreadDetail, ThreadSummary
from app.modules.projects.service import get_project_for_user

router = APIRouter(prefix="/projects/{project_id}", tags=["inbox"])


@router.get("/inbox")
async def list_threads(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[ThreadSummary]:
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.list_threads(db, project.id)


@router.get("/threads/{thread_id}")
async def get_thread(
    project_id: uuid.UUID, thread_id: uuid.UUID, db: DB, user: CurrentUser
) -> ThreadDetail:
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.thread_detail(db, get_storage(), project, thread_id)


@router.post("/threads/{thread_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(project_id: uuid.UUID, thread_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    project, _ = await get_project_for_user(db, project_id, user)
    await service.mark_read(db, project, thread_id)


@router.patch("/threads/{thread_id}")
async def file_thread(
    project_id: uuid.UUID, thread_id: uuid.UUID, data: FileThread, db: DB, user: CurrentUser
) -> ThreadDetail:
    """Files the conversation (and its attachments) under a requirement, or unfiles it."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.file_thread(db, project, user, thread_id, data.requirement_id)
    return await service.thread_detail(db, get_storage(), project, thread_id)
