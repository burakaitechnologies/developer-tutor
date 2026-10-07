"""clock.py - the computer's own clock: time line, calendar day, session day, day arithmetic.

What: now(), today(), session_day() (the day rolls over at 04:00), stamp(), time_line(), days_between().
Why: the model cannot know the time; the hook states it as a fact. Weekday names come from a fixed
English list so the computer's language setting cannot change them.
How it fails safely: invalid dates give None, never an exception. For tests only, the environment
variable TUTOR_FAKE_NOW (an ISO date-time such as 2026-10-07T19:42:00) freezes the clock.
Who calls it: all handlers, ledger, activity, chatlog, learner.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

sys.dont_write_bytecode = True

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_ROLLOVER_HOUR = 4


def now() -> datetime:
    """The current moment on this computer's own clock, with its UTC offset."""
    fake = os.environ.get("TUTOR_FAKE_NOW", "")
    if fake:
        try:
            moment = datetime.fromisoformat(fake.strip())
            return moment if moment.tzinfo else moment.astimezone()
        except ValueError:
            pass
    return datetime.now().astimezone()


def _rollover_hour() -> int:
    try:
        from . import config
        value = int(config.cfg("rollover_hour"))
        return value if 0 <= value <= 12 else DEFAULT_ROLLOVER_HOUR
    except Exception:
        return DEFAULT_ROLLOVER_HOUR


def today() -> str:
    """The calendar day, YYYY-MM-DD."""
    return now().strftime("%Y-%m-%d")


def session_day() -> str:
    """The day a learner would call 'today': before 04:00 it is still the previous calendar day."""
    return (now() - timedelta(hours=_rollover_hour())).strftime("%Y-%m-%d")


def stamp() -> str:
    """ISO time with offset and no fraction, e.g. 2026-10-07T19:42:05+03:00."""
    return now().replace(microsecond=0).isoformat()


def offset_text(moment: Optional[datetime] = None) -> str:
    moment = moment or now()
    off = moment.utcoffset() or timedelta(0)
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return "UTC%s%02d:%02d" % (sign, minutes // 60, minutes % 60)


def time_line(last_words: Optional[int] = None) -> str:
    """`Now: Wed 2026-10-07 19:42 (UTC+03:00)`; adds `Session day: ...` when it differs from the
    calendar day and `Last answer: N words` when last_words is given."""
    moment = now()
    line = "Now: %s %s (%s)" % (WEEKDAYS[moment.weekday()], moment.strftime("%Y-%m-%d %H:%M"), offset_text(moment))
    sday = session_day()
    if sday != moment.strftime("%Y-%m-%d"):
        line += ". Session day: " + sday
    if last_words is not None:
        line += ". Last answer: %d words" % int(last_words)
    return line


def parse_date(value: object) -> Optional[date]:
    """YYYY-MM-DD (or an ISO date-time) to a date; None when invalid."""
    try:
        text = str(value).strip()
        if not text:
            return None
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def days_between(a: object, b: object) -> Optional[int]:
    """Whole days from date a to date b (b - a); None when either is invalid."""
    da, db = parse_date(a), parse_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def add_days(value: object, days: int) -> Optional[str]:
    d = parse_date(value)
    if d is None:
        return None
    return (d + timedelta(days=days)).isoformat()


def date_of(stamp_text: object) -> str:
    """The YYYY-MM-DD part of an ISO stamp, or ''."""
    d = parse_date(stamp_text)
    return d.isoformat() if d else ""
