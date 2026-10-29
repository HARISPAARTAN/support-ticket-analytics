"""Offline lint of the PBIR report against spec section 6 and tools/pbi/pages.json. Each check is a function that
returns its problems, so the mutation tests at the end can prove that it bites."""

import copy
import json
import re
from pathlib import Path

import pytest

import reference as ref
from build_report import bookmark_name
from build_theme import dark_tokens
from pbir import PROJECT, ROLES, iter_fields, load_report, stable_name
from tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / PROJECT["folder"]
REPORT = PBI / f"{PROJECT['name']}.Report" / "definition"
MODEL = PBI / f"{PROJECT['name']}.SemanticModel" / "definition"
SPEC = json.loads((ROOT / "tools" / "pbi" / "pages.json").read_text(encoding="utf-8"))
PAGES = [
    "Overview", "SLA compliance", "Teams and agents", "Backlog and ageing", "Ticket explorer", "Info", "SLA tooltip",
    "Reconciliation",
]  # fmt: skip
TYPES = {"Ticket explorer": "Drillthrough", "SLA tooltip": "Tooltip"}
HIDDEN = {"SLA tooltip", "Reconciliation"}
SLICER_PAGES = {
    "Overview": ["Date", "Team", "Priority", "Channel"],
    "SLA compliance": ["Date", "Team", "Priority", "Channel"],
    "Teams and agents": ["Date", "Team", "Priority", "Channel"],
    "Backlog and ageing": ["Snapshot date", "Team", "Priority", "Channel"],
}
TEMPLATE_TYPES = set(ROLES) - {"lineClusteredColumnComboChart"}  # the 13 templates of spec section 5.6
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
SLICER_ROW = (SPEC["slicer_row"]["y"], SPEC["slicer_row"]["y"] + SPEC["slicer_row"]["h"])
HEX = re.compile(r"'(#[0-9A-Fa-f]{6})'")


def lit(prop):
    return prop["expr"]["Literal"]["Value"]


def text_of(visual) -> str:
    paragraphs = (
        visual.raw["visual"].get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", [])
    )
    return "\n".join("".join(run["value"] for run in p["textRuns"]) for p in paragraphs)


def box(visual):
    p = visual.raw["position"]
    return p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]


def link_of(visual) -> dict:
    return visual.raw["visual"].get("visualContainerObjects", {}).get("visualLink", [{}])[0].get("properties", {})


def in_tab_order(pg) -> list:
    return sorted(pg.visuals, key=lambda v: v.raw["position"]["tabOrder"])


def buttons(pg, kind: str) -> list:
    """The action buttons of a page with this link type, in tab order."""
    return [v for v in in_tab_order(pg) if v.visual_type == "actionButton" and lit(link_of(v)["type"]) == f"'{kind}'"]


@pytest.fixture(scope="module")
def report():
    return load_report(REPORT)


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def page(report, name):
    return next(p for p in report.pages if p.display_name == name)


def visual(report, page_name, title):
    return next(v for v in page(report, page_name).visuals if v.title == title)


# --- checks ---------------------------------------------------------------------------------------------------------


def field_problems(raw, model, where=""):
    """Every Column, Measure and hierarchy Level node names an existing column, measure or level (kind-checked)."""
    out = []
    for entity, prop, kind in iter_fields(raw):
        table = model.tables.get(entity)
        if table is None:
            out.append(f"{where}: unknown table {entity!r}")
        elif kind == "Level":
            hierarchy, level = prop.split("/", 1)
            if level not in table.hierarchies.get(hierarchy, []):
                out.append(f"{where}: {entity} has no hierarchy level {prop!r}")
        elif prop not in (table.columns if kind == "Column" else table.measures):
            out.append(f"{where}: {entity}[{prop}] is used as a {kind} but the model has no such {kind.lower()}")
    return out


