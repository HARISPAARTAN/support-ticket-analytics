"""Generate the Quillstack Software help-desk export: tickets and status events per creation quarter, the agents, teams,
priorities, holidays and the business-hours test cases.

Usage (from the repository root):
    uv run python tools/make_data.py [--out data] [--check]

Seed 20240101 drives numpy.random.default_rng for every number; NAME_SEED drives Faker for the 24 agent names and
e-mail addresses only, so a change of NAME_SEED never changes a number (docs/data-model.md, "Generator tuning").
Every lifecycle is simulated to its end; events after the as-of moment 2025-09-30 18:00 are then dropped and the ticket
columns are derived from the events that remain. Agent events are placed with bizhours.add_business_minutes, so the
business minutes recomputed from the timestamps equal the drawn durations. --check regenerates into a temporary folder
and compares every file byte for byte; it exits 1 if any file differs.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from faker import Faker

from bizhours import CASES, HOLIDAY_DATES, HOLIDAYS, add_business_minutes, is_business_day

ROOT = Path(__file__).resolve().parents[1]
SEED = 20240101
NAME_SEED = 20240101  # raised only if a generated person name collides with the owner's never-committed banned list
FIRST_CREATED = datetime(2024, 1, 1, 0, 0)
LAST_CREATED = datetime(2025, 9, 30, 17, 59)
AS_OF = datetime(2025, 9, 30, 18, 0)
EXPECTED_TICKETS = 25_000
DOMAIN = "quillstack.example"
FORMAT = "%Y-%m-%d %H:%M"
QUARTERS = ("2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3")

# ---------------------------------------------------------------- reference data

TEAMS = ((1, "Service Desk"), (2, "Technical Support"), (3, "Billing & Accounts"), (4, "Integrations"))
INTEGRATIONS = 4
# one row per agent in agent_id order: team, role, and whether the agent leaves on 2025-01-31 or joins on 2025-02-01
AGENT_PLAN = (
    *((1, "Team lead", ""), *[(1, "Agent", "")] * 5, (1, "Agent", "leaver"), (1, "Agent", "joiner")),
    *((2, "Team lead", ""), *[(2, "Agent", "")] * 4, (2, "Agent", "leaver"), (2, "Agent", "joiner")),
    *((3, "Team lead", ""), *[(3, "Agent", "")] * 3),
    *((4, "Team lead", ""), *[(4, "Agent", "")] * 4),
)
LEAVE_DAY = date(2025, 1, 31)
JOIN_DAY = date(2025, 2, 1)
NAME_LOCALES = ("pt_PT", "es_ES", "pt_PT", "en_GB", "pt_PT", "fr_FR")  # cycled over the agents
# priority, name, sort order, first-response and resolution targets in business minutes and as labels
PRIORITIES = (
    ("P1", "Urgent", 1, 60, 240, "1 h", "4 h"),
    ("P2", "High", 2, 240, 600, "4 h", "1 d"),
    ("P3", "Normal", 3, 480, 1800, "8 h", "3 d"),
    ("P4", "Low", 4, 1440, 3000, "24 h", "5 d"),
)
FR_TARGET = np.array([p[3] for p in PRIORITIES])
RES_TARGET = np.array([p[4] for p in PRIORITIES])
CHANNELS = ("E-mail", "Portal", "Chat", "Phone")
CHANNEL_IN_HOURS = (0.36, 0.30, 0.22, 0.12)
CHANNEL_OFF_HOURS = (0.55, 0.45, 0.0, 0.0)
CATEGORIES = ("Bug", "How-to", "Billing", "Feature request", "Access", "Integration")
BUG, HOW_TO, BILLING, FEATURE, ACCESS, INTEGRATION = range(6)
CATEGORY_SHARE = (0.22, 0.30, 0.12, 0.10, 0.14, 0.12)
INVOICE_RUN_BILLING = 1.8  # Billing weight on the first three business days of a month
TIERS = ("Enterprise", "Business", "Starter")
TIER_ACCOUNTS = (60, 220, 320)
TIER_SHARE = (0.35, 0.40, 0.25)
ACCOUNT_EXPONENT = -0.8
# P1 / P2 / P3 / P4 share per category
PRIORITY_MIX = (
    (0.08, 0.27, 0.45, 0.20),
    (0.00, 0.06, 0.44, 0.50),
    (0.00, 0.10, 0.50, 0.40),
    (0.00, 0.00, 0.20, 0.80),
    (0.03, 0.20, 0.52, 0.25),
    (0.06, 0.24, 0.50, 0.20),
)
ENTERPRISE_BUMP = 0.15  # Enterprise tickets in Bug, Integration and Access move up one priority level
BUMP_CATEGORIES = (BUG, INTEGRATION, ACCESS)
# team routing per category: (team, share)
ROUTING = (
    ((2, 0.90), (4, 0.10)),
    ((1, 0.85), (2, 0.15)),
    ((3, 1.00),),
    ((1, 0.60), (2, 0.40)),
    ((1, 0.70), (3, 0.30)),
    ((4, 0.90), (2, 0.10)),
)
MODULES = ("Editor", "Templates", "Workflows", "Approvals", "Reports", "Admin console", "API", "Mobile app")
SUBJECTS = (
    (
        "{module} crashes when saving a document",
        "Error message in {module} after the latest update",
        "{module} does not load for some users",
        "Changes in {module} are lost after a refresh",
        "{module} shows the wrong date format",
        "Export from {module} produces an empty file",
        "{module} is very slow since this morning",
        "Buttons in {module} do not respond",
    ),
    (
        "How do I share a document from {module}?",
        "How can I change the default settings in {module}?",
        "Where do I find the history of changes in {module}?",
        "How do I add a new user to {module}?",
        "Can {module} send a reminder automatically?",
        "How do I copy a setup from one team to another in {module}?",
        "How do I filter the list view in {module}?",
        "What is the best way to organise folders in {module}?",
    ),
    (
        "Question about the latest invoice for {module} seats",
        "Invoice shows the wrong number of {module} licences",
        "Change the billing contact for {module}",
        "Request a credit note for unused {module} seats",
        "Payment failed for the {module} add-on",
        "VAT number missing on the invoice for {module}",
        "Switch {module} billing from monthly to yearly",
        "Duplicate charge for {module}",
    ),
    (
        "Please add a dark mode to {module}",
        "Bulk edit in {module}",
        "Custom fields in {module}",
        "Keyboard shortcuts for {module}",
        "More export formats in {module}",
        "Scheduled e-mail digests from {module}",
        "Comment threads in {module}",
        "Audit log filter in {module}",
    ),
    (
        "Cannot sign in to {module}",
        "Password reset link for {module} expired",
        "User locked out of {module}",
        "Two-step verification problem in {module}",
        "Request admin rights for {module}",
        "Former employee still has access to {module}",
        "Single sign-on fails for {module}",
        "Permission denied when opening {module}",
    ),
    (
        "Webhook from {module} not delivered",
        "API token for {module} rejected",
        "Sync between {module} and the CRM stopped",
        "Data import into {module} fails halfway",
        "Calendar sync with {module} shows duplicates",
        "Rate limit reached when calling {module}",
        "Connector for {module} returns a timeout",
        "Field mapping for {module} is wrong after the update",
    ),
)

# ---------------------------------------------------------------- arrival model

WEEKDAY_WEIGHT = (1.25, 1.15, 1.05, 1.00, 0.85, 0.12, 0.08)
HOUR_WEIGHT = (
    0.10, 0.08, 0.06, 0.06, 0.08, 0.12, 0.25, 0.55, 1.30, 1.75, 1.85, 1.70,
    1.20, 1.25, 1.60, 1.50, 1.30, 1.00, 0.60, 0.40, 0.30, 0.25, 0.20, 0.15,
)  # fmt: skip
GROWTH_END = 1.25  # linear from 1.00 in January 2024 to this in September 2025
AUGUST = 0.85
LATE_DECEMBER = 0.80  # 20 to 31 December
HOLIDAY_ARRIVALS = 0.20
OUTAGES = (date(2024, 11, 12), date(2025, 6, 3))
OUTAGE_HOURS = range(10, 16)  # Bug arrivals x 4 from 10:00 to 16:00
OUTAGE_BUG_FACTOR = 4.0
OUTAGE_P1_FACTOR = 3.0
OUTAGE_FR_FACTOR = 1.5

# ---------------------------------------------------------------- work model (spec section 4.5; tuning knobs marked)

FR_SIGMA = 0.8
FR_DIVISOR = 3.1  # tuning knob: median first response = target / FR_DIVISOR
FR_INTEGRATIONS_P1 = 1.8  # tuning knob
FR_AUGUST = 1.2
FR_CAP = 12_000
RES_SIGMA = 0.9
RES_DIVISOR_P1 = 3.6  # tuning knob: median resolution clock = target / divisor
RES_DIVISOR = 2.9  # tuning knob, P2 to P4
RES_INTEGRATIONS_P1 = 2.2  # tuning knob
RES_CATEGORY = (1.25, 0.75, 0.9, 0.8, 0.6, 1.2)  # P2 to P4 only
RES_MIN_AFTER_FR = 15
RES_CAP = 36_000
SPEED_SIGMA = 0.15
CSAT_OFFSET_SIGMA = 0.2
PENDING_SHARE = (0.45, 0.25, 0.40, 0.10, 0.30, 0.50)
SECOND_PENDING = 0.20
STRAIGHT_TO_PENDING = 5  # the first response goes straight to Pending when its segment ends within this many minutes
REPLY_MEDIAN_H, REPLY_SIGMA, REPLY_MIN_H, REPLY_MAX_H = 20.0, 1.0, 1.0, 240.0
REOPEN_SHARE = (0.09, 0.04, 0.05, 0.02, 0.03, 0.08)
REOPEN_BREACHED = 1.5
SECOND_REOPEN = 0.15
REOPEN_MIN, REOPEN_MAX = 2 * 60, 160 * 60  # calendar minutes after Resolved
REOPEN_WORK_P1, REOPEN_WORK, REOPEN_SIGMA = 45.0, 120.0, 0.8
CLOSE_AFTER = timedelta(days=7)
CSAT_RESPONSE = 0.40
CSAT_MIN, CSAT_MAX = 60, 72 * 60  # minutes after the final resolution
CSAT_BASE, CSAT_BREACH, CSAT_REOPEN, CSAT_SIGMA = 4.2, 0.9, 0.6, 0.9
LEAVE_BLOCKS = (5, 5, 5, 5, 2)  # business days per block, per agent and year
LEAD_WEIGHT, NEW_WEIGHT, NEW_DAYS = 0.6, 0.5, 40

TICKET_COLUMNS = (
    "ticket_id",
    "created_at",
    "channel",
    "category",
    "priority",
    "customer_id",
    "customer_name",
    "customer_tier",
    "team_id",
    "agent_id",
    "subject",
    "status",
    "first_response_at",
    "resolved_at",
    "closed_at",
    "reopen_count",
    "csat_score",
)
EVENT_COLUMNS = ("event_id", "ticket_id", "event_seq", "event_at", "from_status", "to_status", "actor", "agent_id")
AGENT_COLUMNS = ("agent_id", "agent_name", "email", "team_id", "role", "active_from", "active_to")
REFERENCE_COLUMNS = {
    "agents.csv": AGENT_COLUMNS,
    "teams.csv": ("team_id", "team_name", "lead_agent_id"),
    "priorities.csv": (
        "priority",
        "priority_name",
        "sort_order",
        "fr_target_bmin",
        "res_target_bmin",
        "fr_target_label",
        "res_target_label",
    ),
    "holidays.csv": ("date", "name", "scope"),
    "business_hours_cases.csv": ("case_id", "start", "end", "expected_minutes", "note"),
}


def files() -> list[str]:
    """Every file the generator writes, relative to the output folder, in a fixed order."""
    out = [f"tickets/tickets_{q}.csv" for q in QUARTERS] + [f"ticket_events/ticket_events_{q}.csv" for q in QUARTERS]
    return out + list(REFERENCE_COLUMNS)


def stamp(moment: datetime | None) -> str:
    return moment.strftime(FORMAT) if moment is not None else ""


def quarter(moment: datetime) -> str:
    return f"{moment.year}-Q{(moment.month - 1) // 3 + 1}"


def half_up(value: float) -> int:
    return math.floor(value + 0.5)


FOLD = (("ß", "ss"), ("Æ", "Ae"), ("æ", "ae"), ("Ø", "O"), ("ø", "o"), ("Ł", "L"), ("ł", "l"))


def ascii_fold(text: str) -> str:
    for source, target in FOLD:
        text = text.replace(source, target)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def email_for(first: str, last: str) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "", ascii_fold(part).lower()) for part in (first, last)]
    return f"{parts[0]}.{parts[1]}@{DOMAIN}"


def business_days(first: date, last: date) -> list[date]:
    out, day = [], first
    while day <= last:
        if is_business_day(day, HOLIDAY_DATES):
            out.append(day)
        day += timedelta(days=1)
    return out


# ---------------------------------------------------------------- agents and leave


@dataclass
class Agent:
    agent_id: int
    team_id: int
    role: str
    active_from: date
    active_to: date | None
    speed: float
    csat_offset: float
    name: str = ""
    email: str = ""
    leave: set[date] = field(default_factory=set)
    ramp_end: date | None = None  # the last day of the first NEW_DAYS business days

    def active(self, day: date) -> bool:
        return self.active_from <= day and (self.active_to is None or day <= self.active_to)

    def weight(self, day: date) -> float:
        if self.role == "Team lead":
            return LEAD_WEIGHT
        if self.ramp_end is not None and day <= self.ramp_end:
            return NEW_WEIGHT
        return 1.0


def agent_names(count: int) -> list[tuple[str, str]]:
    """(name, e-mail) for each agent, from Faker seeded with NAME_SEED; e-mail addresses are unique."""
    Faker.seed(NAME_SEED)
    fakers = {locale: Faker(locale) for locale in sorted(set(NAME_LOCALES))}
    used: set[str] = set()
    out = []
    for index in range(count):
        fake = fakers[NAME_LOCALES[index % len(NAME_LOCALES)]]
        while True:
            first, last = fake.first_name(), fake.last_name()
            email = email_for(first, last)
            if email not in used:
                used.add(email)
                out.append((f"{first} {last}", email))
                break
    return out


def build_agents(rng: np.random.Generator) -> list[Agent]:
    hired = rng.integers(0, (date(2023, 9, 30) - date(2017, 1, 2)).days + 1, size=len(AGENT_PLAN))
    speed = rng.lognormal(0.0, SPEED_SIGMA, size=len(AGENT_PLAN))
    offset = rng.normal(0.0, CSAT_OFFSET_SIGMA, size=len(AGENT_PLAN))
    agents = []
    for index, (team, role, kind) in enumerate(AGENT_PLAN):
        start = JOIN_DAY if kind == "joiner" else date(2017, 1, 2) + timedelta(days=int(hired[index]))
        agent = Agent(
            index + 1,
            team,
            role,
            start,
            LEAVE_DAY if kind == "leaver" else None,
            float(speed[index]),
            float(offset[index]),
        )
        if kind == "joiner":
            agent.ramp_end = business_days(JOIN_DAY, JOIN_DAY + timedelta(days=120))[NEW_DAYS - 1]
        agents.append(agent)
    for agent, (name, email) in zip(agents, agent_names(len(agents)), strict=True):
        agent.name, agent.email = name, email
    place_leave(rng, agents)
    return agents


def place_leave(rng: np.random.Generator, agents: list[Agent]) -> None:
    """Per agent and year four blocks of five business days and one of two (fewer for an agent active only part of
    the year, in proportion), inside the active period, with at most one agent of a team on leave on any day."""
    for year in (2024, 2025):
        days = business_days(date(year, 1, 1), date(year, 12, 31))
        for team, _ in TEAMS:
            taken: set[date] = set()
            for agent in (a for a in agents if a.team_id == team):
                usable = [d for d in days if agent.active(d)]
                blocks = LEAVE_BLOCKS[: half_up(len(LEAVE_BLOCKS) * len(usable) / len(days))]
                for length in blocks:
                    for _attempt in range(1000):
                        first = int(rng.integers(0, len(usable) - length + 1))
                        block = usable[first : first + length]
                        if not taken.intersection(block):
                            taken.update(block)
                            agent.leave.update(block)
                            break
                    else:
                        raise RuntimeError(f"no free leave block for agent {agent.agent_id} in {year}")


def pick_agent(agents: list[Agent], team: int, day: date, u: float) -> Agent:
    """The agent who takes the ticket at its first response: weighted by role and ramp-up among the team's agents who
    are active and not on leave that day."""
    pool = [a for a in agents if a.team_id == team and a.active(day) and day not in a.leave]
    weights = np.array([a.weight(day) for a in pool])
    cumulative = np.cumsum(weights) / weights.sum()
    return pool[min(int(np.searchsorted(cumulative, u, side="right")), len(pool) - 1)]


# ---------------------------------------------------------------- arrivals


def hour_weights() -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    """Relative arrival weight per hour of the period and the extra Bug weight of the outage hours."""
    hours, moment = [], FIRST_CREATED
    while moment <= LAST_CREATED:
        hours.append(moment)
        moment += timedelta(hours=1)
    first_month = FIRST_CREATED.year * 12 + FIRST_CREATED.month
    months = LAST_CREATED.year * 12 + LAST_CREATED.month - first_month
    weight = np.empty(len(hours))
    extra = np.zeros(len(hours))
    for i, h in enumerate(hours):
        growth = 1.0 + (GROWTH_END - 1.0) * (h.year * 12 + h.month - first_month) / months
        season = AUGUST if h.month == 8 else LATE_DECEMBER if (h.month == 12 and h.day >= 20) else 1.0
        holiday = HOLIDAY_ARRIVALS if h.date() in HOLIDAY_DATES else 1.0
        weight[i] = WEEKDAY_WEIGHT[h.weekday()] * HOUR_WEIGHT[h.hour] * growth * season * holiday
        if h.date() in OUTAGES and h.hour in OUTAGE_HOURS:
            extra[i] = weight[i] * CATEGORY_SHARE[BUG] * (OUTAGE_BUG_FACTOR - 1.0)
    return weight, extra, hours


def arrivals(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Creation minute (since FIRST_CREATED) of every ticket in creation order, and whether it is an outage Bug."""
    weight, extra, _ = hour_weights()
    base = EXPECTED_TICKETS / (weight.sum() + extra.sum())
    normal = rng.poisson(base * weight)
    bugs = rng.poisson(base * extra)
    hour_index = np.arange(len(weight))
    hour_of = np.concatenate([np.repeat(hour_index, normal), np.repeat(hour_index, bugs)])
    forced = np.concatenate([np.zeros(normal.sum(), dtype=bool), np.ones(bugs.sum(), dtype=bool)])
    minute = hour_of * 60 + rng.integers(0, 60, size=hour_of.size)
    order = np.argsort(minute, kind="stable")
    return minute[order], forced[order]


