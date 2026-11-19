"""End-to-end browser tests for the editor workflow with Playwright.

The suite runs against a real uvicorn server and an isolated workspace. It is
skipped when Playwright or the browser binaries are unavailable. Install them
once with:

    uv run playwright install chromium firefox
    uv run pytest tests/test_browser_workflow.py -m browser

The tests use the keyboard-accessible controls (assign, replace, move, remove,
layout change) rather than HTML5 drag-and-drop, so they exercise the same
server-confirmed flows in Chromium and Firefox.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

playwright_api = pytest.importorskip("playwright.sync_api")

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from photo_composition_designer.core.appdata import data_dir  # noqa: E402
from photo_composition_designer.db.schema import WorkspaceDatabase  # noqa: E402
from photo_composition_designer.project.inventory import InventoryService  # noqa: E402
from photo_composition_designer.project.models import LayoutSlot  # noqa: E402
from photo_composition_designer.project.repositories import (  # noqa: E402
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService  # noqa: E402

pytestmark = pytest.mark.browser

BROWSERS = ("chromium", "firefox")

#: Small page size keeps preview and export rendering fast in the test suite.
TEST_PROFILE = {
    "size": {"width": 100, "height": 80, "dpi": 72},
}


def _free_port() -> int:
    """Return a currently unused local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed_workspace(tmp_path: Path) -> tuple[int, list[int], list[int], list[int]]:
    """Create a project with two pages, two slots per page and three photos."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        service = ProjectService(database)
        project = service.create_project(
            name="Browser workflow",
            page_count=2,
            start_date=datetime(2027, 1, 4),
            output_profile=TEST_PROFILE,
        )

        source = tmp_path / "source"
        for index in range(3):
            _write_photo(source / f"photo_{index:02d}.jpg", (index * 60, 20, 40))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        page_slots: list[int] = []
        with database.transaction() as connection:
            layouts = LayoutRepository(connection)
            pages = PageRepository(connection)
            for page in pages.list(project.id):
                slots = [
                    LayoutSlot(
                        id=0,
                        layout_id=0,
                        slot_key=f"slot_{index}",
                        position=index,
                        x=index * 0.5,
                        y=0.0,
                        width=0.5,
                        height=1.0,
                        z_index=0,
                        crop_mode="cover",
                    )
                    for index in range(2)
                ]
                layout = layouts.add(f"browser_{page.page_index}", 1, "Browser", slots)
                pages.set_layout(page.id, layout.id, layout.version)
                page_slots.extend(slot.id for slot in layout.slots)

        photo_ids = [
            int(row["id"])
            for row in database.connect().execute("SELECT id FROM photos ORDER BY id")
        ]
        page_ids = [page.id for page in PageRepository(database.connect()).list(project.id)]
        return project.id, page_ids, photo_ids, page_slots
    finally:
        database.close()


def _wait_for_server(port: int, *, timeout: float = 15.0) -> None:
    """Wait until the health endpoint answers."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"live server did not start on port {port}")


@pytest.fixture()
def live_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Run the web application on a real port with an isolated workspace."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    project_id, page_ids, photo_ids, slot_ids = _seed_workspace(tmp_path)

    import uvicorn

    from photo_composition_designer.gui.app import create_app
    from photo_composition_designer.gui.settings import GuiSettings

    settings = GuiSettings()
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(port)
    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "project_id": project_id,
            "page_ids": page_ids,
            "photo_ids": photo_ids,
            "slot_ids": slot_ids,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(params=BROWSERS)
def browser_page(request):
    """Yield a page in each supported browser, skipping missing binaries."""
    with sync_playwright() as playwright:
        try:
            browser = getattr(playwright, request.param).launch()
        except Exception as exc:  # pragma: no cover - depends on local install
            pytest.skip(f"{request.param} is unavailable: {exc}")
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(20_000)
        try:
            yield page
        finally:
            context.close()
            browser.close()


def _slot(page, key: str):
    return page.locator(f'.slot[data-slot-key="{key}"]')


def _open_editor(page, live_server, page_id: int) -> None:
    page.goto(f"{live_server['base_url']}/projects/{live_server['project_id']}?page={page_id}")
    expect(page.locator(".editor-canvas")).to_be_visible()
    expect(page.locator("#page-detail")).to_be_visible()


