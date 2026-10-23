"""Background worker: sends due notifications, builds the morning summaries, and drafts
requests and reminders to authorities.

Production: run `python -m app.worker` as its own process (any number of copies; deliveries are
claimed with SKIP LOCKED). Dev: it runs inside the API process (settings.run_worker_in_api).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.storage import get_storage
from app.db.session import SessionLocal
from app.modules.checks.service import check_pending
from app.modules.notifications.digest import build_digests
from app.modules.notifications.service import BATCH_SIZE, deliver_due
from app.modules.outreach.service import prepare_reminders, prepare_requests
from app.modules.team.service import remind_open

log = logging.getLogger(__name__)
INTERVAL_SECONDS = 10
# Drafting requests and reminders needs no second-by-second precision.
OUTREACH_EVERY = timedelta(minutes=5)
_last_outreach: datetime | None = None


async def tick(now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        await build_digests(db, now)
    global _last_outreach
    if _last_outreach is None or now - _last_outreach >= OUTREACH_EVERY:
        _last_outreach = now
        async with SessionLocal() as db:
            await prepare_requests(db)
            await prepare_reminders(db, now)
            await check_pending(db, get_storage())
            await remind_open(db, now)
    async with SessionLocal() as db:
        while await deliver_due(db, now) == BATCH_SIZE:  # a full batch: there may be more
            pass


async def run_forever(interval: float = INTERVAL_SECONDS) -> None:
    log.info("notification worker started")
    while True:
        try:
            await tick()
        except Exception:
            log.exception("worker tick failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
