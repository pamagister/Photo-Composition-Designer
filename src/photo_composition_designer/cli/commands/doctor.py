"""Doctor command: report workspace, schema, source and profile problems."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import SCHEMA_VERSION, WorkspaceDatabase, read_version
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)

ERROR = "error"
WARNING = "warning"


@dataclass
class DoctorIssue:
    """One actionable diagnostic message."""

    level: str
    message: str


@dataclass
class DoctorReport:
    """Result of one workspace diagnostic run."""

    workspace: Path
    issues: list[DoctorIssue] = field(default_factory=list)

    def add(self, level: str, message: str) -> None:
        """Record one issue."""
        self.issues.append(DoctorIssue(level, message))

    @property
    def errors(self) -> list[DoctorIssue]:
        """Return only blocking problems."""
        return [issue for issue in self.issues if issue.level == ERROR]

    @property
    def warnings(self) -> list[DoctorIssue]:
        """Return non-blocking problems."""
        return [issue for issue in self.issues if issue.level == WARNING]


def _check_directories(report: DoctorReport, settings: GuiSettings) -> None:
    """Check application directories without creating them."""
    directories = {
        "data": settings.data_dir,
        "cache": settings.cache_dir,
        "thumbnails": settings.thumbnail_dir(),
        "previews": settings.preview_dir(),
        "exports": settings.export_dir(),
    }
    for label, path in directories.items():
        if not path.exists():
            report.add(
                WARNING,
                f"{label} directory does not exist yet: {path} (created on next GUI start)",
            )
        elif not os.access(path, os.W_OK):
            report.add(ERROR, f"{label} directory is not writable: {path}")


def _check_profiles(report: DoctorReport, projects) -> None:
    """Validate non-empty output-profile snapshots."""
    for project in projects:
        if not project.output_profile:
            continue
        try:
            OutputProfile.from_dict(project.output_profile)
        except ValueError as exc:
            report.add(ERROR, f"project {project.id} has an invalid output profile: {exc}")


def _check_sources_and_photos(report: DoctorReport, connection, project) -> None:
    """Report missing source roots, missing files and unavailable assignments."""
    root_repository = SourceRootRepository(connection)
    roots = root_repository.list(project.id)
    roots_by_id = {root.id: root for root in roots}
    missing_roots: set[int] = set()
    for root in roots:
        path = Path(root.path).expanduser()
        if not path.is_dir():
            missing_roots.add(root.id)
            level = ERROR if root.active else WARNING
            report.add(
                level,
                f"project {project.id} source root {'active ' if root.active else ''}"
                f"does not exist: {root.path}",
            )

    photo_repository = PhotoRepository(connection)
    photos = photo_repository.list(project.id)
    photos_by_id = {photo.id: photo for photo in photos}
    missing_files = 0
    missing_examples: list[str] = []
    unavailable = 0
    for photo in photos:
        if not photo.available:
            unavailable += 1
        root = roots_by_id.get(photo.source_root_id)
        if root is None or photo.source_root_id in missing_roots:
            continue
        try:
            path = resolve_source_path(root.path, photo.relative_path)
        except ValueError:
            report.add(
                ERROR,
                f"project {project.id} photo {photo.id} escapes its source root: "
                f"{photo.relative_path}",
            )
            continue
        if not path.is_file():
            missing_files += 1
            if len(missing_examples) < 3:
                missing_examples.append(f"{photo.filename} ({path})")

    if missing_files:
        examples = ", ".join(missing_examples)
        report.add(
            WARNING,
            f"project {project.id} has {missing_files} missing photo file(s): {examples}",
        )
    if unavailable:
        report.add(
            WARNING,
            f"project {project.id} has {unavailable} unavailable photo(s); run scan to reconcile",
        )

    assigned_missing = 0
    for assignment in AssignmentRepository(connection).list_by_project(project.id):
        photo = photos_by_id.get(assignment.photo_id)
        if photo is None or not photo.available:
            assigned_missing += 1
    if assigned_missing:
        report.add(
            WARNING,
            f"project {project.id} has {assigned_missing} assignment(s) to unavailable photos",
        )


def _check_projects(report: DoctorReport, settings: GuiSettings) -> None:
    """Check persisted projects, pages, sources, photos and output profiles."""
    if not settings.workspace_path().is_file():
        report.add(
            WARNING,
            f"workspace database does not exist yet: {settings.workspace_path()}",
        )
        return

    database = WorkspaceDatabase(settings.workspace_path())
    try:
        connection = database.connect()
        version = read_version(connection)
        if version != SCHEMA_VERSION:
            report.add(
                ERROR,
                f"workspace schema version {version} does not match supported "
                f"version {SCHEMA_VERSION}",
            )
            return

        try:
            projects = ProjectRepository(connection).list()
        except (json.JSONDecodeError, ValueError) as exc:
            report.add(ERROR, f"workspace project data cannot be read: {exc}")
            return

        _check_profiles(report, projects)
        for project in projects:
            pages = PageRepository(connection).list(project.id)
            if len(pages) != project.page_count:
                report.add(
                    WARNING,
                    f"project {project.id} stores {project.page_count} page(s) but has "
                    f"{len(pages)} page row(s)",
                )
            _check_sources_and_photos(report, connection, project)
    except Exception as exc:  # Diagnostics must report any unusable workspace.
        report.add(ERROR, f"workspace database cannot be checked: {exc}")
    finally:
        database.close()


def collect(settings: GuiSettings | None = None) -> DoctorReport:
    """Run all workspace checks without modifying project data."""
    resolved = settings or GuiSettings()
    report = DoctorReport(workspace=resolved.workspace_path())
    _check_directories(report, resolved)
    _check_projects(report, resolved)
    return report


def run(settings: GuiSettings | None = None) -> int:
    """Run diagnostics and print a report; return 1 when errors are found."""
    report = collect(settings)
    print(f"Workspace: {report.workspace}")
    for issue in report.issues:
        print(f"{issue.level.upper()}: {issue.message}")
    if not report.issues:
        print("OK: workspace checks passed")
    elif not report.errors:
        print("OK: no blocking problems found")
    return 1 if report.errors else 0


__all__ = ["DoctorIssue", "DoctorReport", "collect", "run"]
