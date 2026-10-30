# ADR 0003: The export as quarterly files

Status: accepted (2026-10-29)

## Context

The portfolio's rule limits every generated file to 2 MB. One ticket file for 21 months would be about 4.5 MB and one event file about 6.4 MB. The client's help desk exports every quarter anyway.

## Decision

The export is split by the creation quarter of the ticket: `data/tickets/tickets_2024-Q1.csv` to `tickets_2025-Q3.csv` and `data/ticket_events/ticket_events_2024-Q1.csv` to `ticket_events_2025-Q3.csv`, seven files each. A ticket's events sit in the file of its creation quarter, even when they happen later. Power Query reads each folder with `Folder.Files` and keeps the `.csv` files in name order (the staging queries `src_Tickets` and `src_Events`), and combines them (`TicketFiles`, `EventFiles`); the reference does the same with `sorted(glob(...))`.

## Consequences

- Each file is 0.6 to 1.0 MB, and a new quarter is one new file per folder with no change in Power Query ([handover](../handover.md)).
- `ExportInfo` counts the files, and the Info page shows the counts, so a missing file is visible.
- A ticket created in one quarter and closed in the next appears in one file only; the folder order does not matter for the result.

## Alternatives considered

- One file per entity: over the 2 MB limit.
- A file per event quarter: a ticket's events would spread over files, and an export would have to rewrite old files when a ticket reopens.
