import uuid

from fastapi import APIRouter, BackgroundTasks, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.enums import MailboxProvider, ProjectRole
from app.core.errors import AppError
from app.core.storage import get_storage
from app.db.models import User
from app.modules.catchup import service
from app.modules.catchup.mailbox import (
    GmailMailbox,
    configured_provider,
    google_auth_url,
    read_state,
)
from app.modules.catchup.schemas import (
    CatchUp,
    CatchUpReport,
    CatchUpResult,
    MailboxConnect,
    ScanOut,
)
from app.modules.projects.service import get_project_for_user
from app.modules.suggestions.service import get_classifier

router = APIRouter(prefix="/projects/{project_id}", tags=["catch-up"])
callbacks = APIRouter(prefix="/mailbox", tags=["catch-up"], include_in_schema=False)


@router.post("/catch-up")
async def catch_up(
    project_id: uuid.UUID, data: CatchUp, db: DB, user: CurrentUser
) -> CatchUpResult:
    """For a project already under way: marks the required steps before `stage` as done."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    return CatchUpResult(marked_done=await service.catch_up(db, project, user, data.stage))


@router.get("/catch-up/report")
async def report(project_id: uuid.UUID, db: DB, user: CurrentUser) -> CatchUpReport:
    """What Arba found for each requirement, and which steps done so far lack documents."""
    project, _ = await get_project_for_user(db, project_id, user)
    return await service.build_report(db, project)


@router.get("/mailbox/connect")
async def connect(project_id: uuid.UUID, db: DB, user: CurrentUser) -> MailboxConnect:
    """How to give Arba one-time, read-only access to the person's mailbox."""
    await get_project_for_user(db, project_id, user, ProjectRole.manager)
    provider = configured_provider()
    if provider != MailboxProvider.gmail:
        return MailboxConnect(provider=provider, url=None)
    return MailboxConnect(provider=provider, url=google_auth_url(project_id, user.id, user.email))


@router.post("/mailbox/scans", status_code=status.HTTP_201_CREATED)
async def start_simulated_scan(
    project_id: uuid.UUID, db: DB, user: CurrentUser, background: BackgroundTasks
) -> ScanOut:
    """Scans the simulated mailbox (dev). Real mailboxes start from the provider's consent page."""
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    if configured_provider() != MailboxProvider.simulator:
        raise AppError(409, "mailbox_needs_consent", "open the connect URL to grant access")
    mailbox = await service.simulated_mailbox(db, project, user)
    scan = await service.start_scan(
        db, project, user, MailboxProvider.simulator, mailbox.account_email
    )
    background.add_task(
        service.run_scan,
        scan.id,
        mailbox,
        get_storage(),
        get_classifier(),
        settings.mailbox_scan_limit,
    )
    return service.scan_out(scan)


@router.get("/mailbox/scans/{scan_id}")
async def get_scan(project_id: uuid.UUID, scan_id: uuid.UUID, db: DB, user: CurrentUser) -> ScanOut:
    project, _ = await get_project_for_user(db, project_id, user)
    return service.scan_out(await service.get_scan(db, project, scan_id))


@callbacks.get("/google/callback")
async def google_callback(
    db: DB,
    background: BackgroundTasks,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google sends the person back here after the consent screen."""
    user_id, project_id = read_state(state)
    page = f"{settings.app_url}/projects/{project_id}/import"
    if error or not code:
        return RedirectResponse(f"{page}?mailbox=denied")
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(400, "invalid_state", "unknown user")
    project, _ = await get_project_for_user(db, project_id, user, ProjectRole.manager)
    mailbox = await GmailMailbox.from_code(code)
    try:
        scan = await service.start_scan(
            db, project, user, MailboxProvider.gmail, mailbox.account_email
        )
    except AppError:
        await mailbox.close()
        return RedirectResponse(f"{page}?mailbox=busy")
    background.add_task(
        service.run_scan,
        scan.id,
        mailbox,
        get_storage(),
        get_classifier(),
        settings.mailbox_scan_limit,
    )
    return RedirectResponse(f"{page}?scan={scan.id}")
