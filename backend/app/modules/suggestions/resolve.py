"""Settles pending suggestions when a person files something by hand.

Kept separate from service.py so the inbox and documents services can call it without
importing the classifiers.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SuggestionStatus
from app.db.models import Suggestion, User
from app.modules.notifications.service import resolve_for_suggestion


async def resolve_pending(
    db: AsyncSession,
    user: User,
    requirement_id: uuid.UUID | None,
    *,
    thread_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
) -> None:
    query = select(Suggestion).where(Suggestion.status == SuggestionStatus.pending)
    if thread_id:
        query = query.where(Suggestion.thread_id == thread_id)
    elif document_id:
        query = query.where(Suggestion.document_id == document_id)
    else:
        return
    now = datetime.now(UTC)
    for suggestion in await db.scalars(query):
        suggestion.status = (
            SuggestionStatus.accepted
            if requirement_id and requirement_id == suggestion.requirement_id
            else SuggestionStatus.changed
        )
        suggestion.decided_by = user.id
        suggestion.decided_at = now
        suggestion.applied_requirement_id = requirement_id
        await resolve_for_suggestion(db, suggestion.id)
