"""The documentation agrees with the code: README outline in both languages, the DAX in docs/measures.md, the M and
Python blocks and the cases in docs/business-hours.md, the tables and columns in docs/data-model.md, the decision
records, the Desktop checklist and the architecture diagram."""

import csv
import json
import re
from pathlib import Path

import pytest

from pbir import PROJECT
from tmdl import load_model

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MODEL = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
PAGES = ROOT / "tools" / "pbi" / "pages.json"
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
FENCE = "`" * 3
README_EN = [
    "Status",
    "Client brief",
    "Live demo",
    "What it does",
    "How it works",
    "Data model",
    "Getting started",
    "Project layout",
    "Decisions",
    "Compared with the original delivery",
    "Licence and data note",
]
README_DE = [
    "Status",
    "Kundenauftrag",
    "Live-Demo",
    "Was es kann",
    "So funktioniert es",
    "Datenmodell",
    "Erste Schritte",
    "Projektstruktur",
    "Entscheidungen",
    "Im Vergleich zur ursprünglichen Lieferung",
    "Lizenz und Hinweis zu den Daten",
]
ADRS = [
    "0001-business-hours-in-power-query.md",
    "0002-sla-outcome-per-ticket-by-creation-date.md",
    "0003-quarterly-export-files.md",
]
CALCULATIONS = ["Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12"]


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def headings(text: str, level: int) -> list[str]:
    outside = re.sub(rf"{FENCE}.*?{FENCE}", "", text, flags=re.DOTALL)
    return re.findall(rf"^{'#' * level} (.+)$", outside, flags=re.MULTILINE)


def sections(text: str, level: int) -> dict[str, str]:
    parts = re.split(rf"^{'#' * level} ", text, flags=re.MULTILINE)[1:]
    return {part.split("\n", 1)[0].strip(): part for part in parts}


def block(section: str, language: str) -> str:
    """The first code block of `language` in a section."""
    match = re.search(rf"{FENCE}{language}\n(.*?)\n{FENCE}", section, flags=re.DOTALL)
    assert match, f"no {language} block"
    return match.group(1)


def code_lines(section: str, language: str = "dax") -> list[str]:
    """The lines of the first block of a section, each stripped (indentation is not compared)."""
    return [line.strip() for line in block(section, language).split("\n")]


def stripped(expression: str) -> list[str]:
    return [line.strip() for line in expression.split("\n")]


@pytest.mark.parametrize(("name", "outline"), [("README.md", README_EN), ("README.de.md", README_DE)])
def test_readme_follows_the_umbrella_outline(name, outline):
    text = read(ROOT / name)
    assert text.startswith("# Support Ticket Analytics\n")
    assert headings(text, 2) == outline
    for badge in ("actions/workflows/ci.yml/badge.svg", "actions/workflows/pages.yml/badge.svg", "img.shields.io"):
        assert badge in text, badge
    other = "README.de.md" if name == "README.md" else "README.md"
    assert f"]({other})" in text
    assert text.rstrip().endswith(FOOTER)
    for adr in ADRS:
        assert f"](docs/adr/{adr})" in text, adr
    for image in re.findall(r"!\[[^\]]*\]\((docs/[^)]+)\)", text):
        assert (ROOT / image).is_file(), image


def test_readme_states_the_canvas_and_the_replica_scope_exactly():
    text = read(ROOT / "README.md")
    assert "seven on a 1280 × 720 canvas" in text
    assert "the SLA tooltip page on 320 × 296, which is not on the canvas" in text
    assert "It leaves out" in text
    assert "every number" not in text.lower()
    assert "31 headline checks" in text


def reading_pages() -> tuple[dict, list[dict], list[dict]]:
    """The report definition, its canvas pages, and the canvas pages that carry slicers."""
    report = json.loads(read(PAGES))
    canvas = [p for p in report["pages"] if p.get("type") != "Tooltip"]
    return report, canvas, [p for p in canvas if p["slicers"]]


