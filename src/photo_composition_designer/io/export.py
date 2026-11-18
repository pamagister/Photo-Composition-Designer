"""Ordered full-page rendering and PDF export from project data.

Renders each page in project order using the project's own output profile and
the persisted layout snapshot and assignments, then optionally combines the
rendered pages into a PDF.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.core.settings import Settings
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import CalendarPage
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import PageRepository
from photo_composition_designer.render.page import PageComposer


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a project export."""

    pages: int
    rendered: list[Path]
    pdf_path: Path | None
    warnings: tuple[str, ...] = ()


class ProjectExporter:
    """Render project pages in order and optionally write a PDF."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        settings: Settings | None = None,
        *,
        composer: PageComposer | None = None,
        anniversaries_path: Path | None = None,
    ) -> None:
        self._database = database
        self._composer = composer or PageComposer()
        self._default_profile = (
            OutputProfile.from_settings(settings) if settings is not None else None
        )
        self._anniversaries_path = anniversaries_path

    def _service(self) -> ProjectRenderingService:
        return ProjectRenderingService(
            self._database,
            composer=self._composer,
            default_profile=self._default_profile,
            anniversaries_path=self._anniversaries_path,
        )

    def render_page(
        self,
        connection,
        project_id: int,
        page: CalendarPage,
        output_dir: Path,
    ) -> Path:
        """Render one full page to a PNG file."""
        image = self._service().render_page_image(connection, page)
        output_path = Path(output_dir) / f"page_{page.page_index:03d}.png"
        image.save(output_path, format="PNG")
        return output_path

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
        service = self._service()
        profile = service.profile_for(connection, project_id)
        pages = PageRepository(connection).list(project_id)
        for page in pages:
            warnings.extend(service.assignment_warnings(connection, page))
            try:
                path = self.render_page(connection, project_id, page, output_dir)
            except (OSError, ValueError) as error:
                warnings.append(f"page {page.page_index} could not be rendered: {error}")
                continue
            rendered.append(path)

        pdf_path: Path | None = None
        if write_pdf and profile.layout.generate_pdf and rendered:
            pdf_path = self._write_pdf(
                rendered,
                output_dir / "output.pdf",
                dpi=profile.size.dpi,
            )

        return ExportResult(
            pages=len(pages),
            rendered=rendered,
            pdf_path=pdf_path,
            warnings=tuple(warnings),
        )

    def _write_pdf(
        self,
        images: list[Path],
        output_path: Path,
        *,
        dpi: int,
    ) -> Path | None:
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
                resolution=dpi,
            )
            return output_path
        finally:
            for image in opened:
                image.close()


__all__ = ["ExportResult", "ProjectExporter"]
