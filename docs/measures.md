# Measures

Every measure of `_Measures` in `pbip/SupportTicketAnalytics.SemanticModel/definition/tables/_Measures.tmdl`,
by display folder, with its description (the `///` line in TMDL), its format and its DAX;
`tests/test_docs.py` compares each DAX block here with the TMDL. Formats: counts `#,0`, percentages `0.0%`,
CSAT `0.00`, signed changes `+#,0;-#,0;0`; the six duration measures in hours use the dynamic format string
of the duration pattern (minutes below one hour). Ticket measures count by the creation date (the active
relationship); `Resolved`, `Active agents` and `Tickets per agent` count by the resolution date
([ADR 0002](adr/0002-sla-outcome-per-ticket-by-creation-date.md)). Snapshot measures (the Backlog folder) read
the last selected day, `MAX(DimDate[Date])`.

## Volume

### Created

Tickets created in the period (creation date).

Folder `Volume` · format `#,0`.

```dax
COUNTROWS(FactTickets)
```

### Resolved

Tickets whose final resolution falls in the period (resolution date, the inactive relationship).

Folder `Volume` · format `#,0`.

```dax
CALCULATE(
    COUNTROWS(FactTickets),
    USERELATIONSHIP(FactTickets[Resolved date], DimDate[Date]),
    FactTickets[Is resolved] = TRUE()
)
```

### Net flow

Created minus Resolved: positive when the backlog grows.

Folder `Volume` · format `+#,0;-#,0;0`.

```dax
[Created] - [Resolved]
```

## Backlog

### Backlog

Open tickets at the end of the period: the backlog deltas of all events up to the last selected day.

Folder `Backlog` · format `#,0`.

```dax
VAR d = MAX(DimDate[Date])
RETURN
    CALCULATE(
        SUM(FactTicketEvents[Backlog delta]),
        REMOVEFILTERS(DimDate),
        FactTicketEvents[Event date] <= d
    )
```

### Backlog change 30 d

Backlog at the end of the period minus the backlog 30 calendar days earlier.

Folder `Backlog` · format `+#,0;-#,0;0`.

```dax
VAR d = MAX(DimDate[Date])
RETURN
    [Backlog]
        - CALCULATE(
            SUM(FactTicketEvents[Backlog delta]),
            REMOVEFILTERS(DimDate),
            FactTicketEvents[Event date] <= d - 30
        )
```

### Backlog PY

Backlog on the same day one year earlier; blank in 2024.

Folder `Backlog` · format `#,0`.

```dax
CALCULATE([Backlog], 'Time intelligence'[Time calculation] = "PY")
```

### Tickets in status

Tickets in the selected status at the end of the period: events into it minus events out of it.

Folder `Backlog` · format `#,0`.

```dax
VAR d = MAX(DimDate[Date])
VAR s = VALUES(DimStatus[Status])
VAR entered = CALCULATE(COUNTROWS(FactTicketEvents), REMOVEFILTERS(DimDate), FactTicketEvents[Event date] <= d)
VAR left =
    CALCULATE(
        COUNTROWS(FactTicketEvents),
        REMOVEFILTERS(DimDate),
        REMOVEFILTERS(DimStatus),
        FactTicketEvents[Event date] <= d,
        TREATAS(s, FactTicketEvents[From status])
    )
RETURN
    entered - left
```

### Backlog in age bucket

Open tickets at the end of the period whose age in calendar days lies in the selected buckets.

Folder `Backlog` · format `#,0`.

```dax
VAR d = MAX(DimDate[Date])
VAR lo = MIN(DimAgeBucket[Min days])
VAR hi = MAX(DimAgeBucket[Max days])
VAR ev = CALCULATETABLE(FactTicketEvents, REMOVEFILTERS(DimDate), FactTicketEvents[Event date] <= d)
VAR perTicket =
    GROUPBY(
        ev,
        FactTicketEvents[Ticket ID],
        FactTicketEvents[Ticket created date],
        "@open", SUMX(CURRENTGROUP(), FactTicketEvents[Backlog delta])
    )
RETURN
    COUNTROWS(
        FILTER(
            perTicket,
            [@open] = 1
                && DATEDIFF(FactTicketEvents[Ticket created date], d, DAY) >= lo
                && DATEDIFF(FactTicketEvents[Ticket created date], d, DAY) <= hi
        )
    )
```

### Open over 7 days

Open tickets at the end of the period created at least 8 calendar days earlier.

Folder `Backlog` · format `#,0`.

```dax
CALCULATE([Backlog in age bucket], DimAgeBucket[Min days] >= 8)
```

