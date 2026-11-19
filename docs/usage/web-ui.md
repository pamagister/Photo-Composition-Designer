# Web UI guide

The local web UI is the primary interface. Start it with:

```bash
uv run photo-composition-designer gui
```

Then open `http://127.0.0.1:8767/`. Use `--host`, `--port` and `--log-level` to
change the listener; the default binds to localhost only.

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
  nudge the focal point and `+`/`-` to zoom; the preview refreshes live. Arrow
  keys inside text fields do not change the crop. Crop settings are assignment
  properties; the source file is untouched.
* **Description** – edit the page description at the bottom of the canvas.
* **Page overrides** – the collapsible **Page overrides** area in the toolbar
  can hide the local map, calendar strip and description for one page. The
  options only appear when the corresponding global setting is enabled. The
  title page shows the composition title and defaults to hiding the map and
  description.
* **Layout** – open **Change layout**, choose a layout and select
  **Preview change**. Assignments are preserved where possible, and displaced
  photos are listed before you confirm.
* **Change page** – select a page thumbnail. The sidebar marks the active page.
* **Photos** – switch the horizontal photo strip between all photos and unused
  photos. A yellow `!` marks photos used more than once.

Every edit is committed in one transaction, increments the page render revision
and refreshes the page preview and unused pool. Adding or removing a photo never
changes the layout.

### Keyboard accessibility

Every drag-and-drop action has a keyboard equivalent: the slot selects, the
remove button, the move control and the layout form. Slots expose group labels,
notices are announced as status messages, focus is always visible, and a skip
link jumps to the main content. At narrow widths the panels stack and the page
list becomes a horizontal strip; no control is hidden in a drawer.

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
countries, page size and DPI, margins and spacing, fonts and colors, map options,
and the description toggle. Removing pages with saved content requires
confirmation. Settings are validated before saving, and actual
render-affecting changes increment page revisions.

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
  must be selected.
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
