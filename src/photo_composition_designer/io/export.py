"""Ordered page rendering and PDF export from project data.

Renders each page in project order using the slot-aware renderer and the
persisted layout snapshot and assignments, then optionally combines the
rendered pages into a PDF.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.settings import Settings
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.layouts.loader import LayoutTemplate
from photo_composition_designer.project.models import CalendarPage
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    SourceRootRepository,
)
from photo_composition_designer.render.slot_renderer import SlotAwareRenderer, SlotPhoto


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a project export."""

    pages: int
    rendered: list[Path]
    pdf_path: Path | None
    warnings: tuple[str, ...] = ()


class ProjectExporter:
    """Render project pages in order and optionally write a PDF."""

    def __init__(self, database: WorkspaceDatabase, settings: Settings | None = None) -> None:
        self._database = database
        self._settings = settings or Settings()
        self._renderer = SlotAwareRenderer(self._settings)

    def _page_width(self) -> int:
        from photo_composition_designer.core.helpers import mm_to_px

        return mm_to_px(self._settings.size.width.value, self._settings.size.dpi.value)

    def _page_height(self) -> int:
        from photo_composition_designer.core.helpers import mm_to_px

        return mm_to_px(self._settings.size.height.value, self._settings.size.dpi.value)

    def _background(self) -> tuple[int, int, int]:
        return self._settings.style.backgroundColor.value.to_pil()

    def _layout_template(
        self,
        connection,
        page: CalendarPage,
    ) -> LayoutTemplate | None:
        if page.layout_id is None:
            return None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        if layout is None:
            return None
        return LayoutTemplate(
            key=layout.key,
            version=layout.version,
            name=layout.name,
            slots=tuple(
                type(
                    "S",
                    (),
                    {
                        "key": slot.slot_key,
                        "x": slot.x,
                        "y": slot.y,
                        "width": slot.width,
                        "height": slot.height,
                        "crop_mode": slot.crop_mode,
                    },
                )()
                for slot in layout.slots
            ),
        )

    def render_page(
        self,
        connection,
        project_id: int,
        page: CalendarPage,
        output_dir: Path,
    ) -> Path | None:
        """Render one page to a PNG file. Returns the path or ``None``."""
        template = self._layout_template(connection, page)
        if template is None:
            return None

        assignments = AssignmentRepository(connection).list_by_page(page.id)
        if not assignments:
            return None

        photo_repo = PhotoRepository(connection)
        root_repo = SourceRootRepository(connection)
        slot_photos: dict[str, SlotPhoto] = {}
        for assignment in assignments:
            photo = photo_repo.get(assignment.photo_id)
            if photo is None or not photo.available:
                continue
            root = root_repo.get(photo.source_root_id)
            if root is None:
                continue
            try:
                path = resolve_source_path(root.path, photo.relative_path)
            except ValueError:
                continue
            if not path.is_file():
                continue
            slot = next(
                (
                    s
                    for s in template.slots
                    if s.key == self._slot_key_for(connection, page, assignment.slot_id)
                ),
                None,
            )
            if slot is None:
                continue
            slot_photos[slot.key] = SlotPhoto(
                photo_path=path,
                crop_zoom=assignment.crop_zoom,
                crop_focus_x=assignment.crop_focus_x,
                crop_focus_y=assignment.crop_focus_y,
            )

        if not slot_photos:
            return None

        image = self._renderer.render(
            template,
            slot_photos,
            page_width=self._page_width(),
            page_height=self._page_height(),
            background_color=self._background(),
        )
        output_path = output_dir / f"page_{page.page_index:03d}.png"
        image.save(output_path, format="PNG")
        return output_path

    def _slot_key_for(self, connection, page: CalendarPage, slot_id: int) -> str:
        from photo_composition_designer.project.repositories import LayoutRepository

        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        if layout is None:
            return ""
        for slot in layout.slots:
            if slot.id == slot_id:
                return slot.slot_key
        return ""

    def render_project(
        self,
        project_id: int,
        output_dir: Path,
        *,
        write_pdf: bool = True,
    ) -> ExportResult:
        """Render all pages in project order and optionally write a PDF."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        rendered: list[Path] = []

        connection = self._database.connect()
        try:
            pages = PageRepository(connection).list(project_id)
            for page in pages:
                path = self.render_page(connection, project_id, page, output_dir)
                if path is not None:
                    rendered.append(path)
                else:
                    warnings.append(f"page {page.page_index} has no renderable content")
        finally:
            connection.close()

        pdf_path: Path | None = None
        if write_pdf and rendered:
            pdf_path = self._write_pdf(rendered, output_dir / "output.pdf")

        return ExportResult(
            pages=len(pages),
            rendered=rendered,
            pdf_path=pdf_path,
            warnings=tuple(warnings),
        )

    def _write_pdf(self, images: list[Path], output_path: Path) -> Path | None:
        """Combine rendered page PNGs into a single PDF."""
        opened: list[Image.Image] = []
        try:
            for path in images:
                opened.append(Image.open(path).convert("RGB"))
            if not opened:
                return None
            opened[0].save(
                output_path,
                "PDF",
                save_all=True,
                append_images=opened[1:],
                resolution=self._settings.size.dpi.value,
            )
            return output_path
        finally:
            for image in opened:
                image.close()
