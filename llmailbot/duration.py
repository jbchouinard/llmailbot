import datetime
import re

RE_DURATION = re.compile(r"^(\d+)\s?(seconds?|sec|s|m|min|minutes?|h|hours?|d|days?)$")

ALT_UNITS = {
    "d": "days",
    "day": "days",
    "h": "hours",
    "hour": "hours",
    "m": "minutes",
    "min": "minutes",
    "minute": "minutes",
    "s": "seconds",
    "sec": "seconds",
    "second": "seconds",
}


def parse_duration(duration: str) -> datetime.timedelta:
    match = re.match(RE_DURATION, duration)
    if not match:
        raise ValueError(f"Invalid duration: {duration}")

    n, unit = match.groups()
    unit = ALT_UNITS.get(unit, unit)
    n = int(n)

    kwargs = {unit: n}
    return datetime.timedelta(**kwargs)
