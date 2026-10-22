import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.errors import AppError
from app.core.storage import get_storage
from app.modules.directory.service import search_localities
from app.modules.permits import conditions_service, extraction, service
from app.modules.permits.schemas import (
    AcceptCondition,
    ConditionsOut,
    PermitExtraction,
    PermitOut,
    PermitUpdate,
)
from app.modules.projects.service import get_project_for_user

router = APIRouter(tags=["permits"])


@router.post("/permits/extract")
async def extract_permit(
    db: DB, _: CurrentUser, file: Annotated[UploadFile, File()]
) -> PermitExtraction:
    """Reads a permit PDF before the project exists. Nothing is stored."""
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(413, "file_too_large", "file is too large")
    if not data.startswith(b"%PDF"):
        raise AppError(415, "file_type_not_allowed", "the permit must be a PDF")
    fields, source = await extraction.extract(data)
    guess = None
    for name in (fields.locality, (fields.committee or "").split("ובנייה")[-1]):
        if name and name.strip():
            matches = await search_localities(db, name.strip(), limit=1)
            if matches:
                guess = matches[0]
                break
    return PermitExtraction(fields=fields, source=source, locality=guess)  # type: ignore[arg-type]


@router.get("/projects/{project_id}/permit")
async def get_permit(project_id: uuid.UUID, db: DB, user: CurrentUser) -> PermitOut:
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.permit_out(db, project)


@router.patch("/projects/{project_id}/permit")
async def update_permit(
    project_id: uuid.UUID, data: PermitUpdate, db: DB, user: CurrentUser
) -> PermitOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await service.run_checks(db, project, user)
    return await service.permit_out(db, project)


@router.post("/projects/{project_id}/permit/check")
async def check_permit(
    project_id: uuid.UUID, db: DB, user: CurrentUser, background: BackgroundTasks
) -> PermitOut:
    """Re-runs the checks, e.g. after the permit file was uploaded. The first time there is a
    permit file, Arba also starts reading its conditions."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.run_checks(db, project, user)
    storage = get_storage()
    if await conditions_service.should_read(db, storage, project):
        await conditions_service.start(db, project)
        background.add_task(conditions_service.read_in_background, project.id, storage)
    return await service.permit_out(db, project)


@router.post("/projects/{project_id}/permit/confirm")
async def confirm_permit(project_id: uuid.UUID, db: DB, user: CurrentUser) -> PermitOut:
    """The person found the permit in the committee's own system."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await service.confirm_with_committee(db, project, user)
    return await service.permit_out(db, project)


@router.get("/projects/{project_id}/permit/conditions")
async def list_conditions(project_id: uuid.UUID, db: DB, user: CurrentUser) -> ConditionsOut:
    """The permit's conditions, with Arba's proposal for each."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await conditions_service.list_conditions(db, project)


@router.post("/projects/{project_id}/permit/conditions/read", status_code=status.HTTP_202_ACCEPTED)
async def read_conditions(
    project_id: uuid.UUID, db: DB, user: CurrentUser, background: BackgroundTasks
) -> ConditionsOut:
    """Reads the conditions again, e.g. after a new permit file."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await conditions_service.start(db, project)
    background.add_task(conditions_service.read_in_background, project.id, get_storage())
    return await conditions_service.list_conditions(db, project)


@router.post("/projects/{project_id}/permit/conditions/accept-all")
async def accept_all_conditions(project_id: uuid.UUID, db: DB, user: CurrentUser) -> ConditionsOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await conditions_service.accept_all(db, project, user)
    return await conditions_service.list_conditions(db, project)


@router.post("/projects/{project_id}/permit/conditions/{condition_id}/accept")
async def accept_condition(
    project_id: uuid.UUID,
    condition_id: uuid.UUID,
    data: AcceptCondition,
    db: DB,
    user: CurrentUser,
) -> ConditionsOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await conditions_service.accept(db, project, user, condition_id, data.as_new)
    return await conditions_service.list_conditions(db, project)


@router.post("/projects/{project_id}/permit/conditions/{condition_id}/ignore")
async def ignore_condition(
    project_id: uuid.UUID, condition_id: uuid.UUID, db: DB, user: CurrentUser
) -> ConditionsOut:
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    await conditions_service.ignore(db, project, user, condition_id)
    return await conditions_service.list_conditions(db, project)
