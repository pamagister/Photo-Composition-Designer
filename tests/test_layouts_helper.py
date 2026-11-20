"""Tests for the layout helper script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "layouts_helper.py"


def _load_helper() -> ModuleType:
    """Load the standalone helper script as a module."""
    spec = importlib.util.spec_from_file_location("layouts_helper", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helper = _load_helper()


def _validate(data: dict) -> helper.Report:
    """Validate generated data with the default page and spacing geometry."""
    return helper.validate_data(
        data,
        key=str(data["key"]),
        file_name=None,
        page_width=2551,
        page_height=1819,
        spacing_px=24,
        min_gap_px=1,
    )


def test_build_row_layout_uses_requested_columns_and_heights() -> None:
    data = helper.build_row_layout(
        "tiles_3_rows_mixed",
        (4, 3, 5),
        name="Mixed",
        heights=(30, 40, 30),
    )

    slots = data["slots"]
    assert len(slots) == 12
    assert [slot["height"] for slot in slots[:4]] == [0.3] * 4
    assert [slot["height"] for slot in slots[4:7]] == [0.4] * 3
    assert [slot["height"] for slot in slots[7:]] == [0.3] * 5
    for start, count in ((0, 4), (4, 3), (7, 5)):
        row = slots[start : start + count]
        assert round(sum(slot["width"] for slot in row), 6) == 1.0

    assert _validate(data).has_errors() is False


def test_build_row_layout_defaults_to_equal_row_heights() -> None:
    data = helper.build_row_layout("equal", (2, 2))

    assert data["name"] == "Equal"
    assert [slot["height"] for slot in data["slots"]] == [0.5] * 4
    assert _validate(data).has_errors() is False


def test_build_row_layout_normalizes_height_percentages() -> None:
    data = helper.build_row_layout("normalized", (1, 1), heights=(1, 3))

    assert [slot["height"] for slot in data["slots"]] == [0.25, 0.75]


def test_build_row_layout_rejects_height_count_mismatch() -> None:
    with pytest.raises(ValueError, match="row heights"):
        helper.build_row_layout("bad", (3, 3, 3), heights=(50, 50))


def test_build_row_layout_rejects_non_positive_column_count() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        helper.build_row_layout("bad", (3, 0))


def test_build_row_layout_rejects_non_positive_height() -> None:
    with pytest.raises(ValueError, match="positive"):
        helper.build_row_layout("bad", (3,), heights=(0,))


def test_validate_data_reports_uncovered_gap() -> None:
    data = {
        "key": "gap",
        "version": 1,
        "name": "Gap",
        "slots": [
            {"key": "left", "x": 0.0, "y": 0.0, "width": 0.4, "height": 1.0},
            {"key": "right", "x": 0.6, "y": 0.0, "width": 0.4, "height": 1.0},
        ],
    }

    report = _validate(data)

    assert report.has_errors() is True
    assert any("uncovered" in issue.message for issue in report.issues)


def test_write_yaml_skips_unchanged_file(tmp_path: Path) -> None:
    path = tmp_path / "layout.yaml"
    data = helper.build_row_layout("generated", (2, 2))

    assert helper.write_yaml(path, data) is True
    assert helper.write_yaml(path, data) is False
    assert helper.load_layout(path)["key"] == "generated"


def test_builtin_template_generation_matches_checked_in_files() -> None:
    for key, spec in helper.BUILTIN_ROW_TEMPLATES.items():
        data = helper.build_row_layout(
            key,
            spec.columns,
            name=spec.name,
            heights=spec.heights,
        )
        path = helper.BUILTIN_LAYOUTS / f"{key}.yaml"
        assert helper.yaml_text(data) == path.read_text(encoding="utf-8"), key


def test_generate_command_writes_valid_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "generated.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "layouts_helper.py",
            "generate",
            "--columns",
            "4,3,5",
            "--heights",
            "30,40,30",
            "--output",
            str(output),
            "--check",
        ],
    )

    assert helper.main() == 0

    data = helper.load_layout(output)
    assert data["key"] == "generated"
    assert len(data["slots"]) == 12
    assert _validate(data).has_errors() is False
