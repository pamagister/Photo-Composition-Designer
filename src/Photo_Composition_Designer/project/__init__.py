"""Project-based calendar editor persistence and domain services."""

from Photo_Composition_Designer.project.db import (
    SCHEMA_VERSION,
    WorkspaceDatabase,
    ensure_schema,
)
from Photo_Composition_Designer.project.errors import (
    CrossProjectAssignmentError,
    DuplicateAssignmentError,
    DuplicatePhotoAssignmentError,
    DuplicateSlotAssignmentError,
    ProjectError,
    ProjectNotFoundError,
    SlotLayoutMismatchError,
)
from Photo_Composition_Designer.project.models import (
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
from Photo_Composition_Designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)
from Photo_Composition_Designer.project.services import ProjectService

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
