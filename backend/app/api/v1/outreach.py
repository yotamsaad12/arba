import uuid

from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.errors import not_found
from app.core.storage import get_storage
from app.db.models import Requirement
from app.modules.outreach import service
from app.modules.outreach.schemas import DraftOut, DraftUpdate, NewDraft
from app.modules.projects.service import get_project_for_user

router = APIRouter(prefix="/projects/{project_id}", tags=["outreach"])


@router.get("/drafts")
async def list_drafts(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[DraftOut]:
    """Requests and reminders Arba wrote, waiting for approval."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.list_open(db, project)


@router.post("/requirements/{requirement_id}/drafts", status_code=status.HTTP_201_CREATED)
async def create_draft(
    project_id: uuid.UUID, requirement_id: uuid.UUID, data: NewDraft, db: DB, user: CurrentUser
) -> DraftOut:
    """Arba writes to the body responsible for this step (or returns the draft already open)."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    requirement = await db.get(Requirement, requirement_id)
    if requirement is None or requirement.project_id != project.id:
        raise not_found("requirement")
    draft = await service.create_draft(db, project, requirement, data.kind, announce=False)
    return await service.draft_out(db, draft)


@router.patch("/drafts/{draft_id}")
async def update_draft(
    project_id: uuid.UUID, draft_id: uuid.UUID, data: DraftUpdate, db: DB, user: CurrentUser
) -> DraftOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    return await service.draft_out(db, await service.update_draft(db, project, draft_id, data))


@router.post("/drafts/{draft_id}/send")
async def send_draft(
    project_id: uuid.UUID, draft_id: uuid.UUID, db: DB, user: CurrentUser
) -> DraftOut:
    """Sends the email. Replies come back to the project inbox."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    draft = await service.send_draft(db, get_storage(), project, user, draft_id)
    return await service.draft_out(db, draft)


@router.post("/drafts/{draft_id}/submitted")
async def mark_submitted(
    project_id: uuid.UUID, draft_id: uuid.UUID, db: DB, user: CurrentUser
) -> DraftOut:
    """The person submitted the text on the body's website or at its counter."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    return await service.draft_out(db, await service.mark_submitted(db, project, user, draft_id))


@router.post("/drafts/{draft_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard_draft(
    project_id: uuid.UUID, draft_id: uuid.UUID, db: DB, user: CurrentUser
) -> None:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.discard(db, project, user, draft_id)
