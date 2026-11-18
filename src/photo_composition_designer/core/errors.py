"""Domain errors raised by the project persistence layer."""

from __future__ import annotations


class ProjectError(Exception):
    """Base class for project domain errors."""


class ProjectNotFoundError(ProjectError):
    """Raised when a project does not exist."""


class DuplicateAssignmentError(ProjectError):
    """Raised when an assignment would violate a uniqueness invariant."""


class DuplicatePhotoAssignmentError(DuplicateAssignmentError):
    """Raised when a photo is already assigned in the project."""


class DuplicateSlotAssignmentError(DuplicateAssignmentError):
    """Raised when a page slot is already occupied."""


class CrossProjectAssignmentError(ProjectError):
    """Raised when an assignment references rows from different projects."""


class SlotLayoutMismatchError(ProjectError):
    """Raised when a slot does not belong to the page layout."""
