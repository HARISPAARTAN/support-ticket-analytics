# Reconciliation

Every pair is computed twice: in Python by `tools/reference.py` (pandas, on the files in `data/`) and in Power BI
Desktop, R1 to R30 from the cards of the hidden Reconciliation page (each card carries the filters of its context)
and R31 from the Created card on Overview under Modeling, View as, role `Team lead`, with the e-mail address of the
Integrations lead (team 4 in `data/teams.csv`, its `lead_agent_id` in `data/agents.csv`) as the other user
(`docs/desktop-session.md`). `tests/test_measures.py` recomputes the Python column and compares each Desktop value as
soon as it is entered.

The Desktop column holds the value as the card shows it (`25,066`, `3.43 h`, `91.2%`, `3.98`, `65.7`). Tolerance:
half a unit of the last displayed digit, so counts are exact, durations ± 0.005 h (± 0.5 min when the card shows
minutes), percentages ± 0.05 percentage points, CSAT ± 0.005 and Tickets per agent ± 0.05.

R11 uses the snapshot 2024-06-30: at 2025-09-30 no open ticket is older than 30 days, so the bucket is blank there.

Desktop session: not yet run.

| Id | Measure | Context | Kind | Python | Desktop | Tolerance |
|---|---|---|---|---|---|---|
| R1 | Created | all dates | count | 25066 |  | exact |
| R2 | Resolved | all dates | count | 24926 |  | exact |
| R3 | Created | year 2025 | count | 11387 |  | exact |
| R4 | Created | year 2025, item PY | count | 10091 |  | exact |
| R5 | Created | 2025-09, item R12 | count | 14975 |  | exact |
| R6 | Created | 2025-09, item YTD | count | 11387 |  | exact |
| R7 | Backlog | snapshot 2024-06-30 | count | 131 |  | exact |
| R8 | Backlog | snapshot 2024-12-31 | count | 107 |  | exact |
| R9 | Backlog | snapshot 2025-09-30 | count | 140 |  | exact |
| R10 | Tickets in status | Pending, snapshot 2025-09-30 | count | 28 |  | exact |
| R11 | Backlog in age bucket | > 30 d, snapshot 2024-06-30 | count | 3 |  | exact |
| R12 | Median first response (h) | all dates | hours | 3.4333 |  | ± 0.005 h |
| R13 | Average first response (h) | all dates | hours | 6.0683 |  | ± 0.005 h |
| R14 | P90 first response (h) | all dates | hours | 14.1667 |  | ± 0.005 h |
| R15 | Median resolution (h) | all dates | hours | 11.0667 |  | ± 0.005 h |
| R16 | Average resolution (h) | all dates | hours | 17.1041 |  | ± 0.005 h |
| R17 | P90 resolution (h) | all dates | hours | 36.9833 |  | ± 0.005 h |
| R18 | SLA first response met % | all dates | percent | 91.151 % |  | ± 0.05 pp |
| R19 | SLA resolution met % | all dates | percent | 88.642 % |  | ± 0.05 pp |
| R20 | SLA resolution met % | Integrations, P1 | percent | 74.118 % |  | ± 0.05 pp |
| R21 | SLA resolution met % | Service Desk | percent | 94.582 % |  | ± 0.05 pp |
| R22 | SLA resolution met % | Technical Support | percent | 81.038 % |  | ± 0.05 pp |
| R23 | SLA resolution met % | Billing & Accounts | percent | 91.638 % |  | ± 0.05 pp |
| R24 | SLA resolution met % | Integrations | percent | 83.208 % |  | ± 0.05 pp |
| R25 | Breaches | all dates | count | 4684 |  | exact |
| R26 | Reopen rate | all dates | percent | 5.544 % |  | ± 0.05 pp |
| R27 | CSAT average | all dates | csat | 3.9770 |  | ± 0.005 |
| R28 | CSAT response rate | all dates | percent | 40.159 % |  | ± 0.05 pp |
| R29 | Tickets per agent | 2025-09 | decimal | 65.6818 |  | ± 0.05 |
| R30 | BH tests passed | TestBusinessHours | count | 18 |  | exact |
| R31 | Created | View as Team lead, Integrations lead | count | 3210 |  | exact |

The Python column is the output of `uv run python tools/reference.py`. "All dates" is the whole date table
(2024-01-01 to 2025-09-30) with no other filter; a snapshot is the last day of the date filter.