### Oldest open ticket (days)

Age in calendar days of the oldest ticket open at the end of the period.

Folder `Backlog` · format `#,0`.

```dax
VAR d = MAX(DimDate[Date])
VAR ev = CALCULATETABLE(FactTicketEvents, REMOVEFILTERS(DimDate), FactTicketEvents[Event date] <= d)
VAR perTicket =
    GROUPBY(
        ev,
        FactTicketEvents[Ticket ID],
        FactTicketEvents[Ticket created date],
        "@open", SUMX(CURRENTGROUP(), FactTicketEvents[Backlog delta])
    )
RETURN
    MAXX(FILTER(perTicket, [@open] = 1), DATEDIFF(FactTicketEvents[Ticket created date], d, DAY))
```

### Open at end of period

1 for a ticket open at the end of the period, 0 otherwise (a visual filter of the oldest-tickets table).

Folder `Backlog` · format `0`.

```dax
[Backlog]
```

### Age at end of period (days)

Calendar days from the ticket's creation date to the end of the period.

Folder `Backlog` · format `#,0`.

```dax
DATEDIFF(MIN(FactTickets[Created date]), MAX(DimDate[Date]), DAY)
```

## Response time

### Median first response (h)

Median business hours to the first response; tickets without one are skipped.

Folder `Response time` · dynamic format string.

```dax
DIVIDE(MEDIAN(FactTickets[First response bmin]), 60)
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

### Average first response (h)

Average business hours to the first response.

Folder `Response time` · dynamic format string.

```dax
DIVIDE(AVERAGE(FactTickets[First response bmin]), 60)
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

### P90 first response (h)

90th percentile (inclusive, interpolated) of the business hours to the first response.

Folder `Response time` · dynamic format string.

```dax
VAR t = FILTER(FactTickets, NOT ISBLANK(FactTickets[First response bmin]))
RETURN
    IF(NOT ISEMPTY(t), DIVIDE(PERCENTILEX.INC(t, FactTickets[First response bmin], 0.9), 60))
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

## Resolution time

### Median resolution (h)

Median business hours on the clock of resolved tickets (New, Open and Reopened).

Folder `Resolution time` · dynamic format string.

```dax
DIVIDE(MEDIAN(FactTickets[Resolution bmin]), 60)
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

### Average resolution (h)

Average business hours on the clock of resolved tickets.

Folder `Resolution time` · dynamic format string.

```dax
DIVIDE(AVERAGE(FactTickets[Resolution bmin]), 60)
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

### P90 resolution (h)

90th percentile (inclusive, interpolated) of the business hours on the clock of resolved tickets.

Folder `Resolution time` · dynamic format string.

```dax
VAR t = FILTER(FactTickets, NOT ISBLANK(FactTickets[Resolution bmin]))
RETURN
    IF(NOT ISEMPTY(t), DIVIDE(PERCENTILEX.INC(t, FactTickets[Resolution bmin], 0.9), 60))
```

Format string:

```dax
VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "'" & FORMAT(h * 60, "0") & " min'", "#,0.00 \h")
```

### Time in status (h)

Business hours spent in the status of the events in context (Ticket explorer).

Folder `Resolution time` · format `#,0.00`.

```dax
DIVIDE(SUM(FactTicketEvents[Interval bmin]), 60)
```

## SLA

### FR SLA met

Tickets whose first response met the priority's target.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[FR SLA status] = "Met")
```

### FR SLA breached

Tickets whose first response missed the target, or still lack one past it.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[FR SLA status] = "Breached")
```

### SLA first response met %

FR SLA met / (met + breached); pending tickets are left out.

Folder `SLA` · format `0.0%`.

```dax
DIVIDE([FR SLA met], [FR SLA met] + [FR SLA breached])
```

### Res SLA met

Tickets resolved within the priority's resolution target.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[Res SLA status] = "Met")
```

### Res SLA breached

Tickets resolved after the target, or open with the clock past it.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[Res SLA status] = "Breached")
```

### SLA resolution met %

Res SLA met / (met + breached); pending tickets are left out.

Folder `SLA` · format `0.0%`.

```dax
DIVIDE([Res SLA met], [Res SLA met] + [Res SLA breached])
```

### Breaches

Tickets with at least one breached target.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[Any SLA breach] = TRUE())
```

### Open breaches now

Breached tickets still open at the as-of moment.

Folder `SLA` · format `#,0`.

```dax
CALCULATE([Breaches], FactTickets[Is open at as-of] = TRUE())
```

## Quality

### Reopened tickets

