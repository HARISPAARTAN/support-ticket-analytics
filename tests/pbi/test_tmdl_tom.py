"""Optional: parse the TMDL folder with Microsoft's own TmdlSerializer (the parser Desktop uses).

Skipped unless build/tom/ holds the TOM client (tools/pbi/copy_tom.py) and pythonnet with a .NET runtime is
available (uv sync --group pbi). A TMDL syntax error or an unresolved link (a relationship or sort-by column that does
not exist) fails here with the reason. DAX is not evaluated offline, so tests/pbi/test_tmdl_lint.py resolves the DAX
references.
"""

import sys
from pathlib import Path

import pytest

import reference as ref
from pbir import PROJECT

pytestmark = [pytest.mark.pbi, pytest.mark.tom]
ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "build" / "tom"
MODEL = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
TABLES = {
    "DimDate", "DimPriority", "DimTeam", "DimAgent", "DimCategory", "DimChannel", "DimCustomer", "DimStatus",
    "DimAgeBucket", "FactTickets", "FactTicketEvents", "Security", "ExportInfo", "TestBusinessHours", "_Measures",
    "Time intelligence", "Rank agents by",
}  # fmt: skip


@pytest.fixture(scope="module")
def serializer():
    if not (LIB / "Microsoft.AnalysisServices.Tabular.dll").exists():
        pytest.skip("TOM client not in build/tom (uv run python tools/pbi/copy_tom.py --from <folder>)")
    try:
        from pythonnet import load

        try:
            load("coreclr")
        except RuntimeError:
            pass  # a runtime is already loaded in this process
        import clr
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pythonnet or the .NET runtime is not available: {exc}")
    sys.path.append(str(LIB))
    clr.AddReference(str(LIB / "Microsoft.AnalysisServices.Tabular.dll"))
    from Microsoft.AnalysisServices.Tabular import TmdlSerializer

    return TmdlSerializer


@pytest.fixture(scope="module")
def database(serializer):
    return serializer.DeserializeDatabaseFromFolder(str(MODEL))


def test_tom_parses_and_validates_the_model(database):
    assert {t.Name for t in database.Model.Tables} == TABLES
    assert database.CompatibilityLevel == 1606
    result = database.Model.Validate()
    errors = [str(e.Message) for e in result.Errors] if result.ContainsErrors else []
    assert errors == []
    assert {e.Name for e in database.Model.Expressions} >= {"DataFolder", "AsOf", "fnBusinessMinutes", "EventIntervals"}


def test_tom_reads_measures_relationships_calculation_group_and_role(database):
    tables = {t.Name: t for t in database.Model.Tables}
    measures = list(tables["_Measures"].Measures)
    assert len(measures) == 49 and all(str(m.Description) for m in measures)
    relationships = list(database.Model.Relationships)
    assert len(relationships) == 10 and sum(1 for r in relationships if not r.IsActive) == 1
    group = tables["Time intelligence"].CalculationGroup
    items = sorted(group.CalculationItems, key=lambda i: i.Ordinal)
    assert [i.Name for i in items] == list(ref.CALCULATIONS)
    assert group.Precedence == 1
    roles = {r.Name: r for r in database.Model.Roles}
    assert list(roles) == ["Team lead"]
    assert {p.Table.Name for p in roles["Team lead"].TablePermissions} == {"DimTeam", "DimAgent", "Security"}
