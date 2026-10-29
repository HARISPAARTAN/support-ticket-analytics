"""tools/bizhours.py: the 18 cases of data/business_hours_cases.csv and the properties of spec section 10."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import bizhours
from bizhours import CASES, HOLIDAY_DATES, add_business_minutes, business_minutes, parse

ROOT = Path(__file__).resolve().parents[1]
FIRST, LAST = datetime(2024, 1, 1), datetime(2025, 12, 31, 23, 59)
moments = st.integers(0, int((LAST - FIRST).total_seconds()) // 60).map(lambda m: FIRST + timedelta(minutes=m))


def read(name: str) -> list[dict[str, str]]:
    with (ROOT / "data" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("case", read("business_hours_cases.csv"), ids=lambda c: c["case_id"])
def test_case(case: dict[str, str]) -> None:
    expected = None if case["expected_minutes"] == "" else int(case["expected_minutes"])
    holidays = bizhours.load_holidays(ROOT / "data" / "holidays.csv")
    assert business_minutes(parse(case["start"]), parse(case["end"]), holidays) == expected


def test_the_cases_file_equals_the_constants() -> None:
    rows = [
        (int(r["case_id"]), r["start"], r["end"], r["expected_minutes"], r["note"])
        for r in read("business_hours_cases.csv")
    ]
    assert rows == [(c, s, e, "" if m is None else str(m), n) for c, s, e, m, n in CASES]


def test_holidays() -> None:
    rows = read("holidays.csv")
    assert len(rows) == 28
    assert {r["scope"] for r in rows} == {"National", "Lisbon"}
    weekdays = [date.fromisoformat(r["date"]) for r in rows if date.fromisoformat(r["date"]).weekday() < 5]
    assert sum(d.year == 2024 for d in weekdays) == 10 and sum(d.year == 2025 for d in weekdays) == 11
    for year, days in ((2024, 252), (2025, 250)):
        first, last = date(year, 1, 1), date(year, 12, 31)
        count = sum(
            bizhours.is_business_day(first + timedelta(days=i), HOLIDAY_DATES) for i in range((last - first).days + 1)
        )
        assert count == days


def test_null_inputs() -> None:
    assert business_minutes(None, FIRST, HOLIDAY_DATES) is None
    assert business_minutes(FIRST, None, HOLIDAY_DATES) is None


@settings(max_examples=300, deadline=None)
@given(moments, moments, moments)
def test_additivity(a: datetime, b: datetime, c: datetime) -> None:
    a, b, c = sorted((a, b, c))
    assert business_minutes(a, c, HOLIDAY_DATES) == business_minutes(a, b, HOLIDAY_DATES) + business_minutes(
        b, c, HOLIDAY_DATES
    )


@settings(max_examples=300, deadline=None)
@given(moments, st.integers(0, 40_000))
def test_round_trip(start: datetime, minutes: int) -> None:
    end = add_business_minutes(start, minutes, HOLIDAY_DATES)
    assert business_minutes(start, end, HOLIDAY_DATES) == minutes
    assert end >= start
    assert bizhours.is_business_day(end.date(), HOLIDAY_DATES) and bizhours.OPEN <= end.time() <= bizhours.CLOSE
    if end > start and minutes > 0:  # earliest: one minute less is not enough
        assert business_minutes(start, end - timedelta(minutes=1), HOLIDAY_DATES) == minutes - 1


@settings(max_examples=300, deadline=None)
@given(moments, moments)
def test_bounds(a: datetime, b: datetime) -> None:
    a, b = sorted((a, b))
    assert 0 <= business_minutes(a, b, HOLIDAY_DATES) <= (b - a).total_seconds() // 60


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 103), st.integers(0, 24 * 60 * 2 - 1))
def test_weekend_only_spans_give_zero(week: int, length: int) -> None:
    saturday = datetime(2024, 1, 6) + timedelta(weeks=week)
    assert business_minutes(saturday, saturday + timedelta(minutes=length), HOLIDAY_DATES) == 0


@pytest.mark.parametrize("day", sorted(d for d in HOLIDAY_DATES if d.weekday() < 5))
def test_holiday_only_spans_give_zero(day: date) -> None:
    assert (
        business_minutes(
            datetime.combine(day, datetime.min.time()), datetime.combine(day, bizhours.CLOSE), HOLIDAY_DATES
        )
        == 0
    )


def test_add_business_minutes_edges() -> None:
    friday = datetime(2024, 3, 8, 17, 30)
    assert add_business_minutes(friday, 45, HOLIDAY_DATES) == datetime(2024, 3, 11, 8, 15)
    assert add_business_minutes(datetime(2024, 3, 9, 3, 0), 0, HOLIDAY_DATES) == datetime(2024, 3, 11, 8, 0)
    assert add_business_minutes(datetime(2024, 3, 5, 18, 0), 0, HOLIDAY_DATES) == datetime(2024, 3, 5, 18, 0)
    assert add_business_minutes(datetime(2024, 4, 24, 17, 0), 120, HOLIDAY_DATES) == datetime(2024, 4, 26, 9, 0)
    with pytest.raises(ValueError):
        add_business_minutes(friday, -1, HOLIDAY_DATES)
