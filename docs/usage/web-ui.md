# Web UI guide

The local web UI is the primary interface.

## Start the app

- **Windows installer:** open the Start Menu and choose **Photo Composition
  Designer**. The shortcut runs `photo-composition-designer.exe gui
  --open-browser` and opens the project page in your browser. Keep the console
  window open while the app runs, or stop it with **Stop server** in the web UI.
- **Linux archive:** run `./photo-composition-designer` from the extracted
  folder.
- **From source or PyPI:** run `photo-composition-designer`, or
  `uv run photo-composition-designer` inside the repository.

Then open `http://127.0.0.1:8767/`. The explicit `gui` command is equivalent.
Use `--host`, `--port` and `--log-level` with the `gui` command to change the
listener; the default binds to localhost only. Add `--open-browser` to open the
browser automatically once the server is ready.

All data is stored in the central workspace and cannot affect source photos:
originals are only read, never moved, renamed or modified.

## Create a project

1. Open **Projects** and choose **New project**.
2. Enter a name, the number of weekly pages and the first week's start date.
3. Optionally pick a starting layout and a source directory.

The project snapshots the current output-profile defaults at creation time. Later
changes to workspace defaults therefore cannot alter an existing project.

The **Projects** overview lists every project as a row. Each row links to the
editor and offers **Export project (.pcd)** and **Duplicate project**. Use
**Import project (.pcd)** next to **New project** to create a project from a
portable archive.

## Global settings and layouts

**App settings** configures the shared `anniversaries.ini` and `locations.ini`
paths. The bundled anniversary file and the merged German and English location
files are always loaded; a custom location file is layered on top and its
entries override built-ins with the same spelling. The files stay outside
projects and are read during scanning and rendering. Each setting has a
**Show built-in format** action that displays the bundled file format.

Location names are resolved during a source scan: EXIF GPS wins, then a
case-insensitive whole-word match against the configured location names in the
filename. If no coordinate can be resolved, pages render a small default map
centered on Berlin.

**Layouts** opens the global layout editor. Define normalized slot rectangles in
the JSON slot list and save a new version. Applying a later version is explicit:
pages already using an older version keep their existing layout snapshots.

## Add and scan sources

* Add one or more local directories under **Source directories**. Exactly one
  root is active; scans use the active root.
* **Scan active source directory** reconciles the inventory and reports added,
  updated and unavailable photos, the scan duration and the symlink policy.
  Missing files are marked unavailable without deleting assignments.
* **Relink or change directory** previews the effect of a moved directory: it
  lists matched, ambiguous and missing basenames before anything changes.
  Ambiguous basenames are never silently bound to a different file.
* Adding, changing, activating and removing source roots is transactional.

## Preview and apply a distribution

Open **Extras** in the project toolbar and choose **Distribute**. On the
distribution page, choose a strategy (`Equal`, `Random` with an optional seed, or
`Date aware`) and select **Preview distribution**. The preview shows per-page
samples, filled and empty slots, overflow and the total unassigned count without
changing the project. **Apply distribution** persists the reviewed proposal in
one transaction; repeating the same confirmation is a no-op and a stale preview
is rejected.

**Extras → Check** is currently under construction.

Photos that exceed the available slots stay in the unused pool. Empty slots are
valid and are reported explicitly.

## Curate pages

The editor shows page thumbnails in the sidebar, the rendered page preview and
slot grid on the canvas, and the unused photos below it.

The large page preview is also a drop target. Slot-shaped dropzones are overlaid
on the rendered page, so you can drag a photo straight onto the page. Empty
slots show a dashed "Drop photo" zone; occupied slots accept a drop to replace
their photo. Dragging one dropzone onto another swaps the two photos. The
dropzones mirror the right-hand slot grid and stay aligned with the rendered
collage; the right-hand panel remains the primary, fully keyboard-accessible
control surface.

* **Assign** – drag an unused photo onto an empty slot or dropzone, choose it in
  the slot's select and press **Assign**, or check several unused photos and use
  **Assign selected** to fill the empty slots in one action.
* **Replace** – drag an unused photo onto an occupied slot or dropzone, or open
  **Replace** in the slot. The previous photo returns to the unused pool.
* **Swap or move** – drag one assigned photo onto another slot or dropzone, or use
  the slot's **Move** select. Dropping a photo onto its own slot does nothing.
