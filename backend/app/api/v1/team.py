import uuid

from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.modules.projects.service import get_project_for_user
from app.modules.team import service
from app.modules.team.schemas import ContactIn, RequestCreate, RequestOut, TeamMemberOut

router = APIRouter(prefix="/projects/{project_id}", tags=["team"])


@router.get("/contacts")
async def list_contacts(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[TeamMemberOut]:
    """The professionals on the project."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.list_contacts(db, project)


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def add_contact(
    project_id: uuid.UUID, data: ContactIn, db: DB, user: CurrentUser
) -> TeamMemberOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    return service.contact_out(await service.add_contact(db, project, data))


@router.put("/contacts/{contact_id}")
async def update_contact(
    project_id: uuid.UUID, contact_id: uuid.UUID, data: ContactIn, db: DB, user: CurrentUser
) -> TeamMemberOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    return service.contact_out(await service.update_contact(db, project, contact_id, data))


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    project_id: uuid.UUID, contact_id: uuid.UUID, db: DB, user: CurrentUser
) -> None:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.delete_contact(db, project, contact_id)


@router.get("/document-requests")
async def list_requests(project_id: uuid.UUID, db: DB, user: CurrentUser) -> list[RequestOut]:
    """Open requests, and those answered in the last two weeks."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.list_requests(db, project)


@router.post("/document-requests", status_code=status.HTTP_201_CREATED)
async def create_request(
    project_id: uuid.UUID, data: RequestCreate, db: DB, user: CurrentUser
) -> RequestOut:
    """Asks a professional for documents and sends them the upload link."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    request, sent = await service.create_request(db, project, user, data)
    return await service.request_out(db, request, sent)


@router.post("/document-requests/{request_id}/resend")
async def resend_request(
    project_id: uuid.UUID, request_id: uuid.UUID, db: DB, user: CurrentUser
) -> RequestOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    sent = await service.resend(db, project, request_id)
    return await service.request_out(db, await service.get_request(db, project, request_id), sent)


@router.post("/document-requests/{request_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_request(
    project_id: uuid.UUID, request_id: uuid.UUID, db: DB, user: CurrentUser
) -> None:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.cancel(db, project, request_id)
