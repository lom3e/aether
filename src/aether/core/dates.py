"""Relative dates the model must not count by itself: a table of the next days for the prompt, and a check that a weekday the
user said ("entro venerdì") lands on that weekday (models are often one day off)."""
from __future__ import annotations

import datetime as dt
import re

_WEEKDAYS = {
    "lunedì": 0, "lunedi": 0, "monday": 0, "martedì": 1, "martedi": 1, "tuesday": 1, "mercoledì": 2, "mercoledi": 2, "wednesday": 2,
    "giovedì": 3, "giovedi": 3, "thursday": 3, "venerdì": 4, "venerdi": 4, "friday": 4, "sabato": 5, "saturday": 5,
    "domenica": 6, "sunday": 6,
}
_WEEKDAY_RE = re.compile(r"\b(" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
# an explicit date ("il 30", "30/10", "30 ottobre", "October 30") wins over the weekday
_EXPLICIT_RE = re.compile(r"\b\d{1,2}\s*(?:/|-|\.)\s*\d{1,2}\b|\b\d{1,2}\s+(?:gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic|jan|may|jun|jul|aug|sep|oct|dec)\w*"
                          r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}\b|\bil\s+\d{1,2}\b", re.IGNORECASE)
_NEXT_WEEK_RE = re.compile(r"\b(?:settimana\s+prossima|prossima\s+settimana|next\s+week)\b", re.IGNORECASE)


def days_table(now: dt.datetime, days: int = 14) -> str:
    """'today Monday 2026-10-26; Tuesday 2026-10-27; …' for the prompt, so the model reads the date instead of counting."""
    rows = [f"today {now.strftime('%A %Y-%m-%d')}"] + [(now + dt.timedelta(days=i)).strftime("%A %Y-%m-%d") for i in range(1, days)]
    return "; ".join(rows)


def said_weekday(text: str) -> int | None:
    """The one weekday the text names (None when it names none, several, or also gives an explicit date)."""
    found = {_WEEKDAYS[m.lower()] for m in _WEEKDAY_RE.findall(text or "")}
    if len(found) != 1 or _EXPLICIT_RE.search(text or ""):
        return None
    return found.pop()


def fix_weekday(text: str, when: dt.datetime | None, now: dt.datetime) -> dt.datetime | None:
    """`when` moved to the weekday the user said when the model picked another day: the next such day after today (a week
    later for "settimana prossima"), keeping the time of day."""
    wd = said_weekday(text)
    if when is None or wd is None or when.weekday() == wd:
        return when
    ahead = (wd - now.weekday()) % 7 or 7
    if _NEXT_WEEK_RE.search(text or "") and ahead < 7 - now.weekday():
        ahead += 7
    day = (now + dt.timedelta(days=ahead)).date()
    return when.replace(year=day.year, month=day.month, day=day.day)
