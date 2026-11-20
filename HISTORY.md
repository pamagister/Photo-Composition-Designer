Changelog
=========


(unreleased)
------------

Fix
~~~
- Add favicon.svg. [Paul Magister]
- Fix centered description alignment and map spacing/rounded corners Refs #72.
  [Paul Magister]

Other
~~~~~
- Add configurable text margins, left/center description alignment and a
  three-state map mode. The map now spans the calendar and description column
  and requires a visible calendar strip.
- Perf(previews): draft previews, background worker and render caches Refs
  #58, #59, #60, #61, #62. [Paul Magister]

  Complete the many-photo render performance plan (Phases 0-4 and 6; Phase 5
  reviewed and closed as not needed). Preview rendering now uses a draft profile
  (reduced DPI) that covers the requested width at ~1.5x device pixels, a
  prioritized in-process worker renders previews off the request path with
  refreshing/ready/error client state, sidebar thumbnails use immutable asset
  URLs, the map render is cached in a bounded LRU, object detection uses a faster
  full-image fingerprint with low-priority warm-up, and build_input batches its
  lookups. Cold 640 px previews dropped from ~226-436 ms to ~86-278 ms and bulk
  refresh of 10 pages from ~8-9 s to ~1.4-2.8 s, with the full-resolution export
  path unchanged. Adds docs/develop/preview-pipeline.md and promotes the
  benchmark harness to scripts/benchmark_render.py.
- Fix(build): add PyInstaller entry point for restructured package Refs
  #56. [Paul Magister]
- Test: add fast baseline subset and testall target. [Paul Magister]

  Add fast/slow pytest markers applied via tests/conftest.py so new tests
  default to the fast baseline. Default 'make test' runs only the fast subset
  (~205 tests, ~21s); 'make testall' (alias 'test-all') runs the full suite
  with coverage. 'precommit' uses the fast target.
- Build(deps): resolve deptry warnings and run deptry in test gate Refs
  #55. [Paul Magister]


2.0.0 (2026-11-19)
------------------

Fix
~~~
- Favicon in browser and description of title. [Paul Magister]

Other
~~~~~
- Docs: Update HISTORY.md for release 2.0.0. [Paul Magister]
- Bugfixes #54: dnd functionality: - fix zoom. [Paul Magister]
- Bugfixes #54: dnd functionality: - bei Photos: Assign selected für
  bereits verwendete photos --> geht - - multi-select und dnd für unused
  photos --> geht. [Paul Magister]
- Bugfixes #54: dnd functionality: - Motiv innerhalb der Collage mit DnD
  tauschen - einzelne Bilder aus der Photos-Leiste direkt auf eine
  Dropzone ziehen - Bilder aus der Photos-Leiste auf bestehende bereits
  vorhandene Slots ziehen. - Fill empty slots with unused photos geht
  auch super - bei Photos: Assign selected für unused photos - multi-
  select und dnd für unused photos. [Paul Magister]

  Was leider noch nicht geht:
  - bei Photos: Assign selected für bereits verwendete photos --> geht nicht, soll aber auch gehen
  - - multi-select und dnd für unused photos --> geht nicht, soll aber auch gehen
- Docs(plans): mark collage image workflow complete Refs #52, #53, #54.
  [Paul Magister]
- Feat(gui): selection sync and keyboard crop on the preview Refs #54.
  [Paul Magister]

  Add a live crop endpoint (POST .../crop/live) that clamps and persists a
  keyboard crop adjustment and returns 204 with X-Page-Revision plus
  HX-Trigger pcd:crop-updated. editor.js now synchronises selection between a
  dropzone and its right-hand slot, and with an occupied slot selected the arrow
  keys nudge crop_focus_x/y by 0.02 while +/- adjust zoom by 0.02 (clamped to
  [0,1] and [1,3]). Changes are debounced and update the preview image and
  sliders in place without a full canvas re-render; keys inside form fields are
  ignored. The crop sliders use finer steps to match. A usage hint explains the
  shortcut and the web UI docs are updated.

  Covered by TestClient crop/live tests, markup checks and Chromium/Firefox
  Playwright tests for selection sync and keyboard crop.
