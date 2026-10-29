"""Build web/assets/data/replica.json and the expected replica states, tests/replica/expected.json.

replica.json holds the dimension lists, the subject templates, one columnar integer array per ticket attribute in
ticket id order, the sparse reopen intervals and a `reference` block (the four tab views of the default state,
without the ticket tables), which tools/checks/replica-values.mjs compares with the rendered page:
  t  created minute since 2024-01-01 00:00, delta-encoded (the first value is absolute)
  d  ((((team * 4 + priority) * 4 + channel) * 6 + category) * 6 + status), every part 0-based
  a  agent id at the first response, 0 = unassigned          c  customer number - 1
  s  subject template * 8 + module                          f  first response bmin, -1 = none yet
  r  resolution bmin, -1 = not resolved                     v  first resolution day - created day, -1 = never
  q  ((first response outcome * 3 + resolution outcome) * 6 + CSAT score) * 3 + reopen count;
     outcomes 0 Met, 1 Breached, 2 Pending; CSAT 0 = no answer
  reopens  flat triples: ticket index, reopen day - created day, resolution day after it - created day (-1 = open)
expected.json holds the 17 states of tests/replica (the default, the 12 filter sets of spec section 10 and four
cross-filter states) with the four tab views computed by tools/reference.py from the CSV files, not from the
arrays. tests/replica/model.test.mjs runs web/assets/js/model.js on replica.json for the same states.

Usage (from the repository root):
    uv run python tools/build_replica_data.py           # write both files
    uv run python tools/build_replica_data.py --check   # exit 1 if either file differs from a fresh build
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

import make_data
import reference as ref
from reference import Context, measure, tile

ROOT = Path(__file__).resolve().parents[1]
REPLICA = ROOT / "web" / "assets" / "data" / "replica.json"
EXPECTED = ROOT / "tests" / "replica" / "expected.json"
TABS = ("overview", "sla", "teams", "backlog")
TEAMS = ref.TEAM_NAMES
PRIORITIES = ref.PRIORITY_ORDER
CHANNELS = tuple(name for name, _ in ref.CHANNELS)
CATEGORIES = tuple(name for name, _ in ref.CATEGORIES)
STATUSES = tuple(name for name, _, _, _ in ref.STATUSES)
TIERS = tuple(name for name, _ in ref.TIERS)
OUTCOMES = ("Met", "Breached", "Pending")
BUCKETS = tuple(name for name, _, _, _ in ref.AGE_BUCKETS)
FIRST_MONTH, LAST_MONTH = "2024-01", "2025-09"
PAGE = 25
EPOCH = pd.Timestamp(ref.START_DATE)


def default_state() -> dict[str, Any]:
    return {
        "tab": "overview",
        "from": FIRST_MONTH,
        "to": LAST_MONTH,
        "team": None,
        "priorities": [],
        "channel": None,
        "cross": None,
        "rankBy": "Resolved",
    }


def state(name: str, **changes: Any) -> dict[str, Any]:
    return {"name": name, "state": {**default_state(), **changes}}


STATES = (
    state("default"),
    *(state(f"team {team}", team=team) for team in TEAMS),
    *(state(f"priority {p}", priorities=[p]) for p in PRIORITIES),
    state("channel Chat", channel="Chat"),
    state("2025-01 to 2025-09", **{"from": "2025-01"}),
    state("2024-04 to 2024-06", **{"from": "2024-04", "to": "2024-06"}),
    state("Integrations, P1", team="Integrations", priorities=["P1"]),
    state("cross-filter Bug, 2025", tab="overview", cross={"dim": "category", "value": "Bug"}, **{"from": "2025-01"}),
    state("cross-filter Integrations x P1", tab="sla", cross={"dim": "cell", "team": "Integrations", "priority": "P1"}),
    state(
        "cross-filter agent 20, rank by CSAT", tab="teams", rankBy="CSAT average", cross={"dim": "agent", "value": 20}
    ),
    state("cross-filter 4–7 d at 2024-06-30", tab="backlog", cross={"dim": "bucket", "value": "4–7 d"}, to="2024-06"),
)


# ---------------------------------------------------------------- months and contexts


def month_start(ym: str) -> date:
    return date(int(ym[:4]), int(ym[5:]), 1)


def month_end(ym: str) -> date:
    first = month_start(ym)
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1)


def months(st: dict[str, Any]) -> list[str]:
    out, day = [], month_start(st["from"])
    while day <= month_start(st["to"]):
        out.append(f"{day.year}-{day.month:02d}")
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return out


def context(st: dict[str, Any], tab: str, *, cross: bool = True) -> Context:
    """The slicers of a state, plus its cross-filter when it belongs to `tab` (the bucket cross-filter of the
    Backlog tab is not a context: it filters the ticket lists only)."""
    teams = {TEAMS.index(st["team"]) + 1} if st["team"] else None
    priorities = set(st["priorities"]) or None
    categories = agents = None
    c = st["cross"] if cross and st["tab"] == tab else None
    if c and c["dim"] == "category":
        categories = {c["value"]}
    if c and c["dim"] in ("priority", "cell"):
        wanted = c["value"] if c["dim"] == "priority" else c["priority"]
        priorities = {wanted} & (priorities or {wanted})
    if c and c["dim"] == "cell":
        teams = {TEAMS.index(c["team"]) + 1} & (teams or {TEAMS.index(c["team"]) + 1})
    if c and c["dim"] == "agent":
        agents = {c["value"]}
    return Context(
        date_from=month_start(st["from"]),
        date_to=month_end(st["to"]),
        teams=frozenset(teams) if teams is not None else None,
        priorities=frozenset(priorities) if priorities is not None else None,
        channels=frozenset({st["channel"]}) if st["channel"] else None,
        categories=frozenset(categories) if categories else None,
        agents=frozenset(agents) if agents else None,
    )


def in_month(ctx: Context, ym: str) -> Context:
    return Context(month_start(ym), month_end(ym), ctx.teams, ctx.priorities, ctx.channels, ctx.categories, ctx.agents)


def ticket_list(frame: pd.DataFrame) -> dict[str, Any]:
    """The ticket table of a tab: the row count and the ids of the first page, newest first."""
    ids = sorted((int(i) for i in frame["ticket_id"]), reverse=True)
    return {"count": len(ids), "ids": ids[:PAGE]}


# ---------------------------------------------------------------- tab views


def overview(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx, base = context(st, "overview"), context(st, "overview", cross=False)
    tiles = {
        key: tile(model, name, ctx)
        for key, name in (
            ("created", "Created"),
            ("resolved", "Resolved"),
            ("backlog", "Backlog"),
            ("medianFr", "Median first response (h)"),
            ("resMet", "SLA resolution met %"),
            ("csat", "CSAT average"),
        )
    }
    days = ref.backlog_days(model, ctx)
    series = [
        [
            ym,
            measure(model, "Created", in_month(ctx, ym)),
            measure(model, "Resolved", in_month(ctx, ym)),
            int(days[pd.Timestamp(min(month_end(ym), ref.END_DATE))]),
        ]
        for ym in months(st)
    ]
    categories = [[c, measure(model, "Created", base.where(categories={c}))] for c in CATEGORIES]
    frame = ref.tickets(model, ctx)
    heat = (frame["created_date"].dt.day_of_week * 24 + frame["created_hour"]).value_counts()
    heatmap = [int(heat.get(i, 0)) for i in range(7 * 24)]
    return {"tiles": tiles, "months": series, "categories": categories, "heatmap": heatmap, "table": ticket_list(frame)}


def sla(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx, base = context(st, "sla"), context(st, "sla", cross=False)
    tiles = {
        key: measure(model, name, ctx)
        for key, name in (
            ("frMet", "SLA first response met %"),
            ("resMet", "SLA resolution met %"),
            ("breaches", "Breaches"),
            ("openBreaches", "Open breaches now"),
            ("medianRes", "Median resolution (h)"),
        )
    }
    shown = [p for p in PRIORITIES if base.priorities is None or p in base.priorities]
    teams = [t for i, t in enumerate(TEAMS, 1) if base.teams is None or i in base.teams]
    by_priority = [
        [
            p,
            measure(model, "SLA first response met %", base.where(priorities={p})),
            measure(model, "SLA resolution met %", base.where(priorities={p})),
        ]
        for p in shown
    ]
    matrix = [
        [t, p, measure(model, "SLA resolution met %", base.where(teams={TEAMS.index(t) + 1}, priorities={p}))]
        for t in teams
        for p in shown
    ]
    series = [
        [
            ym,
            measure(model, "SLA first response met %", in_month(ctx, ym)),
            measure(model, "SLA resolution met %", in_month(ctx, ym)),
        ]
        for ym in months(st)
    ]
    frame = ref.tickets(model, ctx)
    return {
        "tiles": tiles,
        "priorities": by_priority,
        "matrix": matrix,
        "months": series,
        "breaches": ticket_list(frame[frame["any_sla_breach"]]),
        "table": ticket_list(frame),
    }


def teams(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx, base = context(st, "teams"), context(st, "teams", cross=False)
    tiles = {
        key: measure(model, name, base)
        for key, name in (
            ("resolved", "Resolved"),
            ("activeAgents", "Active agents"),
            ("perAgent", "Tickets per agent"),
            ("reopenRate", "Reopen rate"),
            ("csat", "CSAT average"),
            ("csatRate", "CSAT response rate"),
        )
    }
    names = dict(zip(model.agents["agent_id"], model.agents["agent_name"], strict=True)) | {0: "Unassigned"}
    rows = ref.agent_rows(model, base, st["rankBy"])
    ranking = sorted(
        ([r["agent_id"], r["ranking"]] for r in rows if r["ranking"] is not None),
        key=lambda pair: (-pair[1], names[pair[0]]),
    )
    if ctx.agents is not None:
        rows = [r for r in rows if r["agent_id"] in ctx.agents]
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, names[r["agent_id"]]))
    scorecard = [
        [
            r["agent_id"],
            r["rank"],
            r["Resolved"],
            r["Median resolution (h)"],
            r["SLA resolution met %"],
            r["SLA first response met %"],
            r["Reopen rate"],
            r["CSAT average"],
            r["CSAT responses"],
        ]
        for r in rows
    ]
    shown = [i for i in range(1, 5) if base.teams is None or i in base.teams]
    per_agent = [
        [ym, [measure(model, "Tickets per agent", in_month(base, ym).where(teams={team})) for team in shown]]
        for ym in months(st)
    ]
    scores = ref.tickets(model, base)["csat_score"].dropna().astype(int).value_counts()
    return {
        "tiles": tiles,
        "ranking": ranking,
        "scorecard": scorecard,
        "perAgent": per_agent,
        "csat": [int(scores.get(s, 0)) for s in range(1, 6)],
        "table": ticket_list(ref.tickets(model, ctx)),
    }


def backlog(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "backlog")
    snapshot = ctx.last
    tiles = {
        key: measure(model, name, ctx)
        for key, name in (
            ("backlog", "Backlog"),
            ("change30", "Backlog change 30 d"),
            ("over7", "Open over 7 days"),
            ("oldest", "Oldest open ticket (days)"),
        )
    }
    days = ref.backlog_days(model, ctx)
    series = [int(v) for v in days[pd.Timestamp(ctx.first) : pd.Timestamp(snapshot)]]
    now = model.tickets[ref._dimensions(model.tickets, ctx) & model.tickets["is_open"]]
    statuses = [[s, int((now["status"] == s).sum())] for s in ref.OPEN_STATES]
    rows = ref.open_at(model, ctx)
    buckets = [[b, int((rows["bucket"] == b).sum())] for b in BUCKETS]
    shown = [i for i in range(1, 5) if ctx.teams is None or i in ctx.teams]
    by_team = [
        [TEAMS[t - 1], [int(((rows["team_id"] == t) & (rows["bucket"] == b)).sum()) for b in BUCKETS]] for t in shown
    ]
    c = st["cross"] if st["tab"] == "backlog" else None
    if c and c["dim"] == "bucket":
        rows = rows[rows["bucket"] == c["value"]]
    return {
        "snapshot": snapshot.isoformat(),
        "tiles": tiles,
        "days": series,
        "statuses": statuses,
        "buckets": buckets,
        "teams": by_team,
        "oldest": [[int(i), int(a)] for i, a in zip(rows["ticket_id"][:PAGE], rows["age"][:PAGE], strict=True)],
        "table": ticket_list(rows),
    }


VIEWS = {"overview": overview, "sla": sla, "teams": teams, "backlog": backlog}


def expected(model: ref.Model) -> dict[str, Any]:
    out = []
    for entry in STATES:
        views = {tab: VIEWS[tab](model, entry["state"]) for tab in TABS}
        out.append({"name": entry["name"], "state": entry["state"], "views": views})
    return {"version": 1, "states": out}


# ---------------------------------------------------------------- replica.json


def _deltas(values: list[int]) -> list[int]:
    return [values[0], *(b - a for a, b in zip(values, values[1:], strict=False))]


def build(model: ref.Model) -> dict[str, Any]:
    t = model.tickets.sort_values("ticket_id")
    e = model.events
    created_day = (t["created_date"] - EPOCH).dt.days
    minute = ((t["created_at"] - EPOCH).dt.total_seconds() // 60).astype(int)
    status = t["status"].map(STATUSES.index)
    packed = (
        (((t["team_id"] - 1) * 4 + t["priority"].map(PRIORITIES.index)) * 4 + t["channel"].map(CHANNELS.index)) * 6
        + t["category"].map(CATEGORIES.index)
    ) * 6 + status
    lookup = {
        (c, tpl.format(module=mod)): i * 8 + m
        for c, templates in enumerate(make_data.SUBJECTS)
        for i, tpl in enumerate(templates)
        for m, mod in enumerate(make_data.MODULES)
    }
    subject = [lookup[(CATEGORIES.index(c), text)] for c, text in zip(t["category"], t["subject"], strict=True)]
    csat = t["csat_score"].fillna(0).astype(int)
    quality = (
        (t["fr_sla_status"].map(OUTCOMES.index) * 3 + t["res_sla_status"].map(OUTCOMES.index)) * 6 + csat
    ) * 3 + t["reopen_count"]
    resolved_events = e[e["to_status"] == "Resolved"]
    first_res = resolved_events.groupby("ticket_id")["event_date"].min()
    first_res_day = ((first_res - EPOCH).dt.days).reindex(t["ticket_id"])
    offset = first_res_day.to_numpy() - created_day.to_numpy()
    index_of = {int(i): n for n, i in enumerate(t["ticket_id"])}
    reopens: list[int] = []
    for ticket_id, group in e[e["ticket_id"].isin(t.loc[t["reopen_count"] > 0, "ticket_id"])].groupby("ticket_id"):
        start = int(created_day.loc[ticket_id])
        rows = list(zip(group["to_status"], group["event_date"], strict=True))
        for k, (to_status, day) in enumerate(rows):
            if to_status != "Reopened":
                continue
            after = next((d for s, d in rows[k + 1 :] if s == "Resolved"), None)
            end = -1 if after is None else int((after - EPOCH).days) - start
            reopens += [index_of[int(ticket_id)], int((day - EPOCH).days) - start, end]
    agents = model.agents.sort_values("agent_id")
    tiers = t.drop_duplicates("customer_id").set_index("customer_id")["customer_tier"]
    return {
        "version": 1,
        "meta": {
            "epoch": ref.START_DATE.isoformat(),
            "asOf": ref.AS_OF.strftime("%Y-%m-%d %H:%M"),
            "firstMonth": FIRST_MONTH,
            "lastMonth": LAST_MONTH,
            "firstId": int(t["ticket_id"].iloc[0]),
            "rankMinCreated": ref.RANK_MIN_CREATED,
        },
        "dims": {
            "teams": list(TEAMS),
            "priorities": list(PRIORITIES),
            "channels": list(CHANNELS),
            "categories": list(CATEGORIES),
            "statuses": list(STATUSES),
            "openStatuses": list(ref.OPEN_STATES),
            "tiers": list(TIERS),
            "outcomes": list(OUTCOMES),
            "buckets": [[name, lo, hi] for name, lo, hi, _ in ref.AGE_BUCKETS],
            "rankBy": list(ref.RANK_BY),
            "agents": [["Unassigned", 0, ""]]
            + [
                [n, int(tm), r]
                for n, tm, r in zip(agents["agent_name"], agents["team_id"], agents["role"], strict=True)
            ],
            "customerTiers": [TIERS.index(tiers.get(f"C{n:04d}", "Starter")) for n in range(1, 601)],
            "subjects": [list(group) for group in make_data.SUBJECTS],
            "modules": list(make_data.MODULES),
        },
        "tickets": {
            "t": _deltas([int(m) for m in minute]),
            "d": [int(v) for v in packed],
            "a": [int(v) for v in t["agent_id"]],
            "c": [int(c[1:]) - 1 for c in t["customer_id"]],
            "s": subject,
            "f": [int(v) for v in t["first_response_bmin"].fillna(-1)],
            "r": [int(v) for v in t["resolution_bmin"].fillna(-1)],
            "v": [-1 if pd.isna(v) else int(v) for v in offset],
            "q": [int(v) for v in quality],
            "reopens": reopens,
        },
        "reference": {tab: _without_tables(VIEWS[tab](model, default_state())) for tab in TABS},
    }


def _without_tables(view: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in view.items() if k not in ("table", "breaches", "oldest")}


def dumps_replica(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def dumps_expected(data: dict[str, Any]) -> str:
    states = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in data["states"])
    return '{"version":1,"states":[\n' + states + "\n]}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build web/assets/data/replica.json and tests/replica/expected.json.")
    parser.add_argument("--data", type=Path, default=ref.DATA)
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the committed files")
    args = parser.parse_args(argv)
    model = ref.load(args.data.resolve())
    outputs = {REPLICA: dumps_replica(build(model)), EXPECTED: dumps_expected(expected(model))}
    if args.check:
        stale = [p for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"FAIL {path.relative_to(ROOT).as_posix()} differs from a fresh build")
        if stale:
            return 1
        print(f"replica.json ({len(outputs[REPLICA].encode()):,} bytes) and expected.json match a fresh build")
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {REPLICA.relative_to(ROOT).as_posix()} ({len(outputs[REPLICA].encode()):,} bytes)")
    print(f"wrote {EXPECTED.relative_to(ROOT).as_posix()} ({len(STATES)} states)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
