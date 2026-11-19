"""Ordered full-page rendering and image/PDF export from project data.

Renders each page in project order using the project's own output profile and
the persisted layout snapshot and assignments, then writes the requested output
formats: individual JPEG/PNG pages and/or a combined PDF.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.core.settings import Settings
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import CalendarPage
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import PageRepository
from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.page import PageComposer

_IMAGE_SUFFIXES = {"JPEG": ".jpg", "PNG": ".png"}


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a project export."""

    pages: int
    rendered: list[Path]
    pdf_path: Path | None
    warnings: tuple[str, ...] = ()
    rendered_pages: int = 0


class ProjectExporter:
    """Render project pages in order and write the requested output formats."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        settings: Settings | None = None,
        *,
        composer: PageComposer | None = None,
        anniversaries_path: Path | None = None,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._database = database
        self._composer = composer or PageComposer(object_detector=object_detector)
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

    def _save_page(
        self,
        image: Image.Image,
        page: CalendarPage,
        output_dir: Path,
        *,
        image_format: str,
        quality: int,
        dpi: int,
    ) -> Path:
        """Write one rendered page in the requested image format."""
        image_format = image_format.upper()
        suffix = _IMAGE_SUFFIXES[image_format]
        output_path = Path(output_dir) / f"page_{page.page_index:03d}{suffix}"
        if image_format == "JPEG":
            image.convert("RGB").save(
                output_path,
                format="JPEG",
                quality=quality,
                dpi=(dpi, dpi),
                optimize=True,
            )
        else:
            image.save(output_path, format="PNG", dpi=(dpi, dpi))
        return output_path

    def render_page(
        self,
        connection,
        project_id: int,
        page: CalendarPage,
        output_dir: Path,
        *,
        image_format: str = "PNG",
        quality: int = 90,
        dpi: int = 300,
    ) -> Path:
        """Render one full page to an image file."""
        image = self._service().render_page_image(connection, page)
        return self._save_page(
            image,
            page,
            output_dir,
            image_format=image_format,
            quality=quality,
            dpi=dpi,
        )

    def render_project(
        self,
        project_id: int,
        output_dir: Path,
        *,
        write_pdf: bool = True,
        write_pages: bool = True,
        image_format: str = "PNG",
        jpeg_quality: int | None = None,
        dpi: int | None = None,
    ) -> ExportResult:
        """Render all pages in project order and write the requested outputs.

        Individual page images are written when ``write_pages`` is true. The PDF
        is always composed from a lossless render of each page, so disabling the
        JPEG output does not reduce the PDF quality. Missing or unavailable
        assets are reported as warnings instead of aborting the export.
        """
        image_format = image_format.upper()
        if image_format not in _IMAGE_SUFFIXES:
            raise ValueError(f"unsupported export image format: {image_format}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        rendered: list[Path] = []
        rendered_pages = 0

        connection = self._database.connect()
        service = self._service()
        profile = service.profile_for(connection, project_id)
        pages = PageRepository(connection).list(project_id)
        effective_dpi = int(dpi) if dpi is not None else profile.size.dpi
        effective_quality = (
            int(jpeg_quality) if jpeg_quality is not None else profile.size.jpeg_quality
        )

        with tempfile.TemporaryDirectory(prefix="pcd-export-") as temporary:
            temporary_dir = Path(temporary)
            pdf_sources: list[Path] = []
            for page in pages:
                warnings.extend(service.assignment_warnings(connection, page))
                try:
                    image = service.render_page_image(connection, page)
                except (OSError, ValueError) as error:
                    warnings.append(f"page {page.page_index} could not be rendered: {error}")
                    continue
                rendered_pages += 1
                if write_pages:
                    rendered.append(
                        self._save_page(
                            image,
                            page,
                            output_dir,
                            image_format=image_format,
                            quality=effective_quality,
                            dpi=effective_dpi,
                        )
                    )
                if write_pdf:
                    if write_pages and image_format == "PNG":
                        pdf_sources.append(rendered[-1])
                    else:
                        pdf_source = temporary_dir / f"page_{page.page_index:03d}.png"
                        image.save(pdf_source, format="PNG")
                        pdf_sources.append(pdf_source)

            pdf_path: Path | None = None
            if write_pdf and pdf_sources:
                pdf_path = self._write_pdf(
                    pdf_sources,
                    output_dir / "output.pdf",
                    dpi=effective_dpi,
                )

        return ExportResult(
            pages=len(pages),
            rendered=rendered,
            pdf_path=pdf_path,
            warnings=tuple(warnings),
            rendered_pages=rendered_pages,
        )

    def _write_pdf(
        self,
        images: list[Path],
        output_path: Path,
        *,
        dpi: int,
    ) -> Path | None:
        """Combine rendered page images into a single PDF."""
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