def first_business_days(count: int = 3) -> set[date]:
    """The first `count` business days of every month of the period (the invoice run)."""
    out: set[date] = set()
    year, month = FIRST_CREATED.year, FIRST_CREATED.month
    while (year, month) <= (LAST_CREATED.year, LAST_CREATED.month):
        last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
        out.update(business_days(date(year, month, 1), last)[:count])
        year, month = year + (month == 12), month % 12 + 1
    return out


def choose(u: float, shares) -> int:
    cumulative = np.cumsum(shares) / np.sum(shares)
    return min(int(np.searchsorted(cumulative, u, side="right")), len(cumulative) - 1)


# ---------------------------------------------------------------- simulation


@dataclass
class Event:
    at: datetime
    from_status: str | None
    to_status: str
    actor: str
    agent_id: int | None


@dataclass
class Ticket:
    ticket_id: int
    created: datetime
    channel: int
    category: int
    priority: int
    customer: int  # 1 to 600
    tier: int
    team: int
    subject: str
    agent_id: int
    fr_minutes: int  # drawn first response in business minutes
    clock_minutes: int  # drawn resolution clock including reopen work
    events: list[Event]
    csat: int | None
    csat_at: datetime | None


@dataclass
class Simulation:
    agents: list[Agent]
    customers: list[tuple[str, int]]  # (customer id, tier) by customer number - 1
    tickets: list[Ticket]


