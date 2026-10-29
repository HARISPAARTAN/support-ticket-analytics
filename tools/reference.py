"""Python reference of the report's measures (spec sections 5.2 and 7), computed with pandas from the files in data/.

    uv run python tools/reference.py [--data data]     # prints the reconciliation values R1 to R31

The rules are those of the Power Query steps and the DAX measures: business minutes per event interval (an interval
ends at the next event, or at AS_OF for the last event unless it is Closed), the clock runs in New, Open and Reopened,
SLA outcomes are Met, Breached or Pending per ticket and are attributed to the creation date, `Resolved` alone counts by
the resolution date, the backlog sums the event deltas up to the snapshot date, ageing counts calendar days from the
creation date. Medians skip blanks like DAX MEDIAN, P90 interpolates like PERCENTILEX.INC.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from bizhours import business_minutes, load_holidays

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AS_OF = datetime(2025, 9, 30, 18, 0)  # equal to the Power Query parameter AsOf (tests/pbi/test_tmdl_lint.py)
START_DATE = date(2024, 1, 1)  # DimDate, parameters StartDate and EndDate
END_DATE = date(2025, 9, 30)
# DimStatus: Status, Status sort, Is open, Clock running
STATUSES = (
    ("New", 1, True, True),
    ("Open", 2, True, True),
    ("Pending", 3, True, False),
    ("Resolved", 4, False, False),
    ("Closed", 5, False, False),
    ("Reopened", 6, True, True),
)
OPEN_STATES = tuple(s for s, _, is_open, _ in STATUSES if is_open)
CLOCK_STATES = tuple(s for s, _, _, running in STATUSES if running)
RESOLVED_STATES = ("Resolved", "Closed")
CATEGORIES = (("Bug", 1), ("How-to", 2), ("Billing", 3), ("Feature request", 4), ("Access", 5), ("Integration", 6))
CHANNELS = (("E-mail", 1), ("Portal", 2), ("Chat", 3), ("Phone", 4))
TIERS = (("Enterprise", 1), ("Business", 2), ("Starter", 3))
PRIORITY_ORDER = ("P1", "P2", "P3", "P4")
# DimAgeBucket: Bucket, Min days, Max days, Bucket sort (calendar days from the creation date to the snapshot)
AGE_BUCKETS = (
    ("0–1 d", 0, 1, 1),
    ("2–3 d", 2, 3, 2),
    ("4–7 d", 4, 7, 3),
    ("8–14 d", 8, 14, 4),
    ("15–30 d", 15, 30, 5),
    ("> 30 d", 31, 36500, 6),
)
RANK_BY = ("Resolved", "SLA resolution met %", "SLA first response met %", "CSAT average")  # field parameter order
RANK_MIN_CREATED = 20
CALCULATIONS = ("Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12")


def read_folder(folder: Path) -> pd.DataFrame:
    return pd.concat([pd.read_csv(p, keep_default_na=False, dtype=str) for p in sorted(folder.glob("*.csv"))])


def _stamp(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.where(values != "", None), format="%Y-%m-%d %H:%M")


def _int(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.where(values != "", None)).astype("Int64")


@dataclass
class Model:
    tickets: pd.DataFrame  # one row per ticket, the columns of FactTickets in snake case, indexed by ticket_id
    events: pd.DataFrame  # one row per event with the interval columns of EventIntervals
    agents: pd.DataFrame
    teams: pd.DataFrame
    priorities: pd.DataFrame
    holidays: frozenset[date]
    cases: pd.DataFrame  # business_hours_cases.csv, as text


def load(data: Path = DATA) -> Model:
    holidays = load_holidays(data / "holidays.csv")
    priorities = pd.read_csv(data / "priorities.csv").set_index("priority")
    agents = pd.read_csv(data / "agents.csv", keep_default_na=False)
    teams = pd.read_csv(data / "teams.csv")
    t = read_folder(data / "tickets")
    e = read_folder(data / "ticket_events")

    e = e.assign(
        event_id=e["event_id"].astype(int),
        ticket_id=e["ticket_id"].astype(int),
        event_seq=e["event_seq"].astype(int),
        event_at=_stamp(e["event_at"]),
        from_status=e["from_status"].where(e["from_status"] != "", None),
        agent_id=_int(e["agent_id"]),
    ).sort_values(["ticket_id", "event_seq"], ignore_index=True)
    e["next_event_at"] = e.groupby("ticket_id")["event_at"].shift(-1)
    last = e["next_event_at"].isna()
    end = e["next_event_at"].where(~last, pd.Timestamp(AS_OF)).where(~(last & (e["to_status"] == "Closed")))
    e["interval_bmin"] = [
        business_minutes(a.to_pydatetime(), None if pd.isna(b) else b.to_pydatetime(), holidays)
        for a, b in zip(e["event_at"], end, strict=True)
    ]
    e["interval_bmin"] = e["interval_bmin"].astype("Int64")
    e["clock_running"] = e["to_status"].isin(CLOCK_STATES)
    e["backlog_delta"] = e["to_status"].isin(OPEN_STATES).astype(int) - e["from_status"].isin(OPEN_STATES).astype(int)
    e["event_date"] = e["event_at"].dt.normalize()

    t = t.assign(
        ticket_id=t["ticket_id"].astype(int),
        created_at=_stamp(t["created_at"]),
        team_id=t["team_id"].astype(int),
        agent_id=_int(t["agent_id"]).fillna(0).astype(int),  # 0 = Unassigned, as in Power Query
        first_response_at=_stamp(t["first_response_at"]),
        resolved_at=_stamp(t["resolved_at"]),
        closed_at=_stamp(t["closed_at"]),
        reopen_count=t["reopen_count"].astype(int),
        csat_score=_int(t["csat_score"]),
    ).set_index("ticket_id", drop=False)
    t.index.name = None  # the column stays the only `ticket_id`, so groupby and sort_values are unambiguous
    t["created_date"] = t["created_at"].dt.normalize()
    t["created_hour"] = t["created_at"].dt.hour
    t["resolved_date"] = t["resolved_at"].dt.normalize()
    e["ticket_created_date"] = e["ticket_id"].map(t["created_date"])

    count = e.groupby("ticket_id").size()
    first = e[e["event_seq"] == 1].set_index("ticket_id")["interval_bmin"]
    t["first_response_bmin"] = first.where(count.reindex(first.index) > 1).astype("Int64")
    t["clock_bmin"] = e[e["clock_running"]].groupby("ticket_id")["interval_bmin"].sum().reindex(t.index, fill_value=0)
    t["clock_bmin"] = t["clock_bmin"].astype("Int64")
    pending = e[e["to_status"] == "Pending"].groupby("ticket_id")["interval_bmin"].sum()
    t["pending_bmin"] = pending.reindex(t.index, fill_value=0).astype("Int64")
    t["is_resolved"] = t["status"].isin(RESOLVED_STATES)
    t["resolution_bmin"] = t["clock_bmin"].where(t["is_resolved"])
    t["ever_resolved"] = t.index.isin(e.loc[e["to_status"] == "Resolved", "ticket_id"])
    t["is_open"] = t["status"].isin(OPEN_STATES)
    fr_target = t["priority"].map(priorities["fr_target_bmin"])
    res_target = t["priority"].map(priorities["res_target_bmin"])
    new_interval = first.reindex(t.index)
    t["fr_sla_status"] = np.select(
        [
            t["first_response_bmin"].notna() & (t["first_response_bmin"] <= fr_target),
            (t["first_response_bmin"].notna() & (t["first_response_bmin"] > fr_target))
            | (t["first_response_bmin"].isna() & (new_interval > fr_target)),
        ],
        ["Met", "Breached"],
        "Pending",
    )
    measured = t["resolution_bmin"].where(t["is_resolved"], t["clock_bmin"])
    t["res_sla_status"] = np.select(
        [t["is_resolved"] & (measured <= res_target), measured > res_target], ["Met", "Breached"], "Pending"
    )
    t["any_sla_breach"] = (t["fr_sla_status"] == "Breached") | (t["res_sla_status"] == "Breached")
    cases = pd.read_csv(data / "business_hours_cases.csv", keep_default_na=False, dtype=str)
    return Model(t, e, agents, teams, priorities, holidays, cases)


# ---------------------------------------------------------------- filter context


@dataclass(frozen=True)
class Context:
    """A filter context as the slicers set it: a DimDate range (inclusive; None = the whole table) and value sets on
    the dimensions (None = no filter). Dates filter the creation date through the active relationship."""

    date_from: date | None = None
    date_to: date | None = None
    teams: frozenset[int] | None = None
    priorities: frozenset[str] | None = None
    channels: frozenset[str] | None = None
    categories: frozenset[str] | None = None
    agents: frozenset[int] | None = None

    def where(self, **changes: object) -> Context:
        sets = {k: frozenset(v) for k, v in changes.items() if k not in ("date_from", "date_to")}  # type: ignore[call-overload]
        dates = {k: v for k, v in changes.items() if k in ("date_from", "date_to")}
        return replace(self, **sets, **dates)  # type: ignore[arg-type]

    @property
    def first(self) -> date | None:
        """MIN(DimDate[Date]) in this context, or None if no date of DimDate is left."""
        lo, hi = max(self.date_from or START_DATE, START_DATE), min(self.date_to or END_DATE, END_DATE)
        return lo if lo <= hi else None

    @property
    def last(self) -> date | None:
        """MAX(DimDate[Date]) in this context, or None if no date of DimDate is left."""
        lo, hi = max(self.date_from or START_DATE, START_DATE), min(self.date_to or END_DATE, END_DATE)
        return hi if lo <= hi else None


ALL = Context()


def month(year: int, month_number: int) -> Context:
    first = date(year, month_number, 1)
    following = date(year + (month_number == 12), month_number % 12 + 1, 1)
    return Context(first, following - timedelta(days=1))


def year(value: int) -> Context:
    return Context(date(value, 1, 1), date(value, 12, 31))


def shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def shift_month_end(day: date, years: int) -> date:
    """DATEADD by years: the last day of a month moves to the last day of the same month (28 Feb 2025 to 29 Feb
    2024), any other day keeps its day number."""
    if (day + timedelta(days=1)).month == day.month:
        return shift_years(day, years)
    following = date(day.year + years + (day.month == 12), day.month % 12 + 1, 1)
    return following - timedelta(days=1)


def calculation(ctx: Context, name: str) -> Context:
    """The date range a calculation item of `Time intelligence` evaluates the measure in (Current, PY, YTD, PYTD,
    R12); an empty range when no date of DimDate is left (the measure is then blank)."""
    lo, hi = ctx.first, ctx.last
    empty = replace(ctx, date_from=date(1900, 1, 2), date_to=date(1900, 1, 1))
    if lo is None or hi is None:
        return empty
    if name == "Current":
        return ctx
    if name == "PY":  # SAMEPERIODLASTYEAR(DimDate[Date]); a range that ends on a month end keeps the month end
        return replace(ctx, date_from=shift_years(lo, -1), date_to=shift_month_end(hi, -1))
    if name == "YTD":  # DATESYTD(DimDate[Date])
        return replace(ctx, date_from=date(hi.year, 1, 1), date_to=hi)
    if name == "PYTD":  # SAMEPERIODLASTYEAR(DATESYTD(DimDate[Date]))
        return replace(ctx, date_from=date(hi.year - 1, 1, 1), date_to=shift_month_end(hi, -1))
    if name == "R12":  # DATESINPERIOD(DimDate[Date], MAX(DimDate[Date]), -12, MONTH)
        start = shift_years(hi, -1) + timedelta(days=1)
        return replace(ctx, date_from=start, date_to=hi)
    raise ValueError(f"unknown calculation item {name!r}")


def _dimensions(t: pd.DataFrame, ctx: Context) -> pd.Series:
    mask = pd.Series(True, index=t.index)
    for column, values in (
        ("team_id", ctx.teams),
        ("priority", ctx.priorities),
        ("channel", ctx.channels),
        ("category", ctx.categories),
        ("agent_id", ctx.agents),
    ):
        if values is not None:
            mask &= t[column].isin(values)
    return mask


def _in_dates(dates: pd.Series, ctx: Context) -> pd.Series:
    lo, hi = ctx.first, ctx.last
    if lo is None or hi is None:
        return pd.Series(False, index=dates.index)
    return (dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi))


def tickets(model: Model, ctx: Context) -> pd.DataFrame:
    """The FactTickets rows in context: dimension filters and the creation date in the date range."""
    t = model.tickets
    return t[_dimensions(t, ctx) & _in_dates(t["created_date"], ctx)]


def resolved_tickets(model: Model, ctx: Context) -> pd.DataFrame:
    """Final resolutions in the period: USERELATIONSHIP(Resolved date, Date) and Is resolved."""
    t = model.tickets
    return t[_dimensions(t, ctx) & t["is_resolved"] & _in_dates(t["resolved_date"], ctx)]


def _events_to(model: Model, ctx: Context, day: date | None) -> pd.DataFrame:
    """Events of the tickets that pass the dimension filters (REMOVEFILTERS(DimDate)), up to the snapshot date."""
    if day is None:
        return model.events.iloc[0:0]
    t = model.tickets
    keep = t.index[_dimensions(t, ctx)]
    e = model.events
    return e[e["ticket_id"].isin(keep) & (e["event_date"] <= pd.Timestamp(day))]


def _hours(values: pd.Series, how: str) -> float | None:
    v = values.dropna().astype(float)
    if v.empty:
        return None
    if how == "median":
        return float(v.median()) / 60
    if how == "average":
        return float(v.mean()) / 60
    return float(np.percentile(v.to_numpy(), 90, method="linear")) / 60


def _count(values: pd.Series) -> int | None:
    """COUNTROWS or CALCULATE([Created], ...) over the rows where `values` is true: blank instead of 0."""
    return int(values.sum()) or None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    """DIVIDE: blank when the numerator is blank or the denominator is blank or 0."""
    return None if numerator is None or not denominator else numerator / denominator


def _sub(a: float | None, b: float | None) -> float | None:
    """a - b with DAX blanks: blank only when both are blank."""
    return None if a is None and b is None else (a or 0) - (b or 0)


def backlog(model: Model, ctx: Context) -> int | None:
    """SUM of Backlog delta over the events up to MAX(DimDate[Date]); blank when the context has no date."""
    events = _events_to(model, ctx, ctx.last)
    return int(events["backlog_delta"].sum()) if not events.empty else None


def open_tickets(model: Model, ctx: Context) -> pd.DataFrame:
    """The tickets open at the end of MAX(DimDate[Date]) with their age in calendar days (the GROUPBY of `Backlog in
    age bucket`)."""
    day = ctx.last
    events = _events_to(model, ctx, day)
    grouped = events.groupby("ticket_id")
    per_ticket = grouped.agg(open=("backlog_delta", "sum"), created=("ticket_created_date", "first"))
    open_rows = per_ticket[per_ticket["open"] == 1].copy()
    open_rows["age"] = (pd.Timestamp(day) - open_rows["created"]).dt.days if day else 0
    return open_rows


def tickets_in_status(model: Model, status: str, ctx: Context) -> int | None:
    """Events that entered `status` minus events that left it, up to the snapshot date."""
    events = _events_to(model, ctx, ctx.last)
    if events.empty:
        return None
    return int((events["to_status"] == status).sum() - (events["from_status"] == status).sum())


def backlog_in_bucket(model: Model, bucket: str | None, ctx: Context) -> int | None:
    """Open tickets at the snapshot whose age lies in the bucket (None: every bucket, which equals Backlog)."""
    if ctx.last is None:
        return None
    rows = open_tickets(model, ctx)
    if bucket is not None:
        _, lo, hi, _ = next(b for b in AGE_BUCKETS if b[0] == bucket)
        rows = rows[(rows["age"] >= lo) & (rows["age"] <= hi)]
    return len(rows) or None


def measure(model: Model, name: str, ctx: Context = ALL) -> int | float | None:
    """A measure of `_Measures` by its name, in the filter context `ctx`; None where DAX returns blank."""
    t = tickets(model, ctx)
    if name == "Created":
        return len(t) or None
    if name == "Resolved":
        return len(resolved_tickets(model, ctx)) or None
    if name == "Net flow":
        return _sub(measure(model, "Created", ctx), measure(model, "Resolved", ctx))
    if name == "Backlog":
        return backlog(model, ctx)
    if name == "Backlog change 30 d":
        now = backlog(model, ctx)
        if now is None or ctx.last is None:
            return None
        before = _events_to(model, ctx, ctx.last - timedelta(days=30))["backlog_delta"].sum()
        return now - int(before)
    if name == "Backlog PY":
        return backlog(model, calculation(ctx, "PY"))
    if name == "Open over 7 days":
        rows = open_tickets(model, ctx) if ctx.last else None
        return None if rows is None else (int((rows["age"] >= 8).sum()) or None)
    if name == "Oldest open ticket (days)":
        rows = open_tickets(model, ctx) if ctx.last else None
        return None if rows is None or rows.empty else int(rows["age"].max())
    for prefix, how in (("Median", "median"), ("Average", "average"), ("P90", "p90")):
        if name == f"{prefix} first response (h)":
            return _hours(t["first_response_bmin"], how)
        if name == f"{prefix} resolution (h)":
            return _hours(t["resolution_bmin"], how)
    for short, column in (("FR", "fr_sla_status"), ("Res", "res_sla_status")):
        if name == f"{short} SLA met":
            return _count(t[column] == "Met")
        if name == f"{short} SLA breached":
            return _count(t[column] == "Breached")
    if name in ("SLA first response met %", "SLA resolution met %"):
        column = "fr_sla_status" if "first" in name else "res_sla_status"
        met, breached = _count(t[column] == "Met"), _count(t[column] == "Breached")
        return _ratio(met, (met or 0) + (breached or 0))
    if name == "Breaches":
        return _count(t["any_sla_breach"])
    if name == "Open breaches now":
        return _count(t["any_sla_breach"] & t["is_open"])
    if name == "Reopened tickets":
        return _count(t["reopen_count"] > 0)
    if name == "Reopen rate":
        return _ratio(_count(t["reopen_count"] > 0), _count(t["ever_resolved"]))
    if name == "CSAT responses":
        return _count(t["csat_score"].notna())
    if name == "CSAT average":
        scores = t["csat_score"].dropna()
        return float(scores.astype(float).mean()) if len(scores) else None
    if name == "CSAT response rate":
        return _ratio(_count(t["csat_score"].notna()), _count(t["is_resolved"]))
    if name == "CSAT satisfied %":
        return _ratio(_count(t["csat_score"] >= 4), _count(t["csat_score"].notna()))
    if name == "Active agents":
        return int(resolved_tickets(model, ctx)["agent_id"].nunique()) or None
    if name == "Tickets per agent":
        return _ratio(measure(model, "Resolved", ctx), measure(model, "Active agents", ctx))
    if name == "BH tests passed":
        return bh_tests(model)[0]
    if name == "BH tests total":
        return bh_tests(model)[1]
    raise KeyError(f"unknown measure {name!r}")


def item(model: Model, name: str, calc: str, ctx: Context = ALL) -> int | float | None:
    """A measure under a calculation item of `Time intelligence`."""
    if calc in ("Current", "PY", "YTD", "PYTD", "R12"):
        return measure(model, name, calculation(ctx, calc))
    cur, py = measure(model, name, ctx), measure(model, name, calculation(ctx, "PY"))
    if cur is None or py is None:
        return None
    if calc == "YoY":
        return cur - py
    if calc == "YoY %":
        return None if "%" in name else _ratio(cur - py, py)  # cur - py is a number, never blank
    raise ValueError(f"unknown calculation item {calc!r}")


def bh_tests(model: Model) -> tuple[int, int]:
    """(passed, total) of the business-hours cases, recomputed with business_minutes (the TestBusinessHours table)."""
    passed = 0
    for row in model.cases.itertuples():
        start, end = (datetime.strptime(v, "%Y-%m-%d %H:%M") for v in (row.start, row.end))
        expected = None if row.expected_minutes == "" else int(row.expected_minutes)
        passed += business_minutes(start, end, model.holidays) == expected
    return passed, len(model.cases)


# ---------------------------------------------------------------- views of the replica (spec section 9)

SNAPSHOT_MEASURES = ("Backlog",)
ABSOLUTE_DELTAS = ("Median first response (h)", "SLA resolution met %", "CSAT average")  # the other deltas are relative


def tile(model: Model, name: str, ctx: Context) -> dict[str, float | int | None]:
    """A KPI tile: the value, the value of the same months a year earlier and the change (relative, or absolute for
    durations, percentages and CSAT). The previous year is n/a (None) when it does not lie wholly inside DimDate: for
    flow measures when the range starts before 2025, for the snapshot measure Backlog when it ends before 2025."""
    value = measure(model, name, ctx)
    edge = ctx.last if name in SNAPSHOT_MEASURES else ctx.first
    py = None
    if edge is not None and shift_years(edge, -1) >= START_DATE:
        py = measure(model, name, calculation(ctx, "PY"))
    if value is None or py is None:
        delta = None
    elif name in ABSOLUTE_DELTAS:
        delta = value - py
    else:
        delta = _ratio(value - py, py) if value != py else 0.0
    return {"value": value, "py": py, "delta": delta}


def backlog_days(model: Model, ctx: Context) -> pd.Series:
    """Backlog at the end of every DimDate day for the tickets that pass the dimension filters (0 before the first
    event), indexed by day."""
    t = model.tickets
    keep = t.index[_dimensions(t, ctx)]
    e = model.events[model.events["ticket_id"].isin(keep)]
    per_day = e.groupby("event_date")["backlog_delta"].sum()
    days = pd.date_range(START_DATE, END_DATE, freq="D")
    return per_day.reindex(days, fill_value=0).cumsum().astype(int)


def bucket_of(age: int) -> str:
    return next(name for name, lo, hi, _ in AGE_BUCKETS if lo <= age <= hi)


def open_at(model: Model, ctx: Context) -> pd.DataFrame:
    """The tickets open at the end of MAX(DimDate[Date]) with team, status at that day, age and bucket, oldest first
    (ties by ticket id)."""
    rows = open_tickets(model, ctx) if ctx.last else pd.DataFrame(columns=["open", "created", "age"])
    t = model.tickets.loc[rows.index]
    out = pd.DataFrame(
        {
            "ticket_id": rows.index.to_numpy(dtype=int),
            "age": rows["age"].to_numpy(dtype=int),
            "team_id": t["team_id"].to_numpy(dtype=int),
        }
    )
    out["bucket"] = [bucket_of(a) for a in out["age"]]
    return out.sort_values(["age", "ticket_id"], ascending=[False, True], ignore_index=True)


def agent_rows(model: Model, ctx: Context, rank_by: str) -> list[dict[str, object]]:
    """The agent scorecard: one row per DimAgent row (0 = Unassigned) with a non-blank value, the Ranking value of the
    field parameter entry `rank_by` (blank below RANK_MIN_CREATED created tickets) and its dense rank, highest first."""
    rows = []
    for agent_id in [0, *model.agents["agent_id"].tolist()]:
        sub = ctx.where(agents={agent_id})
        values = {
            name: measure(model, name, sub)
            for name in (
                "Created",
                "Resolved",
                "Median resolution (h)",
                "SLA resolution met %",
                "SLA first response met %",
                "Reopen rate",
                "CSAT average",
                "CSAT responses",
            )
        }
        ranking = values[rank_by] if (values["Created"] or 0) >= RANK_MIN_CREATED else None
        if any(v is not None for k, v in values.items() if k != "Created"):  # the table hides all-blank rows
            rows.append({"agent_id": agent_id, "ranking": ranking, **values})
    ranked = sorted({r["ranking"] for r in rows if r["ranking"] is not None}, reverse=True)
    for r in rows:
        r["rank"] = None if r["ranking"] is None else ranked.index(r["ranking"]) + 1
    return rows


# ---------------------------------------------------------------- reconciliation (spec section 10)

INTEGRATIONS = 4
TEAM_NAMES = ("Service Desk", "Technical Support", "Billing & Accounts", "Integrations")
# id, label, measure, calculation item, context, kind
RECONCILIATION: tuple[tuple[str, str, str, str, Context, str], ...] = (
    ("R1", "Created", "Created", "Current", ALL, "count"),
    ("R2", "Resolved", "Resolved", "Current", ALL, "count"),
    ("R3", "Created 2025", "Created", "Current", year(2025), "count"),
    ("R4", "Created PY, year 2025", "Created", "PY", year(2025), "count"),
    ("R5", "Created R12, 2025-09", "Created", "R12", month(2025, 9), "count"),
    ("R6", "Created YTD, 2025-09", "Created", "YTD", month(2025, 9), "count"),
    ("R7", "Backlog at 2024-06-30", "Backlog", "Current", Context(date_to=date(2024, 6, 30)), "count"),
    ("R8", "Backlog at 2024-12-31", "Backlog", "Current", Context(date_to=date(2024, 12, 31)), "count"),
    ("R9", "Backlog at 2025-09-30", "Backlog", "Current", Context(date_to=date(2025, 9, 30)), "count"),
    ("R10", "Tickets in status Pending at 2025-09-30", "Tickets in status:Pending", "Current", ALL, "count"),
    # at 2025-09-30 no open ticket is older than 30 days (blank), so R11 takes the snapshot of R7
    (
        "R11",
        "Backlog in age bucket > 30 d at 2024-06-30",
        "Backlog in age bucket:> 30 d",
        "Current",
        Context(date_to=date(2024, 6, 30)),
        "count",
    ),
    ("R12", "Median first response (h)", "Median first response (h)", "Current", ALL, "hours"),
    ("R13", "Average first response (h)", "Average first response (h)", "Current", ALL, "hours"),
    ("R14", "P90 first response (h)", "P90 first response (h)", "Current", ALL, "hours"),
    ("R15", "Median resolution (h)", "Median resolution (h)", "Current", ALL, "hours"),
    ("R16", "Average resolution (h)", "Average resolution (h)", "Current", ALL, "hours"),
    ("R17", "P90 resolution (h)", "P90 resolution (h)", "Current", ALL, "hours"),
    ("R18", "SLA first response met %", "SLA first response met %", "Current", ALL, "percent"),
    ("R19", "SLA resolution met %", "SLA resolution met %", "Current", ALL, "percent"),
    (
        "R20",
        "SLA resolution met %, Integrations, P1",
        "SLA resolution met %",
        "Current",
        Context(teams=frozenset({INTEGRATIONS}), priorities=frozenset({"P1"})),
        "percent",
    ),
    *(
        (
            f"R{20 + team}",
            f"SLA resolution met %, {name}",
            "SLA resolution met %",
            "Current",
            Context(teams=frozenset({team})),
            "percent",
        )
        for team, name in enumerate(TEAM_NAMES, 1)
    ),
    ("R25", "Breaches", "Breaches", "Current", ALL, "count"),
    ("R26", "Reopen rate", "Reopen rate", "Current", ALL, "percent"),
    ("R27", "CSAT average", "CSAT average", "Current", ALL, "csat"),
    ("R28", "CSAT response rate", "CSAT response rate", "Current", ALL, "percent"),
    ("R29", "Tickets per agent, 2025-09", "Tickets per agent", "Current", month(2025, 9), "decimal"),
    ("R30", "BH tests passed", "BH tests passed", "Current", ALL, "count"),
    (
        "R31",
        "Created, View as the Integrations lead",
        "Created",
        "Current",
        Context(teams=frozenset({INTEGRATIONS})),
        "count",
    ),
)


def value(model: Model, name: str, calc: str, ctx: Context) -> int | float | None:
    if name.startswith("Tickets in status:"):
        return tickets_in_status(model, name.split(":", 1)[1], calculation(ctx, calc))
    if name.startswith("Backlog in age bucket:"):
        return backlog_in_bucket(model, name.split(":", 1)[1], calculation(ctx, calc))
    return item(model, name, calc, ctx)


def reconciliation(model: Model) -> list[tuple[str, str, int | float | None, str]]:
    return [(rid, label, value(model, name, calc, ctx), kind) for rid, label, name, calc, ctx, kind in RECONCILIATION]


def display(value: int | float | None, kind: str) -> str:
    """The Python column of docs/reconciliation.md: counts whole, hours and CSAT with four decimals, percentages as
    percent with three decimals, other decimals with four."""
    if value is None:
        return "(blank)"
    if kind == "count":
        return str(int(value))
    if kind == "percent":
        return f"{value * 100:.3f} %"
    return f"{value:.4f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the reconciliation values R1 to R31 of the pandas reference.")
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args(argv)
    model = load(args.data)
    for rid, label, result, kind in reconciliation(model):
        print(f"{rid:<4} {label:<45} {display(result, kind)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
