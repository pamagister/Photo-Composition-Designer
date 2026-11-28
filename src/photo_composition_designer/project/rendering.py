"""Resolve project data into page render inputs and cached previews.

This is the application seam between SQLite and the pure page composer. It
loads assignments, resolves source paths, builds a :class:`PageRenderInput`
and invokes :class:`PageComposer`. The composer never queries the database.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.anniversaries import Anniversaries
from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.helpers import get_base_path
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
from photo_composition_designer.render.layout_geometry import (
    CollageBox,
    PreparedCollage,
    prepare_collage,
)
from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.page import PageComposer, PageRenderInput
from photo_composition_designer.render.slot_renderer import SlotPhoto

DEFAULT_PREVIEW_WIDTH = 800
THUMBNAIL_PREVIEW_WIDTH = 200

#: Bump when page composition changes without a project/profile revision change.
RENDER_CACHE_VERSION = 2


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


#: Oversampling factor for draft previews. The draft page is rendered at a
#: working resolution that covers the requested preview width at this many
#: device pixels, so the preview stays crisp on high-DPI displays without
#: paying for the full 300 dpi render.
DRAFT_OVERSAMPLE = 1.5


def draft_dpi(profile: OutputProfile, max_width: int) -> int:
    """Return the DPI that covers ``max_width`` at ~1.5x device pixels.

    The draft profile scales only ``size.dpi`` (D1). The result is the
    smallest integer DPI whose rendered page width is at least
    ``max_width * DRAFT_OVERSAMPLE`` pixels, capped at the full profile
    DPI so a draft never renders above full resolution.
    """
    width_mm = profile.size.width
    if width_mm <= 0 or max_width <= 0:
        return profile.size.dpi
    target_px = max_width * DRAFT_OVERSAMPLE
    draft = math.ceil(target_px * 25.4 / width_mm)
    return min(draft, profile.size.dpi)


def draft_profile(profile: OutputProfile, max_width: int) -> OutputProfile:
    """Return a preview-only profile with DPI scaled to cover ``max_width``.

    Only ``size.dpi`` changes; every other profile value (page geometry,
    calendar, style, geo, layout) is preserved so the draft render matches
    the full render's composition. ``profile_hash()`` differs from the full
    profile, so the preview cache key automatically distinguishes draft
    from full renders without a key-shape change.
    """
    return replace(profile, size=replace(profile.size, dpi=draft_dpi(profile, max_width)))


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


def prepared_collage_for_page(page: CalendarPage, profile: OutputProfile) -> PreparedCollage:
    """Return the rendered sub-images and collage content box for a page.

    The result is the same geometry the renderer and editor overlay use, so
    overlays such as the description rectangle line up with the rendered page.
    """
    render_input = PageRenderInput(
        page_date=date.fromisoformat(page.start_date),
        description=page.description,
        layout=None,
        output_profile=profile,
        title=profile.calendar.title,
        title_page=profile.calendar.use_title_page and page.page_index == 0,
        hide_local_map=page.hide_local_map,
        hide_calendar_strip=page.hide_calendar_strip,
        hide_description=page.hide_description,
        center_description=page.center_description,
    )
    return prepare_collage(render_input, profile)


def collage_box_for_page(page: CalendarPage, profile: OutputProfile) -> CollageBox:
    """Return the collage content box for a page using the shared geometry.

    This is the same geometry the renderer and editor overlay use, so auto
    layouts are generated against the real content box aspect ratio.
    """
    return prepared_collage_for_page(page, profile).box


def collage_aspect_for_page(page: CalendarPage, profile: OutputProfile) -> float:
    """Return the width-to-height aspect ratio of a page's collage box."""
    box = collage_box_for_page(page, profile)
    return box.width / box.height


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
        anniversaries_path: Path | None = None,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._database = database
        self._composer = composer or PageComposer(object_detector=object_detector)
        self._preview_dir = Path(preview_dir) if preview_dir is not None else None
        self._default_profile = default_profile
        self._anniversaries_path = (
            Path(anniversaries_path) if anniversaries_path is not None else None
        )

    def profile_for(self, connection, project_id: int) -> OutputProfile:
        """Return the output profile for a project."""
        project = ProjectRepository(connection).get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")
        return profile_from_project(project, default=self._default_profile)

    def build_input(self, connection, page: CalendarPage) -> PageRenderInput:
        """Resolve one page into a render input."""
        render_input, _warnings = self.build_input_with_warnings(connection, page)
        return render_input

    def build_input_with_warnings(
        self, connection, page: CalendarPage
    ) -> tuple[PageRenderInput, tuple[str, ...]]:
        """Resolve a page and return warnings for assigned photos that cannot render."""
        profile = self.profile_for(connection, page.project_id)

        layout: LayoutTemplate | None = None
        slot_keys: dict[int, str] = {}
        if page.layout_id is not None:
            definition = LayoutRepository(connection).get_by_id(page.layout_id)
            if definition is not None:
                layout = layout_template(definition)
                slot_keys = {slot.id: slot.slot_key for slot in definition.slots}

        slot_photos, coordinates, warnings = self._resolve_assignments(connection, page, slot_keys)
        return (
            PageRenderInput(
                page_date=date.fromisoformat(page.start_date),
                description=page.description,
                layout=layout,
                assigned_photos=slot_photos,
                output_profile=profile,
                gps_coordinates=coordinates,
                title=profile.calendar.title,
                title_page=profile.calendar.use_title_page and page.page_index == 0,
                hide_local_map=page.hide_local_map,
                hide_calendar_strip=page.hide_calendar_strip,
                hide_description=page.hide_description,
                center_description=page.center_description,
                anniversaries=Anniversaries(self._anniversaries_path),
            ),
            warnings,
        )

    @staticmethod
    def _resolve_assignments(
        connection,
        page: CalendarPage,
        slot_keys: dict[int, str],
    ) -> tuple[dict[str, SlotPhoto], tuple[tuple[float, float], ...], tuple[str, ...]]:
        photo_repository = PhotoRepository(connection)
        root_repository = SourceRootRepository(connection)

        # Batch the photo and source-root lookups so input resolution issues a
        # constant number of queries regardless of slot count (D7). Resolving
        # source paths and warnings is CPU-only and stays in the loop.
        assignments = AssignmentRepository(connection).list_by_page(page.id)
        photos_by_id = photo_repository.get_many(
            [assignment.photo_id for assignment in assignments]
        )
        root_ids = [photo.source_root_id for photo in photos_by_id.values()]
        roots_by_id = root_repository.get_many(root_ids)

        slot_photos: dict[str, SlotPhoto] = {}
        coordinates: list[tuple[float, float]] = []
        warnings: list[str] = []
        for assignment in assignments:
            photo = photos_by_id.get(assignment.photo_id)
            if photo is None:
                warnings.append(
                    f"page {page.page_index + 1}: photo {assignment.photo_id} "
                    "is missing from the inventory"
                )
                continue
            if not photo.available:
                warnings.append(f"page {page.page_index + 1}: {photo.filename} is unavailable")
                continue
            root = roots_by_id.get(photo.source_root_id)
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
                continue
            slot_key = slot_keys.get(assignment.slot_id)
            if slot_key is not None:
                slot_photos[slot_key] = SlotPhoto(
                    photo_path=path,
                    crop_zoom=assignment.crop_zoom,
                    crop_focus_x=assignment.crop_focus_x,
                    crop_focus_y=assignment.crop_focus_y,
                )
                if photo.gps_lat is not None and photo.gps_lon is not None:
                    coordinates.append((photo.gps_lat, photo.gps_lon))

        return slot_photos, tuple(coordinates), tuple(warnings)

    def render_page_image(self, connection, page: CalendarPage) -> Image.Image:
        """Render one page as a full-resolution image."""
        return self.render_input(self.build_input(connection, page))

    def render_input(self, render_input: PageRenderInput) -> Image.Image:
        """Render a previously resolved page input."""
        return self._composer.render(render_input)

    def render_page_image_with_warnings(
        self, connection, page: CalendarPage
    ) -> tuple[Image.Image, tuple[str, ...]]:
        """Render one page and return warnings resolved from the same input data."""
        render_input, warnings = self.build_input_with_warnings(connection, page)
        return self.render_input(render_input), warnings

    def assignment_warnings(self, connection, page: CalendarPage) -> tuple[str, ...]:
        """Return actionable warnings for assigned photos that cannot render."""
        _slot_photos, _coordinates, warnings = self._resolve_assignments(connection, page, {})
        return warnings

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
            "cache_version": RENDER_CACHE_VERSION,
            "page_index": page.page_index,
            "revision": page.render_revision,
            "layout_id": page.layout_id,
            "layout_version": page.layout_version,
            "profile": profile.profile_hash(),
            "anniversaries": self._anniversaries_signature(),
            "mode": mode,
            "max_width": max_width,
        }
        encoded = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()[:24]

    def _anniversaries_signature(self) -> tuple[str, int, int, str]:
        path = self._anniversaries_path or (get_base_path() / "anniversaries.ini")
        try:
            stat = path.stat()
        except FileNotFoundError:
            return (str(path), 0, 0, "")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return (str(path), stat.st_mtime_ns, stat.st_size, digest)

    def render_preview(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = DEFAULT_PREVIEW_WIDTH,
        mode: str = "preview",
    ) -> Path:
        """Render a cached reduced-resolution preview for one page.

        The preview is rendered at a draft profile (reduced DPI) that covers
        the requested ``max_width`` at ~1.5x device pixels (D1). This cuts
        both the JPEG decode and the resize cost in the slot renderer while
        keeping the preview visually close to the full render. The cache key
        is derived from the draft profile's hash, so a draft render is
        automatically distinguished from a full render without a key-shape
        change.

        ``render_page_image`` and the exporter are untouched: they keep the
        full profile and pixel-exact output.
        """
        if self._preview_dir is None:
            raise RuntimeError("preview directory is not configured")

        connection = self._database.connect()
        page = PageRepository(connection).get(page_id)
        if page is None or page.project_id != project_id:
            raise ProjectNotFoundError(f"page {page_id} does not exist")
        profile = self.profile_for(connection, project_id)

        # Derive the draft profile from the full profile and the requested
        # preview width. The key uses the draft profile's hash so a draft
        # render is distinguished from a full render.
        draft = draft_profile(profile, max_width)
        key = self.preview_cache_key(page, draft, max_width=max_width, mode=mode)
        target = self._preview_dir / "pages" / f"{key}.jpg"
        if target.is_file():
            return target

        render_input = replace(self.build_input(connection, page), output_profile=draft)
        image = self._composer.render(render_input)
        write_preview(
            image,
            target,
            max_width=max_width,
            quality=profile.size.jpeg_quality,
        )
        return target

    def preview_cache_path(
        self,
        project_id: int,
        page_id: int,
        *,
        max_width: int = DEFAULT_PREVIEW_WIDTH,
        mode: str = "preview",
    ) -> Path:
        """Return the path where the preview for a page would be stored.

        This does not render the preview; it only computes the path from
        the cache key. Callers can check ``path.is_file()`` to determine
        whether a preview is already cached for the current revision.
        """
        if self._preview_dir is None:
            raise RuntimeError("preview directory is not configured")

        connection = self._database.connect()
        page = PageRepository(connection).get(page_id)
        if page is None or page.project_id != project_id:
            raise ProjectNotFoundError(f"page {page_id} does not exist")
        profile = self.profile_for(connection, project_id)
        draft = draft_profile(profile, max_width)
        key = self.preview_cache_key(page, draft, max_width=max_width, mode=mode)
        return self._preview_dir / "pages" / f"{key}.jpg"


def preview_cache_key_for(
    rendering: ProjectRenderingService,
    connection,
    page: CalendarPage,
    *,
    max_width: int,
    mode: str = "preview",
) -> str:
    """Compute a preview cache key for a page using an existing service and connection.

    The key is derived from the draft profile (reduced DPI) that
    ``render_preview`` uses, so the key matches the actual rendered file.
    This is a convenience helper for call sites that already have a
    :class:`ProjectRenderingService` and an open database connection but only
    need the cache key (e.g. to build an immutable asset URL).
    """
    profile = rendering.profile_for(connection, page.project_id)
    draft = draft_profile(profile, max_width)
    return rendering.preview_cache_key(page, draft, max_width=max_width, mode=mode)


__all__ = [
    "DEFAULT_PREVIEW_WIDTH",
    "DRAFT_OVERSAMPLE",
    "THUMBNAIL_PREVIEW_WIDTH",
    "ProjectRenderingService",
    "collage_aspect_for_page",
    "collage_box_for_page",
    "draft_dpi",
    "draft_profile",
    "layout_template",
    "prepared_collage_for_page",
    "preview_cache_key_for",
    "profile_from_project",
    "write_preview",
]
