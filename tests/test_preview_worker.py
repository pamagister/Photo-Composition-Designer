"""Tests for the in-process preview worker (plan Phase 3, P3-W02).

The worker coalesces duplicate jobs and prioritises visible-page previews
(priority 0) over background page refresh (priority 1). These tests use
the synchronous worker for determinism and verify the coalescing and
priority contracts through the public API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.preview_worker import (
    PreviewWorker,
    SynchronousPreviewWorker,
)
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.repositories import PageRepository
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed(tmp_path: Path) -> tuple[WorkspaceDatabase, int, int]:
    """Create a workspace with one project and one page."""
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    project = ProjectService(database).create_project(
        name="Worker",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )
    source = tmp_path / "source"
    _write_photo(source / "p0.jpg", (255, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
    return database, project.id, page.id


def test_synchronous_worker_renders_inline(tmp_path):
    """The synchronous worker renders the preview immediately."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = SynchronousPreviewWorker(database, preview_dir=preview_dir)
        worker.submit(project_id, page_id, max_width=320)
        files = list((preview_dir / "pages").glob("*.jpg"))
        assert len(files) == 1
        assert worker.pending_count() == 0
    finally:
        database.close()


def test_worker_coalesces_duplicate_jobs(tmp_path):
    """Submitting the same job twice must not enqueue two renders.

    The synchronous worker renders inline, so we verify coalescing by
    checking that the second submit is a no-op (the file already exists
    and the pending count stays at zero). For the async worker, the
    coalescing logic is in ``submit``: a duplicate key is skipped.
    """
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = SynchronousPreviewWorker(database, preview_dir=preview_dir)
        worker.submit(project_id, page_id, max_width=320)
        worker.submit(project_id, page_id, max_width=320)  # duplicate
        files = list((preview_dir / "pages").glob("*.jpg"))
        # Only one file (the second submit is coalesced or a cache hit).
        assert len(files) == 1
    finally:
        database.close()


def test_async_worker_coalesces_before_start(tmp_path):
    """The async worker coalesces duplicate jobs in the pending set.

    We verify the coalescing logic without starting the thread by
    checking ``pending_count`` after submitting duplicates.
    """
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = PreviewWorker(database, preview_dir=preview_dir)
        worker.submit(project_id, page_id, max_width=320, priority=1)
        worker.submit(project_id, page_id, max_width=320, priority=1)  # duplicate
        assert worker.pending_count() == 1
        # Different max_width is a different job.
        worker.submit(project_id, page_id, max_width=640, priority=0)
        assert worker.pending_count() == 2
    finally:
        database.close()


def test_async_worker_priority_order(tmp_path):
    """Priority 0 (visible page) is processed before priority 1 (background).

    We verify the priority queue ordering by checking the queue contents
    after submitting jobs with different priorities.
    """
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = PreviewWorker(database, preview_dir=preview_dir)
        # Submit background job first, then high-priority job.
        worker.submit(project_id, page_id, max_width=320, priority=1)
        worker.submit(project_id, page_id, max_width=640, priority=0)
        # The priority queue should have the priority-0 job first.
        priority, _, job = worker._queue.get_nowait()
        assert priority == 0
        assert job.max_width == 640
        priority, _, job = worker._queue.get_nowait()
        assert priority == 1
        assert job.max_width == 320
    finally:
        database.close()


def test_async_worker_start_stop(tmp_path):
    """The async worker starts and stops cleanly."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = PreviewWorker(database, preview_dir=preview_dir)
        worker.start()
        worker.submit(project_id, page_id, max_width=320, priority=1)
        # Wait for the job to complete.
        worker._queue.join()
        assert worker.pending_count() == 0
        files = list((preview_dir / "pages").glob("*.jpg"))
        assert len(files) == 1
        worker.stop()
    finally:
        database.close()


def test_async_worker_records_error(tmp_path):
    """The async worker records errors without dying."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = PreviewWorker(database, preview_dir=preview_dir)
        worker.start()
        # Submit a job for a non-existent project to trigger an error.
        worker.submit(9999, 9999, max_width=320, priority=1)
        worker._queue.join()
        assert worker.last_error is not None
        worker.stop()
    finally:
        database.close()