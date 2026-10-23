import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.storage import get_storage
from app.modules.checks.service import check_in_background
from app.modules.projects.service import get_project_for_user
from app.modules.suggestions import service
from app.modules.suggestions.schemas import (
    AcceptAll,
    AcceptAllResult,
    AcceptResult,
    AcceptSuggestion,
    SuggestionOut,
)

router = APIRouter(prefix="/projects/{project_id}/suggestions", tags=["suggestions"])


@router.get("")
async def list_suggestions(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[SuggestionOut]:
    """Filing proposals waiting for approval, newest first."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.list_pending(db, project.id)


@router.post("/accept-all")
async def accept_all(
    project_id: uuid.UUID,
    data: AcceptAll,
    db: DB,
    user: CurrentUser,
    background: BackgroundTasks,
) -> AcceptAllResult:
    """Approves every suggestion that names a requirement, in dependency order."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    result = await service.accept_all(db, project, user, data)
    background.add_task(check_in_background, project.id, get_storage())
    return result


@router.post("/{suggestion_id}/accept")
async def accept_suggestion(
    project_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    data: AcceptSuggestion,
    db: DB,
    user: CurrentUser,
    background: BackgroundTasks,
) -> AcceptResult:
    """Files as suggested (or under the requirement the person chose) and applies the status."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    result = await service.accept(db, project, user, suggestion_id, data)
    background.add_task(check_in_background, project.id, get_storage())
    return result


@router.post("/{suggestion_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_suggestion(
    project_id: uuid.UUID, suggestion_id: uuid.UUID, db: DB, user: CurrentUser
) -> None:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.dismiss(db, project, user, suggestion_id)
