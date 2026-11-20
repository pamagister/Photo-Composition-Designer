"""Compatibility shim for the historical projects route module.

The project routes are now split by responsibility:

* :mod:`project_lifecycle` - listing, creation, detail, rename and deletion
* :mod:`project_preview` - previews, layout previews and preview assets
* :mod:`project_inventory` - inventory and source-root management
* :mod:`project_distribution` - distribution proposals and application

This module re-exports the shared helpers and routers so existing imports keep
working. New code should import the focused modules directly.
"""

from __future__ import annotations

from photo_composition_designer.gui.routes.project_context import (
    _canvas_response,
    _collage_box_for_page,
    _error_redirect,
    _load_project,
    _page_context,
    _project_context,
    _slot_overlay_data,
    _submit_detection_warmups,
)
from photo_composition_designer.gui.routes.project_distribution import (
    _distribution_context,
)
from photo_composition_designer.gui.routes.project_distribution import (
    router as distribution_router,
)
from photo_composition_designer.gui.routes.project_inventory import (
    _inventory_context,
)
from photo_composition_designer.gui.routes.project_inventory import (
    router as inventory_router,
)
from photo_composition_designer.gui.routes.project_lifecycle import (
    _assign_layout_to_all_pages,
    _project_title_image_urls,
)
from photo_composition_designer.gui.routes.project_lifecycle import (
    router as lifecycle_router,
)
from photo_composition_designer.gui.routes.project_preview import (
    _layout_preview_response,
)
from photo_composition_designer.gui.routes.project_preview import (
    router as preview_router,
)

router = lifecycle_router


__all__ = [
    "_assign_layout_to_all_pages",
    "_canvas_response",
    "_collage_box_for_page",
    "_distribution_context",
    "_error_redirect",
    "_inventory_context",
    "_layout_preview_response",
    "_load_project",
    "_page_context",
    "_project_context",
    "_project_title_image_urls",
    "_slot_overlay_data",
    "_submit_detection_warmups",
    "distribution_router",
    "inventory_router",
    "preview_router",
    "router",
]
