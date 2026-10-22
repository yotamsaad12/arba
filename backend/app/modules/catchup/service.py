"""Bringing a project that is already under way into Arba: where it stands, what the person's
mailbox already holds, and what is still missing for Form 4."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import (
    AuthorityType,
    DocumentStatus,
    MailboxProvider,
    MessageDirection,
    NotificationKind,
    RequirementStatus,
    ScanStatus,
    SuggestionStatus,
    Urgency,
)
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import (
    AuditLog,
    Document,
    MailboxScan,
    Message,
    Project,
    Requirement,
    Suggestion,
    User,
)
from app.db.session import SessionLocal
from app.email.processing import store_email
from app.modules.catchup.mailbox import Mailbox, SimulatedMailbox
from app.modules.catchup.schemas import CatchUpReport, ReportItem, ScanOut
from app.modules.catchup.search import build_search
from app.modules.directory.schemas import AuthorityOut
from app.modules.directory.service import authorities_for
from app.modules.notifications.service import WhatsAppContent, notify
from app.modules.projects.schemas import stages_of
from app.modules.requirements.service import apply_automatic_statuses, load_graph, run_engine
from app.modules.suggestions.service import Classifier, suggest_for_message

log = logging.getLogger(__name__)

S = RequirementStatus
# Statuses that say the work happened (or is happening), so its documents should exist.
_UNDER_WAY = {S.done, S.in_progress, S.waiting_for_authority, S.needs_fix}


# --- Where the project stands ---------------------------------------------------------


async def catch_up(db: AsyncSession, project: Project, user: User, stage: str) -> int:
    """Marks every required step in the stages before `stage` as done. Returns how many."""
    project = await _with_template(db, project.id)
    keys = [s.key for s in stages_of(project)]
    if stage not in keys:
        raise AppError(422, "unknown_stage", "no such stage in this project")
    earlier = keys[: keys.index(stage)]
    requirements, deps = await load_graph(db, project.id)
    now = datetime.now(UTC)
    changed = [
        r
        for r in requirements
        if r.stage in earlier and not r.optional and r.status not in (S.done, S.not_applicable)
    ]
    for r in changed:
        r.status, r.status_changed_at, r.completed_at = S.done, now, now
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="project.caught_up",
            entity="project",
            entity_id=project.id,
            after={"stage": stage, "marked_done": len(changed)},
        )
    )
    await db.commit()
    return len(changed)


# --- Mailbox scan ---------------------------------------------------------------------


async def project_authorities(db: AsyncSession, project: Project) -> list[AuthorityOut]:
    return await authorities_for(db, project.municipality_code) if project.municipality_code else []


async def simulated_mailbox(db: AsyncSession, project: Project, user: User) -> SimulatedMailbox:
    """Sample mail from the area's real committee and water corporation domains, so the
    search is exercised as it would be against a real mailbox."""
    box = SimulatedMailbox(project=project, account_email=user.email)
    search = build_search(project, await project_authorities(db, project))
    for a in await project_authorities(db, project):
        domain = next((d for d in search.domains if a.website and d in a.website), None)
        if domain and a.type == AuthorityType.municipality:
            box.committee_domain = domain
        elif domain and a.type == AuthorityType.water_corporation:
            box.water_domain = domain
    return box


async def start_scan(
    db: AsyncSession, project: Project, user: User, provider: MailboxProvider, account: str
) -> MailboxScan:
    running = await db.scalar(
        select(MailboxScan.id).where(
            MailboxScan.project_id == project.id, MailboxScan.status == ScanStatus.running
        )
    )
    if running:
        raise AppError(409, "scan_running", "a mailbox scan is already running")
    search = build_search(project, await project_authorities(db, project))
    scan = MailboxScan(
        project_id=project.id,
        user_id=user.id,
        provider=provider,
        account_email=account,
        query=search.gmail_query(),
    )
    db.add(scan)
    await db.commit()
    return scan


async def run_scan(
    scan_id: uuid.UUID, mailbox: Mailbox, storage: Storage, classifier: Classifier, limit: int
) -> None:
    """Imports the matching mail, then asks for one filing decision per conversation. Runs
    in the background with its own session; never raises."""
    async with SessionLocal() as db:
        scan = await db.get(MailboxScan, scan_id)
        assert scan is not None
        try:
            await _import(db, scan, mailbox, storage, classifier, limit)
            scan.status = ScanStatus.done
        except Exception as exc:  # noqa: BLE001 - recorded on the scan and shown to the person
            log.exception("mailbox scan %s failed", scan_id)
            await db.rollback()
            scan = await db.get(MailboxScan, scan_id)
            assert scan is not None
            scan.status = ScanStatus.failed
            scan.error = f"{type(exc).__name__}: {exc}"[:2000]
        finally:
            await mailbox.close()
        scan.finished_at = datetime.now(UTC)
        await db.commit()
        if scan.status == ScanStatus.done:
            try:
                await _announce(db, scan)
            except Exception:
                log.exception("could not notify about scan %s", scan_id)


async def _import(
    db: AsyncSession,
    scan: MailboxScan,
    mailbox: Mailbox,
    storage: Storage,
    classifier: Classifier,
    limit: int,
) -> None:
    project = await db.get(Project, scan.project_id)
    assert project is not None
    search = build_search(project, await project_authorities(db, project))
    new_messages: list[uuid.UUID] = []
    async for email in mailbox.search(search, limit):
        scan.messages_found += 1
        mine = email.from_email == mailbox.account_email.lower()
        message_id = await store_email(
            db,
            storage,
            project,
            email,
            direction=MessageDirection.outbound if mine else MessageDirection.inbound,
        )
        if message_id:
            new_messages.append(message_id)
            scan.messages_imported += 1
            scan.files_imported += (
                await db.scalar(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.message_id == message_id)
                )
                or 0
            )
        await db.commit()

    # One decision per conversation, from its newest message.
    latest: dict[uuid.UUID, tuple[datetime, uuid.UUID]] = {}
    for message in await db.scalars(select(Message).where(Message.id.in_(new_messages))):
        current = latest.get(message.thread_id)
        if current is None or message.sent_at > current[0]:
            latest[message.thread_id] = (message.sent_at, message.id)
    for _, message_id in sorted(latest.values()):
        try:
            await suggest_for_message(db, storage, classifier, message_id, scan_id=scan.id)
        except Exception:
            log.exception("could not suggest filing for imported message %s", message_id)
            await db.rollback()


async def _announce(db: AsyncSession, scan: MailboxScan) -> None:
    project = await db.get(Project, scan.project_id)
    user = await db.get(User, scan.user_id)
    if project is None or user is None:
        return
    report = await build_report(db, project)
    found = f"{scan.messages_imported} מיילים ו-{scan.files_imported} קבצים"
    missing = (
        f"חסרים מסמכים ל-{len(report.missing)} שלבים שכבר בוצעו."
        if report.missing
        else "לא מצאנו שלבים שחסרים להם מסמכים."
    )
    link = f"/projects/{project.id}/import"
    await notify(
        db,
        [user],
        kind=NotificationKind.import_finished,
        urgency=Urgency.urgent,
        title=f"Arba סיימה לסרוק את המייל · {project.name}",
        body=f"נמצאו {found}. {missing}",
        project_id=project.id,
        action_path=link,
        dedupe_key=f"scan:{scan.id}",
        whatsapp=WhatsAppContent(
            template="arba_import_finished",
            params=[project.name, found, missing, f"{settings.app_url}{link}"],
            session_text=(
                f"🔎 {project.name}: Arba סיימה לסרוק את המייל.\nנמצאו {found}.\n{missing}\n\n"
                f"לסקירה ולאישור: {settings.app_url}{link}"
            ),
        ),
    )


async def get_scan(db: AsyncSession, project: Project, scan_id: uuid.UUID) -> MailboxScan:
    scan = await db.get(MailboxScan, scan_id)
    if scan is None or scan.project_id != project.id:
        raise not_found("scan")
    return scan


async def latest_scan(db: AsyncSession, project_id: uuid.UUID) -> MailboxScan | None:
    return await db.scalar(
        select(MailboxScan)
        .where(MailboxScan.project_id == project_id)
        .order_by(MailboxScan.created_at.desc())
        .limit(1)
    )


def scan_out(scan: MailboxScan) -> ScanOut:
    return ScanOut.model_validate(scan, from_attributes=True)


# --- What's there and what's missing --------------------------------------------------


async def build_report(db: AsyncSession, project: Project) -> CatchUpReport:
    requirements = list(
        await db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id)
            .order_by(Requirement.order, Requirement.floor)
        )
    )
    documents = dict(
        list(
            await db.execute(
                select(Document.requirement_id, func.count())
                .where(
                    Document.project_id == project.id,
                    Document.status == DocumentStatus.ready,
                    Document.requirement_id.is_not(None),
                )
                .group_by(Document.requirement_id)
            )
        )
    )
    pending_rows = list(
        await db.execute(
            select(Suggestion.requirement_id, func.count())
            .where(
                Suggestion.project_id == project.id,
                Suggestion.status == SuggestionStatus.pending,
            )
            .group_by(Suggestion.requirement_id)
        )
    )
    pending = {rid: n for rid, n in pending_rows if rid is not None}
    unsure = sum(n for rid, n in pending_rows if rid is None)

    found, missing = [], []
    for r in requirements:
        item = ReportItem(
            requirement_id=r.id,
            title=r.title,
            stage=r.stage,
            status=r.status,
            required_documents=r.required_documents,
            documents=documents.get(r.id, 0),
            pending=pending.get(r.id, 0),
        )
        if item.documents or item.pending:
            found.append(item)
        elif r.required_documents and r.status in _UNDER_WAY:
            missing.append(item)

    scan = await latest_scan(db, project.id)
    state: Literal["empty", "scanning", "ready"] = (
        "scanning"
        if scan and scan.status == ScanStatus.running
        else "ready"
        if scan or found
        else "empty"
    )
    return CatchUpReport(
        found=found,
        missing=missing,
        pending_suggestions=sum(pending.values()) + unsure,
        unsure=unsure,
        scan=scan_out(scan) if scan else None,
        state=state,
    )


async def _with_template(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id).options(selectinload(Project.template))
    )
    assert project is not None
    return project
