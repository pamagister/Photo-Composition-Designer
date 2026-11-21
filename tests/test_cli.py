"""Tests for the project-oriented command-line interface."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

import photo_composition_designer.launcher as launcher_entry
from photo_composition_designer.cli.app import app as cli_app
from photo_composition_designer.cli.commands import gui as gui_command
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.distribution import DistributionService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    ProjectRepository,
)
from photo_composition_designer.project.services import ProjectService


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GuiSettings:
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PCD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PCD_CACHE_DIR", str(cache_dir))
    settings = GuiSettings(data_dir=data_dir, cache_dir=cache_dir)
    settings.ensure_directories()
    return settings


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed_project(
    settings: GuiSettings,
    tmp_path: Path,
    *,
    name: str = "CLI",
    page_count: int = 2,
    scan: bool = True,
) -> tuple[int, Path]:
    database = WorkspaceDatabase(settings.workspace_path())
    try:
        service = ProjectService(database)
        project = service.create_project(
            name=name,
            page_count=page_count,
            start_date=datetime(2027, 1, 4),
        )
        source = tmp_path / f"source-{project.id}"
        for index in range(2):
            _write_photo(source / f"p{index}.jpg", (index * 80 + 40, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        if scan:
            inventory.scan(project.id, source_root_id=root.id)

        with database.transaction() as connection:
            slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{index}",
                    position=index,
                    x=index * 0.5,
                    y=0.0,
                    width=0.5,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for index in range(2)
            ]
            layout = LayoutRepository(connection).add(f"cli_layout_{project.id}", 1, "CLI", slots)
            page_repository = PageRepository(connection)
            for page in page_repository.list(project.id):
                page_repository.set_layout(page.id, layout.id, layout.version)
        return project.id, source
    finally:
        database.close()


def _invoke(*args: str):
    return CliRunner().invoke(cli_app, list(args))


def test_main_starts_gui_without_arguments(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(launcher_entry.sys, "argv", ["photo-composition-designer"])
    calls: list[str] = []
    monkeypatch.setattr(launcher_entry, "cli_main", lambda: calls.append("cli") or 0)
    monkeypatch.setattr(launcher_entry.gui_command, "run", lambda: calls.append("gui") or 0)

    assert launcher_entry.main() == 0
    assert calls == ["gui"]


def test_main_runs_cli_with_arguments(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(launcher_entry.sys, "argv", ["photo-composition-designer", "doctor"])
    calls: list[str] = []
    monkeypatch.setattr(launcher_entry, "cli_main", lambda: calls.append("cli") or 7)
    monkeypatch.setattr(launcher_entry.gui_command, "run", lambda: calls.append("gui") or 0)

    assert launcher_entry.main() == 7
    assert calls == ["cli"]


def test_cli_help_lists_project_commands():
    result = _invoke("--help")

    assert result.exit_code == 0
    for command in ("gui", "scan", "distribute", "render", "export", "duplicate", "doctor"):
        assert command in result.stdout


def test_gui_open_browser_forwards_flag(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(gui_command, "run", lambda **kwargs: calls.append(kwargs) or 0)

    result = _invoke("gui", "--open-browser")

    assert result.exit_code == 0
    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 8767,
            "log_level": "info",
            "open_browser": True,
        }
    ]


def test_gui_without_open_browser_keeps_default(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(gui_command, "run", lambda **kwargs: calls.append(kwargs) or 0)

    result = _invoke("gui")

    assert result.exit_code == 0
    assert calls[0]["open_browser"] is False


def test_open_browser_helper_opens_expected_url(monkeypatch: pytest.MonkeyPatch):
    opened: list[str] = []
    monkeypatch.setattr(gui_command, "_wait_for_server", lambda host, port, timeout=30.0: True)
    monkeypatch.setattr(gui_command.webbrowser, "open", lambda url: opened.append(url))

    gui_command._open_browser_when_ready("127.0.0.1", 8767)

    assert opened == ["http://127.0.0.1:8767/"]


def test_open_browser_helper_skips_when_server_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    opened: list[str] = []
    monkeypatch.setattr(gui_command, "_wait_for_server", lambda host, port, timeout=30.0: False)
    monkeypatch.setattr(gui_command.webbrowser, "open", lambda url: opened.append(url))

    gui_command._open_browser_when_ready("127.0.0.1", 8767, timeout=0.01)

    assert opened == []
    assert "Browser launch skipped" in capsys.readouterr().out


def test_scan_command_reconciles_inventory(workspace: GuiSettings, tmp_path: Path):
    project_id, _ = _seed_project(workspace, tmp_path, scan=False)

    result = _invoke("scan", str(project_id))

    assert result.exit_code == 0
    assert "discovered 2" in result.stdout
    assert "added 2" in result.stdout
    assert "Symlink policy:" in result.stdout


def test_distribute_command_previews_and_applies(workspace: GuiSettings, tmp_path: Path):
    project_id, _ = _seed_project(workspace, tmp_path)

    preview = _invoke("distribute", str(project_id), "--dry-run")
    assert preview.exit_code == 0
    assert "Preview distribution (equal" in preview.stdout
    assert "assigned 2" in preview.stdout
    database = WorkspaceDatabase(workspace.workspace_path())
    try:
        with database.connect() as connection:
            assert AssignmentRepository(connection).list_by_project(project_id) == []
    finally:
        database.close()

    applied = _invoke("distribute", str(project_id), "--strategy", "equal")
    assert applied.exit_code == 0
    assert "Applied distribution (equal" in applied.stdout

    database = WorkspaceDatabase(workspace.workspace_path())
    try:
        with database.connect() as connection:
            assert len(AssignmentRepository(connection).list_by_project(project_id)) == 2
    finally:
        database.close()


def test_distribute_command_reports_invalid_strategy(workspace: GuiSettings, tmp_path: Path):
    project_id, _ = _seed_project(workspace, tmp_path)

    result = _invoke("distribute", str(project_id), "--strategy", "unknown")

    assert result.exit_code == 1
    assert "error:" in result.stdout


def test_duplicate_command_copies_project(workspace: GuiSettings, tmp_path: Path):
    project_id, _ = _seed_project(workspace, tmp_path)
    database = WorkspaceDatabase(workspace.workspace_path())
    try:
        distribution = DistributionService(database)
        distribution.apply(
            project_id,
            distribution.propose(project_id, strategy="equal"),
        )
    finally:
        database.close()

    result = _invoke("duplicate", str(project_id), "--name", "CLI Copy")

    assert result.exit_code == 0
    assert "Duplicated project" in result.stdout
    assert "CLI Copy" in result.stdout

    database = WorkspaceDatabase(workspace.workspace_path())
    try:
        projects = ProjectService(database).list_projects()
        duplicate = next(project for project in projects if project.name == "CLI Copy")
        with database.connect() as connection:
            assert len(AssignmentRepository(connection).list_by_project(duplicate.id)) == 2
    finally:
        database.close()


def test_duplicate_command_reports_missing_project(workspace: GuiSettings):
    result = _invoke("duplicate", "999")

    assert result.exit_code == 1
    assert "does not exist" in result.stdout


def test_doctor_reports_clean_workspace(workspace: GuiSettings, tmp_path: Path):
    _seed_project(workspace, tmp_path)

    result = _invoke("doctor")

    assert result.exit_code == 0
    assert "OK: workspace checks passed" in result.stdout


def test_doctor_reports_missing_active_source(workspace: GuiSettings, tmp_path: Path):
    _, source = _seed_project(workspace, tmp_path)
    import shutil

    shutil.rmtree(source)

    result = _invoke("doctor")

    assert result.exit_code == 1
    assert "ERROR:" in result.stdout
    assert "active does not exist" in result.stdout


def test_doctor_reports_invalid_output_profile(workspace: GuiSettings, tmp_path: Path):
    project_id, _ = _seed_project(workspace, tmp_path)
    database = WorkspaceDatabase(workspace.workspace_path())
    try:
        with database.transaction() as connection:
            ProjectRepository(connection).update(
                project_id,
                output_profile={"size": {"dpi": 0}},
            )
    finally:
        database.close()

    result = _invoke("doctor")

    assert result.exit_code == 1
    assert "invalid output profile" in result.stdout
    assert "dpi" in result.stdout


def test_doctor_reports_missing_photos_and_cache_directories(
    workspace: GuiSettings, tmp_path: Path
):
    _, source = _seed_project(workspace, tmp_path)
    (source / "p0.jpg").unlink()
    import shutil

    shutil.rmtree(workspace.cache_dir)

    result = _invoke("doctor")

    assert result.exit_code == 0
    assert "WARNING:" in result.stdout
    assert "missing photo file(s)" in result.stdout
    assert "cache directory does not exist" in result.stdout


def test_doctor_reports_unsupported_schema(workspace: GuiSettings, tmp_path: Path):
    _seed_project(workspace, tmp_path)
    connection = sqlite3.connect(workspace.workspace_path())
    try:
        connection.execute("UPDATE schema_meta SET value = '99' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    result = _invoke("doctor")

    assert result.exit_code == 1
    assert "schema" in result.stdout.lower()
