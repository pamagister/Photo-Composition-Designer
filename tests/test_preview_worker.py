"""Tests for the in-process preview worker (plan Phase 3, P3-W02).

The worker coalesces duplicate jobs and prioritises visible-page previews
(priority 0) over background page refresh (priority 1). These tests use
the synchronous worker for determinism and verify the coalescing and
priority contracts through the public API.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.preview_worker import (
    PreviewWorker,
    SynchronousPreviewWorker,
    WarmupJob,
    _preview_job_key,
)
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import PageRepository
from photo_composition_designer.project.services import ProjectService


class _RecordingDetector:
    """Detector double that records how often detection runs."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def detect(self, image: Image.Image) -> list:
        self.calls.append(image.size)
        return []


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
        worker.submit(project_id, page_id, max_width=200)
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
        worker.submit(project_id, page_id, max_width=200)
        worker.submit(project_id, page_id, max_width=200)  # duplicate
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
        worker.submit(project_id, page_id, max_width=200, priority=1)
        worker.submit(project_id, page_id, max_width=200, priority=1)  # duplicate
        assert worker.pending_count() == 1
        # Different max_width is a different job.
        worker.submit(project_id, page_id, max_width=800, priority=0)
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
        worker.submit(project_id, page_id, max_width=200, priority=1)
        worker.submit(project_id, page_id, max_width=800, priority=0)
        # The priority queue should have the priority-0 job first.
        priority, _, job = worker._queue.get_nowait()
        assert priority == 0
        assert job.max_width == 800
        priority, _, job = worker._queue.get_nowait()
        assert priority == 1
        assert job.max_width == 200
    finally:
        database.close()


def test_async_worker_start_stop(tmp_path):
    """The async worker starts and stops cleanly."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        worker = PreviewWorker(database, preview_dir=preview_dir)
        worker.start()
        worker.submit(project_id, page_id, max_width=200, priority=1)
        # Wait for the job to complete.
        worker._queue.join()
        assert worker.pending_count() == 0
        files = list((preview_dir / "pages").glob("*.jpg"))
        assert len(files) == 1
        worker.stop()
    finally:
        database.close()


def test_cache_cleanup_preserves_current_preview_key(tmp_path):
    """A current cache key remains available even after its file ages out."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        preview_dir = tmp_path / "previews"
        rendering = ProjectRenderingService(database, preview_dir=preview_dir)
        current_path = rendering.preview_cache_path(project_id, page_id, max_width=200)
        current_path.parent.mkdir(parents=True)
        current_path.write_bytes(b"current preview")
        stale_path = current_path.with_name(f"{'f' * 24}.jpg")
        stale_path.write_bytes(b"stale preview")
        expired_at = time.time() - 30 * 24 * 60 * 60 - 1
        os.utime(current_path, (expired_at, expired_at))
        os.utime(stale_path, (expired_at, expired_at))

        worker = PreviewWorker(database, preview_dir=preview_dir)
        worker._cleanup_stale_previews()

        assert current_path.is_file()
        assert not stale_path.exists()
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
        worker.submit(9999, 9999, max_width=200, priority=1)
        worker._queue.join()
        assert worker.last_error is not None
        assert worker.error_for(9999, 9999, max_width=200) == worker.last_error
        worker.stop()
    finally:
        database.close()


def test_worker_error_is_scoped_to_preview_job(tmp_path):
    """A failure on one job must not mark another preview job as failed."""
    database, project_id, page_id = _seed(tmp_path)
    try:
        worker = SynchronousPreviewWorker(database, preview_dir=tmp_path / "previews")
        worker.submit(9999, 9999, max_width=200)
        failed_key = _preview_job_key(9999, 9999, 200, "preview")
        assert worker.error_for(9999, 9999, max_width=200) is not None
        assert worker.error_for(project_id, page_id, max_width=200) is None

        worker.submit(project_id, page_id, max_width=200)
        assert worker.error_for(project_id, page_id, max_width=200) is None
        assert worker.error_for(9999, 9999, max_width=800) is None

        # Re-submitting the failed job clears its stale error, then the
        # synchronous worker re-renders and records the failure again.
        worker._job_errors[failed_key] = "stale"
        worker.submit(9999, 9999, max_width=200)
        assert worker.error_for(9999, 9999, max_width=200) is not None
    finally:
        database.close()


def test_sync_worker_warmup_is_idempotent(tmp_path):
    """Warm-up calls the detector once per photo identity (P4-W01)."""
    database, project_id, _ = _seed(tmp_path)
    photo = tmp_path / "source" / "p0.jpg"
    try:
        detector = _RecordingDetector()
        worker = SynchronousPreviewWorker(
            database,
            preview_dir=tmp_path / "previews",
            object_detector=detector,
        )
        identity = (photo.stat().st_mtime_ns, photo.stat().st_size)
        worker.submit_warmup(project_id, photo, identity=identity)
        worker.submit_warmup(project_id, photo, identity=identity)
        with Image.open(photo) as image:
            expected_size = image.size
        assert detector.calls == [expected_size]
    finally:
        database.close()


def test_sync_worker_warmup_skipped_without_detector(tmp_path):
    """Warm-up is a no-op when object-aware cropping is disabled."""
    database, project_id, _ = _seed(tmp_path)
    photo = tmp_path / "source" / "p0.jpg"
    try:
        worker = SynchronousPreviewWorker(
            database,
            preview_dir=tmp_path / "previews",
            object_detector=None,
        )
        worker.submit_warmup(project_id, photo, identity=(1, 1))
        assert worker.last_error is None
    finally:
        database.close()


def test_async_worker_warmup_is_lowest_priority_and_coalesces(tmp_path):
    """Warm-up jobs coalesce and run after preview jobs (P4-W01)."""
    database, project_id, page_id = _seed(tmp_path)
    photo = tmp_path / "source" / "p0.jpg"
    try:
        worker = PreviewWorker(
            database,
            preview_dir=tmp_path / "previews",
            object_detector=_RecordingDetector(),
        )
        identity = (1, 1)
        worker.submit_warmup(project_id, photo, identity=identity)
        worker.submit_warmup(project_id, photo, identity=identity)
        assert worker.pending_count() == 1

        worker.submit(project_id, page_id, max_width=200, priority=0)
        priority, _, job = worker._queue.get_nowait()
        assert priority == 0
        assert not isinstance(job, WarmupJob)
        priority, _, job = worker._queue.get_nowait()
        assert priority == 2
        assert isinstance(job, WarmupJob)
    finally:
        database.close()
