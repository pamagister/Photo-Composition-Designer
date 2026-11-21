"""Tests for the third-party notices generator."""

from __future__ import annotations

from pathlib import Path

from scripts.generate_third_party_notices import build_notices, main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_notices_includes_project_and_bundled_assets():
    content = build_notices(PROJECT_ROOT / "pyproject.toml")

    assert "# Third-Party Notices" in content
    assert "MIT License" in content
    assert "Tim Wilson" in content
    assert "Natural Earth" in content
    assert "htmx 2.0.4" in content
    assert "YOLO object-detection model" in content


def test_main_writes_dependency_notices(tmp_path: Path):
    output = tmp_path / "THIRD_PARTY_NOTICES.md"

    exit_code = main(
        [
            "--pyproject",
            str(PROJECT_ROOT / "pyproject.toml"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    content = output.read_text(encoding="utf-8")
    assert "Runtime Python dependencies" in content
    assert "fastapi" in content.lower()
    assert "### pytest " not in content