def layout_problems(pg):
    """Inside the canvas; the slicer-row slicers in the slicer row; no two visuals overlap."""
    out = []
    boxes = []
    row = {name for names in SLICER_PAGES.values() for name in names}
    for v in pg.visuals:
        x0, y0, x1, y1 = box(v)
        if x0 < 0 or y0 < 0 or x1 > pg.width or y1 > pg.height:
            out.append(f"{pg.display_name}: {v.title} leaves the canvas")
        if v.visual_type == "slicer" and v.title in row and (y0, y1) != SLICER_ROW:
            out.append(f"{pg.display_name}: slicer {v.title} is not in the slicer row")
        boxes.append((v.title or v.name, (x0, y0, x1, y1)))
    for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
        for b, (bx0, by0, bx1, by1) in boxes[i + 1 :]:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                out.append(f"{pg.display_name}: {a!r} overlaps {b!r}")
    return out


def sync_problems(report):
    """Each slicer of the slicer row syncs in a group named after it (Snapshot date only on its page)."""
    out = []
    for pg in report.pages:
        found = [v for v in pg.visuals if v.visual_type == "slicer" and v.title in SPEC["slicers"]]
        if sorted(v.title for v in found) != sorted(SLICER_PAGES.get(pg.display_name, [])):
            out.append(f"{pg.display_name}: slicers {sorted(v.title for v in found)}")
        for v in found:
            group = v.raw["visual"].get("syncGroup", {})
            if group != {"groupName": v.title, "fieldChanges": True, "filterChanges": True}:
                out.append(f"{pg.display_name}: slicer {v.title} has sync group {group}")
    return out


def reset_problems(report):
    """Each page with slicers has one Reset button whose bookmark is its page's bookmark in the group Reset filters."""
    out = []
    by_name = {b["name"]: b for b in report.bookmarks}
    for pg in report.pages:
        if pg.display_name not in SLICER_PAGES:
            continue
        reset = buttons(pg, "Bookmark")
        if len(reset) != 1:
            out.append(f"{pg.display_name}: {len(reset)} Reset buttons")
            continue
        target = lit(link_of(reset[0])["bookmark"]).strip("'")
        if target != bookmark_name(pg.name):
            out.append(f"{pg.display_name}: Reset applies {target!r}")
        bm = by_name.get(target)
        if bm is None:
            out.append(f"{pg.display_name}: bookmark {target!r} does not exist")
            continue
        state = bm["explorationState"]
        if state["activeSection"] != pg.name or list(state["sections"]) != [pg.name]:
            out.append(f"{pg.display_name}: bookmark points at {state['activeSection']!r}")
            continue
        targets = set(bm["options"]["targetVisualNames"])
        slicers = {v.name for v in pg.visuals if v.visual_type == "slicer"}
        if not bm["options"].get("applyOnlyToTargetVisuals") or not slicers <= targets:
            out.append(f"{pg.display_name}: bookmark misses slicers {sorted(slicers - targets)}")
    wanted = {"Reset filters": [bookmark_name(p.name) for p in report.pages if p.display_name in SLICER_PAGES]}
    if report.bookmark_groups != wanted:
        out.append(f"bookmark groups are {report.bookmark_groups}")
    return out


def navigation_problems(report):
    """Every page with a header has the five page buttons, each opening an existing page."""
    out = []
    ids = {p.name for p in report.pages}
    for pg in report.pages:
        if pg.page_type == "Tooltip":
            continue
        targets = [lit(link_of(v)["navigationSection"]).strip("'") for v in buttons(pg, "PageNavigation")]
        if targets != SPEC["navigation"]["pages"] or not set(targets) <= ids:
            out.append(f"{pg.display_name}: page buttons open {targets}")
    return out


