"""Explicit instant/calendar conversions. No implicit naive local timestamps."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc


def now():
    return datetime.now(UTC)


def aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value


def stamp(value):
    return aware(value).astimezone(UTC).isoformat(timespec="microseconds")


def instant(value):
    return aware(datetime.fromisoformat(value))


def system_zone():
    candidate = os.environ.get("TZ", "").removeprefix(":")
    if candidate:
        ZoneInfo(candidate)
        return candidate
    path = str(Path("/etc/localtime").resolve())
    if "/zoneinfo/" in path:
        return path.split("/zoneinfo/", 1)[1]
    return "UTC"


def wall(value, zone):
    """Resolve a local calendar value: first fold, gap shifts forward."""
    z = ZoneInfo(zone)
    candidate = value.replace(tzinfo=z, fold=0)
    return candidate.astimezone(UTC).astimezone(z)


def duration(text):
    match = re.fullmatch(r"([1-9]\d*)([mhdw])", text)
    if not match:
        raise ValueError("Duration must be a positive integer + m/h/d/w (e.g. 30m)")
    return int(match[1]) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[match[2]]


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_date(text, zone, clock=None):
    clock = aware(clock or now()).astimezone(ZoneInfo(zone))
    text = text.strip()
    if text.startswith("in "):
        return (clock.astimezone(UTC) + timedelta(seconds=duration(text[3:])))
    parts = text.lower().split()
    day = parts[0] if parts else ""
    if day in ["today", "tomorrow", *WEEKDAYS]:
        delta = 0 if day == "today" else 1 if day == "tomorrow" else (WEEKDAYS.index(day) - clock.weekday()) % 7
        date = (clock + timedelta(days=delta)).date()
        if len(parts) > 2:
            raise ValueError("Expected day [HH:MM]")
        time = parts[1] if len(parts) == 2 else "09:00"
        return wall(datetime.fromisoformat(f"{date}T{time}"), zone)
    if re.fullmatch(r"\d{2}:\d{2}", text):
        result = wall(datetime.fromisoformat(f"{clock.date()}T{text}"), zone)
        if result.astimezone(UTC) <= clock.astimezone(UTC):
            result = wall(datetime.fromisoformat(f"{(clock + timedelta(days=1)).date()}T{text}"), zone)
        return result
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else wall(value, zone)
