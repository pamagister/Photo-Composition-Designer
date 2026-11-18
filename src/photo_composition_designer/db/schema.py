"""SQLite workspace database setup and forward-only migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

SCHEMA_VERSION = 3

INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    calendar_year       INTEGER,
    page_count          INTEGER NOT NULL,
    settings_json       TEXT NOT NULL DEFAULT '{}',
    output_profile_json TEXT NOT NULL DEFAULT '{}',
    import_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_roots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 0,
    last_scan_at    TEXT,
    source_identity TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(project_id, path)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_roots_one_active
    ON source_roots(project_id) WHERE active = 1;

CREATE TABLE IF NOT EXISTS photos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_root_id INTEGER NOT NULL REFERENCES source_roots(id) ON DELETE CASCADE,
    relative_path  TEXT NOT NULL,
    filename       TEXT NOT NULL,
    file_size      INTEGER NOT NULL DEFAULT 0,
    mtime          REAL,
    digest         TEXT,
    width          INTEGER NOT NULL DEFAULT 0,
    height         INTEGER NOT NULL DEFAULT 0,
    captured_at    TEXT,
    gps_lat        REAL,
    gps_lon        REAL,
    available      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    UNIQUE(project_id, source_root_id, relative_path)
);

CREATE TABLE IF NOT EXISTS layouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,
    version    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(key, version)
);

CREATE TABLE IF NOT EXISTS layout_slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER NOT NULL REFERENCES layouts(id) ON DELETE CASCADE,
    slot_key  TEXT NOT NULL,
    position  INTEGER NOT NULL,
    x         REAL NOT NULL,
    y         REAL NOT NULL,
    width     REAL NOT NULL,
    height    REAL NOT NULL,
    z_index   INTEGER NOT NULL DEFAULT 0,
    crop_mode TEXT NOT NULL DEFAULT 'cover',
    UNIQUE(layout_id, slot_key),
    UNIQUE(layout_id, position)
);

CREATE TABLE IF NOT EXISTS pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    page_index      INTEGER NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    layout_id       INTEGER REFERENCES layouts(id) ON DELETE RESTRICT,
    layout_version  INTEGER,
    render_revision INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(project_id, page_index)
);

CREATE TABLE IF NOT EXISTS assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    page_id       INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    slot_id       INTEGER NOT NULL REFERENCES layout_slots(id) ON DELETE CASCADE,
    photo_id      INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    crop_zoom     REAL NOT NULL DEFAULT 1.0,
    crop_focus_x  REAL NOT NULL DEFAULT 0.5,
    crop_focus_y  REAL NOT NULL DEFAULT 0.5,
    created_at    TEXT NOT NULL,
    UNIQUE(page_id, slot_id),
    UNIQUE(project_id, photo_id)
);

CREATE INDEX IF NOT EXISTS idx_photos_project ON photos(project_id);
CREATE INDEX IF NOT EXISTS idx_photos_available ON photos(project_id, available);
CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id, page_index);
CREATE INDEX IF NOT EXISTS idx_assignments_page ON assignments(page_id);
CREATE INDEX IF NOT EXISTS idx_assignments_project_photo
    ON assignments(project_id, photo_id);

CREATE TRIGGER IF NOT EXISTS assignments_same_project_insert
BEFORE INSERT ON assignments
FOR EACH ROW
BEGIN
    SELECT CASE WHEN (
        (SELECT project_id FROM pages WHERE id = NEW.page_id) IS NOT NEW.project_id
        OR (SELECT project_id FROM photos WHERE id = NEW.photo_id) IS NOT NEW.project_id
    ) THEN RAISE(ABORT, 'cross-project assignment') END;
END;

CREATE TRIGGER IF NOT EXISTS assignments_slot_layout_insert
BEFORE INSERT ON assignments
FOR EACH ROW
BEGIN
    SELECT CASE WHEN (
        (SELECT layout_id FROM pages WHERE id = NEW.page_id) IS NOT
        (SELECT layout_id FROM layout_slots WHERE id = NEW.slot_id)
    ) THEN RAISE(ABORT, 'slot does not belong to page layout') END;
END;
"""

REPEATED_PHOTO_ASSIGNMENTS = """
CREATE TABLE assignments_new (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    page_id       INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    slot_id       INTEGER NOT NULL REFERENCES layout_slots(id) ON DELETE CASCADE,
    photo_id      INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    crop_zoom     REAL NOT NULL DEFAULT 1.0,
    crop_focus_x  REAL NOT NULL DEFAULT 0.5,
    crop_focus_y  REAL NOT NULL DEFAULT 0.5,
    created_at    TEXT NOT NULL,
    UNIQUE(page_id, slot_id)
);

INSERT INTO assignments_new (
    id, project_id, page_id, slot_id, photo_id, crop_zoom,
    crop_focus_x, crop_focus_y, created_at
)
SELECT id, project_id, page_id, slot_id, photo_id, crop_zoom,
       crop_focus_x, crop_focus_y, created_at
FROM assignments;

DROP TABLE assignments;
ALTER TABLE assignments_new RENAME TO assignments;

CREATE INDEX idx_assignments_page ON assignments(page_id);
CREATE INDEX idx_assignments_project_photo ON assignments(project_id, photo_id);

CREATE TRIGGER assignments_same_project_insert
BEFORE INSERT ON assignments
FOR EACH ROW
BEGIN
    SELECT CASE WHEN (
        (SELECT project_id FROM pages WHERE id = NEW.page_id) IS NOT NEW.project_id
        OR (SELECT project_id FROM photos WHERE id = NEW.photo_id) IS NOT NEW.project_id
    ) THEN RAISE(ABORT, 'cross-project assignment') END;
END;

CREATE TRIGGER assignments_slot_layout_insert
BEFORE INSERT ON assignments
FOR EACH ROW
BEGIN
    SELECT CASE WHEN (
        (SELECT layout_id FROM pages WHERE id = NEW.page_id) IS NOT
        (SELECT layout_id FROM layout_slots WHERE id = NEW.slot_id)
    ) THEN RAISE(ABORT, 'slot does not belong to page layout') END;
END;
"""

#: Version -> SQL script. Add new versions here and bump ``SCHEMA_VERSION``.
MIGRATIONS: dict[int, str] = {
    1: INITIAL_SCHEMA,
    2: REPEATED_PHOTO_ASSIGNMENTS,
    3: "ALTER TABLE pages ADD COLUMN hide_local_map INTEGER NOT NULL DEFAULT 0;",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL, foreign keys and a busy timeout."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def read_version(connection: sqlite3.Connection) -> int:
    """Return the stored schema version, or 0 for a fresh database."""
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row["value"]) if row else 0


def write_version(connection: sqlite3.Connection, version: int) -> None:
    """Persist the schema version."""
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


def ensure_schema(connection: sqlite3.Connection) -> int:
    """Create or migrate the workspace schema and return its version."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    current = read_version(connection)
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"database schema {current} is newer than supported schema {SCHEMA_VERSION}"
        )

    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        connection.executescript(MIGRATIONS[version])
        write_version(connection, version)
        connection.commit()
        current = version

    return SCHEMA_VERSION


class WorkspaceDatabase:
    """Own the SQLite connection for a local workspace database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Open the workspace database once and ensure its schema exists."""
        if self._connection is None:
            self._connection = connect(self.db_path)
            ensure_schema(self._connection)
        return self._connection

    def close(self) -> None:
        """Close the owned connection if it is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block in one transaction, committing or rolling back."""
        connection = self.connect()
        with connection:
            yield connection

    def __enter__(self) -> WorkspaceDatabase:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
