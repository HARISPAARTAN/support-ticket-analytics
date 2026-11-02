"""Offline lint of the TMDL model against spec sections 5.2 to 5.5 and 7: tables, columns, relationships, parameters,
the literal tables, measures, calculation group, field parameter, role, partitions and DAX references."""

import re
from datetime import date, datetime
from pathlib import Path

import pytest

import reference as ref
from pbir import PROJECT
from tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
H = True  # hidden
# table -> column -> (data type, hidden, sort-by column)
COLUMNS = {
    "FactTickets": {
        "Ticket ID": ("int64", H, None),
        "Ticket number": ("string", False, None),
        "Created at": ("dateTime", False, None),
        "Created date": ("dateTime", False, None),
        "Created hour": ("int64", False, None),
        "Channel": ("string", H, None),
        "Category": ("string", H, None),
        "Priority": ("string", H, None),
        "Customer ID": ("string", H, None),
        "Team ID": ("int64", H, None),
        "Agent ID": ("int64", H, None),
        "Subject": ("string", False, None),
        "Current status": ("string", False, "Current status sort"),
        "Current status sort": ("int64", H, None),
        "First response at": ("dateTime", False, None),
        "Resolved at": ("dateTime", False, None),
        "Resolved date": ("dateTime", H, None),
        "Closed at": ("dateTime", False, None),
        "Reopen count": ("int64", False, None),
        "CSAT score": ("int64", False, None),
        "First response bmin": ("int64", False, None),
        "Clock bmin": ("int64", False, None),
        "Pending bmin": ("int64", False, None),
        "Resolution bmin": ("int64", False, None),
        "FR SLA status": ("string", False, None),
        "Res SLA status": ("string", False, None),
        "Any SLA breach": ("boolean", False, None),
        "Ever resolved": ("boolean", False, None),
        "Is resolved": ("boolean", False, None),
        "Is open at as-of": ("boolean", False, None),
    },
    "FactTicketEvents": {
        "Event ID": ("int64", False, None),
        "Ticket ID": ("int64", H, None),
        "Event seq": ("int64", False, None),
        "Event at": ("dateTime", False, None),
        "Event date": ("dateTime", H, None),
        "Ticket created date": ("dateTime", H, None),
        "From status": ("string", False, None),
        "To status": ("string", False, None),
        "Actor": ("string", False, None),
        "Actor name": ("string", False, None),
        "Next event at": ("dateTime", H, None),
        "Interval bmin": ("int64", False, None),
        "Clock running": ("boolean", False, None),
        "Backlog delta": ("int64", H, None),
    },
    "DimDate": {
        "Date": ("dateTime", False, None),
        "Year": ("int64", False, None),
        "Quarter": ("string", False, None),
        "Year-quarter": ("string", False, None),
        "Month": ("int64", False, None),
        "Month name": ("string", False, "Month"),
        "Year-month": ("string", False, "Month start"),
        "Month start": ("dateTime", False, None),
        "ISO week": ("int64", False, None),
        "Weekday": ("int64", False, None),
        "Weekday name": ("string", False, "Weekday"),
        "Is business day": ("boolean", False, None),
        "Holiday": ("string", False, None),
    },
    "DimPriority": {
        "Priority": ("string", False, "Priority sort"),
        "Priority name": ("string", False, "Priority sort"),
        "Priority sort": ("int64", H, None),
        "FR target bmin": ("int64", False, None),
        "Res target bmin": ("int64", False, None),
        "FR target": ("string", False, None),
        "Res target": ("string", False, None),
    },
    "DimTeam": {
        "Team ID": ("int64", H, None),
        "Team name": ("string", False, "Team ID"),
        "Team lead": ("string", False, None),
    },
    "DimAgent": {
        "Agent ID": ("int64", H, None),
        "Agent name": ("string", False, None),
        "Agent e-mail": ("string", H, None),
        "Team ID": ("int64", H, None),
        "Team name": ("string", False, None),
        "Role": ("string", False, None),
        "Active from": ("dateTime", False, None),
        "Active to": ("dateTime", False, None),
    },
    "DimCategory": {"Category": ("string", False, "Category sort"), "Category sort": ("int64", H, None)},
    "DimChannel": {"Channel": ("string", False, "Channel sort"), "Channel sort": ("int64", H, None)},
    "DimCustomer": {
        "Customer ID": ("string", H, None),
        "Customer name": ("string", False, None),
        "Tier": ("string", False, "Tier sort"),
        "Tier sort": ("int64", H, None),
    },
    "DimStatus": {
        "Status": ("string", False, "Status sort"),
        "Status sort": ("int64", H, None),
        "Is open": ("boolean", False, None),
        "Clock running": ("boolean", False, None),
    },
    "DimAgeBucket": {
        "Bucket": ("string", False, "Bucket sort"),
        "Min days": ("int64", False, None),
        "Max days": ("int64", False, None),
        "Bucket sort": ("int64", H, None),
    },
    "Security": {"User e-mail": ("string", False, None), "Team ID": ("int64", False, None)},
    "ExportInfo": {
        "As of": ("dateTime", False, None),
        "Ticket files": ("int64", False, None),
        "Event files": ("int64", False, None),
    },
    "TestBusinessHours": {
        "Case ID": ("int64", False, None),
        "Start": ("dateTime", False, None),
        "End": ("dateTime", False, None),
        "Expected minutes": ("int64", False, None),
        "Actual minutes": ("int64", False, None),
        "Pass": ("boolean", False, None),
        "Note": ("string", False, None),
    },
    "_Measures": {"Anchor": ("int64", H, None)},
    "Time intelligence": {"Time calculation": ("string", False, "Ordinal"), "Ordinal": ("int64", H, None)},
    "Rank agents by": {
        "Rank agents by": ("string", False, "Rank agents by Order"),
        "Rank agents by Fields": ("string", H, "Rank agents by Order"),
        "Rank agents by Order": ("int64", H, None),
    },
}
HIDDEN_TABLES = {"Security", "ExportInfo", "TestBusinessHours"}
KEYS = {
    "DimDate": "Date",
    "DimPriority": "Priority",
    "DimTeam": "Team ID",
    "DimAgent": "Agent ID",
    "DimCategory": "Category",
    "DimChannel": "Channel",
    "DimCustomer": "Customer ID",
    "DimStatus": "Status",
    "DimAgeBucket": "Bucket sort",
    "FactTickets": "Ticket ID",
}
# (from, to, active)
RELATIONSHIPS = {
    ("FactTickets.Created date", "DimDate.Date", True),
    ("FactTickets.Resolved date", "DimDate.Date", False),
    ("FactTickets.Priority", "DimPriority.Priority", True),
    ("FactTickets.Team ID", "DimTeam.Team ID", True),
    ("FactTickets.Agent ID", "DimAgent.Agent ID", True),
    ("FactTickets.Category", "DimCategory.Category", True),
    ("FactTickets.Channel", "DimChannel.Channel", True),
    ("FactTickets.Customer ID", "DimCustomer.Customer ID", True),
    ("FactTicketEvents.Ticket ID", "FactTickets.Ticket ID", True),
    ("FactTicketEvents.To status", "DimStatus.Status", True),
}
HOURS = (
    'VAR h = SELECTEDMEASURE() RETURN IF(NOT ISBLANK(h) && h < 1, "\'" & FORMAT(h * 60, "0") & " min\'", "#,0.00 \\h")'
)
RANK_FORMAT = (
    'SWITCH(SELECTEDVALUE(\'Rank agents by\'[Rank agents by Order], 0), 1, "0.0%", 2, "0.0%", 3, "0.00", "#,0")'
)
C, P, S = "#,0", "0.0%", "+#,0;-#,0;0"
# measure -> (display folder, format string, HOURS or RANK_FORMAT for a dynamic one, None for a text result)
MEASURES = {
    "Created": ("Volume", C),
    "Resolved": ("Volume", C),
    "Net flow": ("Volume", S),
    "Backlog": ("Backlog", C),
    "Backlog change 30 d": ("Backlog", S),
    "Backlog PY": ("Backlog", C),
    "Tickets in status": ("Backlog", C),
    "Backlog in age bucket": ("Backlog", C),
    "Open over 7 days": ("Backlog", C),
    "Oldest open ticket (days)": ("Backlog", C),
    "Open at end of period": ("Backlog", "0"),
    "Age at end of period (days)": ("Backlog", C),
    "Median first response (h)": ("Response time", HOURS),
    "Average first response (h)": ("Response time", HOURS),
    "P90 first response (h)": ("Response time", HOURS),
    "Median resolution (h)": ("Resolution time", HOURS),
    "Average resolution (h)": ("Resolution time", HOURS),
    "P90 resolution (h)": ("Resolution time", HOURS),
    "Time in status (h)": ("Resolution time", "#,0.00"),
    "FR SLA met": ("SLA", C),
    "FR SLA breached": ("SLA", C),
    "SLA first response met %": ("SLA", P),
    "Res SLA met": ("SLA", C),
    "Res SLA breached": ("SLA", C),
    "SLA resolution met %": ("SLA", P),
    "Breaches": ("SLA", C),
    "Open breaches now": ("SLA", C),
    "Reopened tickets": ("Quality", C),
    "Reopen rate": ("Quality", P),
    "CSAT responses": ("Quality", C),
    "CSAT average": ("Quality", "0.00"),
    "CSAT response rate": ("Quality", P),
    "CSAT satisfied %": ("Quality", P),
    "Active agents": ("Agents", C),
    "Tickets per agent": ("Agents", "#,0.0"),
    "Ranking value": ("Agents", RANK_FORMAT),
    "Agent rank": ("Agents", "0"),
    "Δ PY Created": ("KPI deltas", None),
    "Δ PY Resolved": ("KPI deltas", None),
    "Δ PY Backlog": ("KPI deltas", None),
    "Δ PY Median first response": ("KPI deltas", None),
    "Δ PY SLA resolution met %": ("KPI deltas", None),
    "Δ PY CSAT average": ("KPI deltas", None),
    "Data as of": ("Info", None),
    "BH tests passed": ("Info", C),
    "BH tests total": ("Info", C),
    "BH tests result": ("Info", None),
    "Ticket files": ("Info", C),
    "Event files": ("Info", C),
}
DEFINITIONS = {  # spec section 7, on one line
    "Created": "COUNTROWS(FactTickets)",
    "Resolved": "CALCULATE(COUNTROWS(FactTickets), USERELATIONSHIP(FactTickets[Resolved date], DimDate[Date]), "
    "FactTickets[Is resolved] = TRUE())",
    "Net flow": "[Created] - [Resolved]",
    "Backlog": "VAR d = MAX(DimDate[Date]) RETURN CALCULATE(SUM(FactTicketEvents[Backlog delta]), "
    "REMOVEFILTERS(DimDate), FactTicketEvents[Event date] <= d)",
    "Backlog PY": "CALCULATE([Backlog], 'Time intelligence'[Time calculation] = \"PY\")",
    "Open over 7 days": "CALCULATE([Backlog in age bucket], DimAgeBucket[Min days] >= 8)",
    "Open at end of period": "[Backlog]",
    "Age at end of period (days)": "DATEDIFF(MIN(FactTickets[Created date]), MAX(DimDate[Date]), DAY)",
    "Median first response (h)": "DIVIDE(MEDIAN(FactTickets[First response bmin]), 60)",
    "Average first response (h)": "DIVIDE(AVERAGE(FactTickets[First response bmin]), 60)",
    "P90 first response (h)": "VAR t = FILTER(FactTickets, NOT ISBLANK(FactTickets[First response bmin])) RETURN "
    "IF(NOT ISEMPTY(t), DIVIDE(PERCENTILEX.INC(t, FactTickets[First response bmin], 0.9), 60))",
    "Median resolution (h)": "DIVIDE(MEDIAN(FactTickets[Resolution bmin]), 60)",
    "Average resolution (h)": "DIVIDE(AVERAGE(FactTickets[Resolution bmin]), 60)",
    "P90 resolution (h)": "VAR t = FILTER(FactTickets, NOT ISBLANK(FactTickets[Resolution bmin])) RETURN "
    "IF(NOT ISEMPTY(t), DIVIDE(PERCENTILEX.INC(t, FactTickets[Resolution bmin], 0.9), 60))",
    "Time in status (h)": "DIVIDE(SUM(FactTicketEvents[Interval bmin]), 60)",
    "FR SLA met": 'CALCULATE([Created], FactTickets[FR SLA status] = "Met")',
    "FR SLA breached": 'CALCULATE([Created], FactTickets[FR SLA status] = "Breached")',
    "SLA first response met %": "DIVIDE([FR SLA met], [FR SLA met] + [FR SLA breached])",
    "Res SLA met": 'CALCULATE([Created], FactTickets[Res SLA status] = "Met")',
    "Res SLA breached": 'CALCULATE([Created], FactTickets[Res SLA status] = "Breached")',
    "SLA resolution met %": "DIVIDE([Res SLA met], [Res SLA met] + [Res SLA breached])",
    "Breaches": "CALCULATE([Created], FactTickets[Any SLA breach] = TRUE())",
    "Open breaches now": "CALCULATE([Breaches], FactTickets[Is open at as-of] = TRUE())",
    "Reopened tickets": "CALCULATE([Created], FactTickets[Reopen count] > 0)",
    "Reopen rate": "DIVIDE([Reopened tickets], CALCULATE([Created], FactTickets[Ever resolved] = TRUE()))",
    "CSAT responses": "COUNT(FactTickets[CSAT score])",
    "CSAT average": "AVERAGE(FactTickets[CSAT score])",
    "CSAT response rate": "DIVIDE([CSAT responses], CALCULATE([Created], FactTickets[Is resolved] = TRUE()))",
    "CSAT satisfied %": "DIVIDE(CALCULATE([CSAT responses], FactTickets[CSAT score] >= 4), [CSAT responses])",
    "Active agents": "CALCULATE(DISTINCTCOUNT(FactTickets[Agent ID]), USERELATIONSHIP(FactTickets[Resolved date], "
    "DimDate[Date]), FactTickets[Is resolved] = TRUE())",
    "Tickets per agent": "DIVIDE([Resolved], [Active agents])",
    "Data as of": '"Data as of " & FORMAT(MAX(ExportInfo[As of]), "yyyy-mm-dd hh:nn")',
    "BH tests passed": "COUNTROWS(FILTER(TestBusinessHours, TestBusinessHours[Pass]))",
    "BH tests total": "COUNTROWS(TestBusinessHours)",
}
CUR_PY = "VAR cur = SELECTEDMEASURE() VAR py = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date])) RETURN "
ITEMS = {  # spec section 5.5, on one line
    "Current": "SELECTEDMEASURE()",
    "PY": "CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date]))",
    "YoY": CUR_PY + "IF(ISNUMERIC(cur) && NOT ISBLANK(cur) && NOT ISBLANK(py), cur - py)",
    "YoY %": CUR_PY
    + 'IF(ISNUMERIC(cur) && NOT ISBLANK(cur) && NOT ISBLANK(py) && NOT CONTAINSSTRING(SELECTEDMEASURENAME(), "%"), '
    "DIVIDE(cur - py, py))",
    "YTD": "CALCULATE(SELECTEDMEASURE(), DATESYTD(DimDate[Date]))",
    "PYTD": "CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DATESYTD(DimDate[Date])))",
    "R12": "IF(NOT ISBLANK(MAX(DimDate[Date])), "
    "CALCULATE(SELECTEDMEASURE(), DATESINPERIOD(DimDate[Date], MAX(DimDate[Date]), -12, MONTH)))",
}
YOY_FORMAT = (
    'IF(CONTAINSSTRING(SELECTEDMEASURENAME(), "%"), "\'" & FORMAT(SELECTEDMEASURE() * 100, "+0.0;-0.0;0.0") & " pp\'", '
    "SELECTEDMEASUREFORMATSTRING())"
)
LEAD = "IN CALCULATETABLE(VALUES(Security[Team ID]), Security[User e-mail] = LOWER(USERPRINCIPALNAME()))"
REF = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
UNQUALIFIED = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
STAGING = (  # each reads exactly one file or folder through DataFolder and nothing else (ADR 0001)
    "src_Holidays",
    "src_Tickets",
    "src_Events",
    "src_Agents",
    "src_Teams",
    "src_Priorities",
    "src_BusinessHoursCases",
)
HELPERS = (*STAGING, "Holidays", "HolidayList", "fnBusinessMinutes", "TicketFiles", "EventFiles", "EventIntervals")
CONSUMERS = {  # staging query -> the queries and partitions that reference it
    "src_Holidays": {"Holidays"},
    "src_Tickets": {"TicketFiles", "ExportInfo"},
    "src_Events": {"EventFiles", "ExportInfo"},
    "src_Agents": {"EventIntervals", "DimAgent", "DimTeam", "Security"},
    "src_Teams": {"DimAgent", "DimTeam"},
    "src_Priorities": {"DimPriority", "FactTickets"},
    "src_BusinessHoursCases": {"TestBusinessHours"},
}
SOURCE_CALL = re.compile(r"\b(?:File\.Contents|Folder\.Files|Csv\.Document)\b")
M_NOISE = re.compile(r'"(?:[^"]|"")*"|//[^\n]*|/\*.*?\*/', re.DOTALL)  # string literals and comments


