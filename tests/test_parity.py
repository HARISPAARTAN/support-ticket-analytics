"""Umbrella section 7 and spec section 10: the replica's numbers come from replica.json, and replica.json is the
reference's numbers.

tests/replica/model.test.mjs runs web/assets/js/model.js on replica.json for the 17 states and compares with
tests/replica/expected.json; this file proves that expected.json, the `reference` block and the arrays themselves
are the reference's numbers. `decode` and `values` re-implement the replica's rules in Python on the arrays.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import build_replica_data as brd
import reference as ref

STATE_NAMES = [
    "default", "team Service Desk", "team Technical Support", "team Billing & Accounts", "team Integrations",
    "priority P1", "priority P2", "priority P3", "priority P4", "channel Chat", "2025-01 to 2025-09",
    "2024-04 to 2024-06", "Integrations, P1", "cross-filter Bug, 2025", "cross-filter Integrations x P1",
    "cross-filter agent 20, rank by CSAT", "cross-filter 4–7 d at 2024-06-30",
]  # fmt: skip
FILTER_SETS = STATE_NAMES[1:13]  # the 12 filter sets of spec section 10
NEVER = 10**6  # an open interval's end day


@pytest.fixture(scope="module")
def replica() -> dict:
    return json.loads(brd.REPLICA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def expected() -> dict:
    return json.loads(brd.EXPECTED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def decoded(replica: dict) -> tuple[pd.DataFrame, list[tuple[int, int, int]]]:
    return decode(replica)


def decode(replica: dict) -> tuple[pd.DataFrame, list[tuple[int, int, int]]]:
    """The ticket arrays as a frame (day numbers since the epoch) and the open intervals [start, end) in days."""
    a = replica["tickets"]
    d, q = np.array(a["d"]), np.array(a["q"])
    frame = pd.DataFrame(
        {
            "minute": np.cumsum(a["t"]),
            "team": d // 576 + 1,
            "priority": d // 144 % 4,
            "channel": d // 36 % 4,
            "category": d // 6 % 6,
            "status": d % 6,
            "agent": a["a"],
            "fr": a["f"],
            "res": a["r"],
            "fr_outcome": q // 54,
            "res_outcome": q // 18 % 3,
            "csat": q // 3 % 6,
            "reopens": q % 3,
            "first_res": a["v"],
        }
    )
    frame["day"] = frame["minute"] // 1440
    frame["first_res"] = np.where(frame["first_res"] >= 0, frame["day"] + frame["first_res"], -1)
    intervals = [
        (i, int(day), NEVER if res < 0 else int(res))
        for i, (day, res) in enumerate(zip(frame["day"], frame["first_res"], strict=True))
    ]
    flat = a["reopens"]
    final = frame["first_res"].copy()
    for k in range(0, len(flat), 3):
        i, start, end = flat[k], flat[k + 1], flat[k + 2]
        day = int(frame.at[i, "day"])
        intervals.append((i, day + start, NEVER if end < 0 else day + end))
        if end >= 0:
            final.at[i] = max(final.at[i], day + end)
    resolved = frame["status"].isin([3, 4])
    frame["final_res"] = np.where(resolved, final, -1)
    return frame, intervals


def day_number(day: date) -> int:
    return (day - ref.START_DATE).days


def mask(frame: pd.DataFrame, ctx: ref.Context) -> pd.Series:
    keep = pd.Series(True, index=frame.index)
    if ctx.teams is not None:
        keep &= frame["team"].isin(ctx.teams)
    if ctx.priorities is not None:
        keep &= frame["priority"].isin([ref.PRIORITY_ORDER.index(p) for p in ctx.priorities])
    if ctx.channels is not None:
        keep &= frame["channel"].isin([brd.CHANNELS.index(c) for c in ctx.channels])
    return keep


def median_hours(values: pd.Series) -> float | None:
    v = values[values >= 0]
    return None if v.empty else float(v.median()) / 60


def ratio(numerator: int, denominator: int) -> float | None:
    return None if not numerator or not denominator else numerator / denominator


def values(frame: pd.DataFrame, intervals: list[tuple[int, int, int]], ctx: ref.Context) -> dict[str, object]:
    """The replica's rules on the arrays: the same measures as the reference for a slicer context."""
    lo, hi = day_number(ctx.first), day_number(ctx.last)
    keep = mask(frame, ctx)
    created = frame[keep & frame["day"].between(lo, hi)]
    resolved = frame[keep & frame["final_res"].between(lo, hi)]
    open_now = [(i, s, e) for i, s, e in intervals if keep.iat[i] and s <= hi < e]
    ages = [hi - int(frame.at[i, "day"]) for i, _, _ in open_now]
    met_fr, breached_fr = int((created["fr_outcome"] == 0).sum()), int((created["fr_outcome"] == 1).sum())
    met_res, breached_res = int((created["res_outcome"] == 0).sum()), int((created["res_outcome"] == 1).sum())
    answered = created["csat"] > 0
    ever = int((created["first_res"] >= 0).sum())
    return {
        "Created": len(created) or None,
        "Resolved": len(resolved) or None,
        "Backlog": len(open_now),
        "Open over 7 days": sum(a >= 8 for a in ages) or None,
        "Oldest open ticket (days)": max(ages) if ages else None,
        "Median first response (h)": median_hours(created["fr"]),
        "Median resolution (h)": median_hours(created["res"]),
        "SLA first response met %": ratio(met_fr, met_fr + breached_fr),
        "SLA resolution met %": ratio(met_res, met_res + breached_res),
        "Breaches": int(((created["fr_outcome"] == 1) | (created["res_outcome"] == 1)).sum()) or None,
        "Reopen rate": ratio(int((created["reopens"] > 0).sum()), ever),
        "CSAT average": float(created.loc[answered, "csat"].mean()) if answered.any() else None,
        "CSAT response rate": ratio(int(answered.sum()), int(created["status"].isin([3, 4]).sum())),
        "Active agents": int(resolved["agent"].nunique()) or None,
    }


