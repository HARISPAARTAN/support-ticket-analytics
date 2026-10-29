"""tools/reference.py on the six mini tickets, whose values are worked out by hand in the comments."""

from __future__ import annotations

from datetime import date, datetime

import pytest

import reference as ref

MARCH = ref.month(2024, 3)
APRIL = ref.month(2024, 4)
AT_MARCH_END = ref.Context(date_to=date(2024, 3, 31))


def by_id(mini: ref.Model, column: str) -> dict[int, object]:
    return {k: (None if v is None or v != v else v) for k, v in mini.tickets[column].to_dict().items()}


def test_first_response_and_clock_minutes(mini: ref.Model) -> None:
    # 100002: Fri 17:00 to Mon 09:00 is 60 + 60; 100003: Thu 12:00 to Mon 10:00 skips Good Friday and the weekend
    assert by_id(mini, "first_response_bmin") == {
        100001: 60, 100002: 120, 100003: 120, 100004: None, 100005: 30, 100006: 30
    }  # fmt: skip
    clock = by_id(mini, "clock_bmin")
    assert {k: clock[k] for k in (100001, 100002, 100003, 100005, 100006)} == {
        100001: 330, 100002: 360, 100003: 600, 100005: 30, 100006: 540
    }  # fmt: skip
    assert clock[100004] == ref.business_minutes(datetime(2024, 3, 20, 9, 0), ref.AS_OF, mini.holidays)  # still New
    assert by_id(mini, "pending_bmin")[100001] == 450  # 11:30 to 18:00 and 08:00 to 09:00
    assert by_id(mini, "resolution_bmin") == {
        100001: 330, 100002: 360, 100003: 600, 100004: None, 100005: None, 100006: 540
    }  # fmt: skip


def test_sla_outcomes(mini: ref.Model) -> None:
    assert by_id(mini, "fr_sla_status") == {
        100001: "Met", 100002: "Breached", 100003: "Met", 100004: "Breached", 100005: "Met", 100006: "Met"
    }  # fmt: skip
    assert by_id(mini, "res_sla_status") == {
        100001: "Met", 100002: "Breached", 100003: "Met", 100004: "Breached", 100005: "Pending", 100006: "Met"
    }  # fmt: skip
    assert ref.measure(mini, "SLA first response met %") == pytest.approx(4 / 6)
    assert ref.measure(mini, "SLA resolution met %") == pytest.approx(3 / 5)
    assert ref.measure(mini, "Breaches") == 2
    assert ref.measure(mini, "Open breaches now") == 1


def test_volume_by_creation_and_by_resolution_date(mini: ref.Model) -> None:
    assert ref.measure(mini, "Created") == 6
    assert ref.measure(mini, "Resolved") == 4
    assert ref.measure(mini, "Created", MARCH) == 6
    assert ref.measure(mini, "Resolved", MARCH) == 3  # 100003 is resolved on 1 April
    assert ref.measure(mini, "Resolved", APRIL) == 1
    assert ref.measure(mini, "Created", APRIL) is None
    assert ref.measure(mini, "Net flow", MARCH) == 3


def test_backlog_statuses_and_ages(mini: ref.Model) -> None:
    assert ref.measure(mini, "Backlog", AT_MARCH_END) == 3  # 100003, 100004 and 100005
    assert ref.measure(mini, "Backlog", APRIL) == 2
    assert ref.tickets_in_status(mini, "New", AT_MARCH_END) == 1
    assert ref.tickets_in_status(mini, "Open", AT_MARCH_END) == 1
    assert ref.tickets_in_status(mini, "Pending", AT_MARCH_END) == 1  # 100001 entered and left Pending
    assert ref.backlog_in_bucket(mini, "2–3 d", AT_MARCH_END) == 1  # 100003, 3 days
    assert ref.backlog_in_bucket(mini, "8–14 d", AT_MARCH_END) == 1  # 100004, 11 days
    assert ref.backlog_in_bucket(mini, "15–30 d", AT_MARCH_END) == 1  # 100005, 25 days
    assert ref.backlog_in_bucket(mini, "0–1 d", AT_MARCH_END) is None
    assert ref.measure(mini, "Open over 7 days", AT_MARCH_END) == 2
    assert ref.measure(mini, "Oldest open ticket (days)", AT_MARCH_END) == 25
    assert ref.measure(mini, "Backlog change 30 d", AT_MARCH_END) == 3  # nothing existed on 1 March