def flat(dax: str) -> str:
    """DAX or M on one line with single spaces, so a test can look for a phrase whatever the line breaks."""
    return re.sub(r"\s+", " ", re.sub(r"([({])\s+", r"\1", re.sub(r"\s+([)}])", r"\1", dax))).strip()


def literal_rows(source: str) -> list[tuple]:
    """The rows of an M `#table` literal: text in double quotes, whole numbers, true and false."""

    def cell(token: str):
        token = token.strip()
        if token.startswith('"'):
            return token[1:-1].replace('""', '"')
        return {"true": True, "false": False}.get(token, int(token) if token.lstrip("-").isdigit() else token)

    return [
        tuple(cell(t) for t in re.findall(r'"(?:[^"]|"")*"|[^,]+', row))
        for row in re.findall(r"\{(\"[^{}]*)\}", source)
    ]


def m_code(source: str) -> str:
    """M with the string literals and comments blanked, so that a name inside a text is not read as a reference."""
    return M_NOISE.sub(" ", source)


def references(source: str, name: str) -> bool:
    """Whether the M `source` uses the query `name`; a step of the same name in the query shadows it."""
    code = m_code(source)
    if name in re.findall(r"(?m)^\s*(?:let\s+)?([A-Za-z_]\w*)\s*=(?!=)", code):
        return False
    return re.search(rf"(?<![\w.\[#\"]){re.escape(name)}(?!\w)", code) is not None


