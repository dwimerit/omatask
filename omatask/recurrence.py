"""Pure recurrence engine; all occurrences are computed from the original anchor."""
import calendar
from dataclasses import dataclass, asdict
from datetime import timedelta
from zoneinfo import ZoneInfo
from .timeutil import UTC, aware, instant, wall


@dataclass(frozen=True)
class Rule:
    frequency: str
    interval: int = 1
    count: int | None = None
    until: str | None = None
    weekdays: list[int] | None = None

    def __post_init__(self):
        if self.frequency not in ("minute", "hour", "day", "week", "month"):
            raise ValueError("frequency: minute/hour/day/week/month")
        if type(self.interval) is not int or not 1 <= self.interval <= 100000:
            raise ValueError("interval must be 1..100000")
        if self.count is not None and (type(self.count) is not int or not 1 <= self.count <= 1000000):
            raise ValueError("count must be 1..1000000")
        if self.until:
            instant(self.until)
        if self.weekdays is not None:
            if self.frequency != "week" or not self.weekdays or any(type(d) is not int or d not in range(7) for d in self.weekdays):
                raise ValueError("weekdays must be 0..6 and require weekly recurrence")
            if sorted(set(self.weekdays)) != self.weekdays:
                raise ValueError("weekdays must be sorted and unique")

    def to_dict(self):
        return asdict(self)


def occurrence(anchor, rule, index, zone):
    """0-based sequence. None means the finite series has ended."""
    aware(anchor)
    if index < 0:
        raise ValueError("Negative occurrence index")
    if rule.count is not None and index >= rule.count:
        return None
    local = anchor.astimezone(ZoneInfo(zone))
    naive = local.replace(tzinfo=None)
    n = rule.interval * index
    if rule.weekdays and local.weekday() not in rule.weekdays:
        raise ValueError("First due date must match recurrence weekdays")
    if index == 0:
        value = anchor
    elif rule.frequency in ("minute", "hour"):
        value = anchor.astimezone(UTC) + timedelta(seconds=n * (60 if rule.frequency == "minute" else 3600))
    elif rule.frequency == "month":
        months = local.year * 12 + local.month - 1 + n
        year, month0 = divmod(months, 12)
        month = month0 + 1
        day = min(local.day, calendar.monthrange(year, month)[1])
        value = wall(naive.replace(year=year, month=month, day=day), zone)
    elif rule.frequency == "week" and rule.weekdays:
        first = [d for d in rule.weekdays if d >= local.weekday()]
        if index < len(first):
            days = first[index] - local.weekday()
        else:
            cycles, offset = divmod(index - len(first), len(rule.weekdays))
            days = (cycles + 1) * rule.interval * 7 + rule.weekdays[offset] - local.weekday()
        value = wall(naive + timedelta(days=days), zone)
    else:
        value = wall(naive + timedelta(days=n * (7 if rule.frequency == "week" else 1)), zone)
    if rule.until and value.astimezone(UTC) > instant(rule.until).astimezone(UTC):
        return None
    return value


def final_index(anchor, rule, zone):
    """Find finite bound in O(log n); None for infinite rules."""
    if rule.count is None and rule.until is None:
        return None
    def exists(i):
        try:
            return occurrence(anchor, rule, i, zone) is not None
        except (OverflowError, ValueError):
            return False
    lo, hi = 0, rule.count or 1
    while exists(hi):
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if exists(mid):
            lo = mid
        else:
            hi = mid
    return lo if exists(lo) else -1