def reconciliation_rows() -> int:
    return len(re.findall(r"^\| R\d+ \|", read(DOCS / "reconciliation.md"), flags=re.MULTILINE))


def test_readme_facts_match_the_project(model):
    text = read(ROOT / "README.md")
    report, canvas, slicer_pages = reading_pages()
    tooltip = [p for p in report["pages"] if p.get("type") == "Tooltip"]
    assert len(report["pages"]) == 8 and len(tooltip) == 1 and len(canvas) == 7
    assert "Eight report pages with the theme Quillstack Dark" in text
    # the header: every page but the tooltip page
    assert [p["id"] for p in report["pages"] if p.get("header") is False] == [tooltip[0]["id"]]
    assert "Every page except the tooltip page has a header with the data date and page buttons." in text
    # the slicers: which pages, which fields, where the snapshot date replaces the date range
    names = [p["displayName"] for p in slicer_pages]
    assert names == ["Overview", "SLA compliance", "Teams and agents", "Backlog and ageing"]
    assert f"The four reading pages with slicers ({', '.join(names)}) have a slicer row" in text
    assert {tuple(p["slicers"]) for p in slicer_pages if p["id"] != "backlog"} == {
        ("Date", "Team", "Priority", "Channel")
    }
    assert [p["slicers"] for p in slicer_pages if p["id"] == "backlog"] == [
        ["Snapshot date", "Team", "Priority", "Channel"]
    ]
    assert "(Date, on Backlog and ageing a snapshot date instead, Team, Priority, Channel, Reset)" in text
    # the tiles: a row on each reading page, the change against the previous year on Overview only
    tile_row = report["tiles"]["y"]
    assert [
        p["displayName"] for p in canvas if any(v["type"] == "card" and v["y"] == tile_row for v in p["visuals"])
    ] == names
    delta = [p["displayName"] for p in canvas if any(v.get("title", "").endswith(" vs PY") for v in p["visuals"])]
    assert delta == ["Overview"]
    assert "a row of KPI tiles (on Overview with the change against the previous year)" in text
    # the counts
    assert f"{len(model.tables['_Measures'].measures)} measures in `_Measures`" in text
    checks = reconciliation_rows()
    assert checks == 31
    assert f"{checks} headline checks reconciled against an independent pandas reference" in text
    assert f"computes the {checks} headline checks with pandas" in text
    # what the replica leaves out
    live = text.split("## Live demo", 1)[1].split("\n## ", 1)[0]
    assert "It leaves out" in live
    for left_out in (
        "the Ticket explorer's status history and time in status",
        "the backlog by status over time",
        "the tier split of created by category",
        "the previous-year backlog line",
        "P90 times and CSAT satisfied %",
        "the YTD, PYTD and R12 matrix and the current, PY and YoY matrix",
        "day-level dates",
        "the role `Team lead`",
        "the SLA tooltip page",
        "the bookmarks (a Reset button instead)",
        "the Info and Reconciliation pages",
    ):
        assert left_out in live, left_out
    for phrase in ("every number", "every measure", "both pass", "that is checked"):
        assert phrase not in text.lower(), phrase