def firewall_violations(queries: dict[str, str], parameters: set[str]) -> list[str]:
    """The queries that call File.Contents, Folder.Files or Csv.Document and also reference another query or table.
    Power Query's privacy firewall refuses the pair ("references other queries or steps, so it may not directly access
    a data source") under the default privacy setting; the parameters are exempt."""
    others = set(queries) - parameters
    return sorted(
        name
        for name, source in queries.items()
        if SOURCE_CALL.search(m_code(source)) and any(references(source, other) for other in others - {name})
    )


def m_queries(model) -> dict[str, str]:
    """Every M query of the model: the expressions and the partitions of the M tables, by name."""
    queries = {name: e.expression for name, e in model.expressions.items()}
    return queries | {name: t.partition_source or "" for name, t in model.tables.items() if t.partition_kind == "m"}


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL_DIR)


def test_tables_columns_types_and_sort_columns(model):
    assert set(model.tables) == set(COLUMNS)
    for table, columns in COLUMNS.items():
        assert set(model.tables[table].columns) == set(columns), table
        for name, (data_type, hidden, sort_by) in columns.items():
            col = model.tables[table].columns[name]
            assert (col.data_type, col.is_hidden, col.sort_by_column) == (data_type, hidden, sort_by), (table, name)
    assert {name for name, t in model.tables.items() if t.is_hidden} == HIDDEN_TABLES


