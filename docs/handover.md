# Handover

Notes for the person who refreshes or changes the dashboard. Commands run from the repository root with uv; the Power BI steps need Power BI Desktop on Windows.

## Set up

```bash
uv sync
uv run python tools/make_data.py --check          # the committed data equal a fresh build
uv run pytest -q                                   # every offline test; the TOM test skips without build/tom
```

Open `pbip\SupportTicketAnalytics.pbip` in Power BI Desktop. Home, Transform data, Edit parameters: `DataFolder` must name this clone's `data` folder without a trailing backslash (the default is `E:\GITGUB\support-ticket-analytics\data`). OK, Apply changes, then Refresh. No credentials are involved: every source is a local file.

The optional TOM parse test needs Microsoft's Tabular Object Model assemblies and pythonnet:

```bash
uv sync --group pbi
uv run python tools/pbi/copy_tom.py --from <folder with the six Microsoft.AnalysisServices DLLs>
uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q
```

## Refresh

Home, Refresh. The model reads the quarterly files from `data\tickets\` and `data\ticket_events\` and the CSV files from `data\`, and computes the business minutes of every event interval with `fnBusinessMinutes`. After a refresh, the Info page shows 18 of 18 business-hours test cases passed, and the cards of the hidden page Reconciliation must still match the Python column of `docs/reconciliation.md` when the data files are unchanged.

## Adding a quarter's export

1. Save the help desk's export as `data/tickets/tickets_<year>-Q<n>.csv` and `data/ticket_events/ticket_events_<year>-Q<n>.csv` with the columns of [the data model](data-model.md#files). A ticket's events belong in the file of its creation quarter; the events of older tickets that changed after the last export are appended to their creation quarter's file. The folder queries pick up every `.csv` file; nothing changes in Power Query.
2. Edit parameters: move `AsOf` to the moment of the export (open tickets count their clock up to it) and `EndDate` to its date, so `DimDate` covers the new quarter. `StartDate` stays.
3. Add the new year's holidays to `data/holidays.csv` (next section) before the refresh, or the durations of that year count holidays as business days.
4. Refresh. `ExportInfo` counts the files, so the Info page shows one more ticket file and one more event file.
5. For this demo the files are generated: change `LAST_CREATED`, `AS_OF` and `QUARTERS` in `tools/make_data.py`, `AS_OF` and `END_DATE` in `tools/reference.py` (a lint test compares `AS_OF` with the parameter), run `uv run python tools/make_data.py`, then `uv run python tools/build_replica_data.py`, and update the bands in `tests/test_generator.py` and the values in `docs/reconciliation.md` from the new run.

## Adding a holiday

Add a row to `data/holidays.csv`: `date` (ISO), `name`, `scope` (`National` or `Lisbon`). Refresh: `Holidays` feeds both `DimDate[Is business day]` and `HolidayList`, so every duration is computed again. In the Python twin, `tools/bizhours.py` reads the same file through `load_holidays`; its constant `HOLIDAYS` is what the generator writes, so for this demo add the row there too and regenerate. A holiday changes business minutes, so first response and resolution times, SLA outcomes and the reconciliation values can change; the 18 test cases cover 2024 and 2025 only and stay valid.

## Adding a team lead

The role `Team lead` reads the `Security` table, which Power Query builds from the rows of `data/agents.csv` with `role` = `Team lead`: the lower-case `email` and the `team_id`. A new lead is a new row (or a changed `role` of an existing agent) and the `lead_agent_id` of the team in `data/teams.csv`; refresh, and no model change is needed. Check it in Desktop: Modeling, View as, Other user = the new address, tick `Team lead`, OK; the Team slicer lists only the lead's team. An address without a row sees no data.

In the Power BI service the role needs members: on the semantic model, More options, Security, role `Team lead`, add the leads or a group. Workspace members with edit rights see all data regardless of the role.

## When a reconciliation pair fails

1. Read the pair's context in `docs/reconciliation.md` (filters, date, team) and set exactly that context on a page or on the hidden page Reconciliation, where each card carries its own filters.
2. Compare the rule: the DAX in [the measures](measures.md) with the function of the same name in `tools/reference.py`. Tolerances are half a unit of the last digit shown; a difference beyond that is a real difference, not rounding.
3. Durations first: if a median or an SLA percentage differs, compare the business minutes of a few tickets in Ticket explorer (status history, Time in status) with `tools/bizhours.py`; the Info page must show 18 of 18 test cases.
4. Fix the side that breaks the written rule, never the expected value. A DAX fix changes `docs/measures.md` too (`tests/test_docs.py` compares the DAX); a Python fix changes the Python column, the replica data (`tools/build_replica_data.py`) and possibly `web/assets/js/model.js`.

## Limits of the SLA attribution

Every SLA figure counts tickets by their creation date ([ADR 0002](adr/0002-sla-outcome-per-ticket-by-creation-date.md)). The last weeks before `AsOf` therefore hold tickets that are still open: their resolution outcome is pending unless they are already past the target, the slow ones are not yet in the resolution medians, and those medians look better than they will be. Compare months only when both are complete, or read the open breaches tile next to them. `Resolved` counts by the resolution date and so does not add up with `Created` for the same month; `Net flow` is the difference.

## Changing the report

Until the first save in Power BI Desktop, the report is generated: edit `tools/pbi/pages.json` (or `tools/pbi/report_extras.py`), run `uv run python tools/pbi/report_extras.py` and `uv run pytest tests/pbi -q`. After the first save, the files Desktop wrote are the source: change the report in Desktop or in the PBIR files directly, and do not run the generator again; it would overwrite Desktop's files ([desktop session](desktop-session.md)). The lint tests keep running on the saved files.

The model is edited in the TMDL files under `pbip/SupportTicketAnalytics.SemanticModel/definition/` or in Desktop. A changed measure changes `docs/measures.md` too and, when its rule changes, `tools/reference.py` and the replica's `web/assets/js/model.js`. A change of `fnBusinessMinutes` changes `docs/business-hours.md` and `tools/bizhours.py` in the same commit.

## Changing the theme

The theme `Quillstack Dark` is generated from the kit's dark tokens: `uv run python tools/pbi/build_theme.py` writes `pbip/SupportTicketAnalytics.Report/StaticResources/RegisteredResources/quillstack-dark.json`; `--check` compares the content with a fresh build. After the kit is updated (next section), run it again and check the contrast with `uv run pytest tests/pbi/test_theme.py -q`.

## Updating portfolio-kit or ECharts

- Kit: with a newer tag in the local clone `E:\GITGUB\portfolio-kit`, run `uv run python tools/sync_kit.py --tag <tag>`, then `uv run python tools/sync_kit.py --check`, change the tag in `.github/workflows/ci.yml` (job `kit`), and run `node tools/checks/contrast.mjs` and the screenshots.
- ECharts: `web/vendor/echarts.min.js` is version 5.6.0 (Apache-2.0, licence in `web/vendor/LICENSE-echarts.txt`). A new version is a new download with its SHA-256 recorded in the commit message; the chart options live in `web/assets/js/charts.js`, and `tests/replica/charts.test.mjs` and the screenshots show what changed.

## Updating Faker or numpy

A Faker or numpy update changes generated names or numbers and needs regeneration: a new Faker release can change the agent names and e-mail addresses, a numpy feature release the random streams and so every number. Regenerate the data and the replica data (`uv run python tools/make_data.py`, then `uv run python tools/build_replica_data.py`), check the bands (`uv run pytest tests/test_generator.py -q`) and update the Python column of `docs/reconciliation.md`; the Desktop column then needs a new session. Dependabot ignores Faker and numpy feature releases for that reason.

## Checks before a push

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python tools/make_data.py --check
uv run python tools/build_replica_data.py --check
uv run python tools/pbi/build_theme.py --check
node --test "tests/replica/*.test.mjs"
node tools/checks/replica-values.mjs
node tools/checks/contrast.mjs
uv run python tools/check_page_weight.py
OFFLINE=1 node tools/checks/verify-site.mjs
uv run python tools/checks/scrub.py
PLAYWRIGHT_FROM=<package.json of a folder with playwright> OUT=<folder outside the repository> node tools/checks/shots.mjs
```

`shots.mjs` serves `web/` on 127.0.0.1, opens every tab at 1440 and 390 px in both themes with the installed Chrome, and fails on any external request, console error, sideways scrolling or a focused control hidden under the filter bar; the screenshots go to `OUT`.
