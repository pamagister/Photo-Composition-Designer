"""Shared pytest configuration.

Defines the ``fast`` baseline used by the default ``make test`` target.

Every collected test is considered part of the fast baseline unless it lives in a
module listed in :data:`SLOW_MODULES` or is explicitly decorated with
``@pytest.mark.slow``. This keeps the quick inner-loop run fast while new tests
automatically join the fast set without extra annotations. The full suite
(``make testall``) runs everything, fast and slow alike.
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

import pytest

from photo_composition_designer.core.model_assets import (
    YOLO_MODEL_ENV,
    YOLO_MODEL_URL,
    default_yolo_model_path,
    repository_yolo_model_path,
)

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


def _interactive_stdin() -> bool:
    """Return whether the original stdin is an interactive terminal.

    Pytest replaces ``sys.stdin`` with a capture object, so the original stream
    is used to decide whether prompting is possible.
    """
    stdin = getattr(sys, "__stdin__", None)
    return bool(stdin is not None and stdin.isatty())


def _prompt_for_model_location(repository_path: Path, user_path: Path) -> Path | None:
    """Ask where a missing development YOLO model should be stored."""
    stdin = getattr(sys, "__stdin__", None)
    stdout = getattr(sys, "__stdout__", None)
    if stdin is None or stdout is None or not stdin.isatty():
        return None

    print("YOLO model not found.", file=stdout)
    print(f"  1) Repository cache: {repository_path}", file=stdout)
    print(f"  2) User data dir:   {user_path}", file=stdout)
    print("  3) Skip object-detection tests", file=stdout)
    print("Select 1, 2 or 3 [1]: ", end="", file=stdout, flush=True)

    answer = stdin.readline().strip().lower()
    if answer in {"", "1", "repo", "repository"}:
        return repository_path
    if answer in {"2", "user", "appdata"}:
        return user_path
    return None


def _download_yolo_model(destination: Path) -> None:
    """Download the YOLO model to ``destination`` atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading YOLO model from {YOLO_MODEL_URL} ...")
    try:
        with urllib.request.urlopen(YOLO_MODEL_URL, timeout=120) as response:
            with partial_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        partial_path.replace(destination)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise
    print(f"YOLO model saved to {destination}")


@pytest.fixture(scope="session")
def yolo_model_path() -> Path:
    """Return a local YOLO model, downloading it once on an interactive first run.

    ``PCD_YOLO_MODEL`` always wins. Otherwise a repository-local test cache and
    the per-user data directory are checked. In non-interactive environments
    such as CI, the dependent tests skip instead of downloading a model.
    """
    override = os.environ.get(YOLO_MODEL_ENV)
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
        pytest.skip(f"{YOLO_MODEL_ENV} does not point to a file: {path}")

    repository_path = repository_yolo_model_path()
    user_path = default_yolo_model_path()
    for candidate in (repository_path, user_path):
        if candidate.is_file():
            return candidate

    is_interactive = _interactive_stdin()
    if os.environ.get("CI") or not is_interactive:
        pytest.skip(
            "YOLO model not found. Set PCD_YOLO_MODEL to a local model or run "
            "the tests interactively to download it."
        )

    destination = _prompt_for_model_location(repository_path, user_path)
    if destination is None:
        pytest.skip("YOLO model download skipped")

    try:
        _download_yolo_model(destination)
    except Exception as exc:
        pytest.skip(f"Could not download YOLO model: {exc}")
    return destination


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
