# ADR 0002: SLA outcome per ticket, attributed to the creation date

Status: accepted (2026-10-29)

## Context

A ticket created in one month may be answered or resolved in another, and some tickets are still open at the as-of moment. The SLA figures need one rule for which tickets count where, and one rule for open tickets, so that Power BI, the Python reference and the replica agree and a reader can follow the numbers.

## Decision

- Every ticket has two outcomes, first response (FR) and resolution, each `Met`, `Breached` or `Pending`. FR is `Met` when the first response came within the target, `Breached` when it came later or the ticket is still New past the target, otherwise `Pending`. Resolution is the same with the business minutes on the clock (New, Open and Reopened), up to the final resolution or, for an open ticket, up to `AsOf`.
- Met % = Met / (Met + Breached); pending tickets count in neither. An open ticket past its target counts as breached at once.
- Every ticket measure is attributed to the creation date through the one active relationship `FactTickets[Created date]` to `DimDate[Date]`. `Resolved` alone counts by the resolution date, through the inactive relationship and `USERELATIONSHIP`, and so do `Active agents` and `Tickets per agent`, which build on it.

## Consequences

- A month's SLA figure does not change when a ticket created in that month is resolved weeks later, except that a pending outcome becomes met or breached.
- The last weeks before the as-of hold fewer resolved tickets, and the slow ones are still open, so their resolution medians are lower and their met % can still fall. The Info page and the handover say so.
- `Resolved` and `Created` of the same month count different tickets; `Net flow` is their difference, the change of the backlog.

## Alternatives considered

- Attribution by resolution date: met % of a month would only cover tickets that are done, and open breaches would be invisible until they close.
- Counting pending tickets as met until they breach: met % would drift down after the fact.
