# Power BI Desktop session

The one validation session in Power BI Desktop, as a checklist. The person in Desktop does all the clicking and typing; screen captures of the Desktop window (`tools/checks/capture_screen.ps1`) record each step. Any credentials dialog is answered by the person in Desktop; this project reads local files only, so none is expected.

## Before the session

- Every offline test is green: `uv run pytest -q` (the TOM parse test with `uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q` after `tools/pbi/copy_tom.py`).
- No Desktop cache exists: `find pbip -name cache.abf` prints nothing.
- The report equals its source: `uv run python tools/pbi/report_extras.py` followed by `git status --short pbip` prints nothing.
- The Python column of `docs/reconciliation.md` is filled and `tests/test_measures.py` passes.

## Source of the report

- **Until the first save in Desktop**, `tools/pbi/pages.json` and `tools/pbi/report_extras.py` (which runs `tools/pbi/build_report.py`) generate the report files (pages, visuals, bookmarks, `report.json`); a fix to the report goes there and the files are generated again. The TMDL files are edited directly.
- **After the first save**, the files Desktop wrote are the source. The generator is not run again: it would overwrite Desktop's normalisation and every fix made in the session. The lint tests keep running on the saved files.

## Steps

1. Close all Desktop windows. Open `E:\GITGUB\support-ticket-analytics\pbip\SupportTicketAnalytics.pbip`. If Desktop asks for the preview features `Power BI Project (.pbip) save option` and `Store semantic model using TMDL format`: File, Options and settings, Options, Preview features, tick both, OK, restart Desktop and open the project again.
2. An error dialog (for example "Unable to open document", "TMDL Format Error" or a PBIR schema error with a file name): copy its text unchanged into the session notes and close Desktop without saving. The error loop below applies.
3. Home, Transform data, Edit parameters: `DataFolder` must name the clone's `data` folder without a trailing backslash (`E:\GITGUB\support-ticket-analytics\data`). OK, Apply changes, then Home, Refresh. No credentials are involved; if a privacy-level dialog appears, set the folder to Organizational. After a "cyclic reference" message, refresh once more. Every table loads; for a table that fails, copy its error text into the session notes.
4. Model view: ten relationships are drawn (`FactTickets` to `DimDate` twice, the one on `Resolved date` dashed as inactive, and to `DimPriority`, `DimTeam`, `DimAgent`, `DimCategory`, `DimChannel` and `DimCustomer`; `FactTicketEvents` to `FactTickets` and `DimStatus`); `DimDate`, Table tools: Mark as date table is set on `Date`; the calculation group `Time intelligence` and the field parameter `Rank agents by` are listed in the Data pane. Capture the model view.
5. Report view, the default state of every page (Ctrl+click Reset first if a slicer moved). Open Overview, SLA compliance, Teams and agents, Backlog and ageing and Info; capture each. On Info, the card "Business-hours test cases passed" reads 18 of 18.
6. Open the hidden page Reconciliation (Desktop lists it with the hidden-page icon) and capture its 30 cards. Enter each card's text in the Desktop column of `docs/reconciliation.md`. Fix a mismatch in the DAX or the Power Query first and refresh; take the screenshots afterwards.
7. Interactions, each captured:
   - SLA compliance: the pointer resting on a bar of "SLA met % by priority", so the page `SLA tooltip` shows.
   - SLA compliance: right-click a row of "Breach list", Drill through, Ticket explorer. The ticket's card row and status history show; Ctrl+click Back returns to the breach list.
   - Teams and agents: switch `Rank agents by` through its four entries; capture CSAT average.
   - Overview: a click on the Billing bar of "Created by category and tier"; the tiles, the other charts and the matrices filter to Billing; the slicers keep their values.
   - Overview: choose Integrations in Team and P1 in Priority, then open SLA compliance and Backlog and ageing (both show the same choice); Ctrl+click Reset on each of the four pages.
8. Row-level security: Modeling, View as, Other user = the Integrations lead's address (`lead_agent_id` of team 4 in `data/teams.csv`, its `email` in `data/agents.csv`), tick `Team lead`, OK. On Overview in the default state, read the Created card (R31) and open the Team slicer: it lists Integrations only. Capture both, then Stop viewing.
9. File, Save; close Desktop. Then follow "After the session".

## What to check on the pages

Expected tiles on Overview in the default state (all dates): Created `25,066`, Resolved `24,926`, Backlog `140` with `vs PY: +17.6%`, Median first response (h) `3.43 h`, SLA resolution met % `88.6%`, CSAT average `3.98`; the other five second lines read `vs PY: n/a`, because the previous year of the whole range starts before the data. No visual may show "Can't display the visual" or a red error icon; otherwise choose "See details" and copy the text into the session notes.

Some formatting objects are written from the published schemas but only Desktop shows whether it applies them. Each has a fallback in Desktop; a fallback used is noted for the commit message.