Tickets reopened at least once.

Folder `Quality` · format `#,0`.

```dax
CALCULATE([Created], FactTickets[Reopen count] > 0)
```

### Reopen rate

Reopened tickets / tickets resolved at least once.

Folder `Quality` · format `0.0%`.

```dax
DIVIDE([Reopened tickets], CALCULATE([Created], FactTickets[Ever resolved] = TRUE()))
```

### CSAT responses

Answered satisfaction surveys.

Folder `Quality` · format `#,0`.

```dax
COUNT(FactTickets[CSAT score])
```

### CSAT average

Average satisfaction score, 1 to 5.

Folder `Quality` · format `0.00`.

```dax
AVERAGE(FactTickets[CSAT score])
```

### CSAT response rate

Answered surveys / resolved tickets.

Folder `Quality` · format `0.0%`.

```dax
DIVIDE([CSAT responses], CALCULATE([Created], FactTickets[Is resolved] = TRUE()))
```

### CSAT satisfied %

Share of answers with a score of 4 or 5.

Folder `Quality` · format `0.0%`.

```dax
DIVIDE(CALCULATE([CSAT responses], FactTickets[CSAT score] >= 4), [CSAT responses])
```

## Agents

### Active agents

Agents with at least one final resolution in the period.

Folder `Agents` · format `#,0`.

```dax
CALCULATE(
    DISTINCTCOUNT(FactTickets[Agent ID]),
    USERELATIONSHIP(FactTickets[Resolved date], DimDate[Date]),
    FactTickets[Is resolved] = TRUE()
)
```

### Tickets per agent

Resolved tickets per active agent.

Folder `Agents` · format `#,0.0`.

```dax
DIVIDE([Resolved], [Active agents])
```

### Ranking value

The measure picked in Rank agents by, for agents with at least 20 created tickets.

Folder `Agents` · dynamic format string.

```dax
VAR c = SELECTEDVALUE('Rank agents by'[Rank agents by Order], 0)
RETURN
    IF([Created] >= 20, SWITCH(c, 0, [Resolved], 1, [SLA resolution met %], 2, [SLA first response met %], 3, [CSAT average]))
```

Format string:

```dax
SWITCH(SELECTEDVALUE('Rank agents by'[Rank agents by Order], 0), 1, "0.0%", 2, "0.0%", 3, "0.00", "#,0")
```

### Agent rank

Dense rank of the agent by Ranking value, 1 = best.

Folder `Agents` · format `0`.

```dax
IF(
    HASONEVALUE(DimAgent[Agent name]) && NOT ISBLANK([Ranking value]),
    RANKX(FILTER(ALLSELECTED(DimAgent[Agent name], DimAgent[Team name]), NOT ISBLANK([Ranking value])), [Ranking value], , DESC, DENSE)
)
```

The scorecard groups by `Agent name` and `Team name`, so each row filters both columns; `ALLSELECTED` restores both, which makes the rank run over all agents shown. With the name column alone the row's team filter would stay and the rank would restart in every team.

## KPI deltas

### Δ PY Created

