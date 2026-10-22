"""When not to push messages: nights and Shabbat, per the person's preferences (Israel time)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.models import User

TZ = ZoneInfo(settings.timezone)
NIGHT_START, NIGHT_END = time(21, 0), time(7, 0)
# Fixed hours that cover candle lighting and havdalah all year round.
SHABBAT_START, SHABBAT_END = time(16, 0), time(20, 0)
FRIDAY, SATURDAY = 4, 5


def local(now: datetime) -> datetime:
    return now.astimezone(TZ)


def in_shabbat(moment: datetime) -> bool:
    t = local(moment)
    return (t.weekday() == FRIDAY and t.time() >= SHABBAT_START) or (
        t.weekday() == SATURDAY and t.time() < SHABBAT_END
    )


def quiet_until(user: User, now: datetime) -> datetime | None:
    """The end of the quiet period `now` falls in, or None if it's fine to send now."""
    moment = local(now)
    moved = True
    while moved:
        moved = False
        if user.quiet_shabbat and in_shabbat(moment):
            saturday = moment.date() + timedelta(days=(SATURDAY - moment.weekday()) % 7)
            moment = datetime.combine(saturday, SHABBAT_END, TZ)
            moved = True
        if user.quiet_nights and (moment.time() >= NIGHT_START or moment.time() < NIGHT_END):
            day = moment.date() + (
                timedelta(days=1) if moment.time() >= NIGHT_START else timedelta()
            )
            moment = datetime.combine(day, NIGHT_END, TZ)
            moved = True
    return moment if moment != local(now) else None
