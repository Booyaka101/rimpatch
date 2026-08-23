from __future__ import annotations

from pathlib import Path

import pytest

from rimpatch import locate
from rimpatch.discover import expand_mod_paths, resolve_load_order
from rimpatch.engine import Report, check

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_autodetect(monkeypatch):
    """A test must never pick up whatever RimWorld happens to be on the machine."""
    monkeypatch.setenv(locate.OFF_ENV, "1")


@pytest.fixture
def run():
    """run("base", "patcher") -> Report for those fixture mods in that load order."""

    def _run(*names: str, strict: bool = False, warnings: bool = True) -> Report:
        mods = expand_mod_paths([FIXTURES / name for name in names])
        order = resolve_load_order(mods, None, auto_order=False)
        return check(order, "1.6", strict=strict, warnings=warnings)

    return _run


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
