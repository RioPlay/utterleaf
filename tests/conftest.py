from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-ui",
        action="store_true",
        default=False,
        help="include desktop UI tests that may open windows",
    )


def pytest_collection_modifyitems(config, items):
    """Keep UI tests out of every run unless the user opts in explicitly."""
    if config.getoption("--run-ui"):
        return

    deselected = [item for item in items if "ui" in item.keywords]
    if not deselected:
        return

    selected = [item for item in items if "ui" not in item.keywords]
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
