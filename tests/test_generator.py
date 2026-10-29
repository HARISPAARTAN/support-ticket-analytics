"""The committed export: determinism, files, schemas, the status machine and every band of spec section 4.5."""

from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import make_data
import reference as ref
from bizhours import HOLIDAY_DATES, business_minutes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# the nine transitions of spec section 4.3 with their actor; the creation (None to New) is checked on its own
TRANSITIONS = {
    ("New", "Open"): "Agent",
    ("New", "Pending"): "Agent",
    ("Open", "Pending"): "Agent",
    ("Open", "Resolved"): "Agent",
    ("Pending", "Open"): "Customer",
    ("Resolved", "Reopened"): "Customer",
    ("Resolved", "Closed"): "System",
    ("Reopened", "Pending"): "Agent",
    ("Reopened", "Resolved"): "Agent",
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def simulation() -> make_data.Simulation:
    return make_data.simulate(np.random.default_rng(make_data.SEED))


# ---------------------------------------------------------------- determinism and files


def test_check_matches_a_fresh_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert make_data.main(["--check"]) == 0
    assert "matches a fresh build (19 files)" in capsys.readouterr().out


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    make_data.generate(tmp_path / "a")
    make_data.generate(tmp_path / "b")
    assert make_data.compare(tmp_path / "a", tmp_path / "b") == []


def test_files_sizes_and_encoding() -> None:
    files = sorted(p.relative_to(DATA).as_posix() for p in DATA.rglob("*") if p.is_file())
    assert files == sorted(make_data.files())
    for rel in files:
        raw = (DATA / rel).read_bytes()
        assert len(raw) <= 2_000_000, rel
        assert not raw.startswith(b"\xef\xbb\xbf"), rel
        assert b"\r" not in raw, rel
        raw.decode("utf-8")


def test_headers() -> None:
    for quarter in make_data.QUARTERS:
        with (DATA / "tickets" / f"tickets_{quarter}.csv").open(encoding="utf-8") as handle:
            assert tuple(next(csv.reader(handle))) == make_data.TICKET_COLUMNS
        with (DATA / "ticket_events" / f"ticket_events_{quarter}.csv").open(encoding="utf-8") as handle:
            assert tuple(next(csv.reader(handle))) == make_data.EVENT_COLUMNS
    for name, columns in make_data.REFERENCE_COLUMNS.items():
        with (DATA / name).open(encoding="utf-8") as handle:
            assert tuple(next(csv.reader(handle))) == columns, name


# ---------------------------------------------------------------- reference files


def test_agents_and_teams() -> None:
    agents = read_csv("agents.csv")
    assert len(agents) == 24
    assert [int(a["agent_id"]) for a in agents] == list(range(1, 25))
    per_team = pd.Series([a["team_id"] for a in agents]).value_counts().sort_index().to_dict()
    assert per_team == {"1": 8, "2": 7, "3": 4, "4": 5}
    for day in ("2024-01-01", "2025-01-31", "2025-02-01", "2025-09-30"):
        active = [a for a in agents if a["active_from"] <= day and (a["active_to"] == "" or day <= a["active_to"])]
        assert len(active) == 22, day
    assert sorted(a["active_to"] for a in agents if a["active_to"]) == ["2025-01-31", "2025-01-31"]
    assert sorted(a["active_from"] for a in agents if a["active_from"] >= "2024") == ["2025-02-01", "2025-02-01"]
    leads = {a["team_id"]: a["agent_id"] for a in agents if a["role"] == "Team lead"}
    assert len(leads) == 4 and all(a["active_to"] == "" for a in agents if a["role"] == "Team lead")
    teams = read_csv("teams.csv")
    assert [(t["team_id"], t["team_name"], t["lead_agent_id"]) for t in teams] == [
        ("1", "Service Desk", leads["1"]),
        ("2", "Technical Support", leads["2"]),
        ("3", "Billing & Accounts", leads["3"]),
        ("4", "Integrations", leads["4"]),
    ]


def test_emails_are_unique_ascii_and_use_the_reserved_domain() -> None:
    emails = [a["email"] for a in read_csv("agents.csv")]
    assert len(set(emails)) == 24
    for email in emails:
        assert re.fullmatch(r"[a-z0-9]+\.[a-z0-9]+@quillstack\.example", email), email


def test_priorities() -> None:
    rows = [tuple(r.values()) for r in read_csv("priorities.csv")]
    assert rows == [tuple(str(v) for v in p) for p in make_data.PRIORITIES]


def test_no_phone_numbers_or_street_addresses() -> None:
    phone = re.compile(r"\+\d{2}|\(\d{2,4}\)|\b\d{3,4}[ /-]\d{4,}\b")
    street = re.compile(r"(?i)\b(rua|avenida|street|road|avenue|rue|calle|strasse|straße|platz|via)\b")
    for path in DATA.rglob("*.csv"):
        text = path.read_text(encoding="utf-8")
        assert not phone.search(text), path.name
        assert not street.search(text), path.name


# ---------------------------------------------------------------- tickets and events


def test_ticket_ids_creation_order_and_quarters(model: ref.Model) -> None:
    t = model.tickets.sort_values("ticket_id")
    assert t["ticket_id"].tolist() == list(range(100001, 100001 + len(t)))
    assert t["created_at"].is_monotonic_increasing
    assert t["created_at"].min() >= pd.Timestamp(make_data.FIRST_CREATED)
    assert t["created_at"].max() <= pd.Timestamp(make_data.LAST_CREATED)
    for quarter in make_data.QUARTERS:
        rows = read_csv(f"tickets/tickets_{quarter}.csv")
        assert {make_data.quarter(datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M")) for r in rows} == {quarter}


def test_value_sets(model: ref.Model) -> None:
    t = model.tickets
    assert set(t["channel"]) == set(make_data.CHANNELS)
    assert set(t["category"]) == set(make_data.CATEGORIES)
    assert set(t["priority"]) == {"P1", "P2", "P3", "P4"}
    assert set(t["customer_tier"]) == set(make_data.TIERS)
    assert t["customer_id"].str.fullmatch(r"C0[0-6]\d\d").all() and t["customer_id"].nunique() <= 600
    assert (t["customer_name"] == "Account " + t["customer_id"]).all()
    assert t.groupby("customer_id")["customer_tier"].nunique().max() == 1
    assert set(t["team_id"]) == {1, 2, 3, 4}
    assert t["csat_score"].dropna().between(1, 5).all()
    subjects = {s.format(module=m) for group in make_data.SUBJECTS for s in group for m in make_data.MODULES}
    assert set(t["subject"]) <= subjects
    assert sum(len(group) for group in make_data.SUBJECTS) == 48


def test_status_machine(model: ref.Model) -> None:
    e = model.events
    assert e["event_id"].tolist() == list(range(1, len(e) + 1))
    first = e.groupby("ticket_id").head(1)
    assert (first["event_seq"] == 1).all() and (first["to_status"] == "New").all()
    assert (e.groupby("ticket_id")["event_seq"].diff().dropna() == 1).all()
    later = e[e["event_seq"] > 1]
    assert later["from_status"].notna().all() and (later["to_status"] != "New").all()
    actors = {(a, b): set(g) for (a, b), g in later.groupby(["from_status", "to_status"])["actor"]}
    assert set(actors) <= set(TRANSITIONS)
    assert all(found == {TRANSITIONS[pair]} for pair, found in actors.items()), actors
    assert e.loc[e["event_seq"] == 1, "from_status"].isna().all()
    assert (e.groupby("ticket_id")["event_at"].diff().dropna() >= pd.Timedelta(0)).all()
    assert e["event_at"].max() <= pd.Timestamp(make_data.AS_OF)
    assert (e["agent_id"].notna() == (e["actor"] == "Agent")).all()  # an agent id exactly for agent events
    channel = e["ticket_id"].map(model.tickets["channel"])
    new = e["to_status"] == "New"
    assert ((e.loc[new, "actor"] == "Agent") == (channel[new] == "Phone")).all()


def test_reopen_and_closure_timing(model: ref.Model) -> None:
    e = model.events
    previous = e.groupby("ticket_id")["event_at"].shift(1)
    reopened = e["to_status"] == "Reopened"
    assert ((e["event_at"] - previous)[reopened] < pd.Timedelta(days=7)).all()
    closed = e["to_status"] == "Closed"
    assert ((e["event_at"] - previous)[closed] == pd.Timedelta(days=7)).all()
    assert e.loc[closed, "next_event_at"].isna().all()  # terminal


def test_agent_events_fall_in_business_hours(model: ref.Model) -> None:
    agent = model.events[(model.events["actor"] == "Agent") & (model.events["event_seq"] > 1)]
    stamps = agent["event_at"]
    assert (stamps.dt.day_of_week < 5).all()
    assert not stamps.dt.date.isin(HOLIDAY_DATES).any()
    minutes = stamps.dt.hour * 60 + stamps.dt.minute
    assert minutes.between(8 * 60, 18 * 60).all()


def test_ticket_columns_equal_the_events(model: ref.Model) -> None:
    t, e = model.tickets, model.events
    last = e.groupby("ticket_id").tail(1).set_index("ticket_id")
    assert (t["status"] == last["to_status"].reindex(t.index)).all()
    second = e[e["event_seq"] == 2].set_index("ticket_id")
    assert t["first_response_at"].reindex(second.index).eq(second["event_at"]).all()
    assert t.loc[~t.index.isin(second.index), "first_response_at"].isna().all()
    assert (t["agent_id"].reindex(second.index) == second["agent_id"].astype(int)).all()
    assert (t.loc[~t.index.isin(second.index), "agent_id"] == 0).all()
    final = e[e["to_status"] == "Resolved"].groupby("ticket_id")["event_at"].max()
    resolved = t[t["is_resolved"]]
    assert resolved["resolved_at"].eq(final.reindex(resolved.index)).all()
    assert t.loc[~t["is_resolved"], "resolved_at"].isna().all()
    closed = e[e["to_status"] == "Closed"].set_index("ticket_id")["event_at"]
    assert t["closed_at"].reindex(closed.index).eq(closed).all()
    assert t["closed_at"].notna().sum() == len(closed)
    reopens = e[e["to_status"] == "Reopened"].groupby("ticket_id").size()
    assert t["reopen_count"].eq(reopens.reindex(t.index, fill_value=0)).all()
    assert t.loc[t["csat_score"].notna(), "is_resolved"].all()


def test_assignment_respects_team_and_active_period(model: ref.Model) -> None:
    agents = model.agents.set_index("agent_id")
    t = model.tickets[model.tickets["agent_id"] > 0]
    assert (t["agent_id"].map(agents["team_id"]) == t["team_id"]).all()
    day = t["first_response_at"].dt.strftime("%Y-%m-%d")
    assert (day >= t["agent_id"].map(agents["active_from"])).all()
    active_to = t["agent_id"].map(agents["active_to"]).replace("", "9999-12-31")
    assert (day <= active_to).all()


def test_recomputed_minutes_equal_the_drawn_durations(model: ref.Model, simulation: make_data.Simulation) -> None:
    drawn = pd.DataFrame(
        {"fr": [s.fr_minutes for s in simulation.tickets], "clock": [s.clock_minutes for s in simulation.tickets]},
        index=[s.ticket_id for s in simulation.tickets],
    )
    t = model.tickets
    answered = t["first_response_bmin"].notna()
    assert (t.loc[answered, "first_response_bmin"] == drawn.loc[t.index[answered], "fr"]).all()
    done = t["status"] == "Closed"
    assert (t.loc[done, "clock_bmin"] == drawn.loc[t.index[done], "clock"]).all()
    assert (t["clock_bmin"] <= drawn.loc[t.index, "clock"].where(t["status"] != "New", t["clock_bmin"])).all()


def test_leave_rules(simulation: make_data.Simulation) -> None:
    by_team: dict[int, list[set[date]]] = {}
    for agent in simulation.agents:
        by_team.setdefault(agent.team_id, []).append(agent.leave)
        assert all(agent.active(day) for day in agent.leave)
        if agent.active_to is None and agent.active_from < date(2024, 1, 1):
            assert len(agent.leave) == 2 * sum(make_data.LEAVE_BLOCKS)
    for leaves in by_team.values():
        days = [day for leave in leaves for day in leave]
        assert len(days) == len(set(days))  # at most one agent of a team away on any day


def test_business_minutes_of_the_new_interval(model: ref.Model) -> None:
    sample = model.tickets[model.tickets["first_response_at"].notna()].sample(300, random_state=1)
    for row in sample.itertuples():
        start, end = row.created_at.to_pydatetime(), row.first_response_at.to_pydatetime()
        assert row.first_response_bmin == business_minutes(start, end, HOLIDAY_DATES)


# ---------------------------------------------------------------- bands (spec 4.5)


def test_band_volumes(model: ref.Model) -> None:
    assert 24_000 <= len(model.tickets) <= 26_000
    assert 110_000 <= len(model.events) <= 135_000


def test_band_sla(model: ref.Model) -> None:
    assert 0.85 <= ref.measure(model, "SLA first response met %") <= 0.95
    assert 0.85 <= ref.measure(model, "SLA resolution met %") <= 0.95
    p1 = ref.ALL.where(priorities={"P1"})
    integrations = ref.measure(model, "SLA resolution met %", p1.where(teams={4}))
    assert 0.55 <= integrations <= 0.78
    for team in (1, 2, 3):
        other = ref.measure(model, "SLA resolution met %", p1.where(teams={team}))
        assert other >= 0.80 and other - integrations >= 0.12, team


def test_band_csat(model: ref.Model) -> None:
    assert 0.35 <= ref.measure(model, "CSAT response rate") <= 0.45
    assert 3.9 <= ref.measure(model, "CSAT average") <= 4.4


def test_outage_days_stand_out(model: ref.Model) -> None:
    t = model.tickets
    bugs = t[t["category"] == "Bug"].groupby("created_date").size()
    tuesdays = bugs[bugs.index.day_of_week == 1]
    for day in make_data.OUTAGES:
        assert bugs[pd.Timestamp(day)] > 2 * tuesdays.median(), day


def test_invoice_run_raises_billing(model: ref.Model) -> None:
    t = model.tickets
    invoice = t["created_date"].dt.date.isin(make_data.first_business_days())
    share = t.groupby(invoice)["category"].apply(lambda c: (c == "Billing").mean())
    assert share[True] > 1.4 * share[False]


def test_as_of_is_one_minute_after_the_last_creation() -> None:
    assert make_data.AS_OF - make_data.LAST_CREATED == timedelta(minutes=1)
    assert make_data.AS_OF == ref.AS_OF
