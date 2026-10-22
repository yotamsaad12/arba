"""The morning summary: one short message per project, only when there's something to do."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import NotificationKind, RequirementStatus, SuggestionStatus, Urgency
from app.db.models import Project, ProjectMember, Suggestion, User
from app.modules.notifications.quiet import in_shabbat, local
from app.modules.notifications.service import WhatsAppContent, notify
from app.modules.requirements.engine import DONE
from app.modules.requirements.service import load_graph, run_engine


@dataclass
class ProjectDay:
    done: int
    total: int
    pending_approvals: int
    needs_fix: list[str]
    ready: list[str]
    waiting: int

    @property
    def actionable(self) -> bool:
        return bool(self.pending_approvals or self.needs_fix or self.ready)

    def one_line(self) -> str:
        parts = []
        if self.pending_approvals:
            parts.append(f"{self.pending_approvals} אישורים ממתינים לך")
        if self.needs_fix:
            parts.append("צריך תיקון: " + ", ".join(self.needs_fix[:2]))
        if self.ready:
            parts.append("אפשר להתחיל: " + ", ".join(self.ready[:2]))
        if self.waiting:
            parts.append(f"{self.waiting} ממתינים לגורם מאשר")
        return " · ".join(parts)

    def lines(self) -> list[str]:
        out = []
        if self.pending_approvals:
            out.append(f"✨ {self.pending_approvals} הצעות של Arba מחכות לאישור שלך.")
        out += [f"🔧 צריך תיקון: {t}" for t in self.needs_fix[:3]]
        out += [f"🚀 אפשר להתחיל: {t}" for t in self.ready[:3]]
        if self.waiting:
            out.append(f"⏳ {self.waiting} דרישות ממתינות לתשובה מגורם מאשר.")
        return out


async def project_day(db: AsyncSession, project: Project) -> ProjectDay:
    requirements, deps = await load_graph(db, project.id)
    result = run_engine(requirements, deps)
    critical = set(result.critical_path)
    # Critical-path items first: they decide when Form 4 can be filed.
    ordered = sorted(requirements, key=lambda r: (r.id not in critical, r.order, r.floor or 0))
    pending = await db.scalar(
        select(func.count())
        .select_from(Suggestion)
        .where(Suggestion.project_id == project.id, Suggestion.status == SuggestionStatus.pending)
    )
    return ProjectDay(
        done=sum(r.status in DONE for r in requirements),
        total=len(requirements),
        pending_approvals=pending or 0,
        needs_fix=[r.title for r in ordered if r.status == RequirementStatus.needs_fix],
        ready=[r.title for r in ordered if r.status == RequirementStatus.ready],
        waiting=sum(r.status == RequirementStatus.waiting_for_authority for r in requirements),
    )


async def build_digests(db: AsyncSession, now: datetime) -> int:
    """Creates today's summaries for people whose summary hour is now. Idempotent per day."""
    today = local(now)
    users = list(await db.scalars(select(User).where(User.digest_hour == today.hour)))
    sent = 0
    for user in users:
        if user.quiet_shabbat and in_shabbat(now):
            continue
        projects = await db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
        )
        for project in projects:
            day = await project_day(db, project)
            if not day.actionable:
                continue
            first_name = user.name.split()[0] if user.name.strip() else ""
            link = f"{settings.app_url}/projects/{project.id}"
            created = await notify(
                db,
                [user],
                kind=NotificationKind.daily_digest,
                urgency=Urgency.normal,
                title=f"מה מחכה לך היום · {project.name}",
                body="\n".join(
                    [f"{project.name}: {day.done} מתוך {day.total} שלבים הושלמו.", *day.lines()]
                ),
                project_id=project.id,
                action_path=f"/projects/{project.id}",
                dedupe_key=f"digest:{project.id}:{today.date().isoformat()}",
                whatsapp=WhatsAppContent(
                    template="arba_daily_digest",
                    params=[
                        first_name,
                        project.name,
                        str(day.done),
                        str(day.total),
                        day.one_line(),
                        link,
                    ],
                ),
                now=now,
            )
            sent += len(created)
    return sent