| Check | Expected | Fallback in Desktop |
|---|---|---|
| KPI tiles | the value card above the `vs PY` card, nothing cut off | resize the two cards inside the tile |
| Priority slicer | four tiles P1 to P4 in one row, several can be selected | Format, Slicer settings, Style Tile; Selection, Single select off |
| Date slicers | Between on Overview, SLA compliance and Teams and agents; "Snapshot date" in mode Before on Backlog and ageing | Format, Slicer settings, Options, Style Between or Before |
| Sync groups | Team, Priority and Channel chosen on one of the four pages are chosen on the other three; Date syncs the first three pages; the snapshot slicer syncs with nothing | View, Sync slicers, tick the pages of the slicer's group |
| Reset buttons | Ctrl+click clears every slicer of the page, the snapshot slicer too | clear the slicers, Bookmarks pane, the page's bookmark, Update |
| Page buttons | Ctrl+click on a header button opens that page | Format, Action, Type Page navigation, Destination |
| Arrival heatmap (Overview) | the numbers coloured from muted (0) over the text colour (300) to the accent (600); a click on a cell filters nothing | Format, Cell elements, Font color, fx, Gradient with a middle colour; Format, Edit interactions, None |
| SLA matrix (SLA compliance) | the numbers coloured from danger (75 %) over warning (85 %) to the text colour (95 %), Integrations P1 in danger | Format, Cell elements, Font color, fx, Gradient with a middle colour |
| Time calculation matrices | columns Current, YTD, PYTD and R12 on Overview; Current, PY and YoY on SLA compliance | Model view, Time intelligence, calculation group editor: put the items in the order Current, PY, YoY, YoY %, YTD, PYTD, R12 (Ordinal 0 to 6) |
| YoY % format | the YoY % column shows the year-on-year difference in percentage points (a signed value with `pp`), not the current value; the YoY column shows the difference in the measure's unit | Model view, Time intelligence, item YoY %, Format string expression: `SELECTEDMEASURE()` is the item's result; if the current value shows, set the expression to a literal format | 
| Breach list | breached tickets only, newest first | Filters pane, Any SLA breach is True; sort by Created at, descending |
| Agents ranked | agents with at least 20 created tickets, sorted descending by the measure chosen in `Rank agents by` after each switch | Filters pane, Created is greater than or equal to 20; More options, Sort axis, the chosen measure, Sort descending |
| Rank agents by | four tiles, single select, Resolved selected | Format, Slicer settings, Selection, Single select on |
| Backlog by status per day | the four open statuses stacked, nothing for Resolved or Closed | Filters pane, Is open is True |
| Oldest open tickets | open tickets only, the oldest first | Filters pane, Open at end of period is 1; sort by Age at end of period (days), descending |
| SLA tooltip | a pointer on "SLA met % by priority", "Resolution SLA by team and priority", "SLA met % per month" or "Agents ranked" shows the tooltip page with five cards | Format, Tooltips, Type Report page, Page SLA tooltip |
| Drill-through | Ticket explorer is offered on a right-click of a row with a ticket number and keeps all filters | Ticket explorer, Visualizations, Drill through, Ticket number, Keep all filters on |
| Cross-filter | a click on a bar filters the other visuals (not highlight) | Format, Edit interactions, Filter |
| Slicers | no click on a chart changes a slicer | Format, Edit interactions, None on each slicer |

## Error loop

Applies until the first save in Desktop, while the generator is still the source.

1. Desktop's error text is copied unchanged into the session notes.
2. Find the file and the line and fix the cause: `tools/pbi/pages.json` or `tools/pbi/report_extras.py` for report files, then generate them again; the TMDL files directly for the model. Generated report files are never edited by hand. Once Desktop has saved the report, the saved PBIR file is fixed directly instead.
3. Run `uv run pytest tests/pbi -q` and the TOM test, and add a regression check to the matching lint test when the kind of error is new.
4. Open the project again in Desktop (or choose "Apply external changes" in Desktop's notification bar) and continue where it failed. After three rounds without progress on the same error, stop the session and record the error texts.

## After the session

1. `git status`: no `.pbi/` file may be staged (`localSettings.json`, `cache.abf`, `editorSettings.json` and `unappliedChanges.json` are git-ignored); another one that appears belongs in `.gitignore`, not in the commit. New `.platform` files from Desktop are committed.
2. Review `git diff pbip`: only formatting and Desktop metadata may change (line endings, property order, `lineageTag`s, the linguistic metadata in `cultures/en-US.tmdl`, `diagramLayout.json`, the theme files as formatted JSON, newer `$schema` versions). Any change of content (a renamed object, a removed visual, changed DAX or M, a changed data type) is a finding to explain in the commit message.
3. Run the offline tests on the saved files. If Desktop wrote a `$schema` version that is not vendored, add its URL to `unpublished` in `tools/pbi/schema_versions.json` (the schema test skips those files); vendoring the newer schema is a separate step with its own download approval. Adapt a lint test only to the formatting, never weaken what it checks.
4. Copy the screenshots of `docs/screenshots/SHOTLIST.md` into `docs/screenshots/`, fill the Desktop column of `docs/reconciliation.md` and replace the line "Desktop session: not yet run." with "Desktop session: YYYY-MM-DD." (the session date), and commit with `chore(pbi): files as saved by Power BI Desktop; screenshots and reconciliation`.
