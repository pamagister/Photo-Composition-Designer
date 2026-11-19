"""In-process background worker for preview rendering.

The worker coalesces duplicate jobs and prioritises visible-page previews
(priority 0) over background page refresh (priority 1). SQLite connections
are created and closed in the worker thread so the request thread never
holds a DB connection while the render runs.

The worker is owned by the app lifespan: :class:`PreviewWorker` runs a
single background thread, and :class:`SynchronousPreviewWorker` renders
inline for tests that need deterministic timing.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.rendering import ProjectRenderingService


@dataclass(frozen=True)
class PreviewJob:
    """A queued preview render request."""

    project_id: int
    page_id: int
    max_width: int
    mode: str
    priority: int  # 0 = visible page (high), 1 = background (low)


class PreviewWorker:
    """Single-worker queue for background preview rendering.

    The worker coalesces duplicate jobs (same project/page/width/mode) and
    prioritises visible-page previews (priority 0) over background page
    refresh (priority 1). SQLite connections are created and closed in the
    worker thread so the request thread never holds a DB connection while
    the render runs.
    """

    def __init__(
        self,
        database: WorkspaceDatabase,
        *,
        preview_dir: Path,
        anniversaries_path: Path | None = None,
        object_detector: object | None = None,
    ) -> None:
        self._database = database
        self._preview_dir = preview_dir
        self._anniversaries_path = anniversaries_path
        self._object_detector = object_detector
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._pending: set[tuple[int, int, int, str]] = set()
        self._seq = 0
        self._thread = threading.Thread(target=self._run, daemon=True, name="preview-worker")
        self._last_error: str | None = None

    def start(self) -> None:
        """Start the background worker thread."""
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        """Stop the worker thread, waiting up to 5 seconds for it to finish."""
        self._queue.put(None)  # Sentinel
        self._thread.join(timeout=5.0)

    def submit(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 320,
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
        job_key = (project_id, page_id, max_width, mode)
        with self._lock:
            if job_key in self._pending:
                return
            self._pending.add(job_key)
            self._seq += 1
            seq = self._seq
        job = PreviewJob(project_id, page_id, max_width, mode, priority)
        self._queue.put((priority, seq, job))

    def pending_count(self) -> int:
        """Return the number of pending (not yet started) jobs."""
        with self._lock:
            return len(self._pending)

    @property
    def last_error(self) -> str | None:
        """Return the last error message, or ``None`` if no error occurred."""
        return self._last_error

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:  # Sentinel
                break
            _, _, job = item
            with self._lock:
                self._pending.discard((job.project_id, job.page_id, job.max_width, job.mode))
            try:
                self._render(job)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
            finally:
                self._queue.task_done()

    def _render(self, job: PreviewJob) -> None:
        """Render one preview job in the worker thread."""
        rendering = ProjectRenderingService(
            self._database,
            preview_dir=self._preview_dir,
            anniversaries_path=self._anniversaries_path,
            object_detector=self._object_detector,
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
        object_detector: object | None = None,
    ) -> None:
        self._database = database
        self._preview_dir = preview_dir
        self._anniversaries_path = anniversaries_path
        self._object_detector = object_detector
        self._last_error: str | None = None

    def start(self) -> None:
        """No-op for the synchronous worker."""

    def stop(self) -> None:
        """No-op for the synchronous worker."""

    def submit(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = 320,
        mode: str = "preview",
        priority: int = 1,
    ) -> None:
        """Render the preview inline (synchronous)."""
        del priority  # Unused; the synchronous worker renders immediately.
        try:
            rendering = ProjectRenderingService(
                self._database,
                preview_dir=self._preview_dir,
                anniversaries_path=self._anniversaries_path,
                object_detector=self._object_detector,
            )
            rendering.render_preview(
                project_id,
                page_id,
                max_width=max_width,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)

    def pending_count(self) -> int:
        return 0

    @property
    def last_error(self) -> str | None:
        return self._last_error


__all__ = [
    "PreviewJob",
    "PreviewWorker",
    "SynchronousPreviewWorker",
]
