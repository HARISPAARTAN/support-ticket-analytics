"""Regenerate the report: tools/pbi/build_report.py, then the parts of this report that the shared generator does not
cover. Run this script instead of build_report.py:

    uv run python tools/pbi/report_extras.py

The additions are driven by keys of tools/pbi/pages.json that build_report.py ignores:

- `navigation` (top level): page buttons in the header of every page with a header, one per listed page id;
- `tile_slicers` (top level): slicers of the slicer row shown as horizontal tiles (Priority P1 to P4);
- `drillthrough` (page): the page becomes a drill-through page on that [table, column] and keeps all filters;
- `back_button` (page): a Back button at that position;
- `visibility` (page): `HiddenInViewMode`, a page shown only in Desktop's edit mode;
- `no_filter_from` (page): content visuals (by index in `visuals`) whose selection filters nothing on the page;
- `gradient_on: "text"` (visual): the `gradient` colours the cell text instead of the cell background, so every value
  keeps its contrast against the surface (a background gradient under the theme's light text would not);
- on every page, a selected data point never filters a slicer (visualInteractions `NoFilter`).

Same rules as build_report.py: stable names, sorted keys, two-space indent, UTF-8 without BOM, LF; run it only until
the first Desktop save (docs/desktop-session.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # lets `python tools/pbi/report_extras.py` import its neighbours

import build_report  # noqa: E402
from build_report import DEFINITION, SPEC_PATH, Colours, _button_objects, _lit, _text, write_json  # noqa: E402
from pbir import Visual, field_ref, stable_name  # noqa: E402

PASSIVE = {"card", "slicer", "textbox", "actionButton"}  # a selection on these filters nothing


def _button(name: str, x: float, y: float, w: float, h: float, label: str, link: dict, colours: Colours) -> dict:
    """An action button with the Reset button's look and the given visualLink properties."""
    link = {"show": _lit("true"), "showDefaultTooltip": _lit("false"), **link}
    return Visual.from_template(
        "actionButton",
        name,
        x,
        y,
        w,
        h,
        label,
        {},
        title_hidden=True,
        extra_objects=_button_objects({"label": label}, colours),
        container={"visualLink": [{"properties": link}]},
    )


def navigation_buttons(page_id: str, spec: dict, colours: Colours) -> list[dict]:
    nav = spec["navigation"]
    names = {p["id"]: p["displayName"] for p in spec["pages"]}
    out = []
    for i, target in enumerate(nav["pages"]):
        x = nav["x"] + i * (nav["w"] + nav["gap"])
        link = {"type": _lit("'PageNavigation'"), "navigationSection": _text(target)}
        name = stable_name(page_id, "nav", target)
        out.append(
            _button(
                name, x, nav["y"], nav["w"], nav["h"], nav.get("labels", {}).get(target, names[target]), link, colours
            )
        )
    return out


def back_button(page_id: str, place: dict, colours: Colours) -> dict:
    link = {"type": _lit("'Back'")}
    return _button(stable_name(page_id, "back"), place["x"], place["y"], place["w"], place["h"], "Back", link, colours)


def interactions(page: dict, visuals: list[dict]) -> list[dict]:
    """NoFilter from every data visual to every slicer, and from the `no_filter_from` visuals to every other visual."""
    pid = page["id"]
    kinds = {v["name"]: v["visual"]["visualType"] for v in visuals}
    slicers = [n for n, k in kinds.items() if k == "slicer"]
    sources = [n for n, k in kinds.items() if k not in PASSIVE]
    pairs = {(s, t) for s in sources for t in slicers}
    for index in page.get("no_filter_from", []):
        source = stable_name(pid, str(index))
        if source not in kinds:
            raise ValueError(f"{pid}: no_filter_from names visual {index}, which does not exist")
        pairs |= {(source, t) for t, k in kinds.items() if t != source and k not in ("textbox", "actionButton")}
    return [{"source": s, "target": t, "type": "NoFilter"} for s, t in sorted(pairs)]


def drillthrough(page_id: str, field: list[str]) -> tuple[dict, dict]:
    """The pageBinding and filterConfig of a drill-through page on one column, in the shape Desktop writes."""
    entity, prop = field
    filter_name = stable_name(page_id, "drillthrough")
    binding = {
        "name": stable_name(page_id, "binding"),
        "type": "Drillthrough",
        "parameters": [
            {
                "name": stable_name(page_id, "parameter"),
                "boundFilter": filter_name,
                "fieldExpr": field_ref(entity, prop, "Column"),
            }
        ],
    }
    filters = {
        "filters": [
            {
                "name": filter_name,
                "field": field_ref(entity, prop, "Column"),
                "type": "Categorical",
                "howCreated": "Drillthrough",
            }
        ]
    }
    return binding, filters


def apply(page: dict, spec: dict, colours: Colours) -> dict[str, int]:
    pid = page["id"]
    pdir = DEFINITION / "pages" / pid
    page_json = json.loads((pdir / "page.json").read_text(encoding="utf-8"))
    visuals = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((pdir / "visuals").glob("*/visual.json"))]
    visuals.sort(key=lambda v: v["position"]["tabOrder"])
    has_header = page.get("header", True)
    head = 1 + len(spec["header"]["visuals"]) if has_header else 0
    nav = navigation_buttons(pid, spec, colours) if has_header else []
    back = [back_button(pid, page["back_button"], colours)] if page.get("back_button") else []
    ordered = visuals[:head] + nav + back + visuals[head:]
    for position, visual in enumerate(ordered):
        visual["position"]["z"] = visual["position"]["tabOrder"] = position
    for index, item in enumerate(page.get("visuals", [])):
        if item.get("gradient_on") == "text":
            target = next(v for v in ordered if v["name"] == stable_name(pid, str(index)))
            for rule in target["visual"]["objects"]["values"]:
                rule["properties"]["fontColor"] = rule["properties"].pop("backColor")
    for name in spec.get("tile_slicers", []):
        if name in page.get("slicers", []):
            slicer = next(v for v in ordered if v["name"] == stable_name(pid, "slicer", name))
            slicer["visual"]["objects"]["general"][0]["properties"]["orientation"] = _lit("1D")
    pairs = interactions(page, ordered)
    if pairs:
        page_json["visualInteractions"] = pairs
    if page.get("drillthrough"):
        page_json["type"] = "Drillthrough"
        page_json["pageBinding"], page_json["filterConfig"] = drillthrough(pid, page["drillthrough"])
    if page.get("visibility"):
        page_json["visibility"] = page["visibility"]
    write_json(pdir / "page.json", page_json)
    for visual in ordered:
        write_json(pdir / "visuals" / visual["name"] / "visual.json", visual)
    return {"buttons": len(nav) + len(back), "interactions": len(pairs)}


def main() -> int:
    build_report.main()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    colours = Colours.from_kit()
    totals = {"buttons": 0, "interactions": 0}
    for page in spec["pages"]:
        for key, count in apply(page, spec, colours).items():
            totals[key] += count
    drill = [p["id"] for p in spec["pages"] if p.get("drillthrough")]
    hidden = [p["id"] for p in spec["pages"] if p.get("visibility")]
    print(
        f"added {totals['buttons']} buttons and {totals['interactions']} NoFilter interactions; "
        f"drill-through page {', '.join(drill)}; hidden page {', '.join(hidden)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