def test_keys_and_summarisation(model):
    for table, column in KEYS.items():
        assert model.tables[table].columns[column].is_key, (table, column)
    keys = {(t, c) for t, c in KEYS.items()}
    assert {(t, c) for t, tab in model.tables.items() for c, col in tab.columns.items() if col.is_key} == keys
    for table, tab in model.tables.items():
        for name, col in tab.columns.items():
            wanted = "sum" if name in ("Ordinal", "Rank agents by Order") else "none"
            assert col.summarize_by == wanted, (table, name)


def test_date_table(model):
    date_table = model.tables["DimDate"]
    assert date_table.data_category == "Time" and date_table.columns["Date"].is_key
    source = flat(date_table.partition_source or "")
    assert (
        "List.Dates(StartDate, Days, #duration(1, 0, 0, 0))" in source
        and "Duration.Days(EndDate - StartDate)" in source
    )
    assert 'Table.NestedJoin(WeekdayName, {"Date"}, Holidays, {"Date"}' in source


def test_relationships_many_to_one_single_direction(model):
    assert {(r.from_column, r.to_column, r.is_active) for r in model.relationships} == RELATIONSHIPS
    for r in model.relationships:
        assert r.cross_filtering_behavior in (None, "oneDirection"), r.name
    unrelated = ("Security", "DimAgeBucket", "ExportInfo", "TestBusinessHours", "_Measures")
    assert not [r for r in model.relationships if r.from_column.split(".")[0] in unrelated]
    assert not [r for r in model.relationships if r.to_column.split(".")[0] in unrelated]