Change of Created against the same period a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MIN(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [Created]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([Created], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(DIVIDE(c - p, p), "+0.0%;-0.0%;0.0%"))
```

### Δ PY Resolved

Change of Resolved against the same period a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MIN(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [Resolved]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([Resolved], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(DIVIDE(c - p, p), "+0.0%;-0.0%;0.0%"))
```

### Δ PY Backlog

Change of Backlog against the same day a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MAX(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [Backlog]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([Backlog], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(DIVIDE(c - p, p), "+0.0%;-0.0%;0.0%"))
```

### Δ PY Median first response

Difference of the median first response in hours against a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MIN(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [Median first response (h)]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([Median first response (h)], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(c - p, "+0.00;-0.00;0.00") & " h")
```

### Δ PY SLA resolution met %

Difference of SLA resolution met % in percentage points against a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MIN(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [SLA resolution met %]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([SLA resolution met %], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT((c - p) * 100, "+0.0;-0.0;0.0") & " pp")
```

### Δ PY CSAT average

Difference of the CSAT average against a year earlier.

Folder `KPI deltas` · text, no format string.

```dax
VAR edge = MIN(DimDate[Date])
VAR first = CALCULATE(MIN(DimDate[Date]), REMOVEFILTERS(DimDate))
VAR c = [CSAT average]
VAR p = IF(EDATE(edge, -12) >= first, CALCULATE([CSAT average], 'Time intelligence'[Time calculation] = "PY"))
RETURN
    IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(c - p, "+0.00;-0.00;0.00"))
```

## Info

### Data as of

The export moment as text for the page header.

Folder `Info` · text, no format string.

```dax
"Data as of " & FORMAT(MAX(ExportInfo[As of]), "yyyy-mm-dd hh:nn")
```

### BH tests passed

Business-hours test cases where fnBusinessMinutes returns the expected minutes.

Folder `Info` · format `#,0`.

```dax
COUNTROWS(FILTER(TestBusinessHours, TestBusinessHours[Pass]))
```

### BH tests total

Business-hours test cases in data/business_hours_cases.csv.

Folder `Info` · format `#,0`.

```dax
COUNTROWS(TestBusinessHours)
```

### BH tests result

BH tests passed of BH tests total as text (Info page).

Folder `Info` · text, no format string.

```dax
FORMAT([BH tests passed], "0") & " of " & FORMAT([BH tests total], "0")
```

### Ticket files

Quarterly ticket files read from data/tickets.

Folder `Info` · format `#,0`.

```dax
MAX(ExportInfo[Ticket files])
```

### Event files

Quarterly event files read from data/ticket_events.

Folder `Info` · format `#,0`.

```dax
MAX(ExportInfo[Event files])
```

## Calculation group Time intelligence

Column `Time calculation`, precedence 1; the items in this order. YoY and YoY % carry the
`ISNUMERIC` guard, so the text measures of the KPI deltas pass through unchanged.

### Current

The measure as filtered.

```dax
SELECTEDMEASURE()
```

### PY

The same dates one year earlier; snapshot measures give the snapshot a year earlier.

```dax
CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date]))
```

### YoY

Current minus PY when both exist; percentage points for measures whose name contains %.

```dax
VAR cur = SELECTEDMEASURE()
VAR py = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date]))
RETURN
    IF(ISNUMERIC(cur) && NOT ISBLANK(cur) && NOT ISBLANK(py), cur - py)
```

Format string:

```dax
IF(CONTAINSSTRING(SELECTEDMEASURENAME(), "%"), "'" & FORMAT(SELECTEDMEASURE() * 100, "+0.0;-0.0;0.0") & " pp'", SELECTEDMEASUREFORMATSTRING())
```

### YoY %

Relative change against PY; blank for measures whose name contains %.

```dax
VAR cur = SELECTEDMEASURE()
VAR py = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date]))
RETURN
    IF(
        ISNUMERIC(cur) && NOT ISBLANK(cur) && NOT ISBLANK(py) && NOT CONTAINSSTRING(SELECTEDMEASURENAME(), "%"),
        DIVIDE(cur - py, py)
    )
```

Format string:

```dax
"+0.0%;-0.0%;0.0%"
```

### YTD

From 1 January to the last selected day.

```dax
CALCULATE(SELECTEDMEASURE(), DATESYTD(DimDate[Date]))
```

### PYTD

YTD one year earlier.

```dax
CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DATESYTD(DimDate[Date])))
```

### R12

The twelve months up to the last selected day.

```dax
CALCULATE(SELECTEDMEASURE(), DATESINPERIOD(DimDate[Date], MAX(DimDate[Date]), -12, MONTH))
```

## Field parameter Rank agents by

The measure of the Agents ranked chart (Teams and agents). Every entry is higher-is-better, so the chart's
descending sort always puts the best agent first; `Ranking value` and `Agent rank` read the same order.

```dax
{
("Resolved", NAMEOF('_Measures'[Resolved]), 0),
("SLA resolution met %", NAMEOF('_Measures'[SLA resolution met %]), 1),
("SLA first response met %", NAMEOF('_Measures'[SLA first response met %]), 2),
("CSAT average", NAMEOF('_Measures'[CSAT average]), 3)
}
```

## Role Team lead

`modelPermission: read`. A team lead sees the tickets of their team; row 0 of `DimAgent` (Unassigned) stays
visible, or the team's unassigned tickets would vanish. `Security` maps the lower-case sign-in address to the
team, and a lead reads only their own row.

### Filter on DimTeam

```dax
DimTeam[Team ID] IN CALCULATETABLE(VALUES(Security[Team ID]), Security[User e-mail] = LOWER(USERPRINCIPALNAME()))
```

### Filter on DimAgent

```dax
DimAgent[Agent ID] = 0 || DimAgent[Team ID] IN CALCULATETABLE(VALUES(Security[Team ID]), Security[User e-mail] = LOWER(USERPRINCIPALNAME()))
```

### Filter on Security

```dax
Security[User e-mail] = LOWER(USERPRINCIPALNAME())
```