def test_durations(mini: ref.Model) -> None:
    assert ref.measure(mini, "Median first response (h)") == pytest.approx(1.0)  # 30 30 60 120 120
    assert ref.measure(mini, "Average first response (h)") == pytest.approx(1.2)
    assert ref.measure(mini, "P90 first response (h)") == pytest.approx(2.0)
    assert ref.measure(mini, "Median resolution (h)") == pytest.approx(7.5)  # (360 + 540) / 2
    assert ref.measure(mini, "Average resolution (h)") == pytest.approx(7.625)
    assert ref.measure(mini, "P90 resolution (h)") == pytest.approx(9.7)  # 540 + 0.7 x 60


def test_quality_and_agents(mini: ref.Model) -> None:
    assert ref.measure(mini, "Reopened tickets") == 1
    assert ref.measure(mini, "Reopen rate") == pytest.approx(1 / 4)
    assert ref.measure(mini, "CSAT responses") == 3
    assert ref.measure(mini, "CSAT average") == pytest.approx(11 / 3)
    assert ref.measure(mini, "CSAT response rate") == pytest.approx(3 / 4)
    assert ref.measure(mini, "CSAT satisfied %") == pytest.approx(2 / 3)
    assert ref.measure(mini, "Active agents", MARCH) == 3  # agents 2, 5 and 7 resolved in March
    assert ref.measure(mini, "Tickets per agent", MARCH) == pytest.approx(1.0)


def test_filters_reach_the_tickets(mini: ref.Model) -> None:
    team2 = ref.ALL.where(teams={2})
    assert ref.measure(mini, "Created", team2) == 2
    assert ref.measure(mini, "Backlog", team2.where(date_to=date(2024, 3, 31))) == 1
    assert ref.measure(mini, "Created", ref.ALL.where(priorities={"P1"})) == 1
    assert ref.measure(mini, "Created", ref.ALL.where(channels={"Phone"})) == 1
    assert ref.measure(mini, "Created", ref.ALL.where(categories={"Bug", "Access"})) == 2
    assert ref.measure(mini, "Created", ref.ALL.where(agents={0})) == 1  # 100004 is unassigned


def test_calculation_items(mini: ref.Model) -> None:
    assert ref.item(mini, "Created", "PY", MARCH) is None  # no 2023 dates in DimDate
    assert ref.item(mini, "Created", "YTD", APRIL) == 6
    assert ref.item(mini, "Created", "R12", APRIL) == 6
    assert ref.item(mini, "Created", "YoY", MARCH) is None
    assert ref.calculation(ref.month(2025, 9), "R12") == ref.Context(date(2024, 10, 1), date(2025, 9, 30))
    # DimDate ends on 2025-09-30, so the year 2025 holds nine months and its PY nine months of 2024
    assert ref.calculation(ref.year(2025), "PY") == ref.Context(date(2024, 1, 1), date(2024, 9, 30))
    assert ref.calculation(ref.month(2025, 9), "PYTD") == ref.Context(date(2024, 1, 1), date(2024, 9, 30))
    assert ref.calculation(ref.month(2025, 2), "PY") == ref.month(2024, 2)  # the month end moves to 29 February
    assert ref.shift_month_end(date(2025, 2, 14), -1) == date(2024, 2, 14)


def test_business_hours_cases(mini: ref.Model) -> None:
    assert ref.bh_tests(mini) == (18, 18)


def test_display() -> None:
    assert ref.display(None, "count") == "(blank)"
    assert ref.display(25066, "count") == "25066"
    assert ref.display(0.911514, "percent") == "91.151 %"
    assert ref.display(3.43333, "hours") == "3.4333"
