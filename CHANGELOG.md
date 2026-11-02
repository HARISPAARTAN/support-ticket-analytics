# Changelog

All notable changes to this project are listed here.

## v0.1.0 (2026-11-03)

- Seeded generator for the help-desk export of the fictional Quillstack Software: 25,066 tickets created from January 2024 to September 2025 and their 122,069 status changes in seven quarterly files each, plus agents, teams, priorities with SLA targets, holidays and 18 business-hours test cases; `--check` compares a fresh build with the committed files.
- Business hours (Monday to Friday 08:00 to 18:00 Lisbon time, holidays excluded) defined once in M (`fnBusinessMinutes`) and once in Python (`tools/bizhours.py`), both written for the same 18 cases.
- Power BI project (PBIP): a TMDL model with a star schema, business-minute durations computed in Power Query, 49 measures, the calculation group `Time intelligence`, the field parameter `Rank agents by` and the role `Team lead` with dynamic row-level security; a PBIR report with eight pages, synced slicers, reset bookmarks, page buttons, a drill-through page, a tooltip page, a hidden reconciliation page and the theme `Quillstack Dark` built from the portfolio-kit tokens.
- An independent pandas reference for the 31 headline checks, and the reconciliation table R1 to R31.
- HTML replica on GitHub Pages with four tabs, the report's filters and rules, a ticket table with search and detail, ECharts 5.6.0 and portfolio-kit v0.1.0; its filter code is tested on 17 filter states against the reference, and its default tiles equal the reference block.
- Offline checks of the PBIP: JSON schemas, TMDL and PBIR lint, the theme's contrast, the TOM parse test (optional).
- Docs: client brief, data model, business hours, measures, architecture, three ADRs, handover notes and the Desktop session.
