"""Tests for the packaged release verifier."""

from __future__ import annotations

from pathlib import Path

from scripts.verify_release import find_missing_entries, main


def _make_release_tree(root: Path, executable: str = "photo-composition-designer") -> Path:
    release = root / "release"
    release.mkdir()
    (release / executable).write_text("binary", encoding="utf-8")
    for name in (
        "anniversaries.ini",
        "locations_en.ini",
        "locations_de.ini",
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    ):
        (release / name).write_text("content", encoding="utf-8")
    for name in ("res", "docs", "images"):
        (release / name).mkdir()
    return release


def test_complete_release_has_no_missing_entries(tmp_path: Path):
    release = _make_release_tree(tmp_path)

    assert find_missing_entries(release) == []


def test_windows_executable_is_accepted(tmp_path: Path):
    release = _make_release_tree(tmp_path, executable="photo-composition-designer.exe")

    assert find_missing_entries(release) == []


def test_missing_entries_are_reported(tmp_path: Path):
    release = _make_release_tree(tmp_path)
    (release / "photo-composition-designer").unlink()
    (release / "res").rmdir()

    missing = find_missing_entries(release)

    assert "photo-composition-designer or photo-composition-designer.exe" in missing
    assert "res/" in missing


def test_main_returns_nonzero_for_incomplete_release(tmp_path: Path, capsys):
    release = _make_release_tree(tmp_path)
    (release / "images").rmdir()

    exit_code = main([str(release)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "images/" in captured.err
