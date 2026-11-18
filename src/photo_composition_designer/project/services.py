"""Application services for project lifecycle and settings snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import Project, ProjectAggregate
from photo_composition_designer.project.repositories import (
    PageRepository,
    ProjectRepository,
    SourceRootRepository,
)


def _now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def _as_date(value: datetime | date) -> date:
    """Normalize a date or datetime to a date."""
    return value.date() if isinstance(value, datetime) else value


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
                page_repository.create(
                    project.id,
                    page_index,
                    page_start.isoformat(),
                    page_end.isoformat(),
                    description=description,
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

    def get_project(self, project_id: int) -> Project:
        """Return one project or raise a domain error."""
        project = ProjectRepository(self._database.connect()).get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")
        return project

    def list_projects(self) -> list[Project]:
        """Return all projects ordered by ID."""
        return ProjectRepository(self._database.connect()).list()