def drillthrough_problems(report):
    out = []
    explorer = page(report, "Ticket explorer")
    field = {"Column": {"Expression": {"SourceRef": {"Entity": "FactTickets"}}, "Property": "Ticket number"}}
    binding = explorer.raw.get("pageBinding") or {}
    filters = explorer.raw.get("filterConfig", {}).get("filters", [])
    if explorer.page_type != "Drillthrough" or binding.get("type") != "Drillthrough":
        out.append("Ticket explorer is not a drill-through page")
    if explorer.drillthrough_fields != [field] or binding.get("acceptsFilterContext", "Default") != "Default":
        out.append(f"Ticket explorer drills on {explorer.drillthrough_fields}")
    bound = [p["boundFilter"] for p in binding.get("parameters", [])]
    if [f["name"] for f in filters if f.get("howCreated") == "Drillthrough"] != bound or not bound:
        out.append("the drill-through parameter has no drill-through filter")
    if len(buttons(explorer, "Back")) != 1:
        out.append("Ticket explorer has no Back button")
    return out


def tooltip_problems(report):
    out = []
    tip = page(report, "SLA tooltip")
    if (tip.page_type, tip.visibility, tip.width, tip.height) != ("Tooltip", "HiddenInViewMode", 320, 240):
        out.append("the tooltip page is not a hidden 320 x 240 tooltip page")
    if (tip.raw.get("pageBinding") or {}).get("type") != "Tooltip":
        out.append("the tooltip page has no tooltip binding")
    for page_name, title in (
        ("SLA compliance", "SLA met % by priority"),
        ("SLA compliance", "Resolution SLA by team and priority"),
        ("SLA compliance", "SLA met % per month"),
        ("Teams and agents", "Agents ranked"),
    ):
        v = visual(report, page_name, title)
        props = v.raw["visual"]["visualContainerObjects"].get("visualTooltip", [{}])[0].get("properties", {})
        if props.get("type", {}).get("expr", {}).get("Literal", {}).get("Value") != "'ReportPage'" or (
            lit(props["section"]).strip("'") != tip.name
        ):
            out.append(f"{title}: no report-page tooltip {tip.name!r}")
    return out


def interaction_problems(report):
    """A data point selection never filters a slicer, and the arrival heatmap filters nothing."""
    out = []
    passive = {"card", "slicer", "textbox", "actionButton"}
    for pg in report.pages:
        found = {(i["source"], i["target"]): i["type"] for i in pg.raw.get("visualInteractions", [])}
        slicers = [v.name for v in pg.visuals if v.visual_type == "slicer"]
        for v in pg.visuals:
            if v.visual_type in passive:
                continue
            missing = [t for t in slicers if found.get((v.name, t)) != "NoFilter"]
            if missing:
                out.append(f"{pg.display_name}: {v.title} may filter slicers {missing}")
    overview = page(report, "Overview")
    heat = visual(report, "Overview", "Arrivals by weekday and hour")
    found = {(i["source"], i["target"]): i["type"] for i in overview.raw.get("visualInteractions", [])}
    for v in overview.visuals:
        if v.name != heat.name and v.visual_type not in ("textbox", "actionButton"):
            if found.get((heat.name, v.name)) != "NoFilter":
                out.append(f"the heatmap filters {v.title}")
    return out


def colour_problems(report, theme_colours):
    """Every colour literal in a visual is a colour of the report theme."""
    out = []
    for pg in report.pages:
        for v in pg.visuals:
            for colour in HEX.findall(json.dumps(v.raw)):
                if colour.upper() not in theme_colours:
                    out.append(f"{pg.display_name}: {v.title} uses {colour}")
    return out


# --- the lint -------------------------------------------------------------------------------------------------------


def test_eight_pages_in_order_types_and_sizes(report):
    assert [p.display_name for p in report.pages] == PAGES
    assert [p.name for p in report.pages] == [p["id"] for p in SPEC["pages"]]
    for pg in report.pages:
        size = (320, 240) if pg.display_name == "SLA tooltip" else (1280, 720)
        assert (pg.width, pg.height) == size, pg.display_name
        assert pg.page_type == TYPES.get(pg.display_name), pg.display_name
        assert pg.visibility == ("HiddenInViewMode" if pg.display_name in HIDDEN else None), pg.display_name