def test_model_settings_and_parameters(model):
    assert model.culture == "en-US" and model.discourage_implicit_measures
    assert model.compatibility_level == 1606
    assert model.annotations.get("__PBI_TimeIntelligenceEnabled") == "0"
    params = {n: e for n, e in model.expressions.items() if "IsParameterQuery = true" in e.expression}
    assert set(params) == {"DataFolder", "StartDate", "EndDate", "AsOf"}
    assert set(model.expressions) == set(params) | set(HELPERS)
    assert params["DataFolder"].expression.startswith('"E:\\GITGUB\\support-ticket-analytics\\data" meta')
    d = ref.START_DATE
    assert params["StartDate"].expression.startswith(f"#date({d.year}, {d.month}, {d.day}) meta")
    d = ref.END_DATE
    assert params["EndDate"].expression.startswith(f"#date({d.year}, {d.month}, {d.day}) meta")
    m = re.match(r"#datetime\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\) meta", params["AsOf"].expression)
    assert m and datetime(*map(int, m.groups())) == ref.AS_OF
    assert all(e.description for e in model.expressions.values())


def test_literal_tables_equal_the_python_constants(model):
    def rows(table):
        return literal_rows(model.tables[table].partition_source or "")

    assert rows("DimStatus") == [tuple(s) for s in ref.STATUSES]
    assert rows("DimCategory") == [tuple(c) for c in ref.CATEGORIES]
    assert rows("DimChannel") == [tuple(c) for c in ref.CHANNELS]
    assert rows("DimAgeBucket") == [tuple(b) for b in ref.AGE_BUCKETS]
    tiers = re.search(r"Tiers = #table\(.*", model.tables["DimCustomer"].partition_source or "").group(0)
    assert literal_rows(tiers) == [tuple(t) for t in ref.TIERS]
    intervals = flat(model.expressions["EventIntervals"].expression)
    assert 'OpenStates = {"' + '", "'.join(ref.OPEN_STATES) + '"}' in intervals
    assert 'ClockStates = {"' + '", "'.join(ref.CLOCK_STATES) + '"}' in intervals


