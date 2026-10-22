from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .contracts import utc


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def day(self, timezone_name: str = "America/New_York") -> str:
        return utc(self.now()).astimezone(ZoneInfo(timezone_name)).date().isoformat()


class FrozenClock(Clock):
    def __init__(self, value: datetime):
        self.value = utc(value)

    def now(self) -> datetime:
        return self.value