def test_german_readme_states_the_same_facts(model):
    text = read(ROOT / "README.de.md")
    _, _, slicer_pages = reading_pages()
    names = [p["displayName"] for p in slicer_pages]
    assert "Acht Berichtsseiten im Design Quillstack Dark" in text
    assert "Jede Seite außer der Tooltip-Seite hat eine Kopfzeile mit dem Datenstand und Seitenschaltflächen." in text
    assert f"Die vier Leseseiten mit Slicern ({', '.join(names)}) haben eine Slicer-Zeile" in text
    assert "(Date, auf Backlog and ageing stattdessen ein Stichtag, Team, Priority, Channel, Reset)" in text
    assert "(auf Overview mit der Veränderung zum Vorjahr)" in text
    assert f"{len(model.tables['_Measures'].measures)} Kennzahlen in `_Measures`" in text
    checks = reconciliation_rows()
    assert f"{checks} Prüfwerte, gegen eine unabhängige pandas-Referenz abgeglichen" in text
    assert f"berechnet `tools/reference.py` die {checks} Prüfwerte mit pandas" in text
    live = text.split("## Live-Demo", 1)[1].split("\n## ", 1)[0]
    assert "Nicht enthalten sind" in live
    for left_out in (
        "der Statusverlauf und die Zeit je Status aus dem Ticket explorer",
        "der Rückstand nach Status im Zeitverlauf",
        "die Aufteilung nach Kundenstufe bei den Tickets je Kategorie",
        "die Vorjahreslinie des Rückstands",
        "P90-Zeiten und CSAT satisfied %",
        "die Matrix mit YTD, PYTD und R12 und die Matrix mit Current, PY und YoY",
        "Tagesdaten",
        "die Rolle `Team lead`",
        "die Tooltip-Seite SLA tooltip",
        "die Lesezeichen (stattdessen eine Schaltfläche Reset)",
        "die Seiten Info und Reconciliation",
    ):
        assert left_out in live, left_out
    for phrase in ("jede kennzahl mit pandas", "beide bestehen", "zweimal dokumentiert und geprüft"):
        assert phrase not in text.lower(), phrase


def test_brief_is_the_same_in_the_readme_and_the_brief():
    quote = re.search(r"^> (.+)$", read(DOCS / "brief.md"), flags=re.MULTILINE).group(1)
    assert f"> {quote}" in read(ROOT / "README.md")
    assert FOOTER in read(DOCS / "brief.md")


def test_every_measure_is_documented_with_its_dax(model):
    doc = sections(read(DOCS / "measures.md"), 3)
    measures = model.tables["_Measures"].measures
    assert len(measures) == 49
    for name, measure in measures.items():
        assert name in doc, name
        assert code_lines(doc[name]) == stripped(measure.expression), f"{name}: the DAX differs from the TMDL"
        assert f"Folder `{measure.display_folder}`" in doc[name], name
        assert measure.description in doc[name], name
        if measure.format_string_definition:
            assert measure.format_string_definition in doc[name], name
        elif measure.format_string:
            assert f"format `{measure.format_string}`" in doc[name], name
        else:
            assert "text, no format string" in doc[name], name


def test_every_calculation_item_is_documented_with_its_dax(model):
    doc = sections(read(DOCS / "measures.md"), 3)
    items = model.tables["Time intelligence"].calculation_group.items
    assert [item.name for item in items] == CALCULATIONS
    for item in items:
        assert code_lines(doc[item.name]) == stripped(item.expression), f"{item.name}: the DAX differs from the TMDL"
        if item.format_string_definition:
            assert item.format_string_definition in doc[item.name], item.name


def test_field_parameter_and_role_are_documented(model):
    doc = sections(read(DOCS / "measures.md"), 2)
    assert stripped(model.tables["Rank agents by"].partition_source) == code_lines(
        doc["Field parameter Rank agents by"]
    )
    role = model.roles[0]
    filters = sections(doc[f"Role {role.name}"], 3)
    assert set(filters) == {f"Filter on {table}" for table in role.table_permissions}
    for table, expression in role.table_permissions.items():
        assert code_lines(filters[f"Filter on {table}"]) == stripped(expression), table


def test_business_hours_blocks_equal_the_code(model):
    doc = sections(read(DOCS / "business-hours.md"), 2)
    function = model.expressions["fnBusinessMinutes"].expression
    assert code_lines(doc["Power Query"], "m") == stripped(function)
    assert block(doc["Python"], "python") in read(ROOT / "tools" / "bizhours.py")


