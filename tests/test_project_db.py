"""Tests for workspace schema creation, versioning and migrations."""

from __future__ import annotations

import pytest

from photo_composition_designer.db.schema import (
    INITIAL_SCHEMA,
    SCHEMA_VERSION,
    WorkspaceDatabase,
    connect,
    ensure_schema,
    read_version,
    write_version,
)
from tests.project_test_helpers import FIXED_NOW


def test_fresh_database_creates_schema(tmp_path):
    with WorkspaceDatabase(tmp_path / "workspace.sqlite3") as database:
        connection = database.connect()
        assert read_version(connection) == SCHEMA_VERSION
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {
        "projects",
        "source_roots",
        "photos",
        "pages",
        "layouts",
        "layout_slots",
        "assignments",
    } <= tables


def test_foreign_keys_are_enabled(tmp_path):
    with WorkspaceDatabase(tmp_path / "workspace.sqlite3") as database:
        connection = database.connect()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_ensure_schema_is_idempotent_and_preserves_data(tmp_path):
    with WorkspaceDatabase(tmp_path / "workspace.sqlite3") as database:
        connection = database.connect()
        connection.execute(
            "INSERT INTO projects(name, page_count, created_at, updated_at) "
            "VALUES('Project', 1, ?, ?)",
            (FIXED_NOW, FIXED_NOW),
        )
        connection.commit()

        ensure_schema(connection)
        ensure_schema(connection)

        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert read_version(connection) == SCHEMA_VERSION


def test_v1_migration_preserves_assignments_and_allows_reuse(tmp_path):
    connection = connect(tmp_path / "workspace.sqlite3")
    connection.executescript(INITIAL_SCHEMA)
    write_version(connection, 1)
    connection.execute(
        "INSERT INTO projects(id, name, page_count, created_at, updated_at) "
        "VALUES(1, 'Calendar', 2, ?, ?)",
        (FIXED_NOW, FIXED_NOW),
    )
    connection.execute(
        "INSERT INTO source_roots(id, project_id, path, created_at) VALUES(1, 1, '/photos', ?)",
        (FIXED_NOW,),
    )
    connection.execute(
        "INSERT INTO photos(id, project_id, source_root_id, relative_path, filename, created_at) "
        "VALUES(1, 1, 1, 'photo.jpg', 'photo.jpg', ?)",
        (FIXED_NOW,),
    )
    connection.execute(
        "INSERT INTO layouts(id, key, version, name, created_at) "
        "VALUES(1, 'single', 1, 'Single', ?)",
        (FIXED_NOW,),
    )
    connection.execute(
        "INSERT INTO layout_slots(id, layout_id, slot_key, position, x, y, width, height) "
        "VALUES(1, 1, 'main', 0, 0, 0, 1, 1)"
    )
    connection.executemany(
        "INSERT INTO pages("
        "id, project_id, page_index, start_date, end_date, created_at, updated_at"
        ") "
        "VALUES(?, 1, ?, ?, ?, ?, ?)",
        [
            (1, 0, "2027-01-04", "2027-01-10", FIXED_NOW, FIXED_NOW),
            (2, 1, "2027-01-11", "2027-01-17", FIXED_NOW, FIXED_NOW),
        ],
    )
    connection.execute("UPDATE pages SET layout_id = 1, layout_version = 1 WHERE project_id = 1")
    connection.execute(
        "INSERT INTO assignments(project_id, page_id, slot_id, photo_id, created_at) "
        "VALUES(1, 1, 1, 1, ?)",
        (FIXED_NOW,),
    )
    connection.commit()

    ensure_schema(connection)

    assert read_version(connection) == SCHEMA_VERSION
    assert connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1
    connection.execute(
        "INSERT INTO assignments(project_id, page_id, slot_id, photo_id, created_at) "
        "VALUES(1, 2, 1, 1, ?)",
        (FIXED_NOW,),
    )
    assert connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 2


def test_newer_schema_is_rejected(tmp_path):
    connection = connect(tmp_path / "workspace.sqlite3")
    ensure_schema(connection)
    connection.execute("UPDATE schema_meta SET value = '999' WHERE key = 'schema_version'")
    connection.commit()

    with pytest.raises(RuntimeError, match="newer than supported"):
        ensure_schema(connection)


def test_transaction_rolls_back_on_error(tmp_path):
    with WorkspaceDatabase(tmp_path / "workspace.sqlite3") as database:
        with pytest.raises(RuntimeError, match="boom"):
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO projects(name, page_count, created_at, updated_at) "
                    "VALUES('Project', 1, ?, ?)",
                    (FIXED_NOW, FIXED_NOW),
                )
                raise RuntimeError("boom")

        count = database.connect().execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        assert count == 0


def test_database_reopen_keeps_schema(tmp_path):
    database_path = tmp_path / "workspace.sqlite3"
    with WorkspaceDatabase(database_path) as database:
        database.connect()

    with WorkspaceDatabase(database_path) as database:
        assert read_version(database.connect()) == SCHEMA_VERSION
