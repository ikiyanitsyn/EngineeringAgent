import os

import pytest

os.environ["ENGAGENT_UNITS"] = "metric"       # tests are written in metric unless they say otherwise
os.environ["ENGAGENT_STANDARD"] = "auto"


@pytest.fixture
def imperial(monkeypatch):
    monkeypatch.setenv("ENGAGENT_UNITS", "imperial")


def pytest_collection_modifyitems(config, items):
    """Solver tests run only with `-m solver` and only when CalculiX is installed."""
    from engagent.config import find_ccx
    selected = "solver" in (config.getoption("-m") or "")
    for item in items:
        if "solver" in item.keywords:
            if not selected:
                item.add_marker(pytest.mark.skip(reason="solver test: run with -m solver"))
            elif not find_ccx():
                item.add_marker(pytest.mark.skip(reason="CalculiX (ccx) not installed"))
