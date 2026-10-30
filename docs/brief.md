# Client brief

## The job post

> We are a B2B software company with 22 support agents in four teams. Our help desk exports tickets and their status changes as CSV files every quarter. We need a Power BI dashboard on that export: ticket volumes, first response and resolution times in business hours, SLA compliance by priority, team and month with a list of breaches, the backlog and how old it is, team and agent performance, and customer satisfaction. Business hours are Monday to Friday 08:00 to 18:00 Lisbon time, public holidays excluded. Team leads should only see their own team.

Rebuilt from memory as a demo. The original client's name and data are not used.

Quillstack Software is a fictional company. Every ticket, customer account, person and number in this repository comes from the seeded generator `tools/make_data.py`; customer accounts carry codes (`Account C0001`) instead of company names, and e-mail addresses use the reserved domain `quillstack.example`.

## Users and roles

| User | Uses | Access |
|---|---|---|
| Head of Support (the client contact) | all pages and teams; the SLA figures for the monthly review | the full model (workspace member, outside the role) |
| Team leads (one per team, four) | Overview, SLA compliance, Teams and agents, Backlog and ageing, Ticket explorer for their team | role `Team lead` through the `Security` table |
| Reviewers and recruiters | the README, the screenshots and the replica | the public Pages site, no login; the replica has no roles |
| Support agents (24 over the period, 22 at any time) | appear as data in `DimAgent`; not report users in this brief | none |

## Scope

In scope:

- the generator and the committed export (7 quarterly ticket files, 7 quarterly event files, five reference files);
- the Power BI project (PBIP): a TMDL model with a star schema, business-hour durations computed in Power Query, a time-intelligence calculation group, a field parameter and dynamic row-level security; a PBIR report with eight pages (a drill-through page, a tooltip page, a reset bookmark on each of the four pages with slicers, a hidden reconciliation page); the theme `Quillstack Dark`;
- an independent computation of every headline number in Python (`tools/reference.py`) and the reconciliation table;
- the HTML replica on GitHub Pages, built from the same reference;
- tests, CI, documentation, decision records and one validation session in Power BI Desktop;
- release v0.1.0 and a card on the portfolio site.

Out of scope: a connection to a help-desk API and scheduled refresh; Publish to web and any deployment to the Power BI service; per-customer SLA calendars or time zones; 24/7 coverage for P1; reassignment between teams; row-level security per agent; text analytics of the subjects; forecasting; the live reconciliation over ADOMD.

## Acceptance criteria

1. `tools/make_data.py --check` is clean, the files are committed, each at most 2 MB, and every band of the generator holds ([data model](data-model.md#generator-tuning)).
2. The business-hours function passes the same 18 cases in Python (`tests/test_business_hours.py`) and in Power Query (the table `TestBusinessHours`, 18 of 18 on the Info page).
3. The PBIP opens, refreshes after setting `DataFolder` and renders every visual in Power BI Desktop without an error; the files Desktop saves are committed after a review of the diff.
4. The 31 checks R1 to R31 of [the reconciliation](reconciliation.md) match between Python and Desktop, R31 under View as for the Integrations lead.
5. The replica's default numbers equal the reference (`tests/test_parity.py`, `tools/checks/replica-values.mjs`); CI is green on Ubuntu and Windows; Pages serves https://harispaartan.github.io/support-ticket-analytics/.
6. Screenshots of the six reading pages, the model view and the replica sit in both READMEs; the Status sections claim only verified facts.