def test_power_query_reads_the_data_folder_with_fixed_formats(model):
    sources = {f"table {n}": t.partition_source or "" for n, t in model.tables.items() if t.partition_kind == "m"}
    sources |= {f"expression {n}": model.expressions[n].expression for n in HELPERS}
    for where, source in sources.items():
        for call in re.findall(r"(?:File\.Contents|Folder\.Files)\(([^)]*)\)", source):
            assert call.startswith("DataFolder & "), (where, call)
        for typed in re.findall(r"Table\.TransformColumnTypes\((?:[^()]|\([^()]*\))*\)", source):
            assert typed.endswith('"en-US")'), (where, typed[:60])
        for parse in re.findall(r"(?:DateTime|Date)\.FromText\([^)]*\)", source):
            assert 'Culture = "en-US"' in parse, (where, parse)
        assert "Sql.Database" not in source, where
    for name, folder in (("src_Tickets", "tickets"), ("src_Events", "ticket_events")):
        staged = flat(model.expressions[name].expression)
        assert f'Folder.Files(DataFolder & "\\{folder}")' in staged and 'each [Extension] = ".csv"' in staged, name
        assert "Table.Sort(" in staged and '{{"Name", Order.Ascending}}' in staged, name
    ticket_files = flat(model.expressions["TicketFiles"].expression)
    assert "Table.Combine(src_Tickets[Rows])" in ticket_files
    assert 'DateTime.FromText(x, [Format = "yyyy-MM-dd HH:mm", Culture = "en-US"])' in ticket_files
    assert "Table.Combine(src_Events[Rows])" in flat(model.expressions["EventFiles"].expression)
    intervals = flat(model.expressions["EventIntervals"].expression)
    assert 'Table.NestedJoin(Keyed, {"ticket_id", "next_seq"}, Following, {"ticket_id", "event_seq"}' in intervals
    assert 'else if [to_status] = "Closed" then null else AsOf' in intervals
    assert "fnBusinessMinutes([event_at], [interval_end])" in intervals
    tests = flat(model.tables["TestBusinessHours"].partition_source or "")
    assert "fnBusinessMinutes([start], [end])" in tests and "[actual_minutes] = [expected_minutes]" in tests
    facts = flat(model.tables["FactTickets"].partition_source or "")
    assert "Table.Group(EventIntervals" in facts and "if [events] > 1 then [new_bmin] else null" in facts
    assert flat(model.expressions["HolidayList"].expression) == "List.Buffer(Holidays[Date])"


def test_no_query_reads_a_file_and_references_another_query(model):
    """A partition may access a data source or reference other queries, not both (privacy firewall)."""
    queries = m_queries(model)
    parameters = {n for n, e in model.expressions.items() if "IsParameterQuery = true" in e.expression}
    assert firewall_violations(queries, parameters) == []


def test_only_the_staging_queries_read_files_and_every_file_is_read_once(model):
    queries = m_queries(model)
    readers = {name for name, source in queries.items() if SOURCE_CALL.search(m_code(source))}
    assert readers == set(STAGING)
    reads = [
        re.findall(r"(?:File\.Contents|Folder\.Files)\(DataFolder & \"([^\"]+)\"\)", s)
        for s in map(queries.get, STAGING)
    ]
    assert all(len(r) == 1 for r in reads), reads
    assert len({r[0] for r in reads}) == len(STAGING)  # one expression per file or folder
    for name in STAGING:
        assert model.expressions[name].description.startswith("Staging, not loaded: "), name
        assert model.expressions[name].annotations.get("PBI_ResultType") == "Table", name
    for staging, consumers in CONSUMERS.items():
        used = {name for name, source in queries.items() if name != staging and references(source, staging)}
        assert used == consumers, staging


