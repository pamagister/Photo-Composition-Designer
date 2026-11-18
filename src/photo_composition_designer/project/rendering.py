"""Resolve project data into page render inputs and cached previews.

This is the application seam between SQLite and the pure page composer. It
loads assignments, resolves source paths, builds a :class:`PageRenderInput`
and invokes :class:`PageComposer`. The composer never queries the database.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.layouts.loader import LayoutTemplate, SlotTemplate
from photo_composition_designer.project.models import CalendarPage, LayoutDefinition, Project
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)
from photo_composition_designer.render.page import PageComposer, PageRenderInput
from photo_composition_designer.render.slot_renderer import SlotPhoto

DEFAULT_PREVIEW_WIDTH = 640


def profile_from_project(
    project: Project,
    *,
    default: OutputProfile | None = None,
) -> OutputProfile:
    """Return a project's typed output profile.

    Existing projects with an empty snapshot receive a stable read-time
    default without rewriting their stored row.
    """
    if project.output_profile:
        return OutputProfile.from_dict(project.output_profile)
    return default or OutputProfile.default()


def layout_template(definition: LayoutDefinition) -> LayoutTemplate:
    """Convert a persisted layout snapshot into a renderer template."""
    return LayoutTemplate(
        key=definition.key,
        version=definition.version,
        name=definition.name,
        slots=tuple(
            SlotTemplate(
                key=slot.slot_key,
                x=slot.x,
                y=slot.y,
                width=slot.width,
                height=slot.height,
                crop_mode=slot.crop_mode,
            )
            for slot in definition.slots
        ),
    )


def write_preview(
    image: Image.Image,
    destination: Path,
    *,
    max_width: int = DEFAULT_PREVIEW_WIDTH,
    quality: int = 90,
) -> None:
    """Write a reduced-resolution JPEG preview atomically."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview = image.convert("RGB")
    if preview.width > max_width:
        height = max(1, round(preview.height * max_width / preview.width))
        preview = preview.resize((max_width, height), Image.Resampling.LANCZOS)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        preview.save(temporary, format="JPEG", quality=quality, optimize=True)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


class ProjectRenderingService:
    """Build render inputs and cached page previews for a project."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        *,
        composer: PageComposer | None = None,
        preview_dir: Path | None = None,
        default_profile: OutputProfile | None = None,
    ) -> None:
        self._database = database
        self._composer = composer or PageComposer()
        self._preview_dir = Path(preview_dir) if preview_dir is not None else None
        self._default_profile = default_profile

    def profile_for(self, connection, project_id: int) -> OutputProfile:
        """Return the output profile for a project."""
        project = ProjectRepository(connection).get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")
        return profile_from_project(project, default=self._default_profile)

    def build_input(self, connection, page: CalendarPage) -> PageRenderInput:
        """Resolve one page into a render input."""
        profile = self.profile_for(connection, page.project_id)

        layout: LayoutTemplate | None = None
        slot_keys: dict[int, str] = {}
        if page.layout_id is not None:
            definition = LayoutRepository(connection).get_by_id(page.layout_id)
            if definition is not None:
                layout = layout_template(definition)
                slot_keys = {slot.id: slot.slot_key for slot in definition.slots}

        photo_repository = PhotoRepository(connection)
        root_repository = SourceRootRepository(connection)
        assignment_repository = AssignmentRepository(connection)

        slot_photos: dict[str, SlotPhoto] = {}
        coordinates: list[tuple[float, float]] = []
        for assignment in assignment_repository.list_by_page(page.id):
            slot_key = slot_keys.get(assignment.slot_id)
            if slot_key is None:
                continue
            photo = photo_repository.get(assignment.photo_id)
            if photo is None or not photo.available:
                continue
            root = root_repository.get(photo.source_root_id)
            if root is None:
                continue
            try:
                path = resolve_source_path(root.path, photo.relative_path)
            except ValueError:
                continue
            if not path.is_file():
                continue
            slot_photos[slot_key] = SlotPhoto(
                photo_path=path,
                crop_zoom=assignment.crop_zoom,
                crop_focus_x=assignment.crop_focus_x,
                crop_focus_y=assignment.crop_focus_y,
            )
            if photo.gps_lat is not None and photo.gps_lon is not None:
                coordinates.append((photo.gps_lat, photo.gps_lon))

        return PageRenderInput(
            page_date=date.fromisoformat(page.start_date),
            description=page.description,
            layout=layout,
            assigned_photos=slot_photos,
            output_profile=profile,
            gps_coordinates=tuple(coordinates),
            title=profile.calendar.title,
            title_page=page.page_index == 0,
        )

    def render_page_image(self, connection, page: CalendarPage) -> Image.Image:
        """Render one page as a full-resolution image."""
        return self._composer.render(self.build_input(connection, page))

    def assignment_warnings(self, connection, page: CalendarPage) -> tuple[str, ...]:
        """Return actionable warnings for assigned photos that cannot render."""
        photo_repository = PhotoRepository(connection)
        root_repository = SourceRootRepository(connection)
        warnings: list[str] = []
        for assignment in AssignmentRepository(connection).list_by_page(page.id):
            photo = photo_repository.get(assignment.photo_id)
            if photo is None:
                warnings.append(
                    f"page {page.page_index + 1}: photo {assignment.photo_id} "
                    "is missing from the inventory"
                )
                continue
            if not photo.available:
                warnings.append(f"page {page.page_index + 1}: {photo.filename} is unavailable")
                continue
            root = root_repository.get(photo.source_root_id)
            if root is None:
                warnings.append(f"page {page.page_index + 1}: {photo.filename} has no source root")
                continue
            try:
                path = resolve_source_path(root.path, photo.relative_path)
            except ValueError:
                warnings.append(f"page {page.page_index + 1}: {photo.filename} cannot be resolved")
                continue
            if not path.is_file():
                warnings.append(
                    f"page {page.page_index + 1}: {photo.filename} is missing at {path}"
                )
        return tuple(warnings)

    def preview_cache_key(
        self,
        page: CalendarPage,
        profile: OutputProfile,
        *,
        max_width: int,
        mode: str,
    ) -> str:
        """Return a deterministic cache key for one page preview."""
        payload = {
            "page_index": page.page_index,
            "revision": page.render_revision,
            "layout_id": page.layout_id,
            "layout_version": page.layout_version,
            "profile": profile.profile_hash(),
            "mode": mode,
            "max_width": max_width,
        }
        encoded = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()[:24]

    def render_preview(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = DEFAULT_PREVIEW_WIDTH,
        mode: str = "preview",
    ) -> Path:
        """Render a cached reduced-resolution preview for one page."""
        if self._preview_dir is None:
            raise RuntimeError("preview directory is not configured")

        connection = self._database.connect()
        page = PageRepository(connection).get(page_id)
        if page is None or page.project_id != project_id:
            raise ProjectNotFoundError(f"page {page_id} does not exist")
        profile = self.profile_for(connection, project_id)
        image = self.render_page_image(connection, page)

        key = self.preview_cache_key(page, profile, max_width=max_width, mode=mode)
        target = self._preview_dir / "pages" / f"{key}.jpg"
        if not target.is_file():
            write_preview(
                image,
                target,
                max_width=max_width,
                quality=profile.size.jpeg_quality,
            )
        return target


__all__ = [
    "DEFAULT_PREVIEW_WIDTH",
    "ProjectRenderingService",
    "layout_template",
    "profile_from_project",
    "write_preview",
]
