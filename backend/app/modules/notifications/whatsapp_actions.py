"""What happens when someone presses a button or writes to Arba on WhatsApp."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import DraftStatus, ProjectRole, SuggestionStatus
from app.core.errors import AppError
from app.db.models import Requirement, Suggestion, User
from app.modules.notifications.service import record_status
from app.modules.notifications.triggers import ACCEPT, CHANGE
from app.modules.projects.service import get_project_for_user
from app.modules.suggestions import service as suggestions
from app.modules.suggestions.schemas import AcceptSuggestion
from app.whatsapp.client import WhatsAppSender
from app.whatsapp.webhook import Incoming, StatusUpdate

log = logging.getLogger(__name__)

STOP_WORDS = {"הסר", "הסרה", "עצור", "stop", "unsubscribe"}
START_WORDS = {"התחל", "הצטרף", "start"}
STATUS_ERRORS = {
    "dependencies_not_done": "קודם צריך להשלים את הדרישות שזו תלויה בהן",
    "requirement_not_optional": "את הדרישה הזו אי אפשר לסמן כלא רלוונטית",
}


async def handle(
    db: AsyncSession, events: list[Incoming | StatusUpdate], sender: WhatsAppSender, now: datetime
) -> None:
    for event in events:
        if isinstance(event, StatusUpdate):
            await record_status(db, event.message_id, event.status, event.error)
            await db.commit()
            continue
        user = await db.scalar(
            select(User).where(
                User.whatsapp_phone == event.phone, User.whatsapp_verified_at.is_not(None)
            )
        )
        if user is None:
            await sender.send_text(
                event.phone,
                "המספר הזה לא מחובר לחשבון Arba. "
                f"אפשר לחבר אותו בהגדרות: {settings.app_url}/settings",
            )
            continue
        user.whatsapp_last_inbound_at = now
        await db.commit()
        try:
            reply = (
                await _button(db, user, event.button)
                if event.button
                else await _text(db, user, event.text, now)
            )
        except Exception:
            log.exception("WhatsApp action failed for %s", user.id)
            await db.rollback()
            reply = "משהו השתבש. אפשר לנסות שוב, או לפתוח את Arba: " + settings.app_url
        if reply:
            await sender.send_text(event.phone, reply)


async def _button(db: AsyncSession, user: User, payload: str) -> str:
    kind, _, rest = payload.partition(":")
    raw_id, _, action = rest.partition(":")
    try:
        target_id = uuid.UUID(raw_id)
    except ValueError:
        return ""
    if kind == "dr":
        return await _draft_button(db, user, target_id, action)
    if kind != "sg":
        return ""
    suggestion_id = target_id
    suggestion = await db.get(Suggestion, suggestion_id)
    if suggestion is None:
        return "ההצעה הזו כבר לא קיימת."
    try:
        project, _ = await get_project_for_user(
            db, suggestion.project_id, user, ProjectRole.manager
        )
    except AppError:
        return "אין לך הרשאה לאשר בפרויקט הזה."

    if action == CHANGE:
        path = (
            f"/projects/{project.id}?tab=inbox&thread={suggestion.thread_id}"
            if suggestion.thread_id
            else f"/projects/{project.id}?tab=documents"
        )
        return f"בחרו דרישה אחרת כאן: {settings.app_url}{path}"
    if action != ACCEPT:
        return ""
    if suggestion.status != SuggestionStatus.pending:
        return "✔️ זה כבר טופל, אין צורך לעשות כלום."

    result = await suggestions.accept(db, project, user, suggestion.id, AcceptSuggestion())
    requirement = await db.get(Requirement, result.requirement_id)
    title = requirement.title if requirement else ""
    if result.status_applied:
        return f'✅ תויק תחת "{title}" והסטטוס עודכן. עוד צעד לטופס 4!'
    if result.status_error:
        reason = STATUS_ERRORS.get(result.status_error, "הסטטוס לא השתנה")
        return f'✅ תויק תחת "{title}". הסטטוס לא עודכן: {reason}.'
    return f'✅ תויק תחת "{title}".'


async def _draft_button(db: AsyncSession, user: User, draft_id: uuid.UUID, action: str) -> str:
    from app.core.storage import get_storage
    from app.db.models import OutboundDraft
    from app.modules.outreach import service as outreach

    draft = await db.get(OutboundDraft, draft_id)
    if draft is None:
        return "הפנייה הזו כבר לא קיימת."
    try:
        project, _ = await get_project_for_user(db, draft.project_id, user, ProjectRole.manager)
    except AppError:
        return "אין לך הרשאה לשלוח בפרויקט הזה."
    if action != "s":
        return f"אפשר לערוך את הנוסח כאן: {settings.app_url}/projects/{project.id}#drafts"
    if draft.status != DraftStatus.draft:
        return "✔️ זה כבר טופל, אין צורך לעשות כלום."
    try:
        await outreach.send_draft(db, get_storage(), project, user, draft.id)
    except AppError as exc:
        link = f"{settings.app_url}/projects/{project.id}#drafts"
        if exc.code == "recipient_required":
            return f"חסרה כתובת מייל של הגורם. אפשר להוסיף אותה כאן: {link}"
        return f"לא נשלח ({exc.code}). אפשר לנסות מהאפליקציה: {link}"
    to = draft.to_name or draft.to_email
    return f"📨 נשלח ל{to}. התשובה תגיע לתיק הפרויקט ו-Arba תעדכן אותך."


async def _text(db: AsyncSession, user: User, text: str, now: datetime) -> str:
    word = text.strip().lower()
    if word in STOP_WORDS:
        user.whatsapp_opted_out_at = now
        await db.commit()
        return "הוסרת מהודעות Arba ב-WhatsApp ✔️ אפשר לחזור בכל רגע: שלחו התחל"
    if word in START_WORDS:
        user.whatsapp_opted_out_at = None
        await db.commit()
        return "ברוך שובך! נעדכן אותך כאן שוב 🙂"
    return (
        f"קיבלתי 🙂 כרגע אפשר לענות כאן רק בכפתורים שבהודעות.\nכל הפרויקטים שלך: {settings.app_url}"
    )