def build_customers(rng: np.random.Generator) -> tuple[list[tuple[str, int]], list[np.ndarray]]:
    """600 accounts with a tier each (tiers spread over the ids at random) and, per tier, the account numbers in rank
    order with the weight rank ** ACCOUNT_EXPONENT."""
    tiers = np.repeat(np.arange(len(TIERS)), TIER_ACCOUNTS)[rng.permutation(sum(TIER_ACCOUNTS))]
    customers = [(f"C{n + 1:04d}", int(t)) for n, t in enumerate(tiers)]
    members = [np.flatnonzero(tiers == t) + 1 for t in range(len(TIERS))]
    return customers, members


@dataclass
class Draws:
    """Every random number of the tickets, drawn at once in this order whether a ticket needs it or not, so that one
    ticket's path never shifts the numbers of the next."""

    u_channel: np.ndarray
    u_category: np.ndarray
    u_tier: np.ndarray
    u_account: np.ndarray
    u_priority: np.ndarray
    u_bump: np.ndarray
    u_team: np.ndarray
    template: np.ndarray
    module: np.ndarray
    z_fr: np.ndarray
    z_res: np.ndarray
    u_agent: np.ndarray
    u_pending: np.ndarray  # (n, 2)
    gamma: np.ndarray  # (n, 3): the work segments
    z_reply: np.ndarray  # (n, 2)
    u_reopen: np.ndarray  # (n, 2)
    reopen_delay: np.ndarray  # (n, 2)
    z_reopen: np.ndarray  # (n, 2)
    u_csat: np.ndarray
    csat_delay: np.ndarray
    z_csat: np.ndarray

    @classmethod
    def take(cls, rng: np.random.Generator, n: int) -> Draws:
        u_channel, u_category, u_tier, u_account, u_priority, u_bump, u_team = rng.random((7, n))
        template = rng.integers(0, 8, size=n)
        module = rng.integers(0, len(MODULES), size=n)
        z_fr, z_res = rng.standard_normal((2, n))
        return cls(
            u_channel,
            u_category,
            u_tier,
            u_account,
            u_priority,
            u_bump,
            u_team,
            template,
            module,
            z_fr,
            z_res,
            rng.random(n),
            rng.random((n, 2)),
            rng.gamma(2.0, size=(n, 3)),
            rng.standard_normal((n, 2)),
            rng.random((n, 2)),
            rng.integers(REOPEN_MIN, REOPEN_MAX + 1, size=(n, 2)),
            rng.standard_normal((n, 2)),
            rng.random(n),
            rng.integers(CSAT_MIN, CSAT_MAX + 1, size=n),
            rng.standard_normal(n),
        )