def test_every_bound_field_exists(report, model):
    problems = [p for pg in report.pages for v in pg.visuals for p in field_problems(v.raw, model, v.title or v.name)]
    problems += [p for b in report.bookmarks for p in field_problems(b, model, b["displayName"])]
    problems += [p for pg in report.pages for p in field_problems(pg.raw, model, pg.display_name)]
    assert not problems, problems


def test_only_the_template_visual_types(report):
    for pg in report.pages:
        for v in pg.visuals:
            assert v.visual_type in TEMPLATE_TYPES, (pg.display_name, v.visual_type)
            assert v.roles() <= ROLES[v.visual_type], (pg.display_name, v.title, v.roles())


def test_layout_slicer_row_and_no_overlaps(report):
    problems = [p for pg in report.pages for p in layout_problems(pg)]
    assert not problems, problems


def test_sync_groups(report):
    assert not sync_problems(report)


def test_snapshot_slicer_and_priority_tiles(report):
    snapshot = visual(report, "Backlog and ageing", "Snapshot date")
    assert lit(snapshot.raw["visual"]["objects"]["data"][0]["properties"]["mode"]) == "'Before'"
    for pg_name in SLICER_PAGES:
        priority = visual(report, pg_name, "Priority")
        general = priority.raw["visual"]["objects"]["general"][0]["properties"]
        assert lit(general["orientation"]) == "1D", pg_name


def test_reset_buttons_target_their_page_bookmark(report):
    assert not reset_problems(report)


def test_page_buttons(report):
    assert not navigation_problems(report)


def test_drillthrough_and_back_button(report):
    assert not drillthrough_problems(report)
    tables = [
        (pg.display_name, v.title)
        for pg in report.pages
        for v in pg.visuals
        if v.visual_type == "tableEx" and ("FactTickets", "Ticket number", "Column") in v.bound_fields()
    ]
    assert tables == [
        ("SLA compliance", "Breach list"),
        ("Backlog and ageing", "Oldest open tickets"),
        ("Ticket explorer", "Ticket"),
    ]


def test_tooltip_page_and_bindings(report):
    assert not tooltip_problems(report)


def test_visual_interactions(report):
    assert not interaction_problems(report)


def test_colours_come_from_the_theme(report):
    theme = REPORT.parent / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]
    data = json.loads(theme.read_text(encoding="utf-8"))
    tokens = dark_tokens((ROOT / PROJECT["theme"]["tokens"]).read_text(encoding="utf-8"))
    assert not colour_problems(report, set(tokens.values()))
    palette = re.search(
        r"\[\s*('#[0-9A-F]{6}'(?:,\s*'#[0-9A-F]{6}'){7})\s*\]", (ROOT / "web/kit/echarts-theme.js").read_text()
    )
    assert data["dataColors"] == [c.strip("'") for c in palette.group(1).split(", ")]


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio of two #RRGGBB colours."""

    def luminance(hex_colour: str) -> float:
        channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_gradient_text_keeps_contrast(report):
    """Every gradient stop colours text on the surface (and the banded rows on surface-2) at 4.5:1 or more."""
    tokens = dark_tokens((ROOT / PROJECT["theme"]["tokens"]).read_text(encoding="utf-8"))
    stops = []
    for pg in report.pages:
        for v in pg.visuals:
            for rule in v.raw["visual"].get("objects", {}).get("values", []):
                stops += HEX.findall(json.dumps(rule))
    assert len(stops) == 6
    for colour in stops:
        for background in ("surface", "surface-2"):
            assert contrast(colour, tokens[background]) >= 4.5, (colour, background)


