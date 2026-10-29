"""Business hours of Quillstack Software: Monday to Friday 08:00 to 18:00 Lisbon time, public holidays excluded.

The definition (docs/business-hours.md) exists twice, here and as the M function fnBusinessMinutes in the PBIP, and
both pass the 18 cases of data/business_hours_cases.csv. Inputs have minute precision and carry no offset; the
daylight-saving changes fall on Sunday nights, outside business hours, so they never change a result.

    business_minutes(start, end, holidays)        whole business minutes between two moments (None if end < start)
    add_business_minutes(start, minutes, holidays) the earliest moment that is `minutes` business minutes after start
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path

OPEN = time(8)
CLOSE = time(18)
DAY_MINUTES = 600  # one business day = 10 business hours
# Portuguese public holidays of 2024 and 2025 plus Lisbon's municipal holiday (data/holidays.csv)
HOLIDAYS = (
    (date(2024, 1, 1), "New Year's Day", "National"),
    (date(2024, 3, 29), "Good Friday", "National"),
    (date(2024, 3, 31), "Easter Sunday", "National"),
    (date(2024, 4, 25), "Freedom Day", "National"),
    (date(2024, 5, 1), "Labour Day", "National"),
    (date(2024, 5, 30), "Corpus Christi", "National"),
    (date(2024, 6, 10), "Portugal Day", "National"),
    (date(2024, 6, 13), "St Anthony", "Lisbon"),
    (date(2024, 8, 15), "Assumption Day", "National"),
    (date(2024, 10, 5), "Republic Day", "National"),
    (date(2024, 11, 1), "All Saints' Day", "National"),
    (date(2024, 12, 1), "Restoration of Independence", "National"),
    (date(2024, 12, 8), "Immaculate Conception", "National"),
    (date(2024, 12, 25), "Christmas Day", "National"),
    (date(2025, 1, 1), "New Year's Day", "National"),
    (date(2025, 4, 18), "Good Friday", "National"),
    (date(2025, 4, 20), "Easter Sunday", "National"),
    (date(2025, 4, 25), "Freedom Day", "National"),
    (date(2025, 5, 1), "Labour Day", "National"),
    (date(2025, 6, 10), "Portugal Day", "National"),
    (date(2025, 6, 13), "St Anthony", "Lisbon"),
    (date(2025, 6, 19), "Corpus Christi", "National"),
    (date(2025, 8, 15), "Assumption Day", "National"),
    (date(2025, 10, 5), "Republic Day", "National"),
    (date(2025, 11, 1), "All Saints' Day", "National"),
    (date(2025, 12, 1), "Restoration of Independence", "National"),
    (date(2025, 12, 8), "Immaculate Conception", "National"),
    (date(2025, 12, 25), "Christmas Day", "National"),
)
HOLIDAY_DATES = frozenset(day for day, _, _ in HOLIDAYS)
# (case_id, start, end, expected minutes or None, note): data/business_hours_cases.csv
CASES = (
    (1, "2024-03-05 09:00", "2024-03-05 10:30", 90, "inside one day"),
    (2, "2024-03-05 06:00", "2024-03-05 09:00", 60, "starts before opening"),
    (3, "2024-03-05 17:00", "2024-03-05 20:00", 60, "ends after closing"),
    (4, "2024-03-05 18:30", "2024-03-05 23:00", 0, "evening only"),
    (5, "2024-03-05 17:30", "2024-03-06 08:30", 60, "overnight"),
    (6, "2024-03-08 17:00", "2024-03-11 09:00", 120, "Friday to Monday"),
    (7, "2024-03-09 10:00", "2024-03-10 16:00", 0, "weekend only"),
    (8, "2024-03-04 08:00", "2024-03-08 18:00", 3000, "full week"),
    (9, "2024-04-25 09:00", "2024-04-25 17:00", 0, "holiday (Thursday)"),
    (10, "2024-04-24 17:00", "2024-04-26 09:00", 120, "spans a holiday"),
    (11, "2024-12-24 16:00", "2024-12-27 10:00", 840, "Christmas; 26 Dec is a working day"),
    (12, "2024-03-05 10:00", "2024-03-05 10:00", 0, "start equals end"),
    (13, "2024-03-05 10:00", "2024-03-05 09:00", None, "end before start"),
    (14, "2024-03-05 08:00", "2024-03-05 18:00", 600, "exact boundaries"),
    (15, "2024-03-05 18:00", "2024-03-06 08:00", 0, "closing to opening"),
    (16, "2024-10-25 17:00", "2024-10-28 09:00", 120, "weekend with the DST change"),
    (17, "2024-12-31 17:00", "2025-01-02 09:00", 120, "year end, 1 Jan holiday"),
    (18, "2024-01-01 00:00", "2024-12-31 23:59", 151200, "whole year, 252 business days"),
)
FORMAT = "%Y-%m-%d %H:%M"


def parse(text: str) -> datetime:
    """A datetime as the export writes it: `YYYY-MM-DD HH:MM`."""
    return datetime.strptime(text, FORMAT)


def load_holidays(path: Path) -> frozenset[date]:
    """The dates of holidays.csv (columns date, name, scope)."""
    with path.open(encoding="utf-8", newline="") as handle:
        return frozenset(date.fromisoformat(row["date"]) for row in csv.DictReader(handle))


def is_business_day(day: date, holidays: frozenset[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def business_minutes(start: datetime | None, end: datetime | None, holidays: frozenset[date]) -> int | None:
    if start is None or end is None or end < start:
        return None
    total, day = 0, start.date()
    while day <= end.date():
        if day.weekday() < 5 and day not in holidays:
            s, e = max(start, datetime.combine(day, OPEN)), min(end, datetime.combine(day, CLOSE))
            total += int((e - s).total_seconds()) // 60 if e > s else 0
        day += timedelta(days=1)
    return total


def add_business_minutes(start: datetime, minutes: int, holidays: frozenset[date]) -> datetime:
    """The earliest moment m >= start inside business hours (a business day, 08:00 to 18:00 inclusive) with
    business_minutes(start, m) == minutes. The generator places every agent event with it."""
    if minutes < 0:
        raise ValueError(f"minutes must not be negative, got {minutes}")
    current, remaining = start, minutes
    while True:
        day = current.date()
        if is_business_day(day, holidays):
            opening, closing = datetime.combine(day, OPEN), datetime.combine(day, CLOSE)
            current = max(current, opening)
            if current <= closing:
                available = int((closing - current).total_seconds()) // 60
                if remaining <= available:
                    return current + timedelta(minutes=remaining)
                remaining -= available
        current = datetime.combine(day + timedelta(days=1), time(0))