- Feat(gui): add dropzone preview overlay with drag-and-drop Refs #53.
  [Paul Magister]

  Extract the collage content-box computation from PageComposer.render into a
  shared render/layout_geometry module (CollageBox, compute_collage_box,
  prepare_collage) so the renderer and the editor overlay cannot drift. The
  page context builders now expose per-slot overlay rectangles as page
  percentages.

  Wrap the large preview in an aspect-ratio-locked frame with absolutely
  positioned .slot-dropzone elements (empty/occupied/hover/drag-over states).
  editor.js treats dropzones like the existing .slot drop targets: strip drags
  assign or replace, and occupied-dropzone drags swap, reusing the existing
  endpoints and data-transfer types.

  Covered by compute_collage_box/slot_overlay_rectangles unit tests, TestClient
  markup tests and a Chromium/Firefox Playwright drag test.
- Feat(gui): add multi-select assign to the photo strip Refs #52. [Paul
  Magister]

  Add PageEditingService.assign_selected and the POST .../assign-selected
  endpoint to assign several unused photos to the empty slots of the current
  page in one action. The photo strip gains per-photo checkboxes and a
  selection toolbar (count, Assign selected, Clear) wired through editor.js
  using document-level delegation so it survives strip refreshes.

  Covered by service unit tests, a TestClient route test, a markup test and a
  Chromium/Firefox Playwright test.
- Chore(config): remove obsolete config.yaml Refs #51. [Paul Magister]

  config.yaml was a leftover from the removed config_cli_gui framework and is not read by any runtime code. Remove the file plus its PyInstaller, prepare-release and gitignore references, and correct the stale generated-docs instructions in AGENTS.md. Add handoff_settings.md describing the duplicated defaults in core/settings.py and core/output_profile.py.
- Feat(gui): add populate action to fill empty slots Refs #50. [Paul
  Magister]
- Feat(gui): cap slot grid at three columns Refs #49. [Paul Magister]
- Feat(distribution): match photo orientation to slot orientation. [Paul
  Magister]

  During auto-distribution, reorder each page's proposed photos so
  portrait photos prefer portrait slots and landscape photos prefer
  landscape slots. Slot orientation is derived from normalized slot
  geometry and the page aspect ratio; unmatched photos fall back to
  proposal order. Refs #48
- Feat(render): wire object detection into the live render pipeline.
  [Paul Magister]

  Remove the unused CollageRenderer and its test, keep SmartCrop and
  ObjectDetector, and route a globally configured YOLO model through
  PageComposer so object-aware cropping actually runs.

  Move the object recognition toggle from per-project settings to the
  global app settings (default off) and add model download and test
  actions on the settings page.
- Feat(layouts): refine tiled layouts with varied tile sizes Refs #47.
  [Paul Magister]

  - Replace six/seven/eight/nine/ten/eleven/twelve_tiles with:
    fourteen_tiles_3x5 (5-5-4), thirty_tiles_4x8 (6-8-7-9),
    fortyfive_tiles_5x9 (8-10-7-11-9). Each row mixes slot
    widths and heights so tiles vary between portrait/landscape/
    square, creating staggered lines without gaps or overlaps.

  - Sort layout catalogue ascending by slot count (1 -> 45) so
    the dropdown starts with the simplest layout.

  - Pre-select the currently active layout in the Change layout
    dropdown via current_layout_key in the template context.

  - Show slot count as a right-aligned [N] prefix in the
    dropdown instead of a verbose suffix.
- Feat(layouts): add staggered and tiled slot templates Refs #47. [Paul
  Magister]

  New built-in YAML layouts:

  - four_staggered_x/y: 4 images with offset splits (no continuous center line)
  - five_two_three, five_split_center: 5-image compositions
  - six_tiles_3x4 .. twelve_tiles_5x10: dense tiled layouts (6-12 images)
    with moderate portrait/landscape/square mix and zero gaps/overlaps

  load_catalogue() now returns templates sorted by slot count (descending)
  so the layout dropdowns can iterate directly and show the image count.

  Update templates to display "Name (N Bilder)" and cover the new keys
  in tests/test_layouts.py.
- Feat(gui): add extras subpages and refine project actions layout Refs
  #46. [Paul Magister]

  - Stack the export format checkboxes vertically.
  - Keep the duplicate project name field and button on one line.
  - Replace the left-expanding Extras panel with a right-expanding menu that links to the distribute and check subpages.
- Feat(gui): add jpg/pdf export options and project overview actions
  Refs #46. [Paul Magister]

  - Export JPG pages and/or a combined PDF with per-export DPI and JPEG quality overrides.
  - Remove the project-level PDF toggle and duplicate form.
  - Move .pcd import/export and duplication to a vertical projects overview.
  - Group project Extras into Distribution and Check sections.
