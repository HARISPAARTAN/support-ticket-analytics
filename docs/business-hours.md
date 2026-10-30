# Business hours

Quillstack Software's support works Monday to Friday from 08:00 to 18:00 Lisbon time; the Portuguese national holidays and Lisbon's municipal holiday (13 June) are closed days. Every duration of the report (first response, resolution, pending, time in status) counts business minutes, "bmin" for short. One business day has 600 bmin.

## Definition

For start ≤ end, the business minutes are the sum over every date d from the date of start to the date of end that is a Monday to Friday and not in `data/holidays.csv` of the overlap of [start, end] with [d 08:00, d 18:00], in whole minutes. End equal to start gives 0; end before start or a missing input gives blank (null in M, `None` in Python).

The export writes minute-precision Lisbon wall-clock times without an offset. The daylight-saving changes fall on Sunday nights, outside business hours, so they never change a result (case 16).

The definition exists twice and both copies pass the same 18 cases: in Power Query as the function `fnBusinessMinutes` (`expressions.tmdl`, used for every event interval at refresh, [ADR 0001](adr/0001-business-hours-in-power-query.md)) and in Python as `tools/bizhours.py` (used by the generator and the reference). `tests/test_docs.py` checks that both blocks below equal the code.

## Power Query

`HolidayList` is `List.Buffer(Holidays[Date])`, the dates of `data/holidays.csv`.

```m
(start as nullable datetime, finish as nullable datetime) as nullable number =>
    if start = null or finish = null or finish < start then null
    else List.Sum(List.Transform(
        List.Dates(DateTime.Date(start), Duration.Days(DateTime.Date(finish) - DateTime.Date(start)) + 1, #duration(1, 0, 0, 0)),
        (d as date) as number =>
            if Date.DayOfWeek(d, Day.Monday) >= 5 or List.Contains(HolidayList, d) then 0
            else let s = List.Max({start, d & #time(8, 0, 0)}), e = List.Min({finish, d & #time(18, 0, 0)})
                 in if e > s then Duration.TotalMinutes(e - s) else 0))
```

## Python

`OPEN = time(8)`, `CLOSE = time(18)`; `holidays` is the set of dates from `data/holidays.csv` (`load_holidays`). `add_business_minutes(start, minutes, holidays)` in the same module is the inverse the generator uses to place agent events: `business_minutes(start, add_business_minutes(start, m, holidays), holidays) == m` for every m ≥ 0 (a hypothesis property in `tests/test_business_hours.py`).

```python
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
```

## Test cases

`data/business_hours_cases.csv` (`case_id`, `start`, `end`, `expected_minutes`, `note`) holds 18 cases. `tests/test_business_hours.py` runs them against `business_minutes`, and the hidden table `TestBusinessHours` runs them through `fnBusinessMinutes` at every refresh; the card on the Info page shows the cases passed (`BH tests passed` of `BH tests total`), and R30 of [the reconciliation](reconciliation.md) checks that all 18 pass. A blank expected value passes when the result is blank too.

| Case | Start | End | Minutes | Note |
|---|---|---|---|---|
| 1 | 2024-03-05 09:00 | 2024-03-05 10:30 | 90 | inside one day |
| 2 | 2024-03-05 06:00 | 2024-03-05 09:00 | 60 | starts before opening |
| 3 | 2024-03-05 17:00 | 2024-03-05 20:00 | 60 | ends after closing |
| 4 | 2024-03-05 18:30 | 2024-03-05 23:00 | 0 | evening only |
| 5 | 2024-03-05 17:30 | 2024-03-06 08:30 | 60 | overnight |
| 6 | 2024-03-08 17:00 | 2024-03-11 09:00 | 120 | Friday to Monday |
| 7 | 2024-03-09 10:00 | 2024-03-10 16:00 | 0 | weekend only |
| 8 | 2024-03-04 08:00 | 2024-03-08 18:00 | 3000 | full week |
| 9 | 2024-04-25 09:00 | 2024-04-25 17:00 | 0 | holiday (Thursday) |
| 10 | 2024-04-24 17:00 | 2024-04-26 09:00 | 120 | spans a holiday |
| 11 | 2024-12-24 16:00 | 2024-12-27 10:00 | 840 | Christmas; 26 Dec is a working day |
| 12 | 2024-03-05 10:00 | 2024-03-05 10:00 | 0 | start equals end |
| 13 | 2024-03-05 10:00 | 2024-03-05 09:00 | blank | end before start |
| 14 | 2024-03-05 08:00 | 2024-03-05 18:00 | 600 | exact boundaries |
| 15 | 2024-03-05 18:00 | 2024-03-06 08:00 | 0 | closing to opening |
| 16 | 2024-10-25 17:00 | 2024-10-28 09:00 | 120 | weekend with the DST change |
| 17 | 2024-12-31 17:00 | 2025-01-02 09:00 | 120 | year end, 1 Jan holiday |
| 18 | 2024-01-01 00:00 | 2024-12-31 23:59 | 151200 | whole year, 252 business days |

The 2024 calendar has 252 business days (262 weekdays minus 10 holidays on weekdays), 2025 has 250 (261 minus 11). Carnival is not an official holiday and is not in the file.

## Properties

Besides the cases, `tests/test_business_hours.py` checks with hypothesis: additivity, bm(a, c) = bm(a, b) + bm(b, c) for a ≤ b ≤ c; the round trip with `add_business_minutes`; 0 ≤ bm ≤ the calendar minutes between the two moments; weekend-only and holiday-only spans give 0.
