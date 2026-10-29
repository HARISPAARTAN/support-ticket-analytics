"""Shared fixtures: the committed data loaded once, and the six-ticket mini data set."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import reference

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "tests" / "fixtures" / "mini"
SHARED = ("priorities.csv", "holidays.csv", "business_hours_cases.csv")  # taken from data/, not duplicated


def build_mini(target: Path) -> Path:
    """The mini tickets, events, agents and teams with the committed priorities, holidays and cases."""
    shutil.copytree(MINI, target, dirs_exist_ok=True)
    for name in SHARED:
        shutil.copy(ROOT / "data" / name, target / name)
    return target


@pytest.fixture(scope="session")
def model() -> reference.Model:
    return reference.load(ROOT / "data")


@pytest.fixture(scope="session")
def mini(tmp_path_factory: pytest.TempPathFactory) -> reference.Model:
    return reference.load(build_mini(tmp_path_factory.mktemp("mini")))