- Feat(gui): add status emoji to page tiles and align layout summaries
  Refs #45. [Paul Magister]

  Show an info emoji after the page number when a rendered description is empty and a warning emoji when a page has unfilled slots. Share the tile meta markup between the full page and an out-of-band refresh so the hints update after edits. Remove the horizontal padding that pushed the Page overrides summary out of alignment with Change layout.
- Feat(gui): move page date to status line and add description hint Refs
  #44. [Paul Magister]

  Show the page start date in the top status line after the page number and drop the redundant page header row from the layout column. Add the page number (bold, left) beside the start date (right, muted) in the left page thumbnails. When a description is rendered but still empty, show a small (i) overlay over the page preview.
- Feat(gui): consolidate editor status and compact canvas layout Refs
  #43. [Paul Magister]

  Move the per-page overrides into the layout panel above Change layout and drop the editor toolbar so the large preview no longer loses vertical space to page identity and status text.

  Show the page date and page number as a narrow header at the top of the layout column. Consolidate the top status line into clearly separated groups: calendar facts (name, page count, last calendar update), current page facts (page number, last page save) and the latest save/status message. Label them "Calendar updated" and "Page saved" to clarify the difference; the page timestamp now reflects actual page edits instead of the stale project-level timestamp.

  Reduce the top editor region by roughly 10% so the bottom Photos strip is reachable on laptop viewports. Transient notices are swapped into the top status via an out-of-band htmx update.
- Feat: add per-page overrides and stabilize map rendering. [Paul
  Magister]

  Serialize map rendering to prevent corrupted maps when previews are rendered concurrently, for example after saving a description. Add per-page hide overrides for the map, calendar strip and description in a collapsible toolbar area, and respect global toggles by hiding unavailable overrides. Add a project-level use_title_page setting, move the composition title into the Project group, and default title pages to hide the map and description while still showing the title. Bump the schema to version 4.
- Feat: place local map beside the calendar strip. [Paul Magister]

  Replace the separate map width/height settings with a single map size that is the map width for horizontal calendars and the map height for vertical ones. The map now sits at the bottom-right, matches the calendar height, and narrows the calendar strip. Empty maps show Europe centered on Berlin without a marker. Existing profiles fall back to the former map width.
- Feat: render default maps and make location lookup configurable. [Paul
  Magister]

  Resolve photo locations from the bundled English and German location files during scans, add an optional custom locations.ini on top, and show the built-in file formats in app settings. Render a Berlin-centered map when no coordinates are available, omit maps on the title page, and add a per-page hide-map override. Bump the schema and render cache version, and include the renamed location-test images.
- Fix(gui): refresh selected page preview Refs #42. [Paul Magister]

  Keep the selected page in the Preview link and route, render the large preview for that page in addition to the thumbnails, and return to the same page. This prevents the large preview from appearing stale after edits.
- Fix(render): compact description spacing and reserve empty space Refs
  #40, #41. [Paul Magister]

  Align the description ink bottom with the calendar's first text ink row so the descender touches the ascender without an extra spacing gap. Always render the description block when the toggle is enabled, even for empty text, so the layout does not jump when text is added.
- Fix(render): align calendar margins and reorder description Refs #38,
  #39. [Paul Magister]

  The horizontal calendar header and day columns now respect both side margins. The page description is composed between the photo collage and the calendar strip instead of below the calendar. Both layouts are covered by rendering regression tests.
- Fix(gui): persist nested font settings Refs #37. [Paul Magister]

  Font fields use three-level form paths such as style.font_large.size. The settings parser only split once, so OutputProfile.from_dict never received nested font data and fell back to the default size 9.0 and white color. Store dotted form fields as nested mappings and cover the round trip with a regression test.
- Ignore .idea/jsonSchemas.xml. [Paul Magister]
- Chore(config): replace hard-coded home paths with portable references.
  [Paul Magister]
- Chore(tooling): add IDE, Serena and OpenCode project config. [Paul
  Magister]
- Fix(gui): track missing route modules and project archive files Refs
  #36. [Paul Magister]
