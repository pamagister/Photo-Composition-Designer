"""Project settings and workspace-level project duplication routes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile, OutputProfileError
from photo_composition_designer.gui.dependencies import ProjectServiceDependency
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.rendering import profile_from_project
from photo_composition_designer.project.services import ProjectService

router = APIRouter()

_BOOL_FIELDS = (
    "calendar.use_calendar",
    "calendar.horizontal_orientation",
    "calendar.use_short_day_names",
    "calendar.use_short_month_names",
    "geo.use_photo_location_maps",
    "layout.use_rounded_corners",
    "layout.use_photo_description",
    "layout.generate_pdf",
    "layout.object_recognition",
)

_INT_FIELDS = (
    "geo.minimal_extension",
    "geo.map_size",
    "size.width",
    "size.height",
    "size.calendar_height",
    "size.dpi",
    "size.jpeg_quality",
    "layout.margin_top",
    "layout.margin_bottom",
    "layout.margin_sides",
    "layout.spacing",
)

_FLOAT_FIELDS = (
    "style.font_large.size",
    "style.font_small.size",
    "style.font_description.size",
    "style.font_anniversaries.size",
    "layout.image_score_factor",
)

_TEXT_FIELDS = (
    "calendar.language",
    "calendar.holiday_countries",
    "calendar.title",
    "style.background_color",
    "style.font_large.name",
    "style.font_large.color",
    "style.font_small.name",
    "style.font_small.color",
    "style.font_description.name",
    "style.font_description.color",
    "style.font_anniversaries.name",
    "style.font_anniversaries.color",
)


def _assign_field(payload: dict[str, Any], name: str, value: Any) -> None:
    """Store a dotted form field as nested profile data."""
    parts = name.split(".")
    if len(parts) < 2 or any(not part for part in parts):
        raise OutputProfileError(f"invalid settings field: {name}")
    node = payload
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise OutputProfileError(f"conflicting settings field: {name}")
        node = child
    node[parts[-1]] = value


def _is_checked(value: Any) -> bool:
    """Return whether a submitted checkbox or toggle is enabled."""
    return str(value).lower() in {"1", "true", "on", "yes"}


def _profile_from_form(form: Mapping[str, Any]) -> OutputProfile:
    """Build a validated output profile from submitted settings fields."""
    payload: dict[str, Any] = {}
    for name in _BOOL_FIELDS:
        _assign_field(payload, name, _is_checked(form.get(name)))
    for name in _INT_FIELDS:
        _assign_field(payload, name, _number_from_form(form, name, int))
    for name in _FLOAT_FIELDS:
        _assign_field(payload, name, _number_from_form(form, name, float))
    for name in _TEXT_FIELDS:
        value = form.get(name)
        _assign_field(payload, name, "" if value is None else str(value).strip())
    return OutputProfile.from_dict(payload)


def _number_from_form(
    form: Mapping[str, Any],
    name: str,
    converter: type[int] | type[float],
) -> int | float:
    """Convert a required numeric form field with an actionable error."""
    raw = form.get(name)
    if raw is None or not str(raw).strip():
        raise OutputProfileError(f"{name} is required")
    try:
        return converter(str(raw).strip())
    except ValueError as exc:
        raise OutputProfileError(f"{name} must be a number") from exc


def _values_from_profile(profile: OutputProfile) -> dict[str, Any]:
    """Flatten a profile into the form field values used by the template."""
    return {
        "calendar.use_calendar": profile.calendar.use_calendar,
        "calendar.language": profile.calendar.language,
        "calendar.holiday_countries": ",".join(profile.calendar.holiday_countries),
        "calendar.title": profile.calendar.title,
        "calendar.horizontal_orientation": profile.calendar.horizontal_orientation,
        "calendar.use_short_day_names": profile.calendar.use_short_day_names,
        "calendar.use_short_month_names": profile.calendar.use_short_month_names,
        "style.background_color": profile.style.background_color,
        "style.font_large.name": profile.style.font_large.name,
        "style.font_large.size": profile.style.font_large.size,
        "style.font_large.color": profile.style.font_large.color,
        "style.font_small.name": profile.style.font_small.name,
        "style.font_small.size": profile.style.font_small.size,
        "style.font_small.color": profile.style.font_small.color,
        "style.font_description.name": profile.style.font_description.name,
        "style.font_description.size": profile.style.font_description.size,
        "style.font_description.color": profile.style.font_description.color,
        "style.font_anniversaries.name": profile.style.font_anniversaries.name,
        "style.font_anniversaries.size": profile.style.font_anniversaries.size,
        "style.font_anniversaries.color": profile.style.font_anniversaries.color,
        "geo.use_photo_location_maps": profile.geo.use_photo_location_maps,
        "geo.minimal_extension": profile.geo.minimal_extension,
        "geo.map_size": profile.geo.map_size,
        "size.width": profile.size.width,
        "size.height": profile.size.height,
        "size.calendar_height": profile.size.calendar_height,
        "size.dpi": profile.size.dpi,
        "size.jpeg_quality": profile.size.jpeg_quality,
        "layout.margin_top": profile.layout.margin_top,
        "layout.margin_bottom": profile.layout.margin_bottom,
        "layout.margin_sides": profile.layout.margin_sides,
        "layout.spacing": profile.layout.spacing,
        "layout.use_rounded_corners": profile.layout.use_rounded_corners,
        "layout.image_score_factor": profile.layout.image_score_factor,
        "layout.use_photo_description": profile.layout.use_photo_description,
        "layout.generate_pdf": profile.layout.generate_pdf,
        "layout.object_recognition": profile.layout.object_recognition,
    }


def _values_from_form(form: Mapping[str, Any]) -> dict[str, Any]:
    """Keep submitted values when a settings save is rejected."""
    values: dict[str, Any] = {name: _is_checked(form.get(name)) for name in _BOOL_FIELDS}
    values.update(
        {
            name: "" if form.get(name) is None else str(form.get(name))
            for name in (*_INT_FIELDS, *_FLOAT_FIELDS, *_TEXT_FIELDS)
        }
    )
    values.update(
        {
            "project.name": str(form.get("project.name", "")),
            "project.start_date": str(form.get("project.start_date", "")),
            "project.page_count": str(form.get("project.page_count", "")),
            "project.confirm_remove": _is_checked(form.get("project.confirm_remove")),
        }
    )
    return values


def _get_project(service: ProjectService, project_id: int):
    """Return one project or raise a 404 response."""
    try:
        return service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def _settings_response(
    request: Request,
    service: ProjectService,
    project_id: int,
    *,
    values: dict[str, Any] | None = None,
    error: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    """Render the project settings page."""
    aggregate = service.open_project(project_id)
    project = aggregate.project
    profile = profile_from_project(project)
    page_start = aggregate.pages[0].start_date if aggregate.pages else ""
    source_states = [
        {"root": root, "exists": Path(root.path).is_dir()} for root in aggregate.source_roots
    ]
    form_values = _values_from_profile(profile) if values is None else values
    if values is None:
        form_values.update(
            {
                "project.name": project.name,
                "project.start_date": page_start,
                "project.page_count": len(aggregate.pages),
                "project.confirm_remove": False,
            }
        )
    return TEMPLATES.TemplateResponse(
        request,
        "project_settings.html",
        {
            "page_title": f"Settings - {project.name}",
            "project": project,
            "profile": profile,
            "values": form_values,
            "source_states": source_states,
            "error": error,
            "save_state": "Saved",
        },
        status_code=status_code,
    )


@router.get("/projects/{project_id}/settings", response_class=HTMLResponse)
def project_settings(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    error: str = "",
) -> HTMLResponse:
    """Show the per-project output settings form."""
    return _settings_response(request, service, project_id, error=error)


@router.post("/projects/{project_id}/settings", response_model=None)
async def save_project_settings(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
) -> HTMLResponse | RedirectResponse:
    """Validate and persist the per-project output profile."""
    form = await request.form()
    try:
        profile = _profile_from_form(form)
        aggregate = service.open_project(project_id)
        current_start = aggregate.pages[0].start_date if aggregate.pages else ""
        start_value = str(form.get("project.start_date", current_start)).strip()
        count_value = str(form.get("project.page_count", len(aggregate.pages))).strip()
        if not start_value:
            raise ValueError("project.start_date is required")
        if not count_value:
            raise ValueError("project.page_count is required")
        project_name = str(form.get("project.name", aggregate.project.name)).strip()
        service.update_calendar(
            project_id,
            start_date=date.fromisoformat(start_value),
            page_count=int(count_value),
            name=project_name,
            confirm_remove=_is_checked(form.get("project.confirm_remove")),
        )
        service.update_output_profile(project_id, profile)
    except (ValueError, ProjectError) as exc:
        return _settings_response(
            request,
            service,
            project_id,
            values=_values_from_form(form),
            error=str(exc),
            status_code=400,
        )
    return RedirectResponse(f"/projects/{project_id}?settings=1", status_code=303)


@router.post("/projects/{project_id}/duplicate", response_class=HTMLResponse)
def duplicate_project(
    project_id: int,
    service: ProjectServiceDependency,
    name: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Duplicate a project within the workspace and open the copy."""
    try:
        duplicate = service.duplicate_project(project_id, name=name or None)
    except (ValueError, ProjectError) as exc:
        return RedirectResponse(
            f"/projects/{project_id}/settings?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(f"/projects/{duplicate.id}?duplicated=1", status_code=303)


__all__ = ["router"]
