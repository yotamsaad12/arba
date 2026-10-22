import uuid

from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.modules.directory import service
from app.modules.directory.schemas import AuthorityOut, LocalityOut
from app.modules.projects.service import get_project_for_user

router = APIRouter(tags=["directory"])


@router.get("/directory/localities")
async def localities(q: str, db: DB, _: CurrentUser) -> list[LocalityOut]:
    """Official localities matching a name, with their authority and planning committee."""
    return await service.search_localities(db, q)


@router.get("/projects/{project_id}/authorities")
async def project_authorities(
    project_id: uuid.UUID, db: DB, user: CurrentUser
) -> list[AuthorityOut]:
    """The bodies responsible for this project's area, with known contacts."""
    project, _ = await get_project_for_user(db, project_id, user)
    if project.municipality_code is None:
        return []
    return await service.authorities_for(db, project.municipality_code)
