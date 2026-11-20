"""Application services for project lifecycle and settings snapshots."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import PhotoAsset, Project, ProjectAggregate
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)


def _now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def _as_date(value: datetime | date) -> date:
    """Normalize a date or datetime to a date."""
    return value.date() if isinstance(value, datetime) else value


_COPY_SUFFIX_RE = re.compile(r"^(.*) copy(?:-(\d+))?$")


def _next_copy_name(name: str, existing_names: set[str]) -> str:
    """Return the next free automatic copy name for a project."""
    match = _COPY_SUFFIX_RE.match(name)
    base = match.group(1) if match else name
    candidate = f"{base} copy"
    if candidate not in existing_names:
        return candidate
    index = 1
    while f"{base} copy-{index}" in existing_names:
        index += 1
    return f"{base} copy-{index}"


class ProjectService:
    """Create, open, close and save calendar projects."""

    def __init__(self, database: WorkspaceDatabase) -> None:
        self._database = database

    def create_project(
        self,
        *,
        name: str,
        page_count: int,
        start_date: datetime | date,
        settings: dict[str, Any] | None = None,
        output_profile: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        calendar_year: int | None = None,
        description: str = "",
    ) -> Project:
        """Create a project and its explicitly dated pages in one transaction."""
        if not name.strip():
            raise ValueError("project name must not be empty")
        if page_count < 1:
            raise ValueError("page_count must be at least 1")

        # New projects snapshot the current application defaults so later
        # workspace changes can never alter an existing project.
        profile = (
            OutputProfile.from_dict(output_profile) if output_profile else OutputProfile.default()
        )

        first_day = _as_date(start_date)
        year = calendar_year if calendar_year is not None else first_day.year

        with self._database.transaction() as connection:
            project_repository = ProjectRepository(connection)
            page_repository = PageRepository(connection)
            project = project_repository.create(
                name=name,
                page_count=page_count,
                calendar_year=year,
                settings=settings or {},
                output_profile=profile.to_dict(),
                import_metadata=import_metadata or {},
                created_at=_now(),
            )
            for page_index in range(page_count):
                page_start = first_day + timedelta(days=7 * page_index)
                page_end = page_start + timedelta(days=6)
                is_title_page = profile.calendar.use_title_page and page_index == 0
                page_repository.create(
                    project.id,
                    page_index,
                    page_start.isoformat(),
                    page_end.isoformat(),
                    description=description,
                    hide_local_map=is_title_page,
                    hide_calendar_strip=is_title_page,
                    hide_description=is_title_page,
                    created_at=project.created_at,
                )

        return project

    def open_project(self, project_id: int) -> ProjectAggregate:
        """Return a project with its pages and source roots."""
        connection = self._database.connect()
        project = ProjectRepository(connection).get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")
        return ProjectAggregate(
            project=project,
            pages=PageRepository(connection).list(project_id),
            source_roots=SourceRootRepository(connection).list(project_id),
        )

    def close_project(self, project_id: int) -> None:
        """Close a project.

        The service is stateless: closing only verifies that the project still
        exists. Reopening reads the same persisted state.
        """
        if ProjectRepository(self._database.connect()).get(project_id) is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")

    def save_project(
        self,
        project_id: int,
        *,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
        output_profile: dict[str, Any] | None = None,
    ) -> Project:
        """Persist mutable project fields and settings snapshots."""
        if name is not None and not name.strip():
            raise ValueError("project name must not be empty")

        with self._database.transaction() as connection:
            return ProjectRepository(connection).update(
                project_id,
                name=name,
                settings=settings,
                output_profile=output_profile,
                updated_at=_now(),
            )

    def rename_project(self, project_id: int, name: str) -> Project:
        """Rename a project."""
        return self.save_project(project_id, name=name)

    def update_output_profile(
        self,
        project_id: int,
        output_profile: OutputProfile | dict[str, Any],
    ) -> Project:
        """Validate and persist a project output profile.

        The stored profile is a complete snapshot. Every page revision is
        incremented only when an output-affecting value actually changed, so
        previews and exports are invalidated together.

        Raises:
            ProjectNotFoundError: If the project does not exist.
            OutputProfileError: If the supplied profile is invalid.
        """
        profile = (
            output_profile
            if isinstance(output_profile, OutputProfile)
            else OutputProfile.from_dict(output_profile)
        )

        with self._database.transaction() as connection:
            project_repository = ProjectRepository(connection)
            current = project_repository.get(project_id)
            if current is None:
                raise ProjectNotFoundError(f"project {project_id} does not exist")
            current_profile = (
                OutputProfile.from_dict(current.output_profile)
                if current.output_profile
                else OutputProfile.default()
            )
            updated = project_repository.update(
                project_id,
                output_profile=profile.to_dict(),
                updated_at=_now(),
            )
            if profile.calendar.use_title_page and not current_profile.calendar.use_title_page:
                pages = PageRepository(connection).list(project_id)
                if pages:
                    PageRepository(connection).set_local_overrides(
                        pages[0].id,
                        hide_local_map=True,
                        hide_calendar_strip=True,
                        hide_description=True,
                    )
            elif current_profile.calendar.use_title_page and not profile.calendar.use_title_page:
                pages = PageRepository(connection).list(project_id)
                if pages:
                    PageRepository(connection).set_local_overrides(
                        pages[0].id,
                        hide_local_map=False,
                        hide_calendar_strip=False,
                        hide_description=False,
                    )
            if profile.profile_hash() != current_profile.profile_hash():
                PageRepository(connection).increment_revisions(project_id)
        return updated

    def update_calendar(
        self,
        project_id: int,
        *,
        start_date: datetime | date,
        page_count: int,
        name: str | None = None,
        confirm_remove: bool = False,
    ) -> Project:
        """Change a project's weekly date range and page count.

        Pages are identified by their index, so changing the start date keeps
        existing assignments attached to the same relative week. New pages
        inherit the final existing page's layout snapshot.
        """
        if page_count < 1:
            raise ValueError("page_count must be at least 1")
        if name is not None and not name.strip():
            raise ValueError("project name must not be empty")
        first_day = _as_date(start_date)

        with self._database.transaction() as connection:
            project_repository = ProjectRepository(connection)
            project = project_repository.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"project {project_id} does not exist")
            page_repository = PageRepository(connection)
            pages = page_repository.list(project_id)

            if page_count < len(pages):
                if page_repository.has_content_from(project_id, page_count) and not confirm_remove:
                    raise ValueError(
                        "Removing pages with photos or descriptions requires confirmation"
                    )
                page_repository.delete_from_index(project_id, page_count)
                pages = pages[:page_count]

            last_layout = pages[-1] if pages else None
            for page_index in range(len(pages), page_count):
                page_start = first_day + timedelta(days=7 * page_index)
                page_end = page_start + timedelta(days=6)
                page_repository.create(
                    project_id,
                    page_index,
                    page_start.isoformat(),
                    page_end.isoformat(),
                    layout_id=last_layout.layout_id if last_layout else None,
                    layout_version=last_layout.layout_version if last_layout else None,
                    created_at=_now(),
                )

            for page_index, page in enumerate(page_repository.list(project_id)):
                page_start = first_day + timedelta(days=7 * page_index)
                page_end = page_start + timedelta(days=6)
                if (
                    page.start_date != page_start.isoformat()
                    or page.end_date != page_end.isoformat()
                ):
                    page_repository.update_dates(
                        page.id,
                        page_start.isoformat(),
                        page_end.isoformat(),
                    )

            return project_repository.update(
                project_id,
                name=name,
                calendar_year=first_day.year,
                page_count=page_count,
                updated_at=_now(),
            )

    def duplicate_project(self, project_id: int, *, name: str | None = None) -> Project:
        """Deep copy a project into an independent workspace project.

        Pages, layout snapshots, assignments, source roots, inventory and the
        output profile are copied in one transaction. Source files stay in
        place and source-root paths remain relative and relinkable.

        Raises:
            ProjectNotFoundError: If the source project does not exist.
            ValueError: If the duplicate name is empty.
        """
        with self._database.transaction() as connection:
            project_repository = ProjectRepository(connection)
            source = project_repository.get(project_id)
            if source is None:
                raise ProjectNotFoundError(f"project {project_id} does not exist")

            existing_names = {project.name for project in project_repository.list()}
            duplicate_name = (
                name if name is not None else _next_copy_name(source.name, existing_names)
            ).strip()
            if not duplicate_name:
                raise ValueError("project name must not be empty")

            timestamp = _now()
            duplicate = project_repository.create(
                name=duplicate_name,
                page_count=source.page_count,
                calendar_year=source.calendar_year,
                settings=source.settings,
                output_profile=source.output_profile,
                import_metadata=source.import_metadata,
                created_at=timestamp,
            )

            source_root_repository = SourceRootRepository(connection)
            duplicate_root_ids: dict[int, int] = {}
            for root in source_root_repository.list(project_id):
                copied_root = source_root_repository.add(
                    duplicate.id,
                    root.path,
                    active=root.active,
                    source_identity=root.source_identity,
                    last_scan_at=root.last_scan_at,
                    created_at=timestamp,
                )
                duplicate_root_ids[root.id] = copied_root.id

            photo_repository = PhotoRepository(connection)
            source_photos = photo_repository.list(project_id)
            photo_repository.upsert_many(
                PhotoAsset(
                    id=0,
                    project_id=duplicate.id,
                    source_root_id=duplicate_root_ids[photo.source_root_id],
                    relative_path=photo.relative_path,
                    filename=photo.filename,
                    file_size=photo.file_size,
                    mtime=photo.mtime,
                    digest=photo.digest,
                    width=photo.width,
                    height=photo.height,
                    captured_at=photo.captured_at,
                    gps_lat=photo.gps_lat,
                    gps_lon=photo.gps_lon,
                    available=photo.available,
                    created_at=timestamp,
                )
                for photo in source_photos
            )
            duplicate_photo_ids = {
                (photo.source_root_id, photo.relative_path): photo.id
                for photo in photo_repository.list(duplicate.id)
            }
            duplicate_photo_id_by_source: dict[int, int] = {
                photo.id: duplicate_photo_ids[
                    (duplicate_root_ids[photo.source_root_id], photo.relative_path)
                ]
                for photo in source_photos
            }

            page_repository = PageRepository(connection)
            duplicate_page_ids: dict[int, int] = {}
            for page in page_repository.list(project_id):
                copied_page = page_repository.create(
                    duplicate.id,
                    page.page_index,
                    page.start_date,
                    page.end_date,
                    description=page.description,
                    layout_id=page.layout_id,
                    layout_version=page.layout_version,
                    created_at=timestamp,
                )
                duplicate_page_ids[page.id] = copied_page.id

            assignment_repository = AssignmentRepository(connection)
            for assignment in assignment_repository.list_by_project(project_id):
                assignment_repository.assign(
                    duplicate.id,
                    duplicate_page_ids[assignment.page_id],
                    assignment.slot_id,
                    duplicate_photo_id_by_source[assignment.photo_id],
                    crop_zoom=assignment.crop_zoom,
                    crop_focus_x=assignment.crop_focus_x,
                    crop_focus_y=assignment.crop_focus_y,
                    created_at=timestamp,
                )

        return duplicate

    def delete_project(self, project_id: int) -> None:
        """Delete a project and its project-owned rows.

        Raises:
            ProjectNotFoundError: If the project does not exist.
        """
        with self._database.transaction() as connection:
            repository = ProjectRepository(connection)
            if repository.get(project_id) is None:
                raise ProjectNotFoundError(f"project {project_id} does not exist")
            repository.delete(project_id)

    def get_project(self, project_id: int) -> Project:
        """Return one project or raise a domain error."""
        project = ProjectRepository(self._database.connect()).get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")
        return project

    def list_projects(self) -> list[Project]:
        """Return all projects ordered by ID."""
        return ProjectRepository(self._database.connect()).list()