def simulate(rng: np.random.Generator) -> Simulation:
    agents = build_agents(rng)
    customers, members = build_customers(rng)
    minutes, forced = arrivals(rng)
    n = minutes.size
    draws = Draws.take(rng, n)
    invoice_days = first_business_days()
    weights = [np.arange(1, len(m) + 1, dtype=float) ** ACCOUNT_EXPONENT for m in members]
    tickets = []
    for i in range(n):
        created = FIRST_CREATED + timedelta(minutes=int(minutes[i]))
        day = created.date()
        in_hours = is_business_day(day, HOLIDAY_DATES) and 8 <= created.hour < 18
        channel = choose(draws.u_channel[i], CHANNEL_IN_HOURS if in_hours else CHANNEL_OFF_HOURS)
        if forced[i]:
            category = BUG
        else:
            shares = list(CATEGORY_SHARE)
            if day in invoice_days:
                shares[BILLING] *= INVOICE_RUN_BILLING
            category = choose(draws.u_category[i], shares)
        tier = choose(draws.u_tier[i], TIER_SHARE)
        customer = int(members[tier][choose(draws.u_account[i], weights[tier])])
        mix = list(PRIORITY_MIX[category])
        if category == BUG and day in OUTAGES:
            mix[0] *= OUTAGE_P1_FACTOR
        priority = choose(draws.u_priority[i], mix)
        if tier == 0 and category in BUMP_CATEGORIES and priority > 0 and draws.u_bump[i] < ENTERPRISE_BUMP:
            priority -= 1
        teams = ROUTING[category]
        team = teams[choose(draws.u_team[i], [share for _, share in teams])][0]
        subject = SUBJECTS[category][int(draws.template[i])].format(module=MODULES[int(draws.module[i])])
        tickets.append(lifecycle(i, created, channel, category, priority, customer, tier, team, subject, agents, draws))
    return Simulation(agents, customers, tickets)


