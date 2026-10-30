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
CHECKLIST = Path(__file__).resolve().parents[1] / "docs" / "desktop-session.md"
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


def checklist() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


def test_checklist_quotes_the_calculation_items_on_the_sla_matrix(model):
    text = checklist()
    sla = "SLA resolution met %"
    for year_number, month_number in ((2025, 9), (2025, 3)):
        ctx = ref.month(year_number, month_number)
        cur, py, yoy = (ref.item(model, sla, calc, ctx) for calc in ("Current", "PY", "YoY"))
        assert f"row {year_number}-{month_number:02d} reads `{cur * 100:.1f}%`, `{py * 100:.1f}%`" in text
        assert f"and `{yoy * 100:+.1f} pp`" in text
    for month_number in range(1, 13):  # the first year has no previous year: PY and YoY are blank
        ctx = ref.month(2024, month_number)
        assert ref.item(model, sla, "PY", ctx) is None and ref.item(model, sla, "YoY", ctx) is None
    assert "the rows of 2024 are blank in PY and YoY" in text


def test_checklist_quotes_the_overview_tiles_of_2025(model):
    text = checklist()
    ctx = ref.Context(date(2025, 1, 1), date(2025, 9, 30))
    for name in ("Created", "Resolved", "Backlog"):
        t = ref.tile(model, name, ctx)
        assert f"{name} `{t['value']:,}` with `vs PY: {t['delta'] * 100:+.1f}%`" in text, name
    t = ref.tile(model, "Median first response (h)", ctx)
    assert f"`{t['value']:.2f} h` with `vs PY: {t['delta']:+.2f} h`" in text
    t = ref.tile(model, "SLA resolution met %", ctx)
    assert f"`{t['value'] * 100:.1f}%` with `vs PY: {t['delta'] * 100:+.1f} pp`" in text
    t = ref.tile(model, "CSAT average", ctx)
    assert f"`{t['value']:.2f}` with `vs PY: {t['delta']:+.2f}`" in text


def test_checklist_quotes_the_role_values_of_the_integrations_lead(model):
    text = checklist()
    lead = ref.Context(teams=frozenset({ref.INTEGRATIONS}))
    values = {name: ref.measure(model, name, lead) for name in ("Created", "Resolved", "Backlog", "Active agents")}
    per_agent = ref.measure(model, "Tickets per agent", lead)
    assert values == {"Created": 3210, "Resolved": 3183, "Backlog": 27, "Active agents": 5}
    assert (
        f"Created `{values['Created']:,}`, Resolved `{values['Resolved']:,}` and Backlog `{values['Backlog']}`" in text
    )
    assert f"Active agents `{values['Active agents']}` and Tickets per agent `{per_agent:.1f}`" in text


def test_agent_ranks_run_over_all_teams(model):
    """The scorecard shows 24 agents in four teams; Agent rank counts across the teams, so 1 to 24 without a tie."""
    rows = [r for r in ref.agent_rows(model, ref.ALL, "Resolved") if r["rank"] is not None]
    assert sorted(r["rank"] for r in rows) == list(range(1, 25))
    names = dict(zip(model.agents["agent_id"], model.agents["agent_name"], strict=True))
    rank = {names[r["agent_id"]]: r["rank"] for r in rows}
    assert len({tid for tid in model.agents["team_id"]}) == 4
    for name, number in (("Larissa Pacheco", 1), ("Ben Hutchinson", 6), ("Encarnita Meléndez", 24)):
        assert rank[name] == number
        assert f"{name} `{number}`" in checklist()
