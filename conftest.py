"""Keep archived phase assertions out of the current-state default suite.

Historical test sources remain byte-for-byte unchanged and can be run with
``pytest --include-historical``.
"""

import json
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--include-historical",
        action="store_true",
        default=False,
        help="Run archived phase-specific tests alongside current-state tests.",
    )


def pytest_collection_modifyitems(config, items):
    registry_path = Path(__file__).parent / "tests" / "test_lineage.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    archived_modules = set(registry["archived_modules"])
    archived_nodeids = set(registry["archived_nodeids"])

    if config.getoption("--include-historical"):
        return

    reason = "Archived phase contract; run with --include-historical for forensic reproduction."
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        module_name = Path(str(item.fspath)).name
        if module_name in archived_modules or item.nodeid in archived_nodeids:
            item.add_marker(marker)
