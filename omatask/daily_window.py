"""Compact daily reminder windows, expressed in local wall-clock minutes."""
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .timeutil import UTC, wall


def minute_of_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}', value):
        raise ValueError('Time must be HH:MM, for example 08:00')
    parsed = time.fromisoformat(value)
    return parsed.hour * 60 + parsed.minute


def spread_times(count, window):
    if type(count) is not int or not 1 <= count <= 1440:
        raise ValueError('Daily reminder count must be 1..1440, for example 8x')
    if not isinstance(window, str) or not re.fullmatch(r'\d{2}:\d{2}-\d{2}:\d{2}', window):
        raise ValueError('Daily window must be HH:MM-HH:MM, for example 08:00-22:00')
    start, end = map(minute_of_day, window.split('-'))
    if end < start:
        raise ValueError('Daily window must end on the same day after it starts')
    if count > end - start + 1:
        raise ValueError('Allow at least one minute between daily reminders')
    minutes = [end] if count == 1 else [start + round((end-start)*i/(count-1)) for i in range(count)]
    return [f'{value//60:02d}:{value%60:02d}' for value in minutes]


def window_due(times, day, zone, clock):
    local = clock.astimezone(ZoneInfo(zone))
    date = day.astimezone(ZoneInfo(zone)).date() if day else local.date()
    due = wall(datetime.combine(date, time.fromisoformat(times[-1])), zone)
    if day is None and due.astimezone(UTC) <= clock.astimezone(UTC):
        due = wall(datetime.combine(date + timedelta(days=1), time.fromisoformat(times[-1])), zone)
    return due


def clock_fire(due, value, zone):
    minute = minute_of_day(value)
    local = due.astimezone(ZoneInfo(zone))
    if minute > local.hour * 60 + local.minute:
        raise ValueError('Daily task deadline must be at or after its last reminder')
    return wall(datetime.combine(local.date(), time(minute//60, minute%60)), zone)
