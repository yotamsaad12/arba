"""Events in a project that people should hear about."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MessageKind, NotificationKind, ProjectRole, RequirementStatus, Urgency
from app.db.models import Project, Requirement, Suggestion, Thread
from app.modules.notifications.service import WhatsAppContent, members, notify

KIND_LABEL = {
    MessageKind.approval: "התקבל אישור",
    MessageKind.rejection: "הבקשה נדחתה",
    MessageKind.request_for_info: "מבקשים להשלים מסמכים",
    MessageKind.info: "עדכון חדש",
    MessageKind.other: "הודעה חדשה",
}
STATUS_LABEL = {
    RequirementStatus.done: "הושלם",
    RequirementStatus.needs_fix: "צריך תיקון",
    RequirementStatus.waiting_for_authority: "ממתין לגורם מאשר",
    RequirementStatus.in_progress: "בטיפול",
}
# Approvals and requests change what has to happen next: worth a push. Updates can wait.
PUSH_KINDS = {MessageKind.approval, MessageKind.rejection, MessageKind.request_for_info}

ACCEPT, CHANGE = "a", "c"


def button_id(suggestion: Suggestion, action: str) -> str:
    return f"sg:{suggestion.id}:{action}"


async def suggestion_created(db: AsyncSession, suggestion: Suggestion) -> None:
    project = await db.get(Project, suggestion.project_id)
    if project is None:
        return
    requirement = (
        await db.get(Requirement, suggestion.requirement_id) if suggestion.requirement_id else None
    )
    thread = await db.get(Thread, suggestion.thread_id) if suggestion.thread_id else None

    source = (
        f"מייל מ{thread.counterparty_name or thread.counterparty_email}"
        if thread
        else "קובץ שהועלה"
    )
    if requirement:
        proposal = f'לתייק תחת "{requirement.title}"'
        if suggestion.suggested_status in STATUS_LABEL:
            proposal += f" ולסמן {STATUS_LABEL[suggestion.suggested_status]}"
    else:
        proposal = "לא בטוחה לאן זה שייך. בחרו דרישה באפליקציה"

    path = (
        f"/projects/{project.id}?tab=inbox&thread={thread.id}"
        if thread
        else f"/projects/{project.id}?tab=documents"
    )
    buttons = (
        [
            (button_id(suggestion, ACCEPT), "✓ אישור"),
            (button_id(suggestion, CHANGE), "שינוי באפליקציה"),
        ]
        if requirement
        else []
    )
    await notify(
        db,
        await members(db, project.id, ProjectRole.manager),
        kind=NotificationKind.approval_needed,
        urgency=Urgency.urgent if suggestion.kind in PUSH_KINDS else Urgency.normal,
        title=f"{KIND_LABEL[suggestion.kind]} · {project.name}",
        body=f"{suggestion.summary}\nArba מציעה: {proposal}.",
        project_id=project.id,
        action_path=path,
        suggestion_id=suggestion.id,
        dedupe_key=f"suggestion:{suggestion.id}",
        whatsapp=WhatsAppContent(
            template="arba_approval_request",
            params=[project.name, source, suggestion.summary, proposal],
            buttons=buttons,
            session_text=(
                f"📁 {project.name} · {source}\n{suggestion.summary}\n\nArba מציעה: {proposal}"
            ),
        ),
    )
