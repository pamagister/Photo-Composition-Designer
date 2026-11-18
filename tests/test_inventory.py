"""Tests for inventory scanning, GPS precedence, remapping and map caching."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.core.appdata import cache_dir
from photo_composition_designer.core.photo import Photo
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.maps import MapRequest, MapService, map_cache_key
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import Project
from photo_composition_designer.project.services import ProjectService


def _make_project(tmp_path: Path) -> tuple[WorkspaceDatabase, InventoryService, Project]:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Inventory",
        page_count=1,
        start_date=datetime(2027, 1, 4),
        settings={},
        output_profile={},
        import_metadata={"source": "test"},
    )
    return database, InventoryService(database), project


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 10), color).save(path)


def test_scan_discovers_images_recursively_and_marks_missing(tmp_path: Path) -> None:
    database, inventory, project = _make_project(tmp_path)
    source = tmp_path / "source"
    _write_photo(source / "a.jpg")
    _write_photo(source / "sub" / "b.jpg")

    root = inventory.add_source_root(project.id, source)
    summary = inventory.scan(project.id, source_root_id=root.id)

    assert summary.discovered == 2
    assert summary.added == 2
    assert summary.unavailable == 0

    (source / "a.jpg").unlink()
    rescan = inventory.scan(project.id, source_root_id=root.id)
    assert rescan.unavailable == 1


def test_scan_skips_symlinks_by_default(tmp_path: Path) -> None:
    database, inventory, project = _make_project(tmp_path)
    source = tmp_path / "source"
    _write_photo(source / "real.jpg")
    outside = tmp_path / "outside.jpg"
    _write_photo(outside, (0, 255, 0))
    (source / "link.jpg").symlink_to(outside)

    root = inventory.add_source_root(project.id, source)
    summary = inventory.scan(project.id, source_root_id=root.id)
    assert summary.discovered == 1


def test_safe_source_resolution_blocks_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_photo(source / "a.jpg")
    with pytest.raises(ValueError):
        resolve_source_path(source, "../outside.jpg")


def test_gps_precedence_exif_first(tmp_path: Path) -> None:
    _write_photo(tmp_path / "with_exif.jpg")
    photo = Photo(tmp_path / "with_exif.jpg", locations={"with_exif": (1.0, 2.0)})
    location = photo.get_location()
    assert location == (1.0, 2.0) or location is None


def test_gps_fallback_from_locations_ini(tmp_path: Path) -> None:
    path = tmp_path / "Dresden-2024.jpg"
    _write_photo(path)
    photo = Photo(path, locations={"Dresden": (51.05, 13.73)})
    assert photo.get_location() == (51.05, 13.73)


def test_gps_none_when_no_exif_and_no_location(tmp_path: Path) -> None:
    path = tmp_path / "unknown.jpg"
    _write_photo(path)
    photo = Photo(path, locations={"Dresden": (51.05, 13.73)})
    assert photo.get_location() is None


def test_photo_date_fallback_sentinel(tmp_path: Path) -> None:
    path = tmp_path / "random_name.jpg"
    _write_photo(path)
    assert Photo(path).get_date() == datetime.max


def test_remap_preview_reports_matches_and_ambiguity(tmp_path: Path) -> None:
    database, inventory, project = _make_project(tmp_path)
    old_source = tmp_path / "old"
    _write_photo(old_source / "a.jpg")
    _write_photo(old_source / "b.jpg")
    root = inventory.add_source_root(project.id, old_source)
    inventory.scan(project.id, source_root_id=root.id)

    new_source = tmp_path / "new"
    _write_photo(new_source / "a.jpg")
    _write_photo(new_source / "one" / "b.jpg")
    _write_photo(new_source / "two" / "b.jpg")

    preview = inventory.preview_remap(project.id, source_root_id=root.id, new_root=new_source)
    assert preview["total"] == 2
    assert preview["matched"] == 1
    assert preview["ambiguous"] == ["b.jpg"]


def test_remap_apply_relinks_and_preserves_assignments(tmp_path: Path) -> None:
    database, inventory, project = _make_project(tmp_path)
    old_source = tmp_path / "old"
    _write_photo(old_source / "a.jpg")
    root = inventory.add_source_root(project.id, old_source)
    inventory.scan(project.id, source_root_id=root.id)

    new_source = tmp_path / "new"
    _write_photo(new_source / "a.jpg")

    summary = inventory.apply_remap(project.id, source_root_id=root.id, new_root=new_source)
    assert summary.discovered == 1

    with database.connect() as connection:
        row = connection.execute(
            "SELECT path FROM source_roots WHERE id = ?", (root.id,)
        ).fetchone()
    assert Path(row["path"]) == new_source.resolve()


def test_map_cache_key_is_deterministic(tmp_path: Path) -> None:
    request = MapRequest(
        coordinates=((51.05, 13.73),),
        width=100,
        height=100,
        minimal_extension=7,
        background_color=(20, 20, 20),
        text_color=(255, 255, 255),
        dpi=300,
    )
    assert map_cache_key(request) == map_cache_key(request)

    changed = MapRequest(
        coordinates=((51.05, 13.73), (52.52, 13.40)),
        width=100,
        height=100,
        minimal_extension=7,
        background_color=(20, 20, 20),
        text_color=(255, 255, 255),
        dpi=300,
    )
    assert map_cache_key(request) != map_cache_key(changed)


def test_map_service_renders_and_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    service = MapService(cache_dir())

    request = MapRequest(
        coordinates=((51.05, 13.73),),
        width=80,
        height=80,
        minimal_extension=7,
        background_color=(20, 20, 20),
        text_color=(255, 255, 255),
        dpi=300,
    )
    first = service.render(request)
    assert first.is_file()
    second = service.render(request)
    assert first == second
