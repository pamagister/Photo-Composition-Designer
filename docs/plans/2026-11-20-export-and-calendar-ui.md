# Plan: Export progress, page navigation and calendar locale options

## Objective and desired outcome

Improve four local web UI details without changing the rendering pipeline or project data format:

1. Show a subtle live percentage inside the existing export progress text.
2. Make the exported folder path in the export result clickable and open it in the OS file manager.
3. Allow keyboard navigation between page thumbnails with `ArrowUp` / `ArrowDown`.
4. Replace the free-text calendar language field with a language dropdown and offer
   a small, language-dependent selection of holiday subdivision codes.

## Scope and constraints

- Keep changes local to the existing FastAPI + Jinja + htmx UI.
- Do not change the output profile schema or persisted project format.
- Keep the export POST synchronous; progress is exposed through a lightweight polling
  endpoint so existing export behavior and tests remain intact.
- Use region-qualified locales for the language dropdown because the calendar derives
  the holiday country from the locale (`de_DE`, `de_AT`, `en_US`, `fr_FR`, `es_ES`,
  `it_IT`).
- Holiday countries remain subdivision codes. No selection means nationwide holidays.
- The OS folder link is a local server endpoint; no `file://` links.
- Follow existing project style, type hints, tests and formatting commands.

## Key decisions

- **Language options:** `de_DE`, `de_AT`, `en_US`, `fr_FR`, `es_ES`, `it_IT`.
- **Holiday options:** curated subdivision checkboxes for DE, AT, US, FR and ES;
  IT only shows a nationwide-only note.
- **Progress transport:** exporter invokes an optional callback; the web route keeps a
  small thread-safe progress record on `app.state`; the browser polls it while the
  htmx export request is in flight.
- **Folder opening:** `GET /projects/{id}/export/folder` validates the folder against
  the export paths recorded in this server session and calls `xdg-open`, `open` or
  `explorer` via `subprocess.Popen`.
- **Page navigation:** event delegation on the sidebar; arrow keys move focus and
  activate the previous/next `.page-thumb`. Existing crop keyboard handling stays
  unchanged because the sidebar handler stops propagation.

## Phase 1: Export progress indicator

- [x] P1-W01: Add an optional `progress` callback to `ProjectExporter.render_project`
  and invoke it after each rendered page.
- [x] P1-W02: Add a thread-safe export progress registry and a JSON progress endpoint.
- [x] P1-W03: Update the export template and `export.js` to poll while the htmx request
  is active and render a discreet percentage.
- [x] P1-W04: Add unit coverage for the callback and route-level coverage for the
  progress endpoint.

**Acceptance criteria**

- During an export the progress text shows `Rendering pages... N% ...`.
- Progress reaches 100% or is reset when the request finishes.
- Existing export result and error behavior is unchanged.

## Phase 2: Open exported folder

- [x] P2-W01: Add a platform-aware folder opener and a validated local route.
- [x] P2-W02: Add an "Open folder" link to the export result partial and pass a safely
  quoted URL in the template context.
- [x] P2-W03: Add route tests for successful validation and rejection of unknown
  folders.

**Acceptance criteria**

- The export result shows the folder as a clickable link.
- Only folders exported during the current server session can be opened.
- The route returns to the export page with a visible error when opening fails.

## Phase 3: Page thumbnail keyboard navigation

- [x] P3-W01: Add `ArrowUp` / `ArrowDown` navigation to the pages sidebar in
  `editor.js`, including focus transfer and click activation.
- [x] P3-W02: Add a browser workflow test covering both directions and the first/last
  boundary.

**Acceptance criteria**

- With a page thumbnail focused, `ArrowDown` opens the next page and `ArrowUp` the
  previous page.
- Crop arrow-key behavior remains unchanged.
- Navigation is skipped at the first/last thumbnail.

## Phase 4: Calendar language and holiday selection

- [x] P4-W01: Add a GUI option module with language choices and subdivision labels.
- [x] P4-W02: Harden calendar country-code extraction for region-less legacy locales
  (`en`, `fr`, `es`, `it`).
- [x] P4-W03: Update project settings form parsing to accept repeated holiday country
  fields while remaining compatible with comma-separated strings.
- [x] P4-W04: Update the settings template with the language dropdown and grouped
  holiday checkboxes, plus a small script that shows only the selected country group.
- [x] P4-W05: Add tests for the rendered options, persistence of repeated values and
  the region-less locale fallback.

**Acceptance criteria**

- The settings page offers the six locale choices.
- Changing the language shows the matching subdivision choices and clears hidden ones.
- Saving multiple subdivisions persists them as a tuple/list in the output profile.
- Legacy comma-separated values continue to save and render.
- Calendar rendering no longer crashes for a region-less language such as `en`.

## Phase 5: Verification and documentation

- [x] P5-W01: Run focused tests, then the fast suite and lint/format checks.
- [x] P5-W02: Update the relevant web UI documentation if wording or behavior changed.

**Acceptance criteria**

- `uv run pytest` passes for touched tests.
- `make lint` passes.
- Generated documentation is not edited by hand; run `make fmt` if typed defaults
  change (they are not expected to change here).

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-20-export-and-calendar-ui.md`
- **Completed:** P1-W01 to P1-W04 (#73), P2-W01 to P2-W03 (#74), P3-W01 to P3-W02 (#76), P4-W01 to P4-W05 (#77), P5-W01 to P5-W02 (#75)
- **Active:** none
- **Next:** push, monitor CI, close agent-created phase issues when green
- **Relevant files:** `src/photo_composition_designer/io/export.py`,
  `src/photo_composition_designer/gui/routes/export.py`,
  `src/photo_composition_designer/gui/routes/project_settings.py`,
  `src/photo_composition_designer/gui/calendar_options.py`,
  `src/photo_composition_designer/render/calendar.py`,
  `src/photo_composition_designer/gui/static/export.js`,
  `src/photo_composition_designer/gui/static/editor.js`,
  `src/photo_composition_designer/gui/static/project-settings.js`,
  `tests/test_export_ui.py`, `tests/test_project_settings.py`,
  `tests/test_browser_workflow.py`
- **Decisions:** region-qualified locales; subdivision checkboxes; polling progress;
  server-side folder opening; sidebar arrow navigation.
- **Blockers:** none
- **Last verified:** 2026-11-20, `make test` green (277 passed, 120 deselected),
  `uv run pytest` browser subset green (4 passed)
- **Context status:** clean