def test_business_hours_cases_equal_the_csv():
    doc = sections(read(DOCS / "business-hours.md"), 2)["Test cases"]
    rows = re.findall(r"^\| (\d+) \| ([\d: -]+) \| ([\d: -]+) \| (\d+|blank) \| (.+) \|$", doc, flags=re.MULTILINE)
    with (ROOT / "data" / "business_hours_cases.csv").open(encoding="utf-8", newline="") as handle:
        cases = [
            (c["case_id"], c["start"], c["end"], c["expected_minutes"] or "blank", c["note"])
            for c in csv.DictReader(handle)
        ]
    assert [tuple(part.strip() for part in row) for row in rows] == cases
    assert len(cases) == 18


def test_data_model_lists_every_table_column_and_relationship(model):
    text = read(DOCS / "data-model.md")
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| `([^`\[]+)` \| [^|]+ \| (.+) \|$", text, re.MULTILINE)}
    for name, table in model.tables.items():
        assert name in rows, name
        for column in table.columns:
            assert f"`{column}`" in rows[name], f"{name}[{column}]"
    found = re.findall(r"^\| `(\w+)\[([^\]]+)\]` \| `(\w+)\[([^\]]+)\]` \| (yes|no[^|]*) \|$", text, flags=re.MULTILINE)
    pairs = {(a, b, c, d, active.startswith("yes")) for a, b, c, d, active in found}
    expected = {(*r.from_column.split(".", 1), *r.to_column.split(".", 1), r.is_active) for r in model.relationships}
    assert pairs == expected


def test_data_model_lists_every_data_file():
    text = read(DOCS / "data-model.md")
    files = sorted((ROOT / "data").rglob("*.csv"))
    assert len(files) == 19
    for path in files:
        assert f"`{path.relative_to(ROOT).as_posix()}`" in text, path.name


def test_decision_records():
    found = sorted(p.name for p in (DOCS / "adr").glob("*.md"))
    assert found == ADRS
    for name in ADRS:
        text = read(DOCS / "adr" / name)
        assert text.startswith(f"# ADR {name[:4]}: ")
        assert re.search(r"^Status: accepted \(\d{4}-\d{2}-\d{2}\)$", text, flags=re.MULTILINE), name
        assert headings(text, 2)[:3] == ["Context", "Decision", "Consequences"], name


def test_desktop_session_is_a_neutral_checklist():
    text = read(DOCS / "desktop-session.md")
    assert headings(text, 2)[-1] == "After the session"
    assert "assistant" not in text.lower()
    assert not re.search(r"\b\d+\s*(?:min|minutes|hours?)\b", text), "no time estimates in the checklist"
    steps = re.findall(r"^\d+\. (\w+)", sections(text, 2)["Steps"], flags=re.MULTILINE)
    assert len(steps) == 9 and all(word[0].isupper() for word in steps)


def test_architecture_diagram_is_self_contained():
    svg = read(DOCS / "architecture.svg")
    assert svg.startswith("<svg ") and "<title" in svg and "<desc" in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "") and "https://" not in svg
    assert "<image" not in svg and "@import" not in svg
    for label in ("tools/make_data.py", "Power Query", "fnBusinessMinutes", "TMDL model", "PBIR report"):
        assert label in svg, label
    for label in ("tools/reference.py", "replica.json", "expected.json", "HTML replica", "Reconciliation R1 to R31"):
        assert label in svg, label


def test_docs_named_by_the_spec_exist():
    for name in ("brief.md", "data-model.md", "business-hours.md", "measures.md", "architecture.md", "handover.md"):
        assert (DOCS / name).is_file(), name
    for name in ("desktop-session.md", "reconciliation.md", "screenshots/SHOTLIST.md"):
        assert (DOCS / name).is_file(), name
    handover = headings(read(DOCS / "handover.md"), 2)
    for heading in (
        "Refresh",
        "Adding a quarter's export",
        "Adding a holiday",
        "Adding a team lead",
        "When a reconciliation pair fails",
        "Limits of the SLA attribution",
        "Updating Faker or numpy",
    ):
        assert heading in handover, heading
    assert "needs regeneration" in read(DOCS / "handover.md")