- Ignore serena logs. [Paul Magister]
- Rendering and UI enhancements have been implemented: slot spacing and
  corner rounding are now accounted for, the calendar is positioned
  below the photos, and previews update automatically following any
  changes. Additional features include project settings for start date
  and page count, global anniversary settings, versioned layouts, a
  filterable photo strip with indicators for multiple-use instances, and
  reference-based .pcd import and export. Render exports can be saved to
  any chosen location, with the system’s default image folder suggested
  as the destination. [Paul Magister]
- Gui starter. [Paul Magister]
- Docs: describe the shipped project workflow and release checks Refs
  #35. [Paul Magister]
- Test(browser): add Playwright workflow suite for Chromium and Firefox
  Refs #35. [Paul Magister]
- Perf(previews): serve cached page previews without rendering Refs #35.
  [Paul Magister]
- Fix(distribution): accept blank seed in the preview form Refs #35.
  [Paul Magister]
- Feat(editor): add accessible swap and replace controls Refs #35. [Paul
  Magister]
- Feat(cli): add project scan, distribution, duplicate and doctor
  commands Refs #34. [Paul Magister]
- Feat(export): add browser export and full-project previews Refs #33.
  [Paul Magister]
- Feat(projects): add project settings and workspace duplication Refs
  #28. [Paul Magister]
- Feat(distribution): add preview samples and idempotent confirmation
  Refs #32. [Paul Magister]
- Feat(sources): add safe browser relinking and source management Refs
  #29. [Paul Magister]
- Feat(editor): add page editing, crops and cached previews Refs #31.
  [Paul Magister]

  Implement deterministic layout changes with displaced-photo previews and confirmation, per-assignment crop and focal-point controls, page-description editing, cached page previews with sidebar thumbnails, and unused-pool refresh after edits. Add a two_rows catalogue layout and Phase 2 tests.
- Feat(render): add full-page composition and output profiles Refs #30.
  [Paul Magister]
- Docs(plan): revise web UI continuation plan for current baseline.
  [Paul Magister]
- Update README.md from docs/index.md. [github-actions]
- Merge pull request #27 from pamagister/plan/web-ui-calendar-project-
  workflow. [Paul Magister]

  Web UI first project workflow
- Fix(idea): use uv GUI entry point Refs #26. [Paul Magister]

  The PyCharm run configuration now launches the installed uv project entry point with the gui argument, uses the current module name and the project module SDK.
- Docs(phase-9): finalize documentation and release readiness Refs #23.
  [Paul Magister]
- Feat(phase-8): add project export and remove legacy workflow code Refs
  #22. [Paul Magister]
- Feat(phase-7): add guided project creation and distribution preview
  Refs #24. [Paul Magister]
- Feat(phase-6): add three-panel editor with drag-and-drop and keyboard
  alternatives Refs #21. [Paul Magister]
- Feat(phase-5): add distribution proposals and page editing services
  Refs #25. [Paul Magister]
- Feat(phase-4): add YAML layout catalogue and slot-aware renderer Refs
  #20. [Paul Magister]
- Feat(phase-3): harden inventory, GPS fallback and cached local map
  Refs #17. [Paul Magister]
- Feat(gui): add local web foundation and project workflow. [Paul
  Magister]

  Refs #19
- Docs(phase-1): update handoff for Phase 2 web foundation Refs #18.
  [Paul Magister]
- Feat(phase-1): restructure into photo_composition_designer package;
  drop Tkinter/config-cli-gui Refs #18. [Paul Magister]
- Chore(phase-0): replace old week fixtures with flat Pixabay collection
  Refs #16. [Paul Magister]
- Plan for web ui. [Paul Magister]
- Feat(project): add workspace schema and project lifecycle Refs #15.
  [Paul Magister]
- Docs(architecture): lock web UI project workflow baseline Refs #13.
  [Paul Magister]
- Ci: run checks on every branch push Refs #12. [Paul Magister]
- Playwright-cli for web-ui inspection. [Paul Magister]
- Docs: refine project storage and portability decisions. [Paul
  Magister]
- Docs: correct plan self-reference. [Paul Magister]
- Docs: add web UI calendar editor refactoring plan. [Paul Magister]
- Ci(Photo-Composition-Designer): clarify required Linux check in main
  workflow. [Paul Magister]

  Refs #11