def test_kpi_cards_and_their_py_lines(report):
    overview = page(report, "Overview")
    lines = sorted((v for v in overview.visuals if v.title and v.title.endswith(" vs PY")), key=lambda v: box(v)[0])
    assert [list(v.bound_fields()) for v in lines] == [
        [("_Measures", f"Δ PY {name}", "Measure")]
        for name in ("Created", "Resolved", "Backlog", "Median first response", "SLA resolution met %", "CSAT average")
    ]
    for name, titles in (
        ("SLA compliance", ["SLA first response met %", "SLA resolution met %", "Breaches", "Open breaches now"]),
        ("Teams and agents", ["Resolved", "Active agents", "Tickets per agent", "Reopen rate", "CSAT average"]),
        ("Backlog and ageing", ["Backlog", "Backlog change 30 d", "Open over 7 days", "Oldest open ticket (days)"]),
    ):
        cards = [v.title for v in page(report, name).visuals if v.visual_type == "card"]
        assert all(t in cards for t in titles), name


def test_charts_bind_what_section_6_says(report):
    created = visual(report, "Overview", "Created: current, YTD, PYTD, R12")
    assert '"Values": [[{"Literal": {"Value": "\'Current\'"}}]' in json.dumps(created.raw["filterConfig"])
    for title, page_name in (
        ("Arrivals by weekday and hour", "Overview"),
        ("Resolution SLA by team and priority", "SLA compliance"),
    ):
        rules = visual(report, page_name, title).raw["visual"]["objects"]["values"]
        assert [sorted(r["properties"]) for r in rules] == [["fontColor"]], title  # text colour, never the cell
        assert "linearGradient3" in json.dumps(rules), title
    breaches = visual(report, "SLA compliance", "Breach list")
    assert breaches.raw["visual"]["query"]["sortDefinition"]["sort"][0]["direction"] == "Descending"
    assert '"Property": "Any SLA breach"' in json.dumps(breaches.raw["filterConfig"])
    assert '"Value": "true"' in json.dumps(breaches.raw["filterConfig"])
    ranked = visual(report, "Teams and agents", "Agents ranked")
    assert ranked.raw["visual"]["query"]["queryState"]["Y"]["fieldParameters"]
    assert '"ComparisonKind": 2' in json.dumps(ranked.raw["filterConfig"]) and '"20D"' in json.dumps(ranked.raw)
    area = visual(report, "Backlog and ageing", "Backlog by status per day")
    assert '"Property": "Is open"' in json.dumps(area.raw["filterConfig"])
    assert '"Value": "true"' in json.dumps(area.raw["filterConfig"])
    assert area_colours(area) == [name for name, _, is_open, _ in ref.STATUSES if is_open]
    oldest = visual(report, "Backlog and ageing", "Oldest open tickets")
    assert "Open at end of period" in json.dumps(oldest.raw["filterConfig"])


def area_colours(v) -> list[str]:
    """The legend values that carry a series colour, in order."""
    points = v.raw["visual"]["objects"]["dataPoint"]
    return [p["selector"]["data"][0]["scopeId"]["Comparison"]["Right"]["Literal"]["Value"].strip("'") for p in points]


def test_reconciliation_cards_follow_the_reference(report):
    cards = in_tab_order(page(report, "Reconciliation"))
    cards = [v for v in cards if v.visual_type == "card" and v.title and re.match(r"R\d+ ", v.title)]
    assert [v.title.split(" ")[0] for v in cards] == [f"R{i}" for i in range(1, 31)]
    for v, (rid, _, name, *_rest) in zip(cards, ref.RECONCILIATION[:30], strict=True):
        measure = name.split(":", 1)[0]
        assert [f for f in iter_fields(v.raw["visual"]["query"])] == [("_Measures", measure, "Measure")], rid


def test_alt_text_on_every_visual(report):
    missing = [(pg.display_name, v.visual_type, v.title) for pg in report.pages for v in pg.visuals if not v.alt_text]
    assert not missing, missing


