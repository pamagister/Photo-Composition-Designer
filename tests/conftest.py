"""Shared pytest configuration.

Defines the ``fast`` baseline used by the default ``make test`` target.

Every collected test is considered part of the fast baseline unless it lives in a
module listed in :data:`SLOW_MODULES` or is explicitly decorated with
``@pytest.mark.slow``. This keeps the quick inner-loop run fast while new tests
automatically join the fast set without extra annotations. The full suite
(``make testall``) runs everything, fast and slow alike.
"""

from __future__ import annotations

import pytest

# Test modules that are too slow for the default inner-loop run. These are the
# expensive browser, page-rendering and export suites. Paths are file names
# relative to the ``tests/`` directory.
SLOW_MODULES = frozenset(
    {
        "test_browser_workflow.py",
        "test_page_rendering.py",
        "test_editor.py",
        "test_editing.py",
        "test_export.py",
        "test_MapRenderer.py",
    }
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Tag collected tests as ``fast`` or ``slow``.

    Tests in :data:`SLOW_MODULES` or carrying an explicit ``slow`` marker are
    tagged ``slow``; all other tests are tagged ``fast``. This makes
    ``pytest -m fast`` run the quick baseline subset used by ``make test``.
    """
    for item in items:
        module_path = item.nodeid.split("::", 1)[0]
        module_name = module_path.rsplit("/", 1)[-1]
        is_slow = module_name in SLOW_MODULES or item.get_closest_marker("slow") is not None
        item.add_marker(pytest.mark.slow if is_slow else pytest.mark.fast)