- Ci(Photo-Composition-Designer): Linux always-on, Win/macOS opt-in via
  --all. [Paul Magister]

  - flags job detects --all opt-in from commit subject / PR title / input
  - Linux test job (make test) always runs
  - Windows/macOS test jobs only run with build_all=true
  - Release DAG: quality gate blocks release/PyPI; build-linux always,
    build-windows/build-macos only opt-in
  - Separate build-*-yml workflows consolidated into release.yml
  - setup-environment uses cached setup-uv@v10.3.3

  Refs #11


1.0.7 (2026-10-09)
------------------
- Docs: Update HISTORY.md for release 1.0.7. [Paul Magister]
- Update AGENTS.md. [Paul Magister]
- Vibe-coding session: [Paul Magister]

  CompositionDesigner verwendet jetzt den CompositionFileOperations-Vertrag. Die Application-Factory bündelt den Aufbau der Datei- und Renderer-Kollaboratoren und injiziert sie; direkte Konstruktion bleibt als Kompatibilitätspfad erhalten. Echte Integrationstests rendern temporäre Fotos und prüfen JPEG- und PDF-Ausgaben. Außerdem löscht der CLI-Test keine projektweiten Collagen mehr.
- Vibe-coding session: [Paul Magister]

  Die erste große Verbesserung ist umgesetzt: CLI und GUI erstellen Composition-Workflows jetzt über einen gemeinsamen CompositionApplicationFactory. Auch Vorschauen verwenden dieselbe Designer-Factory; sie nutzen die Seitengröße des bestehenden Designers, statt dafür einen zusätzlichen Designer zu erzeugen. Die GUI greift für Verzeichnisse und Cache-Steuerung über den Workflow zu. Fortschritt wird typisiert beim Erzeugen übergeben; leere Verarbeitungsläufe lösen keinen GUI-Fehler mehr aus.
- Vibe-coding session: [Paul Magister]

  Die Renderer-Abhängigkeiten werden jetzt im neuen CompositionRendererBuilder aufgebaut und als typisierte CompositionRenderComponents an CompositionDesigner übergeben. Bestehende Aufrufe bleiben kompatibel; Tests können die Komponenten gezielt injizieren. In TODO.md habe ich den bereits vorhandenen Schnitt als erledigt markiert, die nächsten Architekturthemen priorisiert und „tests with teeth“ ergänzt.
- Vibe-coding session: [Paul Magister]

  CompositionDesigner ist jetzt in fokussierte Komponenten aufgeteilt: CompositionLayout berechnet Maße und Beschreibungsoptionen, CompositionPageRenderer rendert die Seite und CompositionIO übernimmt Fotoeingabe sowie Bild-/PDF-Ausgabe. Die Designer-Klasse koordiniert diese Aufgaben weiter; bei der Stapelverarbeitung werden Fotoordner nur noch einmal aufgelistet.
- Vibe-coding session: [Paul Magister]

  Die erste Architekturverbesserung ist umgesetzt: MainGui delegiert Kompositionsmodi, Vorschau-Erstellung und Fotoverteilung jetzt an UI-unabhängige Dienste im neuen Paket src/Photo_Composition_Designer/application/. Tkinter, Hintergrundthreads und Fortschrittsanzeige bleiben in der GUI; das bisherige Verhalten der Abläufe bleibt erhalten.
- Fix text color: Only red text if holiday. [Paul Magister]
- #5 vertical calendar: first approach. [Paul Magister]
- #5 vertical calendar: first approach. [Paul Magister]
- Add tests for new flag feature. [Paul Magister]
- Merge pull request #2 from
  pamagister/dependabot/github_actions/actions/setup-python-6. [Paul
  Magister]

  Bump actions/setup-python from 4 to 6
- Merge branch 'main' into dependabot/github_actions/actions/setup-
  python-6. [Paul Magister]