def test_staging_queries_are_listed_in_the_query_order(model):
    order = re.findall(r'"([^"]+)"', model.annotations["PBI_QueryOrder"])
    assert order[:4] == ["DataFolder", "StartDate", "EndDate", "AsOf"]
    assert list(STAGING) == order[4 : 4 + len(STAGING)]
    assert set(order) == set(model.expressions) | {n for n, t in model.tables.items() if t.partition_kind == "m"}


def test_mutation_a_file_read_next_to_a_reference_is_caught():
    parameters = {"DataFolder", "AsOf"}
    reader = 'let Source = Csv.Document(File.Contents(DataFolder & "\\priorities.csv"), [Delimiter = ","]) in Source'
    queries = {
        "DataFolder": '"C:\\data" meta [IsParameterQuery = true]',
        "AsOf": "#datetime(2025, 9, 30, 18, 0, 0) meta [IsParameterQuery = true]",
        "EventIntervals": "let Source = 1 in Source",
        "src_Priorities": reader,
        "FactTickets": reader.replace("in Source", 'in Table.NestedJoin(Source, {}, EventIntervals, {}, "X")'),
        "ExportInfo": 'let Source = #table({}, {{AsOf, Folder.Files(DataFolder & "\\tickets")}}) in Source',
        "DimTeam": 'let T = Folder.Files(DataFolder & "\\x"), Joined = Table.Join(T, {}, DimAgent, {}) in Joined',
        "DimAgent": "let Source = src_Priorities in Source",
    }
    assert firewall_violations(queries, parameters) == ["DimTeam", "FactTickets"]


def test_mutation_names_in_texts_comments_and_steps_are_not_references():
    parameters = {"DataFolder"}
    read = 'File.Contents(DataFolder & "\\a.csv")'
    queries = {
        "DataFolder": '"C:\\data" meta [IsParameterQuery = true]',
        "EventIntervals": "let Source = 1 in Source",
        "Holidays": "let Source = 1 in Source",
        "InText": f'let Source = {read}, Note = "EventIntervals" in Source',
        "InComment": f"let Source = {read} // EventIntervals\n in Source",
        "InBlockComment": f"let Source = {read} /* EventIntervals */ in Source",
        "Shadowed": f"let Source = {read},\n    Holidays = Table.RowCount(Source) in Holidays",
        "AsField": f"let Source = {read}, Column = Source[Holidays] in Column",
    }
    assert firewall_violations(queries, parameters) == []


def test_49_measures_with_description_folder_and_format(model):
    measures = model.tables["_Measures"].measures
    assert set(measures) == set(MEASURES)
    for name, (folder, fmt) in MEASURES.items():
        m = measures[name]
        assert m.description, name
        assert m.display_folder == folder, name
        if fmt in (HOURS, RANK_FORMAT):
            assert m.format_string is None and flat(m.format_string_definition or "") == fmt, name
        else:
            assert m.format_string == fmt and m.format_string_definition is None, name


def test_measure_definitions_of_section_7(model):
    m = {name: flat(x.expression) for name, x in model.tables["_Measures"].measures.items()}
    for name, dax in DEFINITIONS.items():
        assert m[name] == dax, name
    assert "TREATAS(s, FactTicketEvents[From status])" in m["Tickets in status"]
    assert "REMOVEFILTERS(DimStatus)" in m["Tickets in status"] and m["Tickets in status"].endswith(
        "RETURN entered - left"
    )
    for name in ("Backlog in age bucket", "Oldest open ticket (days)"):
        assert "GROUPBY(ev, FactTicketEvents[Ticket ID], FactTicketEvents[Ticket created date], " in m[name], name
        assert '"@open", SUMX(CURRENTGROUP(), FactTicketEvents[Backlog delta])' in m[name], name
    assert "DATEDIFF(FactTicketEvents[Ticket created date], d, DAY) >= lo" in m["Backlog in age bucket"]
    assert "FactTicketEvents[Event date] <= d - 30" in m["Backlog change 30 d"]
    assert m["Ranking value"].endswith(
        "IF([Created] >= 20, SWITCH(c, 0, [Resolved], 1, [SLA resolution met %], 2, [SLA first response met %], "
        "3, [CSAT average]))"
    )
    # the scorecard groups by agent and team, so the rank restores both columns and runs over all agents shown
    assert (
        "RANKX(FILTER(ALLSELECTED(DimAgent[Agent name], DimAgent[Team name]), NOT ISBLANK([Ranking value])), "
        "[Ranking value], , DESC, DENSE)" in (m["Agent rank"])
    )
    for name in [n for n in MEASURES if n.startswith("Δ PY ")]:
        assert "'Time intelligence'[Time calculation] = \"PY\"" in m[name], name
        assert 'IF(ISBLANK(p), "vs PY: n/a", "vs PY: " & FORMAT(' in m[name], name
        assert "IF(EDATE(edge, -12) >= first, " in m[name], name  # n/a without a full previous year


