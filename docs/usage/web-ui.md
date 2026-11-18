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

Choose a strategy (`Equal`, `Random` with an optional seed, or `Date aware`) in
**Extras / Distribution**, then select **Preview distribution**. The preview
shows per-page samples, filled and empty slots, overflow and the total
unassigned count without changing the project. **Apply distribution** persists
the reviewed proposal in one transaction; repeating the same confirmation is a
no-op and a stale preview is rejected.

Photos that exceed the available slots stay in the unused pool. Empty slots are
valid and are reported explicitly.

## Curate pages

The editor shows page thumbnails in the sidebar, the rendered page preview and
slot grid on the canvas, and the unused photos below it.

* **Assign** – drag an unused photo onto an empty slot, or choose it in the slot's
  select and press **Assign**.
* **Replace** – drag an unused photo onto an occupied slot, or open **Replace** in
  the slot. The previous photo returns to the unused pool.
* **Swap or move** – drag one assigned photo onto another slot, or use the slot's
  **Move** select. Dropping a photo onto its own slot does nothing.
* **Remove** – press the slot's remove button.
* **Crop** – open **Crop** in an occupied slot to adjust zoom and focal point.
  Crop settings are assignment properties; the source file is untouched.
* **Description** – edit the page description at the bottom of the canvas.
* **Hide local map** – the small toolbar checkbox overrides the project's
  `Render local photo maps` setting for one page. The title page never shows a
  map, so the checkbox is omitted there.
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

**Project settings** edits the name, start date, page count and output profile:
calendar language and holiday countries, page size and DPI, margins and
spacing, fonts and colors, map options, and description/PDF toggles. Removing
pages with saved content requires confirmation. Settings are validated before
saving, and actual render-affecting changes increment page revisions.

## Duplicate a project

**Duplicate project** in the settings page copies pages, layout snapshots,
assignments, source roots, inventory and the output profile inside the workspace.
The copy is fully independent of the original. It is not a portable archive:
source references remain relative and relinkable.

## Preview and export

* **Preview all pages** renders every page in project order and opens the first
  page.
* **Export photos** renders PNG pages and, when enabled, a combined PDF. The
  default is a project-specific folder under the OS Pictures/Bilder directory
  when it exists; an absolute local path or workspace-relative folder can be
  entered instead.
* **Export project (.pcd)** downloads a reference-only project archive.
  **Import project (.pcd)** creates a new project from such an archive. Archives
  include layout snapshots, assignments and source references, not photo files;
  source directories may need relinking on another computer.
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
