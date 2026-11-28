"""In-process background worker for preview rendering.

The worker coalesces duplicate jobs and prioritises visible-page previews
(priority 0) over background page refresh (priority 1) and detection warm-up
(priority 2). SQLite connections are created and closed in the worker thread so
the request thread never holds a DB connection while the render runs.

The worker is owned by the app lifespan: :class:`PreviewWorker` runs a
single background thread, and :class:`SynchronousPreviewWorker` renders
inline for tests that need deterministic timing.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.preview_cache import (
    CURRENT_PREVIEW_WIDTHS,
    PREVIEW_CACHE_CLEANUP_INTERVAL_SECONDS,
    cleanup_stale_preview_assets,
)
from photo_composition_designer.project.rendering import (
    ProjectRenderingService,
    draft_profile,
    profile_from_project,
)
from photo_composition_designer.project.repositories import (
    PageRepository,
    ProjectRepository,
)
from photo_composition_designer.render.object_detector import ObjectDetector

logger = logging.getLogger(__name__)

PreviewJobKey = tuple[int, int, int, str]


def _preview_job_key(project_id: int, page_id: int, max_width: int, mode: str) -> PreviewJobKey:
    """Return the identity used to coalesce and track one preview job."""
    return (project_id, page_id, max_width, mode)


@dataclass(frozen=True)
class PreviewJob:
    """A queued preview render request."""

    project_id: int
    page_id: int
    max_width: int
    mode: str
    priority: int  # 0 = visible page (high), 1 = background (low)

    @property
    def key(self) -> PreviewJobKey:
        """Return the coalescing and status-tracking identity of this job."""
        return _preview_job_key(self.project_id, self.page_id, self.max_width, self.mode)


@dataclass(frozen=True)
class WarmupJob:
    """A queued low-priority object-detection warm-up request."""

    project_id: int
    photo_path: Path
    identity: tuple[int, int]
    priority: int  # 2 = detection warm-up (lowest)


def _warm_photo(detector: ObjectDetector, photo_path: Path) -> None:
    """Run detection once for a photo so its cache entry is populated."""
    with Image.open(photo_path) as source:
        image = source.convert("RGB")
    detector.detect(image)


class PreviewWorker:
    """Single-worker queue for background preview rendering.

    The worker coalesces duplicate jobs (same project/page/width/mode) and
    prioritises visible-page previews (priority 0) over background page
    refresh (priority 1) and detection warm-up (priority 2). SQLite
    connections are created and closed in the worker thread so the request
    thread never holds a DB connection while the render runs.
    """

    def __init__(
        self,
        database: WorkspaceDatabase,
        *,
        preview_dir: Path,
        anniversaries_path: Path | None = None,
        object_detector: ObjectDetector | None = None,
        detector_provider: Callable[[], ObjectDetector | None] | None = None,
    ) -> None:
        self._database = database
        self._preview_dir = preview_dir
        self._anniversaries_path = anniversaries_path
        self._object_detector = object_detector
        self._detector_provider = detector_provider
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._pending: set[PreviewJobKey] = set()
        self._pending_warmups: set[tuple[int, str, tuple[int, int]]] = set()
        self._warmed: set[tuple[int, str, tuple[int, int]]] = set()
        self._seq = 0
        self._thread = threading.Thread(target=self._run, daemon=True, name="preview-worker")
        self._last_error: str | None = None
        self._job_errors: dict[PreviewJobKey, str] = {}

    def start(self) -> None:
        """Start the background worker thread."""
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        """Stop the worker thread, waiting up to 5 seconds for it to finish."""
        # Use a tuple sentinel so the priority queue never compares ``None``
        # with queued jobs while it drains pending work.
        self._queue.put((3, -1, None))
        self._thread.join(timeout=5.0)

    def submit(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 200,
        mode: str = "preview",
        priority: int = 1,
    ) -> None:
        """Submit a preview render job. Duplicate jobs are coalesced.

        If a job with the same (project_id, page_id, max_width, mode) is
        already pending, the submission is skipped. This prevents duplicate
        renders when the same page is edited multiple times quickly.

        Priority 0 is for the visible page (processed first); priority 1
        is for background page refresh.
        """
        job_key = _preview_job_key(project_id, page_id, max_width, mode)
        with self._lock:
            if job_key in self._pending:
                return
            self._pending.add(job_key)
            # A retry supersedes the previous failure for this exact job.
            self._job_errors.pop(job_key, None)
            self._seq += 1
            seq = self._seq
        job = PreviewJob(project_id, page_id, max_width, mode, priority)
        self._queue.put((priority, seq, job))

    def submit_warmup(
        self,
        project_id: int,
        photo_path: Path | str,
        *,
        identity: tuple[int, int],
    ) -> None:
        """Submit a low-priority detection warm-up for one photo.

        Warm-up jobs are coalesced and run at priority 2 so visible-page
        previews (priority 0) and background page refresh (priority 1) are
        always processed first. Re-submitting the same photo identity is a
        no-op, which keeps project page loads idempotent.
        """
        key = (project_id, str(photo_path), identity)
        with self._lock:
            if key in self._warmed or key in self._pending_warmups:
                return
            self._pending_warmups.add(key)
            self._seq += 1
            seq = self._seq
        self._queue.put((2, seq, WarmupJob(project_id, Path(photo_path), identity, 2)))

    def pending_count(self) -> int:
        """Return the number of pending (not yet started) jobs."""
        with self._lock:
            return len(self._pending) + len(self._pending_warmups)

    @property
    def last_error(self) -> str | None:
        """Return the last error message, or ``None`` if no error occurred."""
        return self._last_error

    def error_for(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 200,
        mode: str = "preview",
    ) -> str | None:
        """Return the recorded failure for one preview job, if any.

        Errors are associated with the job's project, page, width, and mode
        so a stale failure cannot incorrectly mark another preview request as
        failed. Submitting a new job clears only that job's previous failure.
        """
        return self._job_errors.get(_preview_job_key(project_id, page_id, max_width, mode))

    def _record_job_error(self, key: PreviewJobKey, message: str) -> None:
        with self._lock:
            self._job_errors[key] = message

    def _resolve_detector(self) -> ObjectDetector | None:
        """Return the detector configured for the current app settings."""
        if self._detector_provider is not None:
            return self._detector_provider()
        return self._object_detector

    def _run(self) -> None:
        next_cache_cleanup = 0.0
        while True:
            now = time.monotonic()
            if now >= next_cache_cleanup:
                self._cleanup_stale_previews()
                next_cache_cleanup = time.monotonic() + PREVIEW_CACHE_CLEANUP_INTERVAL_SECONDS
            try:
                item = self._queue.get(timeout=max(0.0, next_cache_cleanup - time.monotonic()))
            except queue.Empty:
                continue
            _, _, job = item
            if job is None:  # Sentinel
                self._queue.task_done()
                break
            try:
                if isinstance(job, WarmupJob):
                    self._warm(job)
                else:
                    self._render(job)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self._last_error = message
                if not isinstance(job, WarmupJob):
                    self._record_job_error(job.key, message)
            finally:
                if isinstance(job, WarmupJob):
                    key = (job.project_id, str(job.photo_path), job.identity)
                    with self._lock:
                        self._pending_warmups.discard(key)
                else:
                    with self._lock:
                        self._pending.discard(job.key)
                self._queue.task_done()

    def _cleanup_stale_previews(self) -> None:
        """Remove expired preview files while preserving current cache keys."""
        try:
            connection = self._database.connect()
            rendering = ProjectRenderingService(
                self._database,
                preview_dir=self._preview_dir,
                anniversaries_path=self._anniversaries_path,
            )
            current_keys: set[str] = set()
            for project in ProjectRepository(connection).list():
                profile = profile_from_project(project)
                for page in PageRepository(connection).list(project.id):
                    for width in CURRENT_PREVIEW_WIDTHS:
                        draft = draft_profile(profile, width)
                        current_keys.add(
                            rendering.preview_cache_key(
                                page, draft, max_width=width, mode="preview"
                            )
                        )
            cleanup_stale_preview_assets(self._preview_dir, current_keys=current_keys)
        except Exception:
            logger.exception("Could not clean expired page preview assets")

    def _warm(self, job: WarmupJob) -> None:
        """Populate the detector cache for one photo."""
        detector = self._resolve_detector()
        if detector is None:
            return
        _warm_photo(detector, job.photo_path)
        key = (job.project_id, str(job.photo_path), job.identity)
        with self._lock:
            self._warmed.add(key)

    def _render(self, job: PreviewJob) -> None:
        """Render one preview job in the worker thread."""
        rendering = ProjectRenderingService(
            self._database,
            preview_dir=self._preview_dir,
            anniversaries_path=self._anniversaries_path,
            object_detector=self._resolve_detector(),
        )
        rendering.render_preview(
            job.project_id,
            job.page_id,
            max_width=job.max_width,
            mode=job.mode,
        )


class SynchronousPreviewWorker:
    """A test-only worker that renders inline.

    Used in tests to avoid async timing issues. Production uses
    :class:`PreviewWorker` which renders in a background thread.
    """

    def __init__(
        self,
        database: WorkspaceDatabase,
        *,
        preview_dir: Path,
        anniversaries_path: Path | None = None,
        object_detector: ObjectDetector | None = None,
        detector_provider: Callable[[], ObjectDetector | None] | None = None,
    ) -> None:
        self._database = database
        self._preview_dir = preview_dir
        self._anniversaries_path = anniversaries_path
        self._object_detector = object_detector
        self._detector_provider = detector_provider
        self._warmed: set[tuple[int, str, tuple[int, int]]] = set()
        self._last_error: str | None = None
        self._job_errors: dict[PreviewJobKey, str] = {}

    def start(self) -> None:
        """No-op for the synchronous worker."""

    def stop(self) -> None:
        """No-op for the synchronous worker."""

    def _resolve_detector(self) -> ObjectDetector | None:
        """Return the detector configured for the current app settings."""
        if self._detector_provider is not None:
            return self._detector_provider()
        return self._object_detector

    def submit(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 200,
        mode: str = "preview",
        priority: int = 1,
    ) -> None:
        """Render the preview inline (synchronous)."""
        del priority  # Unused; the synchronous worker renders immediately.
        key = _preview_job_key(project_id, page_id, max_width, mode)
        self._job_errors.pop(key, None)
        try:
            rendering = ProjectRenderingService(
                self._database,
                preview_dir=self._preview_dir,
                anniversaries_path=self._anniversaries_path,
                object_detector=self._resolve_detector(),
            )
            rendering.render_preview(
                project_id,
                page_id,
                max_width=max_width,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._last_error = message
            self._job_errors[key] = message

    def submit_warmup(
        self,
        project_id: int,
        photo_path: Path | str,
        *,
        identity: tuple[int, int],
    ) -> None:
        """Warm the detector inline (synchronous)."""
        key = (project_id, str(photo_path), identity)
        if key in self._warmed:
            return
        detector = self._resolve_detector()
        if detector is None:
            return
        try:
            _warm_photo(detector, Path(photo_path))
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return
        self._warmed.add(key)

    def pending_count(self) -> int:
        return 0

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def error_for(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 200,
        mode: str = "preview",
    ) -> str | None:
        """Return the recorded failure for one preview job, if any."""
        return self._job_errors.get(_preview_job_key(project_id, page_id, max_width, mode))


__all__ = [
    "PreviewJob",
    "PreviewJobKey",
    "PreviewWorker",
    "SynchronousPreviewWorker",
    "WarmupJob",
    "_preview_job_key",
]
