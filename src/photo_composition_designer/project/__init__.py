"""Project-based calendar editor persistence and domain services."""

from photo_composition_designer.core.errors import (
    CrossProjectAssignmentError,
    DuplicateAssignmentError,
    DuplicatePhotoAssignmentError,
    DuplicateSlotAssignmentError,
    ProjectError,
    ProjectNotFoundError,
    SlotLayoutMismatchError,
)
from photo_composition_designer.db.schema import (
    SCHEMA_VERSION,
    WorkspaceDatabase,
    ensure_schema,
)
from photo_composition_designer.project.models import (
    CalendarPage,
    DistributionProposal,
    LayoutDefinition,
    LayoutSlot,
    PhotoAsset,
    PhotoAssignment,
    Project,
    ProjectAggregate,
    SourceRoot,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)
from photo_composition_designer.project.services import ProjectService

__all__ = [
    "AssignmentRepository",
    "CalendarPage",
    "CrossProjectAssignmentError",
    "DistributionProposal",
    "DuplicateAssignmentError",
    "DuplicatePhotoAssignmentError",
    "DuplicateSlotAssignmentError",
    "LayoutDefinition",
    "LayoutRepository",
    "LayoutSlot",
    "PageRepository",
    "PhotoAsset",
    "PhotoAssignment",
    "PhotoRepository",
    "Project",
    "ProjectAggregate",
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectRepository",
    "ProjectService",
    "SCHEMA_VERSION",
    "SlotLayoutMismatchError",
    "SourceRoot",
    "SourceRootRepository",
    "WorkspaceDatabase",
    "ensure_schema",
]