def assert_close(actual: object, wanted: object, label: str) -> None:
    if isinstance(wanted, float) and actual is not None:
        assert actual == pytest.approx(wanted, rel=1e-9, abs=1e-12), label
    else:
        assert actual == wanted, label


# ---------------------------------------------------------------- the committed files


def test_committed_files_equal_a_fresh_build(model: ref.Model) -> None:
    assert brd.REPLICA.read_text(encoding="utf-8") == brd.dumps_replica(brd.build(model))
    assert brd.EXPECTED.read_text(encoding="utf-8") == brd.dumps_expected(brd.expected(model))


def test_seventeen_states_in_order(expected: dict) -> None:
    assert expected["version"] == 1
    assert [s["name"] for s in expected["states"]] == STATE_NAMES
    assert expected["states"][0]["state"] == brd.default_state()
    for entry in expected["states"]:
        assert set(entry["views"]) == set(brd.TABS), entry["name"]


def test_reference_block_equals_the_default_views(replica: dict, expected: dict) -> None:
    default = expected["states"][0]["views"]
    for tab in brd.TABS:
        wanted = {k: v for k, v in default[tab].items() if k not in ("table", "breaches", "oldest")}
        assert replica["reference"][tab] == wanted, tab


def test_default_tiles_equal_the_reference(model: ref.Model, replica: dict) -> None:
    tiles = replica["reference"]["overview"]["tiles"]
    for key, name in (("created", "Created"), ("resolved", "Resolved"), ("backlog", "Backlog"),
                      ("medianFr", "Median first response (h)"), ("resMet", "SLA resolution met %"),
                      ("csat", "CSAT average")):  # fmt: skip
        assert_close(tiles[key]["value"], ref.measure(model, name), key)
    assert tiles["created"]["py"] is None  # the default range starts in 2024: no full previous year
    assert tiles["backlog"]["py"] == ref.measure(model, "Backlog", ref.Context(date_to=date(2024, 9, 30)))
    assert replica["reference"]["sla"]["tiles"]["breaches"] == ref.measure(model, "Breaches")
    assert replica["reference"]["backlog"]["tiles"]["backlog"] == ref.measure(model, "Backlog")