def test_calculation_group_items_in_order(model):
    group = model.tables["Time intelligence"].calculation_group
    assert group is not None and group.precedence == 1
    assert [i.name for i in group.items] == list(ref.CALCULATIONS) == list(ITEMS)
    for item in group.items:
        assert flat(item.expression) == ITEMS[item.name], item.name
        assert item.description, item.name
    formats = {i.name: flat(i.format_string_definition or "") for i in group.items}
    assert formats["YoY"] == YOY_FORMAT and formats["YoY %"] == '"+0.0%;-0.0%;0.0%"'
    assert all(not formats[n] for n in ("Current", "PY", "YTD", "PYTD", "R12"))


def test_field_parameter_entries_are_measures(model):
    table = model.tables["Rank agents by"]
    entries = re.findall(r"\(\"([^\"]+)\", NAMEOF\('_Measures'\[([^\]]+)\]\), (\d+)\)", table.partition_source or "")
    assert entries == [(m, m, str(i)) for i, m in enumerate(ref.RANK_BY)]
    assert all(m in model.tables["_Measures"].measures for _, m, _ in entries)
    assert '"kind": 2' in (table.raw or "") and table.partition_kind == "calculated"


def test_role_filters_three_tables(model):
    assert [r.name for r in model.roles] == ["Team lead"]
    role = model.roles[0]
    assert role.model_permission == "read" and role.description
    perms = {t: flat(e) for t, e in role.table_permissions.items()}
    assert perms == {
        "DimTeam": f"DimTeam[Team ID] {LEAD}",
        "DimAgent": f"DimAgent[Agent ID] = 0 || DimAgent[Team ID] {LEAD}",
        "Security": "Security[User e-mail] = LOWER(USERPRINCIPALNAME())",
    }


def _expressions(model):
    out = [(f"measure {m.name}", m.expression) for m in model.tables["_Measures"].measures.values()]
    out += [(f"format {m.name}", m.format_string_definition or "") for m in model.tables["_Measures"].measures.values()]
    out += [(f"item {i.name}", i.expression) for i in model.tables["Time intelligence"].calculation_group.items]
    out += [(f"role {t}", e) for r in model.roles for t, e in r.table_permissions.items()]
    return out


def test_dax_references_resolve(model):
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    measures = {m for tab in model.tables.values() for m in tab.measures}
    for where, dax in _expressions(model):
        for quoted, bare, item in REF.findall(dax):
            table = quoted or bare
            assert (table, item) in cols, (where, table, item)
        for item in UNQUALIFIED.findall(REF.sub("", dax)):
            assert item in measures or item.startswith("@"), (where, item)


def test_fn_business_minutes_body_pinned(model):
    """The M function keeps the rules of tools/bizhours.py: Monday to Friday, 08:00 to 18:00, holidays excluded."""
    body = flat(model.expressions["fnBusinessMinutes"].expression)
    for token in (
        "finish < start then null",
        "Date.DayOfWeek(d, Day.Monday) >= 5",
        "List.Contains(HolidayList, d)",
        "#time(8, 0, 0)",
        "#time(18, 0, 0)",
        "if e > s then Duration.TotalMinutes(e - s) else 0",
    ):
        assert token in body, token


def test_no_table_level_isfiltered(model):
    """ISFILTERED on a whole table is TRUE under the role's filter on a hidden key column and blanks the measure."""
    table_level = re.compile(r"ISFILTERED\s*\(\s*'?[^'\[\]()]+'?\s*\)", re.IGNORECASE)
    for where, dax in _expressions(model):
        assert not table_level.search(dax), where


def test_mutation_unknown_column_is_caught(model):
    bad = [("measure X", "SUM(FactTickets[Clock bmn])")]
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    missing = [(w, t or b, i) for w, dax in bad for t, b, i in REF.findall(dax) if ((t or b), i) not in cols]
    assert missing == [("measure X", "FactTickets", "Clock bmn")]


def test_constants_cover_the_whole_period():
    assert ref.START_DATE == date(2024, 1, 1) and ref.AS_OF.date() == ref.END_DATE