* **Remove** – press the slot's remove button.
* **Crop** – open **Crop** in an occupied slot to adjust zoom and focal point. You
  can also click a dropzone (or its slot) to select it and use the arrow keys to
  pan in 2% steps and `+`/`-` to zoom in 2% steps; at 1x, panning is available
  only along edges already cropped by the slot, and stops at the source image
  boundary. The preview refreshes live. Arrow keys inside text fields do not
  change the crop. Crop settings are assignment properties; the source file is
  untouched.
* **Description** – edit the page description at the bottom of the canvas.
* **Page overrides** – the collapsible **Page overrides** area in the toolbar
  can hide the local map, calendar strip and description for one page, and can
  center the description. The options only appear when the corresponding global
  setting is enabled. The title page shows the composition title, defaults to
  hiding the map and description, and centers the description. A map is never
  rendered on the title page or on a page without a visible calendar strip. The
  map starts one slot spacing below the collage and follows the rounded-corner
  setting.
* **Layout** – open **Change layout**, choose a layout and select
  **Preview change**. Assignments are preserved where possible, and displaced
  photos are listed before you confirm. Choose **Automatic** to derive the
  grid from the photos themselves; see
  [Automatic collage layout](auto-layout.md).
* **Change page** – select a page thumbnail. The sidebar marks the active page.
* **Photos** – switch the horizontal photo strip between all photos and unused
  photos. A yellow `!` marks photos used more than once.

Every edit is committed in one transaction, increments the page render revision
and refreshes the page preview and unused pool. Adding or removing a photo never
changes the layout.

### Keyboard accessibility

Every drag-and-drop action has a keyboard equivalent: the slot selects, the
remove button, the move control and the layout form. With a page thumbnail
focused, ArrowUp and ArrowDown move to the previous or next page. Slots expose
group labels, notices are announced as status messages, focus is always visible,
and a skip link jumps to the main content. At narrow widths the panels stack and
the page list becomes a horizontal strip; no control is hidden in a drawer.

## Page previews and caching

Sidebar thumbnails and the canvas preview are rendered from project data at
reduced resolution. Slot spacing and rounded photo corners follow the project
output profile; the calendar strip is composed below the photos. Previews are
cached by page revision, layout version, output profile hash, shared anniversary
file version and requested width. Photo thumbnails are cached by photo and
source modification time. A cached preview is served without decoding the
originals again. Editing a page invalidates its cached preview.

## Project settings

**Project settings** edits the name, start date, page count, title page usage and
composition title, and the output profile: calendar language and holiday
countries, page size and DPI, margins, slot spacing, text margin, description
alignment, fonts and colors, map mode, and the description toggle. The calendar
language is a dropdown of region-qualified locales; holiday countries are a
language-dependent checkbox selection of subdivisions, and no selection means
nationwide holidays. The map can be turned off, restricted to pages with location
data, or forced on for every page with a visible calendar strip. Removing pages
with saved content requires confirmation. Settings are validated before saving,
and actual render-affecting changes increment page revisions.

## Duplicate a project

The **Projects** overview offers **Duplicate project** on every project row. Enter
a new project name in the row and confirm. The duplicate copies pages, layout
snapshots, assignments, source roots, inventory and the output profile inside the
workspace. The copy is fully independent of the original. It is not a portable
archive: source references remain relative and relinkable.

## Preview and export

* **Preview all pages** renders every page in project order and opens the first
  page.
* **Export photos** opens the export dialog. Select **JPG**, **PDF** or both.
  JPG pages use the project's DPI and JPEG quality defaults, which can be
  overridden for this export. The default destination is a project-specific
  folder under the OS Pictures/Bilder directory when it exists; an absolute local
  path or workspace-relative folder can be entered instead. At least one format
  must be selected. A live percentage appears in the rendering message, and the
  exported folder path is a link that opens the folder in the OS file manager.
* **Export project (.pcd)** on the Projects overview downloads a reference-only
  project archive. **Import project (.pcd)** creates a new project from such an
  archive. Archives include layout snapshots, assignments and source references,
  not photo files; source directories may need relinking on another computer.
* Exported pages and the PDF follow the exact project page order and use the
  project's stored output profile.
* Missing or unavailable assets produce actionable warnings instead of silent
  partial output.

## Troubleshooting

* Run `photo-composition-designer doctor` to check the schema version, workspace
  paths, source roots, missing photos, cache directories and profile validity.
* If photos moved, relink the source root and rescan. Assignments are preserved
  when a photo is temporarily missing.
* Delete the `thumbnails/` or `previews/` cache directories to force regeneration;
  they are disposable and rebuild on demand.