def split(total: int, parts: np.ndarray) -> list[int]:
    """`total` minutes split in the proportions of `parts`, as whole minutes that add up to `total`."""
    edges = [half_up(total * c) for c in np.cumsum(parts) / parts.sum()]
    edges[-1] = total
    return [b - a for a, b in zip([0, *edges[:-1]], edges, strict=True)]


def lifecycle(
    i: int,
    created: datetime,
    channel: int,
    category: int,
    priority: int,
    customer: int,
    tier: int,
    team: int,
    subject: str,
    agents: list[Agent],
    d: Draws,
) -> Ticket:
    """One ticket's events from creation to closure (nothing is cut here) and its CSAT answer."""
    h = HOLIDAY_DATES
    day = created.date()
    integrations_p1 = team == INTEGRATIONS and priority == 0
    fr_median = FR_TARGET[priority] / FR_DIVISOR
    fr_median *= FR_INTEGRATIONS_P1 if integrations_p1 else 1.0
    fr_median *= FR_AUGUST if created.month == 8 else 1.0
    fr_median *= OUTAGE_FR_FACTOR if day in OUTAGES else 1.0
    fr = max(1, min(FR_CAP, half_up(fr_median * math.exp(FR_SIGMA * d.z_fr[i]))))
    fr_at = add_business_minutes(created, fr, h)
    agent = pick_agent(agents, team, fr_at.date(), d.u_agent[i])
    if priority == 0:
        res_median = RES_TARGET[0] / RES_DIVISOR_P1
    else:
        res_median = RES_TARGET[priority] / RES_DIVISOR * RES_CATEGORY[category]
    res_median *= RES_INTEGRATIONS_P1 if integrations_p1 else 1.0
    clock = half_up(res_median * math.exp(RES_SIGMA * d.z_res[i]) * agent.speed)
    clock = min(RES_CAP, max(fr + RES_MIN_AFTER_FR, clock))

    phone = CHANNELS[channel] == "Phone"
    events = [Event(created, None, "New", "Agent" if phone else "Customer", agent.agent_id if phone else None)]

    def add(at: datetime, to_status: str, actor: str) -> None:
        events.append(Event(at, events[-1].to_status, to_status, actor, agent.agent_id if actor == "Agent" else None))

    cycles = 0
    if d.u_pending[i, 0] < PENDING_SHARE[category]:
        cycles = 2 if d.u_pending[i, 1] < SECOND_PENDING else 1
    segments = split(clock - fr, d.gamma[i, : cycles + 1])
    straight = cycles >= 1 and segments[0] <= STRAIGHT_TO_PENDING
    if straight:
        segments[1] += segments[0]
        add(fr_at, "Pending", "Agent")
        moment = fr_at
    else:
        add(fr_at, "Open", "Agent")
        moment = add_business_minutes(fr_at, segments[0], h)
        add(moment, "Pending" if cycles else "Resolved", "Agent")
    for j in range(1, cycles + 1):
        hours = min(REPLY_MAX_H, max(REPLY_MIN_H, REPLY_MEDIAN_H * math.exp(REPLY_SIGMA * d.z_reply[i, j - 1])))
        reply = moment + timedelta(minutes=half_up(hours * 60))
        add(reply, "Open", "Customer")
        moment = add_business_minutes(reply, segments[j], h)
        add(moment, "Pending" if j < cycles else "Resolved", "Agent")

    reopen_p = REOPEN_SHARE[category] * (REOPEN_BREACHED if clock > RES_TARGET[priority] else 1.0)
    for n, p in enumerate((reopen_p, reopen_p * SECOND_REOPEN)):
        if d.u_reopen[i, n] >= p:
            break
        reopened = moment + timedelta(minutes=int(d.reopen_delay[i, n]))
        add(reopened, "Reopened", "Customer")
        work = REOPEN_WORK_P1 if priority == 0 else REOPEN_WORK
        extra = max(1, half_up(work * math.exp(REOPEN_SIGMA * d.z_reopen[i, n]) * agent.speed))
        clock += extra
        moment = add_business_minutes(reopened, extra, h)
        add(moment, "Resolved", "Agent")
    add(moment + CLOSE_AFTER, "Closed", "System")

    csat = csat_at = None
    if d.u_csat[i] < CSAT_RESPONSE:
        reopened_any = any(e.to_status == "Reopened" for e in events)
        raw = (
            CSAT_BASE
            + agent.csat_offset
            - CSAT_BREACH * (clock > RES_TARGET[priority])
            - CSAT_REOPEN * reopened_any
            + CSAT_SIGMA * d.z_csat[i]
        )
        csat, csat_at = min(5, max(1, half_up(raw))), moment + timedelta(minutes=int(d.csat_delay[i]))
    return Ticket(
        100001 + i,
        created,
        channel,
        category,
        priority,
        customer,
        tier,
        team,
        subject,
        agent.agent_id,
        fr,
        clock,
        events,
        csat,
        csat_at,
    )


