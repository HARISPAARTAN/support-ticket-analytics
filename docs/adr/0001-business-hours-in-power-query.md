# ADR 0001: Business-hour durations in Power Query

Status: accepted (2026-10-29)

## Context

The help desk's export holds timestamps only: when a ticket was created and when each status change happened. Every SLA figure needs durations in business hours (Monday to Friday 08:00 to 18:00 Lisbon time, holidays excluded), and the report must derive them from the raw files, as it would at the client. About 120,000 event intervals need a duration at each refresh. The same definition must be checked outside Power BI.

## Decision

Power Query computes the durations at refresh with one documented M function, `fnBusinessMinutes` ([business hours](../business-hours.md)): `EventIntervals` gives every event the business minutes to the next event (or to `AsOf` for an open ticket), and `FactTickets` sums them per ticket into `First response bmin`, `Clock bmin`, `Pending bmin` and `Resolution bmin`. The measures are plain aggregations of these stored integer columns (`MEDIAN`, `AVERAGE`, `PERCENTILEX.INC`, `COUNTROWS`). The same definition is written in Python (`tools/bizhours.py`); both pass the 18 cases of `data/business_hours_cases.csv`, and the hidden table `TestBusinessHours` shows the M results in Desktop.

## Consequences

- Measures stay fast and simple: no iterator walks a calendar at query time, and the medians and percentiles read one column.
- The rule is testable twice: in Python by pytest and hypothesis, in M by the 18 cases at every refresh (R30 of the reconciliation).
- Each refresh evaluates about 120,000 function calls, each linear in the calendar days of its interval; on the 25,000 tickets of the demo that is a matter of seconds.
- A change of the business hours or of the holidays needs a refresh; durations are not recomputed per query. A new holiday is one row in `data/holidays.csv` ([handover](../handover.md)).

## Alternatives considered

- DAX calculated columns over a minute calendar: a table of about 900,000 rows for 21 months, and the logic would sit in DAX, where only Desktop can run it.
- DAX iterators inside the measures: every median would iterate the calendar for each ticket at query time.
- Durations precomputed in Python before the load: the client's export has no such columns, so the report would depend on a script outside Power BI.
