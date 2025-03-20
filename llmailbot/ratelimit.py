import datetime
from enum import Enum


class LimitResult(Enum):
    OK = True
    EXCEEDED = False


# TODO: use bucket algorithm instead
# TODO: implement RedisRateLimiter
class RateLimiter:
    def __init__(self, duration: datetime.timedelta, limit: int):
        self.duration = duration
        self.limit = limit
        self._limit_count = 0
        self._limit_expiry = datetime.datetime.now() + self.duration

    def _reset(self, now: datetime.datetime) -> None:
        self._limit_count = 0
        self._limit_expiry = now + self.duration

    def _is_expired(self, now: datetime.datetime | None = None) -> bool:
        now = now or datetime.datetime.now()
        return now > self._limit_expiry

    def count(self) -> LimitResult:
        now = datetime.datetime.now()
        if self._is_expired(now):
            self._reset(now)

        self._limit_count += 1
        if self._limit_count > self.limit:
            return LimitResult.EXCEEDED
        return LimitResult.OK