def test_header_and_info_texts(report):
    for pg in report.pages:
        if pg.page_type == "Tooltip":
            continue
        texts = [text_of(v) for v in pg.visuals if v.visual_type == "textbox"]
        assert f"Quillstack Software · {pg.display_name}" in texts, pg.display_name
    info = "\n".join(text_of(v) for v in page(report, "Info").visuals if v.visual_type == "textbox")
    for phrase in (
        "Quillstack Software is a fictional B2B software company in Lisbon, Portugal.",
        FOOTER,
        "github.com/HARISPAARTAN/support-ticket-analytics",
        "tools/make_data.py with seed 20240101",
        "Monday to Friday 08:00 to 18:00 Lisbon time",
    ):
        assert phrase in info, phrase
    assert not re.search(r"https?://", info)


def test_theme_registered_and_report_settings(report):
    assert report.theme_name == PROJECT["theme"]["file"]
    assert report.settings.get("defaultFilterActionIsDataFilter") is True
    theme = REPORT.parent / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]
    assert json.loads(theme.read_text(encoding="utf-8"))["name"] == PROJECT["theme"]["name"]


# --- mutations: each check catches a planted defect -----------------------------------------------------------------


def test_mutation_unknown_field_is_caught(report, model):
    raw = copy.deepcopy(visual(report, "SLA compliance", "Breach list").raw)
    assert not field_problems(raw, model)
    text = json.dumps(raw).replace('"Property": "Ticket number"', '"Property": "Ticket no"')
    assert len(field_problems(json.loads(text), model)) == 1
    text = json.dumps(raw).replace('"Property": "Any SLA breach"', '"Property": "Any breach"')
    assert len(field_problems(json.loads(text), model)) == 2  # the filter's field and its condition


def test_mutation_overlap_and_slicer_outside_the_row_are_caught(report):
    pg = copy.deepcopy(page(report, "Overview"))
    slicer = next(v for v in pg.visuals if v.title == "Team")
    slicer.raw["position"]["y"] = 120
    problems = layout_problems(pg)
    assert any("not in the slicer row" in p for p in problems) and any("overlaps" in p for p in problems)


def test_mutation_sync_group_bookmark_and_page_button_are_caught(report):
    broken = copy.deepcopy(report)
    slicer = next(v for v in broken.pages[0].visuals if v.title == "Channel")
    del slicer.raw["visual"]["syncGroup"]
    assert sync_problems(broken)
    reset = buttons(broken.pages[1], "Bookmark")[0]
    link_of(reset)["bookmark"] = {"expr": {"Literal": {"Value": "'" + bookmark_name("overview") + "'"}}}
    assert reset_problems(broken)
    nav = buttons(broken.pages[2], "PageNavigation")[0]
    link_of(nav)["navigationSection"] = {"expr": {"Literal": {"Value": "'nowhere'"}}}
    assert navigation_problems(broken)


def test_mutation_drillthrough_tooltip_and_interactions_are_caught(report):
    broken = copy.deepcopy(report)
    page(broken, "Ticket explorer").raw.pop("pageBinding")
    assert drillthrough_problems(broken)
    page(broken, "SLA tooltip").visibility = None
    assert tooltip_problems(broken)
    overview = page(broken, "Overview")
    overview.raw["visualInteractions"] = overview.raw["visualInteractions"][1:]
    assert interaction_problems(broken)


def test_mutation_foreign_colour_is_caught(report):
    broken = copy.deepcopy(report)
    target = visual(broken, "Teams and agents", "Tickets per agent per month")
    target.raw = json.loads(json.dumps(target.raw).replace("#C38102", "#123456", 1))
    tokens = dark_tokens((ROOT / PROJECT["theme"]["tokens"]).read_text(encoding="utf-8"))
    assert colour_problems(broken, set(tokens.values()))


def test_stable_names_are_deterministic():
    assert stable_name("overview", "16") == stable_name("overview", "16")