def test_assign_replace_move_and_remove(live_server, browser_page):
    page = browser_page
    photo_ids = live_server["photo_ids"]
    _open_editor(page, live_server, live_server["page_ids"][0])
    project_id = live_server["project_id"]

    first_slot = _slot(page, "slot_0")

    # Add: assign the first unused photo to the empty first slot.
    first_slot.locator("select[name=photo_id]").select_option(str(photo_ids[0]))
    first_slot.get_by_role("button", name="Assign").click()
    expect(page.locator("#workspace-status")).to_contain_text("Photo assigned.")
    expect(_slot(page, "slot_0").locator("img")).to_have_attribute(
        "data-photo-id", str(photo_ids[0])
    )

    # Replace: swap in a different unused photo and return the old one to the pool.
    first_slot = _slot(page, "slot_0")
    first_slot.locator(".replace-controls summary").click()
    first_slot.locator(".replace-controls select[name=photo_id]").select_option(str(photo_ids[1]))
    first_slot.locator(".replace-controls").get_by_role("button", name="Replace").click()
    expect(page.locator("#workspace-status")).to_contain_text("Photo replaced.")
    expect(_slot(page, "slot_0").locator("img")).to_have_attribute(
        "data-photo-id", str(photo_ids[1])
    )

    # Move: transfer the photo to the empty second slot.
    first_slot = _slot(page, "slot_0")
    first_slot.locator(".move-controls summary").click()
    first_slot.locator(".move-controls select[name=slot_b]").select_option(
        str(live_server["slot_ids"][1])
    )
    first_slot.locator(".move-controls").get_by_role("button", name="Move").click()
    expect(page.locator("#workspace-status")).to_contain_text("Photos swapped.")
    expect(_slot(page, "slot_1").locator("img")).to_have_attribute(
        "data-photo-id", str(photo_ids[1])
    )
    expect(_slot(page, "slot_0")).to_have_class("slot empty")

    # Remove: the photo returns to the unused pool and the slot becomes empty.
    _slot(page, "slot_1").locator(".slot-remove button").click()
    expect(page.locator("#workspace-status")).to_contain_text("Photo removed.")
    expect(_slot(page, "slot_1")).to_have_class("slot empty")
    expect(page.locator(".unused-pool").get_by_text("photo_01.jpg")).to_be_visible()

    # The page URL and project still render after the edits.
    page.goto(f"{live_server['base_url']}/projects/{project_id}")
    expect(page.locator(".editor-canvas")).to_be_visible()


def test_layout_change_and_page_navigation(live_server, browser_page):
    page = browser_page
    photo_ids = live_server["photo_ids"]
    page_ids = live_server["page_ids"]
    _open_editor(page, live_server, page_ids[0])

    # Assign two photos so switching to a single-slot layout displaces one.
    for index, key in enumerate(("slot_0", "slot_1")):
        slot = _slot(page, key)
        slot.locator("select[name=photo_id]").select_option(str(photo_ids[index]))
        slot.get_by_role("button", name="Assign").click()
        expect(slot.locator("img")).to_have_attribute("data-photo-id", str(photo_ids[index]))

    page.locator(".layout-change summary").click()
    page.locator('.layout-change select[name="layout_key"]').select_option("single_full")
    page.get_by_role("button", name="Preview change").click()
    preview = page.locator("#layout-change-preview")
    expect(preview).to_contain_text("keeps 1 photo(s)")
    expect(preview).to_contain_text("1 photo(s) will return to the unused pool")
    preview.get_by_role("button", name="Confirm layout change").click()
    expect(page.locator("#workspace-status")).to_contain_text("Layout changed.")
    expect(page.locator(".slot")).to_have_count(1)
    expect(page.locator(".unused-pool").get_by_text("photo_01.jpg")).to_be_visible()

    # Page navigation keeps the active state and the page URL in sync.
    page.locator(f'a.page-thumb[href$="page={page_ids[1]}"]').click()
    expect(page).to_have_url(
        f"{live_server['base_url']}/projects/{live_server['project_id']}?page={page_ids[1]}"
    )
    expect(page.locator("#workspace-status")).to_contain_text("2027-01-11")
    expect(page.locator(".page-thumb.active")).to_have_attribute("aria-current", "page")


def test_export_workflow(live_server, browser_page):
    page = browser_page
    project_id = live_server["project_id"]
    _open_editor(page, live_server, live_server["page_ids"][0])
    page.get_by_role("link", name="Export photos").click()
    expect(page.get_by_role("heading", name="Export project")).to_be_visible()

    page.get_by_role("button", name="Export pages").click()
    result = page.locator("#export-result")
    expect(result).to_contain_text("Exported 2 of 2 page(s)", timeout=60_000)
    expect(result.get_by_role("link", name="Download PDF")).to_be_visible()
    expect(result.locator(".export-files a")).to_have_count(2)
    first_file = result.locator(".export-files a").first
    assert f"/projects/{project_id}/export/files" in first_file.get_attribute("href")
