"""Background worker: sends due notifications and builds the morning summaries.

Production: run `python -m app.worker` as its own process (any number of copies; deliveries are
claimed with SKIP LOCKED). Dev: it runs inside the API process (settings.run_worker_in_api).
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.modules.notifications.digest import build_digests
from app.modules.notifications.service import BATCH_SIZE, deliver_due

log = logging.getLogger(__name__)
INTERVAL_SECONDS = 10


async def tick(now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        await build_digests(db, now)
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