- Bump actions/setup-python from 4 to 6. [dependabot[bot]]

  Bumps [actions/setup-python](https://github.com/actions/setup-python) from 4 to 6.
  - [Release notes](https://github.com/actions/setup-python/releases)
  - [Commits](https://github.com/actions/setup-python/compare/v4...v6)

  ---
  updated-dependencies:
  - dependency-name: actions/setup-python
    dependency-version: '6'
    dependency-type: direct:production
    update-type: version-update:semver-major
  ...
- #4 fix filename length. [Paul Magister]
- Introduce flags in description:   - `[no-calendar]` — prevents a
  calendar from being generated for this photo.   - `[no-description]` —
  suppresses the generated photo description. [Paul Magister]
- Merge pull request #3 from
  pamagister/dependabot/github_actions/actions/checkout-6. [Paul
  Magister]

  Bump actions/checkout from 4 to 6
- Bump actions/checkout from 4 to 6. [dependabot[bot]]

  Bumps [actions/checkout](https://github.com/actions/checkout) from 4 to 6.
  - [Release notes](https://github.com/actions/checkout/releases)
  - [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)
  - [Commits](https://github.com/actions/checkout/compare/v4...v6)

  ---
  updated-dependencies:
  - dependency-name: actions/checkout
    dependency-version: '6'
    dependency-type: direct:production
    update-type: version-update:semver-major
  ...


1.0.6 (2026-06-25)
------------------
- Docs: Update HISTORY.md for release 1.0.6. [Paul Magister]
- Fix gui: no duplicated button frame. [Paul Magister]
- Add documentation for new feature, fix links in README.md, new images.
  [Paul Magister]
- Transparent description text. [Paul Magister]


1.0.5 (2026-06-24)
------------------
- Docs: Update HISTORY.md for release 1.0.5. [Paul Magister]
- Collages in Portrait mode: improve layouting for portrait collages.
  [Paul Magister]
- Collages in Portrait mode: improve layouting for portrait collages.
  [Paul Magister]
- Use side margins also for collage to avoid images to be cropped in
  print shop. [Paul Magister]
- More intuitive workflow concept: New button structure and alignment.
  [Paul Magister]


1.0.4 (2026-06-24)
------------------
- Docs: Update HISTORY.md for release 1.0.4. [Paul Magister]
- Clear cache only optionally with explicit menu entry. [Paul Magister]
- Fix last used config issue: pass config into MainGui. [Paul Magister]
- Align title description centrally. [Paul Magister]
- Do not run precommit twice on make release. [Paul Magister]


1.0.3 (2026-06-23)
------------------
- Docs: Update HISTORY.md for release 1.0.3. [Paul Magister]
- Fix test for github actions. [Paul Magister]
- Bugfix: fix essencial bug due to overwrite size.dpi setting because of
  copy-by-reference mistake. [Paul Magister]
- Bugfix: fix linux locale problem with languages. [Paul Magister]
- Pass language to python-holidays so holiday names are localized; load
  subdivisions per-language. [Paul Magister]

  Added test to ensure German names and Saxony holidays are present (tests/test_CalendarRenderer.py)\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>


1.0.2 (2026-06-22)
------------------
- Docs: Update HISTORY.md for release 1.0.2. [Paul Magister]
- Improve layouting: distribute 2x2 images more equally. Use image
  importance weight where useful. Consider object area when calculating
  importance. Clear cache at session start. [Paul Magister]
- No more workspace.xml in vcs. [Paul Magister]
- Calculate image weights better. [Paul Magister]
- Calculate image weights better. [Paul Magister]
- Improve reactivity: add file cache to store image recognition data.
  [Paul Magister]
- Improve reactivity: render preview only as large as needed. [Paul
  Magister]
- Update config-cli-gui: improved gui handling, reload last config.yaml,
  move AppConfig into general base class. [Paul Magister]
- Use ttkbootstrap for modern gui design. [Paul Magister]
- CollageRenderer.py: imageScoreFactor: Factor how much the objects
  (humans, animals, ...) in the image are considered for weighting the
  image size. [Paul Magister]
- CollageRenderer.py: add rounded corner functionality: add parameter.
  [Paul Magister]
- CollageRenderer.py: add rounded corner functionality. [Paul Magister]
- CollageRenderer.py: improve tests, more variants, shorter P and L for
  portrait and landscape. Overweight portraits in one row so that they
  get more space. [Paul Magister]
- Adjust weight in SmartCrop. [Paul Magister]
- Code formatting and import optimization. [Paul Magister]
- Algorithm finally working. [Paul Magister]
- Draft: spezielle Behandlung für 3: fast perfekt: fix gap bug. [Paul
  Magister]
- Draft: spezielle Behandlung für 3: fast perfekt. [Paul Magister]
- Draft: spezielle Behandlung für 3. [Paul Magister]
- Draft: neues arrangement mit fitting algo: schon viel besser, aber bei
  3 Bildern geht es nicht. [Paul Magister]
- Draft: neues arrangement mit fitting algo: schon viel besser, aber bei
  3 Bildern geht es nicht. [Paul Magister]
- Draft: neues arrangement mit fitting algo. [Paul Magister]
- Make pytree: improvements on show_tree.py: doc external tool. [Paul
  Magister]
- Improve cropping boxes and test visualization. [Paul Magister]
- CollageRenderer.py: rename private methods. [Paul Magister]


1.0.1 (2026-06-14)
------------------
- Docs: Update HISTORY.md for release 1.0.1. [Paul Magister]
- Object recognition: improve cropping: prevent crash on None. [Paul
  Magister]
- Object recognition: improve cropping. [Paul Magister]
- Object recognition: add tests, add improved cropping and object
  prioritization, add test images. [Paul Magister]
- Object recognition: add tests, add improved cropping and object
  prioritization, add test images. [Paul Magister]
- Object recognition: improve module structure, add SmartCrop test.
  [Paul Magister]
- Object recognition: improve module structure. [Paul Magister]
- Image recognition: add parameter whether to use object recognition.
  [Paul Magister]
- Image recognition: add example images for improved testing. [Paul
  Magister]
- Image recognition: use onnx file and onnxruntime instead of
  ultralytics and pytorch. [Paul Magister]
- Image recognition: detect not only persons, but different objects.
  [Paul Magister]
- Collage designer: using YOLO for object recognition. [Paul Magister]
- Make pytree: consider doc strings. [Paul Magister]
- Make pytree: improvements on show_tree.py: rename to
  project_structure.py. [Paul Magister]
- Make pytree: improvements on show_tree.py: doc external tool. [Paul
  Magister]
- Make pytree: improvements on show_tree.py: bild compact llm
  understandable json, consider functions. [Paul Magister]
- Make pytree: improvements on show_tree.py: - class attributes,
  instance attributes. [Paul Magister]
- Pipx in doc, support python until <4.0. [Paul Magister]


1.0.0 (2025-12-04)
------------------
- Docs: Update HISTORY.md for release 1.0.0. [Paul Magister]
- Upgrade libs. [Paul Magister]
- Fix doc: start app from pypi. [Paul Magister]


0.1.5 (2025-12-04)
------------------
- Add collages with transparency. [Paul Magister]
- Update README.md from docs/index.md. [github-actions]
- Rename installer download zip. [Paul Magister]
- Improve doc, add collages.png example image. [Paul Magister]


0.1.4 (2025-12-04)
------------------
- Docs: Update HISTORY.md for release 0.1.4. [Paul Magister]
- Update lib, probably fix windows font issue. [Paul Magister]


0.1.3 (2025-12-03)
------------------
- Docs: Update HISTORY.md for release 0.1.3. [Paul Magister]
- Docs: Update HISTORY.md for release 0.1.2. [Paul Magister]
- Update README.md from docs/index.md. [github-actions]


0.1.2 (2025-12-03)
------------------
- Docs: Update HISTORY.md for release 0.1.2. [Paul Magister]
- Improve doc. [Paul Magister]
- Use logging module from lib. [Paul Magister]
- Selection and preview issue fixed, remove tight layout parameter.
  [Paul Magister]
- Code structure refactorings, new config_cli_gui version with preserved
  config order and logger. [Paul Magister]
- Code structure refactorings, new config_cli_gui version with preserved
  config order and logger. [Paul Magister]
- Remove unused helpers. [Paul Magister]
- Use new Font class, use dpi awareness so that the fonts do not change
  in size relatively if dpi is changed. [Paul Magister]
- Use new Font class. [Paul Magister]
- Update config_cli_gui. [Paul Magister]


0.1.1 (2025-12-01)
------------------
- Docs: Update HISTORY.md for release 0.1.1. [Paul Magister]
- Make font configurable. [Paul Magister]


0.1.0 (2025-12-01)
------------------
- Docs: Update HISTORY.md for release 0.1.0. [Paul Magister]
- Gitignore. [Paul Magister]
- Docs: Update HISTORY.md for release 0.0.9. [Paul Magister]
- Docs: Update HISTORY.md for release 0.0.8. [Paul Magister]
- Fix test. [Paul Magister]
- Update README.md from docs/index.md. [github-actions]


0.0.9 (2025-12-01)
------------------
- Docs: Update HISTORY.md for release 0.0.9. [Paul Magister]


0.0.8 (2025-12-01)
------------------
- Docs: Update HISTORY.md for release 0.0.8. [Paul Magister]
- Fix test. [Paul Magister]
- Progress bar, logger in base.py, lifecycle fixes. [Paul Magister]
- Improved logging. [Paul Magister]
- Update README.md from docs/index.md. [github-actions]
- Set up nice documentation. [Paul Magister]


0.0.7 (2025-11-30)
------------------
- Docs: Update HISTORY.md for release 0.0.7. [Paul Magister]
- Remove zip function from makefile. [Paul Magister]


0.0.6 (2025-11-30)
------------------
- Docs: Update HISTORY.md for release 0.0.6. [Paul Magister]
- Fix zip linux. [Paul Magister]
- Fix more import errors. [Paul Magister]


0.0.5 (2025-11-30)
------------------
- Docs: Update HISTORY.md for release 0.0.5. [Paul Magister]
- Improve path issue with relative paths to res/ini files. [Paul
  Magister]
- Fix test_cli.py for windows. [Paul Magister]
- Add ini files individually, fix test_cli.py for windows. [Paul
  Magister]


0.0.4 (2025-11-29)
------------------
- Docs: Update HISTORY.md for release 0.0.4. [Paul Magister]
- Add ini files individually. [Paul Magister]
- Move all ini files top-level so that the user can find them
  immediately. [Paul Magister]
- Cli tests. [Paul Magister]
- Fix cli, update requirements. [Paul Magister]
- Button to open alternative config, reload config functionality. [Paul
  Magister]


0.0.3 (2025-11-29)
------------------
- Docs: Update HISTORY.md for release 0.0.3. [Paul Magister]
- Remove duplicated clean from Makefile. [Paul Magister]
- Fix main.py startup. [Paul Magister]
- Exclude some more folders. [Paul Magister]
- Build stage for linux. [Paul Magister]
- Add docs and res folders to build artifacts. [Paul Magister]


0.0.2 (2025-11-28)
------------------
- Docs: Update HISTORY.md for release 0.0.2. [Paul Magister]
- Step to every image with arrows. [Paul Magister]
- Tooltips, generate preview immediately. [Paul Magister]


0.0.1 (2025-11-28)
------------------
- Docs: Update HISTORY.md for release 0.0.1. [Paul Magister]
- Remove logger from CompositionDesigner.py. [Paul Magister]
- Remove unused module. [Paul Magister]
- Generate all compositions from gui. [Paul Magister]
- Smoothly update preview image, fix exceptions on empty folder, fix
  title image issue. [Paul Magister]
- Gui elements do resize. [Paul Magister]
- Show preview image in gui. [Paul Magister]
- Update config-cli-gui. [Paul Magister]
- Refactor generate_composition method. [Paul Magister]
- Consistent renaming of the render modules. [Paul Magister]
- First gui adaption. [Paul Magister]
- Correct typing, CompositionDesigner.py generate_composition returns
  image object. [Paul Magister]
- Remove unused images, restructure test. [Paul Magister]
- Only use Image.Image in CollageGenerator.py. [Paul Magister]
- Consistently rename core methods. [Paul Magister]
- * move all generators that create images to image * typings *
  refactorings. [Paul Magister]
- Add tests for CompositionDesigner.py, fix issue with font. [Paul
  Magister]
- Add anniversaries.ini and locations_de.ini. [Paul Magister]
- Adjusted version of CompositionDesigner.py. [Paul Magister]
- Original version of CompositionDesigner.py. [Paul Magister]
- Use to_pil function of new cli_config_gui. [Paul Magister]
- Add CalendarGenerator.py and. [Paul Magister]
- Add CalendarGenerator.py. [Paul Magister]
- Add MapGenerator.py. [Paul Magister]
- Add DescriptionGenerator.py. [Paul Magister]
- Add GeoPlotter.py, move logging.py so that it does not interfere with
  general built-in logging. [Paul Magister]
- Add PhotoLayoutManager.py. [Paul Magister]
- Add further basic functionality. [Paul Magister]
- Move common into project dir. [Paul Magister]
- Add common functions and according tests. [Paul Magister]
- Only use on py file to show tree with or without python classes. [Paul
  Magister]
- Add show_filelist.py to be able to run on linux. Add new libraries.
  [Paul Magister]
- Add maps data for displaying contours. [Paul Magister]
- Add example images. [Paul Magister]
- Use new updated config_cli_gui. Adjust parameters to the calendar
  project. [Paul Magister]
- ✅ Project renamed from template. [github-actions[bot]]
- Initial commit. [Paul Magister]


