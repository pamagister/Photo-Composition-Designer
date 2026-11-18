"""Typed domain models for project-based calendar editing.

The models are persistence-agnostic. Repositories map them to and from SQLite
rows; application services coordinate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Project:
    """A calendar project and its output-affecting settings snapshot."""

    id: int
    name: str
    calendar_year: int | None
    page_count: int
    settings: dict[str, Any]
    output_profile: dict[str, Any]
    import_metadata: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SourceRoot:
    """A configured source directory for a project."""

    id: int
    project_id: int
    path: str
    active: bool
    last_scan_at: str | None
    source_identity: str | None
    created_at: str


@dataclass(slots=True)
class PhotoAsset:
    """A source photo referenced by a project.

    ``relative_path`` is relative to the owning source root and uses POSIX
    separators. Originals are never copied or modified by this model.
    """

    id: int
    project_id: int
    source_root_id: int
    relative_path: str
    filename: str
    file_size: int
    mtime: float | None
    digest: str | None
    width: int
    height: int
    captured_at: str | None
    gps_lat: float | None
    gps_lon: float | None
    available: bool
    created_at: str


@dataclass(slots=True)
class CalendarPage:
    """One calendar page with explicit dates and an optional layout snapshot."""

    id: int
    project_id: int
    page_index: int
    start_date: str
    end_date: str
    description: str
    layout_id: int | None
    layout_version: int | None
    render_revision: int
    created_at: str
    updated_at: str
    hide_local_map: bool = False


@dataclass(slots=True)
class LayoutSlot:
    """One normalized slot within a layout definition."""

    id: int
    layout_id: int
    slot_key: str
    position: int
    x: float
    y: float
    width: float
    height: float
    z_index: int
    crop_mode: str


@dataclass(slots=True)
class LayoutDefinition:
    """An immutable, versioned layout template."""

    id: int
    key: str
    version: int
    name: str
    slots: list[LayoutSlot]
    created_at: str


@dataclass(slots=True)
class PhotoAssignment:
    """A photo assigned to one slot on one page."""

    id: int
    project_id: int
    page_id: int
    slot_id: int
    photo_id: int
    crop_zoom: float
    crop_focus_x: float
    crop_focus_y: float
    created_at: str


@dataclass(slots=True)
class DistributionProposal:
    """An in-memory distribution proposal.

    Photo IDs are grouped per page. Applying a proposal is a separate,
    transactional operation; constructing one never mutates the project.
    """

    strategy: str
    pages: list[list[int]]
    unassigned: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seed: int | None = None


@dataclass(slots=True)
class ProjectAggregate:
    """A project together with its pages and source roots."""

    project: Project
    pages: list[CalendarPage]
    source_roots: list[SourceRoot]
