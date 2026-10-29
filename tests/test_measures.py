"""Spec section 10: identities of tools/reference.py, the Python column of docs/reconciliation.md and, once entered,
the Desktop values within the tolerance of half a unit of the last displayed digit."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import reference as ref

DOC = Path(__file__).resolve().parents[1] / "docs" / "reconciliation.md"
KINDS = "count|hours|percent|csat|decimal"
ROW = re.compile(rf"^\| (R\d+) \| ([^|]+?) \| ([^|]+?) \| ({KINDS}) \| ([^|]+?) \| ([^|]*?) *\| ([^|]+?) \|$", re.M)
SESSION = re.compile(r"^Desktop session: (.+)$", re.M)
HALF = {"count": Decimal(0), "hours": Decimal("0.005"), "percent": Decimal("0.05"), "csat": Decimal("0.005")}
MONTH_ENDS = [
    date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    for y in (2024, 2025)
    for m in range(1, 13)
    if date(y, m, 1) <= ref.END_DATE
]


def rows() -> list[tuple[str, ...]]:
    return ROW.findall(DOC.read_text(encoding="utf-8"))


def matches(kind: str, value: float, desktop: str) -> bool:
    """value as tools/reference.py returns it (a ratio for percentages); desktop as the card shows it."""
    text = desktop.replace(",", "").strip()
    if kind == "hours" and text.endswith("min"):
        return abs(Decimal(text.removesuffix("min").strip()) - Decimal(str(value)) * 60) <= Decimal("0.5")
    shown = Decimal(text.removesuffix("%").removesuffix("h").strip())
    if kind == "percent":
        return abs(shown - Decimal(str(value)) * 100) <= HALF[kind]
    if kind == "count":
        return shown == Decimal(int(value))
    return abs(shown - Decimal(str(value))) <= HALF.get(kind, Decimal("0.05"))


def test_the_table_lists_r1_to_r31():
    assert [r[0] for r in rows()] == [f"R{n}" for n in range(1, 32)]


def test_python_column_equals_the_reference(model):
    for row, (rid, _, value, kind) in zip(rows(), ref.reconciliation(model), strict=True):
        assert (row[0], row[3]) == (rid, kind)
        assert row[4] == ref.display(value, kind), rid


def test_desktop_values_match_within_the_tolerance(model):
    expected = {rid: value for rid, _, value, _ in ref.reconciliation(model)}
    entered = [(r[0], r[3], r[5]) for r in rows() if r[5].strip()]
    if not entered:
        pytest.skip("Desktop values pending (docs/desktop-session.md)")
    assert len(entered) == 31, "enter all 31 Desktop values"
    assert not SESSION.search(DOC.read_text(encoding="utf-8")).group(1).startswith("not yet"), "date the session"
    bad = [(rid, desktop) for rid, kind, desktop in entered if not matches(kind, expected[rid], desktop)]
    assert not bad, bad


@pytest.mark.parametrize(
    ("kind", "value", "desktop", "ok"),
    [
        ("count", 25066, "25,066", True),
        ("count", 25066, "25,067", False),
        ("hours", 3.4333, "3.43 h", True),
        ("hours", 3.4333, "3.44 h", False),
        ("hours", 0.75, "45 min", True),
        ("hours", 0.75, "47 min", False),
        ("percent", 0.91151, "91.2%", True),
        ("percent", 0.91151, "91.0%", False),
        ("csat", 3.977, "3.98", True),
        ("csat", 3.977, "3.97", False),
        ("decimal", 65.6818, "65.7", True),
        ("decimal", 65.6818, "65.6", False),
    ],
)
def test_tolerance_rules(kind, value, desktop, ok):
    assert matches(kind, value, desktop) is ok


@pytest.mark.parametrize("day", MONTH_ENDS, ids=str)
def test_statuses_and_buckets_add_up_to_the_backlog(model, day):
    ctx = ref.Context(date_to=day)
    backlog = ref.backlog(model, ctx) or 0
    assert sum(ref.tickets_in_status(model, s, ctx) or 0 for s in ref.OPEN_STATES) == backlog
    assert sum(ref.backlog_in_bucket(model, b[0], ctx) or 0 for b in ref.AGE_BUCKETS) == backlog
    assert (ref.backlog_in_bucket(model, None, ctx) or 0) == backlog
    for closed in ("Resolved", "Closed"):
        assert (ref.tickets_in_status(model, closed, ctx) or 0) >= 0


@pytest.mark.parametrize("day", MONTH_ENDS[1:], ids=str)
def test_backlog_change_is_the_sum_of_the_deltas(model, day):
    ctx = ref.Context(date_to=day)
    dates = model.events["event_date"]
    window = model.events[(dates > pd.Timestamp(day - timedelta(days=30))) & (dates <= pd.Timestamp(day))]
    assert ref.measure(model, "Backlog change 30 d", ctx) == int(window["backlog_delta"].sum())


def test_r31_is_the_integrations_slice(model):
    assert ref.measure(model, "Created", ref.Context(teams=frozenset({ref.INTEGRATIONS}))) == int(
        (model.tickets["team_id"] == ref.INTEGRATIONS).sum()
    )