def test_replica_json_stays_in_budget() -> None:
    assert brd.REPLICA.stat().st_size <= 1_300_000


# ---------------------------------------------------------------- the arrays


def test_arrays_have_one_value_per_ticket(model: ref.Model, replica: dict) -> None:
    arrays = replica["tickets"]
    for key in ("t", "d", "a", "c", "s", "f", "r", "v", "q"):
        assert len(arrays[key]) == len(model.tickets), key
    assert len(arrays["reopens"]) == 3 * int(model.tickets["reopen_count"].sum())
    assert replica["meta"]["firstId"] == 100001


def test_arrays_rebuild_the_ticket_columns(model: ref.Model, decoded: tuple) -> None:
    frame, _ = decoded
    t = model.tickets.sort_values("ticket_id")
    minute = ((t["created_at"] - brd.EPOCH).dt.total_seconds() // 60).astype(int)
    assert frame["minute"].tolist() == minute.tolist()
    assert frame["team"].tolist() == t["team_id"].tolist()
    assert [ref.PRIORITY_ORDER[p] for p in frame["priority"]] == t["priority"].tolist()
    assert [brd.STATUSES[s] for s in frame["status"]] == t["status"].tolist()
    assert frame["agent"].tolist() == t["agent_id"].tolist()
    assert [brd.OUTCOMES[o] for o in frame["res_outcome"]] == t["res_sla_status"].tolist()
    final = t["resolved_date"].map(lambda d: -1 if pd.isna(d) else (d - brd.EPOCH).days)
    assert frame["final_res"].tolist() == final.tolist()


@pytest.mark.parametrize("team", [None, 1, 2, 3, 4])
def test_backlog_on_every_day_equals_the_events(model: ref.Model, decoded: tuple, team: int | None) -> None:
    frame, intervals = decoded
    ctx = ref.ALL if team is None else ref.ALL.where(teams={team})
    keep = mask(frame, ctx)
    days = (ref.END_DATE - ref.START_DATE).days + 1
    change = np.zeros(days + 1, dtype=int)
    for i, start, end in intervals:
        if keep.iat[i]:
            change[start] += 1
            change[min(end, days)] -= 1
    from_arrays = np.cumsum(change)[:days]
    assert from_arrays.tolist() == ref.backlog_days(model, ctx).tolist()


@pytest.mark.parametrize("name", FILTER_SETS)
def test_filter_sets_reproduce_the_reference(model: ref.Model, decoded: tuple, name: str) -> None:
    frame, intervals = decoded
    st = next(s["state"] for s in brd.STATES if s["name"] == name)
    ctx = brd.context(st, "overview")
    for measure_name, value in values(frame, intervals, ctx).items():
        wanted = ref.measure(model, measure_name, ctx)
        if measure_name == "Backlog":
            wanted = wanted or 0
        assert_close(value, wanted, f"{name}: {measure_name}")


def test_month_ranges_end_on_the_last_day(expected: dict) -> None:
    by_name = {s["name"]: s for s in expected["states"]}
    assert by_name["2024-04 to 2024-06"]["views"]["backlog"]["snapshot"] == "2024-06-30"
    assert by_name["default"]["views"]["backlog"]["snapshot"] == "2025-09-30"
    assert len(by_name["default"]["views"]["backlog"]["days"]) == (ref.END_DATE - ref.START_DATE).days + 1
    assert date(2024, 4, 1) + timedelta(
        days=len(by_name["2024-04 to 2024-06"]["views"]["backlog"]["days"]) - 1
    ) == date(2024, 6, 30)