# ---------------------------------------------------------------- export


def export(sim: Simulation) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Ticket and event rows per creation quarter, cut at AS_OF."""
    tickets: dict[str, list[dict]] = {q: [] for q in QUARTERS}
    events: dict[str, list[dict]] = {q: [] for q in QUARTERS}
    event_id = 0
    for t in sim.tickets:
        kept = [e for e in t.events if e.at <= AS_OF]
        status = kept[-1].to_status
        resolved = [e.at for e in kept if e.to_status == "Resolved"]
        closed = [e.at for e in kept if e.to_status == "Closed"]
        q = quarter(t.created)
        for seq, e in enumerate(kept, 1):
            event_id += 1
            events[q].append(
                {
                    "event_id": event_id,
                    "ticket_id": t.ticket_id,
                    "event_seq": seq,
                    "event_at": stamp(e.at),
                    "from_status": e.from_status or "",
                    "to_status": e.to_status,
                    "actor": e.actor,
                    "agent_id": e.agent_id if e.agent_id is not None else "",
                }
            )
        customer_id, _ = sim.customers[t.customer - 1]
        tickets[q].append(
            {
                "ticket_id": t.ticket_id,
                "created_at": stamp(t.created),
                "channel": CHANNELS[t.channel],
                "category": CATEGORIES[t.category],
                "priority": PRIORITIES[t.priority][0],
                "customer_id": customer_id,
                "customer_name": f"Account {customer_id}",
                "customer_tier": TIERS[t.tier],
                "team_id": t.team,
                "agent_id": t.agent_id if len(kept) > 1 else "",
                "subject": t.subject,
                "status": status,
                "first_response_at": stamp(kept[1].at) if len(kept) > 1 else "",
                "resolved_at": stamp(resolved[-1]) if status in ("Resolved", "Closed") else "",
                "closed_at": stamp(closed[-1]) if closed else "",
                "reopen_count": sum(e.to_status == "Reopened" for e in kept),
                "csat_score": t.csat if t.csat is not None and t.csat_at <= AS_OF else "",
            }
        )
    return tickets, events


def reference_rows(sim: Simulation) -> dict[str, list[dict]]:
    leads = {a.team_id: a.agent_id for a in sim.agents if a.role == "Team lead"}
    return {
        "agents.csv": [
            {
                "agent_id": a.agent_id,
                "agent_name": a.name,
                "email": a.email,
                "team_id": a.team_id,
                "role": a.role,
                "active_from": a.active_from.isoformat(),
                "active_to": a.active_to.isoformat() if a.active_to else "",
            }
            for a in sim.agents
        ],
        "teams.csv": [{"team_id": t, "team_name": name, "lead_agent_id": leads[t]} for t, name in TEAMS],
        "priorities.csv": [dict(zip(REFERENCE_COLUMNS["priorities.csv"], p, strict=True)) for p in PRIORITIES],
        "holidays.csv": [{"date": d.isoformat(), "name": name, "scope": scope} for d, name, scope in HOLIDAYS],
        "business_hours_cases.csv": [
            {"case_id": c, "start": s, "end": e, "expected_minutes": "" if m is None else m, "note": note}
            for c, s, e, m, note in CASES
        ],
    }


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([row[c] for c in columns] for row in rows)


def generate(out: Path) -> Simulation:
    sim = simulate(np.random.default_rng(SEED))
    tickets, events = export(sim)
    for q in QUARTERS:
        write_csv(out / "tickets" / f"tickets_{q}.csv", TICKET_COLUMNS, tickets[q])
        write_csv(out / "ticket_events" / f"ticket_events_{q}.csv", EVENT_COLUMNS, events[q])
    for name, rows in reference_rows(sim).items():
        write_csv(out / name, REFERENCE_COLUMNS[name], rows)
    return sim


def compare(expected: Path, actual: Path) -> list[str]:
    problems = []
    for rel in files():
        if not (actual / rel).is_file():
            problems.append(f"{rel}: missing")
        elif (actual / rel).read_bytes() != (expected / rel).read_bytes():
            problems.append(f"{rel}: differs from a fresh build")
    return problems


def shown_path(path: Path) -> str:
    """The path as printed: relative to the repository root when it lies inside it."""
    resolved = path.resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else resolved.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Quillstack Software help-desk export (seed 20240101).")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the files in --out")
    args = parser.parse_args(argv)
    shown = shown_path(args.out)
    if not args.check:
        generate(args.out)
        print(f"wrote {len(files())} files to {shown}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        problems = compare(Path(tmp), args.out)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        return 1
    print(f"{shown} matches a fresh build ({len(files())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
