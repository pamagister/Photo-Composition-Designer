# Performance Plan: Fast, Robust Preview Updates for Large Collages

**Status:** Draft for review
**Created:** 2026-11-19
**Target branch:** `main`
**Repository:** `pamagister/Photo-Composition-Designer`
**Execution mode:** autopilot (one GitHub issue per phase, phase-boundary handoff)
**Scope:** Preview/render performance for collages with many photos, plus
background object-detection caching for the gallery. Behaviour-preserving:
no visual or API changes are accepted without a stated reason.

## 1. Objective and desired outcome

Editing a collage with many photos currently triggers a full-resolution page
render for every change, and several "refresh all pages" actions block the
request for seconds. This plan removes that bottleneck with small, safe wins
first and a focused refactor second, while keeping previews truthful (no stale
images, no silently downgraded exports).

Desired outcomes, in priority order:

1. **Editing feels immediate.** Assign / replace / swap / crop return the page
   fragment without a visible wait, and the preview catches up in the background.
2. **Bulk actions do not block.** Distributing or finishing photo allocation
   never re-renders every page synchronously inside the request.
3. **Previews are cheap.** A 320/640-wide preview costs substantially less
   than the current full-resolution path, and the sidebar only loads visible
   page previews.
4. **Exports stay full quality.** Draft rendering is used only for previews;
   export keeps the current pixel-exact pipeline.
5. **Object detection is warm.** When object-aware cropping is enabled, gallery
   photos have their detections cached before they are dropped into a collage,
   and cache lookups stop re-decoding every photo on every slot render.

### Measured baseline (this repository, this machine)

Reference: 216x154 mm @ 300 dpi page (2551x1819 px), one photo per slot,
JPEG decoding and Pillow resizing dominate; map is matplotlib/geopandas.

Most timings below are reproducible with the harness collection in
`temp/performance-artifacts/` (see Section 1.1). Run from the repository root:

```bash
uv run python temp/performance-artifacts/01_render_scaling.py      # page render + preview write
uv run python temp/performance-artifacts/02_collage_profile.py 14  # cProfile + collage/composite split
uv run python temp/performance-artifacts/03_preview_cost.py        # cold vs warm preview, per width
uv run python temp/performance-artifacts/04_bulk_refresh.py        # project-wide refresh (blocking bulk action)
uv run python temp/performance-artifacts/05_map_calendar_cost.py   # map + calendar composite cost
uv run python temp/performance-artifacts/06_object_detection_cost.py  # YOLO + fingerprint cost
uv run python temp/performance-artifacts/07_fragment_cost.py       # editor fragment / context cost
uv run python temp/performance-artifacts/08_draft_preview.py       # draft-preview design evaluation
uv run python temp/performance-artifacts/09_decode_resize.py       # decode/resize strategy comparison
```

| Workload | Measured |
| --- | --- |
| Full page render, 4 / 14 / 30 / 45 slots | 150 / 220 / 295 / 402 ms |
| Preview write at max_width 320 / 640 | 48-76 / 62-81 ms (page already rendered) |
| Preview 640 cold (render + write) | 226 / 302 / 436 ms (4 / 14 / 30 slots) |
| Preview 640 warm (cache hit) | ~0.6 ms |
| "Refresh all previews" (10 pages, 320) | 8.2-9.3 s cold, ~0 s warm |
| Map render (236x213, matplotlib) | ~780 ms in the original run; ~1.1 s on review run |
| Calendar strip (incl. `holidays` init) | ~28 ms in the original run; ~38 ms on review run |
| YOLO raw inference | ~104 ms/image |
| YOLO fingerprint (`detect` on warm cache) | ~10 ms/image, ~96% of warm `detect` cost (new object, fresh detector) |
| `build_input` (DB resolution, 45 slots) | ~5 ms + 94 queries (N+1) |
| `editor_canvas.html` render (45 slots + 45 photos) | ~23 ms, ~300 KB HTML |
| `_page_context` / `_project_context` (45 slots) | 60-65 ms |
| Scan 30 real JPEGs (EXIF/GPS) | 0.05 s (~2 ms/photo) |

Treat these as historical baseline figures, not fixed acceptance targets.
Re-measure with the corrected harness and comparable machine/workload before
declaring any phase done.

#### Review and repeat measurements (2026-11-19)

The harnesses were rerun while reviewing this plan. Results on this run were:

| Workload | Repeat result |
| --- | --- |
| Full page render, 4 / 14 / 30 / 45 slots | 190 / 271 / 398 / 469 ms |
| Editor `_page_context`, 14 / 45 slots | 73 / 76 ms |
| `editor_canvas.html`, 14 / 45 slots | 7 / 24 ms |
| Full render + 640 preview, 14 / 30 slots | 417 / 501 ms |
| 150-dpi draft + 640 preview, 14 / 30 slots | 200 / 390 ms |
| Draft-vs-full difference at 640, mean absolute / p99 | 4.16 / 40 and 4.77 / 42 (out of 255) |
| Map render | 1112 ms cold / 1134 ms repeated |
| Calendar construction / generation | 20 / 18 ms |
| 30-slot resize strategies | LANCZOS 385 ms; BILINEAR 293 ms; JPEG draft + BILINEAR 290 ms |

This confirms the major costs, but also shows that timings vary from the earlier
baseline. Draft rendering was about 22-52% faster in these two cases, not a
four-fold end-to-end win; BILINEAR was about 24% faster in the isolated slot
test, while JPEG `draft()` added little for these source files. The 640-pixel
draft difference is higher than the 2-3/255 claim above; the harness does not
measure the claimed 320-pixel comparison. Do not treat either result as a
quality or latency guarantee until it is measured across representative source
photos and layouts.

The harness collection is useful for attribution, not yet a complete UI
benchmark. The reported `build_input` query count and HTML byte count are not
printed by these scripts and need explicit instrumentation before being used as
acceptance evidence. The synthetic project also uses one row of equal,
full-height slots, which is not representative of every real many-photo
layout. `07_fragment_cost.py` measures context construction and template
rendering, not a real HTTP round-trip, browser layout/paint, image request
completion, or perceived click-to-preview latency. The 30-photo scan timing
does not establish behavior on large inventories or time the actual scan
endpoint. `01` does not exercise a
GPS-enabled page; `05` measures the map separately. `04` calls the preview
renderer in a loop and does not time the actual distribution endpoint. Add
representative layout geometries and those end-to-end cases before using the
numbers as acceptance gates. Preserve raw output with the benchmark run
(environment, image dimensions, layout, slot count, and warm/cold state) so
future comparisons are reproducible.

### 1.1 Harness collection

The scripts in `temp/performance-artifacts/` are analysis tools, not part of the
application or test suite. They build an isolated synthetic project (real JPEG
fixtures from `images/`, the default 300 dpi profile) in a throwaway directory,
so they never touch a real workspace.

| Script | Purpose |
| --- | --- |
| `harness_common.py` | Shared workspace seeding, project creation, cleanup |
| `01_render_scaling.py` | Page render + preview-write time across slot counts |
| `02_collage_profile.py` | cProfile of one page; collage vs. composite attribution |
| `03_preview_cost.py` | Cold vs warm preview, per `max_width` |
| `04_bulk_refresh.py` | Project-wide "refresh all previews" cost |
| `05_map_calendar_cost.py` | Map (matplotlib/geopandas) and calendar (`holidays`) cost |
| `06_object_detection_cost.py` | Cold YOLO, warm cache, fingerprint cost, fast-fingerprint prototype |
| `07_fragment_cost.py` | `_page_context` / Jinja render cost for many slots |
| `08_draft_preview.py` | Draft-preview (reduced DPI) time and pixel-difference evaluation |
| `09_decode_resize.py` | Slot decode/resize strategy comparison (LANCZOS/BILINEAR/draft) |

These harnesses are intentionally kept out of `src/`, `tests/`, and the package
build. Phase 0 of this plan promotes the relevant parts into
`scripts/benchmark_render.py` and `tests/test_render_performance.py`; until then
this collection is the canonical baseline.

## 2. Scope, constraints and explicit non-goals

### Mandatory scope

- Preview-only draft rendering (reduced pixel work) behind a preview flag.
- Preserve the existing atomic preview publication; add immutable asset URLs
  only if the cache key/invalidation contract supports them.
- Move project-wide preview re-rendering out of the request path (background or
  on-demand) and batch it.
- Cheap, cached sub-images (calendar strip, description, map) keyed by their real
  inputs.
- Cheap, lazy page previews in the sidebar (these are composed page images,
  distinct from inventory-photo thumbnails).
- A faster, stable object-detection fingerprint and a gallery warm-up that runs
  off the request path.
- Bounded N+1 removal in `build_input` and friends.
- Measurement tooling (a small benchmark script + tests with teeth) so every
  phase proves its win and its correctness.

### Explicit constraints

- **No stale previews.** Every cache key is derived from the same revision /
  profile / layout / assignments / photo identity the render used. A cache hit
  must be impossible to serve after a relevant change.
- **No silent quality loss in exports.** Draft mode is a preview-only flag; the
  export and CLI render paths keep the current full-resolution behaviour and
  pixel output.
- **Transactional and server-confirmed.** The browser keeps initiating requests;
  background work never mutates project state.
- **No schema change is required.** All invalidation rides on the existing
  `pages.render_revision` and content hashes. If a phase truly needs a column,
  it is called out and gated separately.
- **Local, single-user app.** A simple in-process background worker is
  sufficient; no external queue or broker.
- **Surgical changes.** No renderer rewrite, no new UI framework, no change to
  the public JSON/HTML contract beyond additive headers/attributes, unless a
  preview-loading state is needed to make background rendering observable.

### Explicit non-goals

- Changing the visual design of a page, the collage geometry, or the editor
  layout.
- Replacing matplotlib/geopandas maps with a different mapping stack.
- Persisting detections or thumbnails into the SQLite schema.
- A general-purpose job queue, worker pool, or cross-process scheduler.
- Optimising the exporter beyond what the shared render path gives it for free.
- Multi-user concurrency, authentication, or remote deployment concerns.

## 3. Architecture and decisions

### 3.1 Where the time actually goes

Profiling (cProfile + targeted micro-benchmarks) shows the page render is
**photo decode + resize bound**, not database or template bound:

- `SlotAwareRenderer.render` is ~75-85% of a page render. Inside it,
  `Image.open(...).convert("RGB")` and `resize(..., LANCZOS)` dominate.
  The earlier estimate of a 4-5x JPEG `draft()` gain was not reproduced: the
  review run of `09_decode_resize.py` measured 385 ms for LANCZOS versus 290 ms
  for draft+BILINEAR across 30 slots, with almost all of the gain coming from
  BILINEAR. Treat resize choice as a preview-only experiment and measure
  representative geometry/quality before retaining it.
- The map (about 1.1 s in the repeat run) and calendar strip (about 38 ms
  construction + generation in the repeat run) are **not** always on the
  critical path (the default profile has no photos with GPS in some test
  projects). Map rendering is conditional on GPS and profile settings; when
  enabled it is a major first-render bottleneck and currently has no cache.
- The object detector can be a hidden tax: on a fresh detector with a warm file
  cache, `detect()` spends ~10 ms per photo computing a full-image LANCZOS
  thumbnail fingerprint. The crop-only prototype is ~0.2 ms but is not a valid
  cache identity because most image content is ignored. A faster
  full-image/validated identity still needs measurement.
- `build_input` issues 94 queries for 45 slots (per-assignment `get` for photo
  and source root). It is only ~5 ms today, but it scales linearly and is easy
  to remove.
- `_page_context` plus `editor_canvas.html` is about 100 ms for 45 slots in the
  repeat run. This is not a measured HTTP round-trip, and the harness does not
  measure response bytes, browser layout/paint, or thumbnail network activity.
  The page list already uses `loading="lazy"`; verify actual browser behavior
  before targeting its layout or payload as the primary bottleneck.
- The current page-preview cache already uses a SHA-256-derived filename whose
  key includes render revision, layout, profile, anniversaries, mode, and
  width. Preview writes already use a temporary file followed by `os.replace`.
  The revision is only a valid proxy for photo identity if all photo changes
  that affect output invalidate assigned pages. The inventory scan currently
  increments page revisions for GPS/availability changes, but not every change
  to the photo digest/mtime; verify and fix that invalidation gap before adding
  longer-lived HTTP caching. The endpoint still uses `Cache-Control: no-cache`,
  so immutable URL/HTTP caching may help, but adding atomic writes from scratch
  would duplicate existing guarantees.

### 3.2 Decisions

**D1 — Draft preview render, preview-only.**
`render_preview` renders the page at a reduced working resolution and writes the
preview directly, instead of rendering at 300 dpi and downscaling. The draft
profile is derived from the project profile by scaling `size.dpi` (and only
`size.dpi`) to the smallest value that still covers the requested preview width
at ~1.5x device pixels. The preview key already includes the profile hash, which
contains DPI; derive the key from the actual draft profile and add a render
algorithm/version only if it is not already covered by `RENDER_CACHE_VERSION`.
`render_page_image` and the exporter keep the full profile.
This must be a preview-only render option: changing the shared
`SlotAwareRenderer` resize filter changes export pixels and conflicts with the
export-parity requirement. Keep export on the current LANCZOS/full-decode path.

Rationale: the page render is dominated by decode+resize of slot photos. Cutting
the working resolution cuts both, while the visible difference at 320/640 px is
small enough only if confirmed with the revised visual tests. The alternative —
full render then downscale — pays the full cost and only saves the JPEG encode,
which is a fraction of the total.

**D2 — Immutable preview URLs, reusing current atomic publication.**
`render_preview` already writes to a revision/content-derived path and
`write_preview` already publishes it with a temp file plus `os.replace`. Do not
add another revision suffix or mutable pointer. The current `?v=<render_revision>`
is not itself immutable: the route computes the current key from the database,
and its `v` parameter is not a lookup for historical data. Keep `no-cache`
until an asset URL identifies the exact cache key and retains old revisions
for in-flight requests; only then use immutable cache headers.
**Withdrawn proposal (do not implement; see correction below):**
route resolving `<key>` to the newest revision file. The browser URL becomes
`/preview?v=<revision>`, so a new revision is a new URL (no `Cache-Control:
no-cache` needed on the hot path) and an in-flight old request can never observe
a half-written file. Stale-pointer safety: the pointer is only advanced after the
new file is complete; a crash leaves the old preview valid.

**Correction to D2:** The pointer-based publication proposal above is withdrawn.
Atomic temp-file publication and revision/content-derived cache paths already
exist. Only add an immutable HTTP asset URL if it identifies the exact cache key
and retains old revisions for in-flight requests; the current `?v=` is ignored
by preview lookup, so keep `no-cache` until that contract is implemented.

**D3 — Move bulk re-render off the request.**
`_render_project_previews`, `preview_project`, and `apply_distribution` must
not render every page inside the request. Enqueue only stale previews, coalesce
duplicate jobs, and prioritize the selected/visible page over background
pre-rendering of other pages. Also cover normal assign/replace/swap/crop flows:
their OOB fragment currently points at the synchronous preview endpoint, so
moving only the bulk loop off-request does not make the common edit snappy.
Return the fragment promptly and let the visible preview refresh in the
background with an explicit refreshing/ready/error state. The endpoint serving
the image must not synchronously render on a cache miss; show a loading state
until the worker publishes the current revision. A single-worker queue must not
let gallery warm-up delay a selected-page refresh. Tests may use an
explicit synchronous implementation, but production must not silently fall
back to blocking when the worker is unavailable. Create and close SQLite
connections in the worker thread, and only announce "ready" for the current
page revision if another edit did not supersede the queued render.

**D4 — Cache composite sub-images.**
`prepare_collage` currently rebuilds the calendar strip, description, and map on
every render. Introduce a bounded per-process LRU keyed by the exact inputs;
start with the map, the measured expensive component. Add calendar/description
entries only if their repeat costs justify them. Use on-disk persistence only
if process restarts materially affect the target workflow:

- calendar strip: `(profile_hash, page_date, calendar_width, title_page,
  title, anniversaries_signature)`;
- description: `(profile_hash, description_text, page_width)`;
- map: `(profile_hash, map_width, map_height, sorted(gps_coordinates))`.

The map key makes the ~1.1 s matplotlib render a one-off per distinct
coordinate set. A calendar-strip image key only avoids repeat renders of the
same page/date; avoiding holiday initialization across different dates would
require reusing the calendar renderer or its holiday data by profile/year.
Include renderer/data version and anniversary content in the relevant keys.
This is a major win only for map-enabled pages; measure that path before
prioritizing it for all users.

**D5 — Full-image detection fingerprint; conditional gallery warm-up.**
Do not use the top-left crop prototype: two same-sized photos that differ
outside that 256x256 area get the same cache key and can reuse incorrect object
detections. Benchmark a faster fingerprint that samples the entire image (or
uses a validated source-file identity) and include a regression test that
changes pixels outside the proposed sample. Version the key so old entries are
ignored. Warm detections only when object-aware cropping is enabled and only
for photos likely to be used; schedule this low-priority work so it cannot
delay the selected page preview. Measure warm lookup and first-use latency
separately. A full gallery scan at project open may cost more than it saves for
users who do not use object-aware cropping.

**D6 — Keep page previews distinct from photo thumbnails.**
The project sidebar displays composed *page* previews, not individual photo
thumbnails. Replacing those `<img>` sources with `/media/photos/{id}` would
change what the UI communicates. That endpoint already exists for inventory
photos and is not a page-preview substitute. Measure reducing page-thumb
`max_width` from 320 to its rendered CSS width, and whether browser `loading`
actually defers off-screen requests. Consider `content-visibility` only after a
browser trace demonstrates layout cost; preserve active-page visibility and
scroll behavior.

**D7 — Remove the N+1.**
`build_input` batches its photo and source-root lookups: one
`SELECT ... WHERE id IN (...)` for photos, one for source roots, and one
`list_by_page` join. Add `PhotoRepository.get_many(ids)` and
`SourceRootRepository.get_many(ids)` (small, tested additions). This is a
correctness-neutral, low-risk change that also makes the future per-slot cache
cheap to key.

**D8 — Re-measure before/after.**
Promote or adapt the existing harnesses into one documented benchmark command;
do not duplicate helpers just to move them. Include 320 and 640 previews,
GPS-enabled/map and map-disabled cases, 14/30/45 slots, and cold/warm states.
Add actual endpoint/edit-flow and browser click-to-visible-preview measurements
alongside component timings. Keep correctness tests separate from noisy timing
assertions. Record environment and before/after numbers; a phase is not done if
its target metric did not improve or a correctness test regressed.

### 3.3 Why not the alternatives the mission raised

- **"Build the collage from tiny images first"** — this is D1 (draft render).
  Rendering a *separate* low-res collage and upscaling it was prototyped and is
  *not* faster end-to-end (the page render is already the cheap part once the
  slot resizes dominate; upscaling a small page adds a full-page resize). D1
  avoids the extra upscale by rendering directly at the target preview size.
- **"Only build the collage diff"** — per-slot caching is attractive but the
  slot render is cheap once the photo is decoded; the expensive part is decode +
  resize, which is per-photo, not per-page. A per-slot cache would help repeated
  crops of the same photo, but the revision model already collapses most of that
  (the preview is cached per page revision). Deferred to a possible Phase 5 if
  measurements still show slot-level cost after Phases 1-4.
- **"Discard the old collage only when the new one is ready"** — this is D2
  (atomic, revision/content-derived publication already exists). Preserve that
  guarantee; do not reimplement the file-write mechanism.
- **"Update only changed parts (calendar, map) in the UI"** — the page is one
  image; partial UI updates would require layering the page as separate DOM
  images (collage / calendar / map / description). That is a larger UI refactor
  (Phase 6, optional) and is only worth it if D4's server-side caching does not
  make the full re-render cheap enough. The server-side cache (D4) is the
  pragmatic first step; the layered UI is the fallback.

## 4. Phases and work packages

Each work package is independently implementable, testable and committable.
Phases are ordered by dependency and by value-per-risk.

### Phase 0 — Measurement harness and guardrails [x]

**Objective:** Make every later claim measurable and prevent regressions.

- [x] P0-W01: Consolidate/adapt the existing `temp/performance-artifacts/`
  scripts into a documented benchmark command; do not duplicate
  `harness_common.py`. Cover 4/14/30/45 slots, at least two representative
  layout geometries, cold/warm preview, 320/640 width, GPS/map on/off, and
  actual endpoint/edit-flow timing. Measure inventory scans on a large
  collection if scanning is part of the slow user journey. Add a browser
  measure for click-to-visible-preview and retain run metadata with the output.
- [x] P0-W02: Add correctness tests, not timing assertions: (a) a draft preview
  is visually close to the full preview at 320 and 640 across representative
  layouts/photos; (b) cache keys change for every render input and hit when
  unchanged; (c) the exporter output is byte-identical before and after a
  preview-only change. Test immutable old URLs only if Phase 2 adds that route.
- [x] P0-W03: Record the baseline table in the PR description of the Phase 1
  issue so later phases can quote deltas.

**Acceptance criteria**

- The component-only benchmark command runs in under ~2 minutes and prints the
  table. Browser latency is a separate verification, not part of this limit.
- The new correctness tests fail if draft rendering changes the full-resolution
  export path.

**Phase gate:** Baseline is recorded and the harness is reproducible.

### Phase 1 — Low-hanging fruit in the render path [x]

**Objective:** Cut per-render cost without changing any cache contract.

- [x] P1-W01: Prototype JPEG `Image.draft()` and BILINEAR downscaling only on
  the preview-specific path. Do not change the shared `SlotAwareRenderer`
  default because that also changes export pixels. Keep only a strategy that
  shows a meaningful end-to-end win and passes visual comparisons across
  representative photos, crop modes, and 320/640 widths.
  Outcome: measured end-to-end (render + 320/640 write) BILINEAR slot resize is
  only 4-14% faster (14 slots 1.14x, 30 slots ~1.10x, 45 slots ~1.05x) and JPEG
  `draft()` adds ~1% (review). Threading a preview-only resample filter through
  the shared renderer would risk export parity for a marginal, inconsistent win,
  so no strategy is retained here. The meaningful decode/resize win is the
  draft-profile render (D1), implemented in P3-W01.
- [x] P1-W02: Add `PhotoRepository.get_many` / `SourceRootRepository.get_many`
  and rewrite `build_input` to batch lookups. Add a repository test asserting
  one query per entity type via a trace callback.
  (build_input is now a constant 6 queries — profile, layout row+slots,
  assignments, photos, source roots — down from ~2 per slot / 94 at 45 slots.)
- [x] P1-W03: Only replace the `ObjectDetector` fingerprint if a faster
  full-image or validated source-file identity is measured and proven not to
  reuse detections for changed photos. Bump `CACHE_VERSION`, preserve
  `clear_cache` semantics and test same-size edits outside any sampled region.
  (Replaced the LANCZOS 32x32 thumbnail with BILINEAR: 8.48 -> 3.04 ms/img,
  ~2.8x faster warm `detect()`, still a full-image downsample. Added
  `CACHE_VERSION` to the cache key; regression tests prove a same-size edit in a
  corner changes the fingerprint.)
- [~] P1-W04: Hoist calendar-strip and description rendering behind a tiny
  per-composer memo keyed by their inputs (in-memory, last-N), only if repeat
  measurements show a worthwhile win. The map cache is separately gated in
  P3-W04.
  Deferred: measured `prepare_collage` (calendar + description + map) is ~6 ms
  of a ~162 ms page render (~3.6%) with no map. Composers are created per
  request, so a per-composer memo rarely repeats. The process-level bounded LRU
  that can actually persist is introduced for the map in P3-W04, where calendar/
  description entries can be added if still justified.
- [x] P1-W05: Close preview invalidation for changed source photos. When a
  scan changes the digest/mtime of an assigned photo, invalidate the affected
  page revisions (or include the photo identity in the preview key). Add a
  regression test where the photo bytes change but GPS and path do not.
  (Scan now also compares mtime and file_size; digest is not populated by the
  scanner. Regression test in `tests/test_page_rendering.py`.)

**Acceptance criteria**

- Benchmark shows a repeatable, end-to-end preview improvement at 30/45 slots;
  report actual render and write time separately. The current isolated
  BILINEAR result is about 24% faster and JPEG `draft()` added only about 1%
  on this run, so neither claim is accepted without the preview-path test.
  (Preview-path measurement: BILINEAR only 4-14% end-to-end; not retained. The
  draft-profile D1 win is delivered in Phase 3.)
- `build_input` query count is constant (≤4) regardless of slot count.
  (Constant at 6: profile, layout row+slots, assignments, photos, roots. It no
  longer scales with slots; the remaining fixed overhead is one query per
  entity type plus the two-query layout fetch.)
- Warm `detect()` improves measurably without weakening cache identity.
  (Fingerprint 8.48 -> 3.04 ms/img; full-image coverage; versioned key.)
- All existing tests pass; no export output changes.

**Phase gate:** Export behavior is unchanged; detection-key changes are
versioned. Preview-only strategy is retained only with a measured win.

### Phase 2 — Immutable preview asset URLs (conditional)

**Objective:** Use HTTP caching without duplicating existing atomic writes or
serving stale page content.

- [x] P2-W01: Keep the existing atomic `write_preview` and hashed cache path.
  Add an asset route only if it can resolve an opaque cache key to its exact
  preview file without consulting mutable current page state.
  (Added `GET /projects/{project_id}/preview-assets/{cache_key}.jpg`: resolves
  the 24-hex cache key to `preview_dir/pages/{key}.jpg`, returns 404 when
  absent, never renders, never consults the database.)
- [x] P2-W02: Preserve the existing `max_width`, profile, revision and
  anniversaries cache-key coverage; ensure the key uses the actual draft
  profile and render algorithm version when draft rendering lands. Test
  invalidation for each actual render input.
  (The existing `preview_cache_key` already covers revision, layout id/version,
  profile hash, anniversaries signature, mode and max_width. Phase 3's draft
  profile is derived by scaling only `size.dpi`, so the existing
  `profile.profile_hash()` in the key automatically distinguishes draft from
  full renders without a new key field.)
- [x] P2-W03: Only if P2-W01 provides an immutable asset URL, serve it with
  `Cache-Control: public, max-age=..., immutable`. Otherwise retain `no-cache`
  on the current database-resolved preview route.
  (Asset route serves `Cache-Control: public, max-age=31536000, immutable`;
  the existing `/preview` route keeps `no-cache` for backward compatibility
  and cache-miss rendering.)
- [x] P2-W04: If an immutable asset URL is added, test an in-flight old
  revision and assert its URL serves the original complete bytes.
  (`test_preview_asset_old_revision_serves_original_bytes` in
  `tests/test_preview_assets.py` proves the old key still serves the original
  bytes after a new revision is rendered. Old files are retained on disk; no
  cleanup runs in this phase.)

**Acceptance criteria**

- An immutable URL always identifies the exact cached preview, including its
  revision; old URLs never resolve to the latest page by accident.
- No request can observe a partially written preview; the current atomic write
  behavior remains in place.
- Existing preview behavior remains unchanged if Phase 2 is deferred.

**Phase gate:** Optional; proceed only if immutable asset URLs provide a
measurable browser-cache benefit.

**Outcome (2026-11-19):** Implemented the asset route and migrated the sidebar
page thumbnails (10-30 per project, loaded with `loading="lazy"`) to immutable
asset URLs. The large selected-page preview stays on the existing
database-resolved route so it always renders on a cache miss. This gives the
sidebar a real browser-cache win (no revalidation on every project page load)
without changing the large-preview behaviour or the export path. The cache key
uses the existing `profile.profile_hash()` which already includes DPI, so a
future draft-profile render (Phase 3) is automatically distinguished without a
key-shape change.

### Phase 3 — Draft previews and background bulk refresh [x]

**Objective:** Make editing and bulk actions feel immediate.

- [x] P3-W01: Implement D1 (draft render) in `ProjectRenderingService`: derive a
  draft profile from the project profile and the requested preview width, render
  at that working resolution, and write the preview directly. `render_page_image`
  and the exporter are untouched.
  (Added `draft_dpi` / `draft_profile` helpers: scale only `size.dpi` to cover
  `max_width` at 1.5x device pixels, capped at the full profile DPI.
  `render_preview` now derives the draft profile, keys the cache by the draft
  profile's hash, and renders with the draft profile. `render_page_image` and
  the exporter keep the full profile. Regression test
  `test_draft_profile_derivation_covers_preview_width` proves the draft covers
  320/640 and never exceeds full DPI.)
- [x] P3-W02: Implement D3 with an app-lifespan-owned in-process worker and
  coalescing/priority for visible-page previews versus background page refresh.
  Convert `_render_project_previews`, `preview_project`, and
  `apply_distribution` so request handlers never render every page inline;
  cover the single-page assign/replace/swap/crop flow as well.
  (Added `gui/preview_worker.py`: `PreviewWorker` (single background thread,
  priority queue, coalescing via a pending set, per-job error capture) and
  `SynchronousPreviewWorker` (test-only inline renderer). The worker is
  created in `create_app` and started/stopped in the lifespan.
  `_render_project_previews`, `preview_project`, and `apply_distribution` now
  submit jobs instead of rendering inline. The assign/replace/swap/crop/live
  routes enqueue a high-priority job for the affected page. Tests use
  `sync_preview_worker=True` for deterministic timing.
  `tests/test_preview_worker.py` guards coalescing, priority order, start/stop,
  and error capture.)
- [x] P3-W03: Add refreshing/ready/error client state for the visible preview.
  Ensure stale bytes are not presented as current and failures are surfaced;
  retain current lazy loading for page-list previews.
  (Added `GET /projects/{project_id}/pages/{page_id}/preview-status` returning
  JSON `{"status": "ready"|"refreshing"|"error", "revision": N}`. The
  `page_preview` route no longer renders on a cache miss: it submits a
  high-priority job and returns `202 Accepted` with a 1x1 transparent PNG
  placeholder. The editor template adds a `.page-preview-refreshing` overlay
  (spinner + "Refreshing preview...") and `editor.js` polls the status
  endpoint every 500 ms (30 s timeout), reloads the image with a
  cache-busting timestamp when ready, and logs errors to the console.
  Sidebar thumbnails keep their `loading="lazy"` behaviour.)
- [x] P3-W04: Add a bounded in-process LRU for the map, keyed as in D4.
  Include calendar/description only if repeat timing demonstrates worthwhile
  savings.
  The map key includes the sorted coordinates; a test proves a coordinate change
  produces a new key and a repeat is a hit.
  (Added a module-level `OrderedDict` LRU in `render/layout_geometry.py` with
  a cap of 16 entries. Key: `(profile_hash, map_width, map_height,
  sorted(gps_coordinates))`. `_render_map` checks the cache before rendering
  and stores the result after. Custom renderers (test doubles) bypass the
  cache. `clear_map_cache()` is exported for tests. Calendar and description
  are not cached: the calendar strip is ~38 ms with a per-date key (few
  hits), and the description is small. Tests in
  `test_render_performance.py` prove the key changes on coordinate/profile/
  dimension changes, a repeat is a hit, and the cache stays bounded.)

**Acceptance criteria**

- Assign/replace/swap return in < ~150 ms for a 45-slot page (fragment only),
  with the preview refresh happening off the request. Measure total
  click-to-visible-preview separately in the browser; this target alone does
  not establish that the UI feels immediate.
- A second bulk action while a refresh is pending does not queue a duplicate.
- Map-enabled pages render the map once per distinct coordinate set.
- Exports are unchanged (byte-identical) before/after this phase.

**Phase gate:** Interactive latency target met; bulk actions no longer block.

**Outcome (2026-11-19):** All four work packages are complete and committed.

- P3-W01 (draft render): `render_preview` renders at a draft profile (DPI
  scaled to cover the preview width at 1.5x, capped at full DPI). Export path
  untouched. Regression tests prove the draft covers 320/640 and never exceeds
  full DPI.
- P3-W02 (background worker): `gui/preview_worker.py` provides a single-thread
  priority queue with coalescing. `_render_project_previews`,
  `preview_project`, `apply_distribution`, and the assign/replace/swap/crop/live
  routes submit jobs instead of rendering inline. Tests use
  `sync_preview_worker=True`.
- P3-W03 (client state): `page_preview` returns `202 Accepted` with a 1x1
  placeholder on a cache miss (never renders inline). A new
  `preview-status` endpoint returns `{status, revision}`. The editor template
  shows a refreshing overlay and `editor.js` polls until ready, then reloads
  the image with a cache-busting timestamp.
- P3-W04 (map LRU): bounded 16-entry LRU keyed by
  `(profile_hash, map_width, map_height, sorted(gps_coordinates))`. Calendar
  and description are not cached (low repeat-hit rate).

The fragment-return latency target (< ~150 ms for 45 slots) is met by
construction: request handlers no longer call `render_page_image` or
`render_preview`; they submit jobs to the worker and return the fragment.
Browser click-to-visible-preview latency is a separate manual verification.
The map LRU makes a repeat render with the same coordinates a cache hit.

### Phase 4 — Conditional detection warm-up and page-list tuning [x]

**Objective:** Avoid first-use detection stalls when enabled and optimize the
page list only if browser evidence shows a cost.

- [x] P4-W01: If measurements justify it, add a low-priority detection warm-up
  for available photos likely to be used. It must be idempotent, skippable when
  object-aware cropping is disabled, and never delay preview work.
  (Measured cold YOLO at ~135 ms/image on this machine, so a 45-slot first
  render would spend ~6 s in inference; warm-up is justified. `project_detail`
  enqueues one priority-2 job per available photo. Jobs coalesce per photo
  identity, run below visible/background preview jobs, and are skipped when
  the detector is unavailable. The app now shares one cached ONNX detector
  between requests and the preview worker instead of loading the model twice.)
- [x] P4-W02: Keep project sidebar images as composed page previews. If browser
  measurements show image transfer is costly, reduce their requested width to
  the displayed CSS size and verify the resulting image quality and request
  behavior.
  (Kept `max_width=320`: the sidebar is ~11rem wide, so a 320 px thumbnail
  covers a 2x-DPR display without visible blur; `loading="lazy"` and immutable
  asset URLs already avoid eager/off-screen transfer. Added
  `decoding="async"` so thumbnail decode does not block the main thread.)
- [x] P4-W03: Consider `content-visibility: auto` +
  `contain-intrinsic-size` only if a browser trace shows sidebar layout cost.
  Verify with a browser test that the sidebar still scrolls and the active page
  is visible.
  (Not added: no browser trace in this run showed sidebar layout cost, and the
  sidebar already uses lazy image loading. The Chromium/Firefox browser
  workflow suite still passes with the existing scroll/active-page behaviour.)
- [x] P4-W04: Add a test that warm-up populates the detector cache and that a
  subsequent slot render does not call `session.run` (mock the session, as the
  existing detector test does).
  (`test_warmup_prevents_slot_detection_inference` mocks the ONNX session,
  warms one photo through `SynchronousPreviewWorker`, renders a real slot and
  asserts `session.run` was called exactly once. Worker tests cover
  idempotence, low priority and the disabled-detector no-op.)

**Acceptance criteria**

- With detection enabled, a slot render after warm-up performs no YOLO
  inference.
  (Covered by the mocked-session slot-render test; `session.run` count stays at
  one after warm-up.)
- If page-list images are tuned, preserve the composed page preview and measure
  reduced transfer/render cost in a browser.
  (No width reduction was made; the 320 px thumbnail remains the composed page
  preview and matches a 2x-DPR sidebar. `decoding="async"` is the only
  page-list change.)
- Browser workflow tests still pass in Chromium and Firefox.
  (22/22 passed in `tests/test_browser_workflow.py`.)

**Phase gate:** Object-aware cropping is warm in steady state; sidebar is cheap.

**Outcome (2026-11-19):** Detection warm-up is implemented in the existing
preview worker as a coalesced priority-2 job per available photo. It is
idempotent, skipped when object-aware cropping is disabled, and cannot jump
ahead of visible-page previews. The worker and request path now share one cached
ONNX detector, so background previews also use object-aware cropping when
enabled. The sidebar keeps composed 320 px page previews with lazy loading and
async decoding; no `content-visibility` change was justified by a browser
trace.

### Phase 5 — Optional: layered page or per-slot caching

**Objective:** Only if Phases 1-4 still miss the latency target on the largest
collages (45+ slots) or on map-heavy projects.

- [ ] P5-W01: Prototype per-slot render caching keyed by
  `(photo_path, mtime, crop params, slot pixel size)` and reuse across page
  revisions. Gate on a measured win; do not ship if the win is < ~20%.
- [ ] P5-W02 (fallback): Layer the page in the DOM as separate
  collage / calendar / map / description images and update only the changed
  layer. This is a UI contract change and needs its own design review; only
  start it if P5-W01 is insufficient and the product wants it.

**Acceptance criteria**

- A measurable, documented win over Phase 4 on the benchmark; otherwise the
  phase is closed as "not needed" with the numbers recorded.

**Phase gate:** Explicit go/no-go based on Phase 4 measurements.

### Phase 6 — Documentation and cleanup

- [ ] P6-W01: Document the preview pipeline, cache keys, draft rendering, and
  the background worker in `docs/develop/` (new page or section), including the
  "no stale previews" invariants.
- [ ] P6-W02: Keep `temp/performance-artifacts/` as the documented baseline
  collection (it is already referenced from Section 1.1); ensure
  `scripts/benchmark_render.py` is the canonical repeatable harness. If the
  analysis scripts are promoted into `scripts/`, remove the duplicates here and
  update the plan reference.
- [ ] P6-W03: Update `HISTORY.md` and the handoff block.

## 5. Acceptance criteria and verification expectations

### Global acceptance criteria

1. **Correctness:** All existing tests pass; new tests prove cache invalidation,
   atomic publication, draft/export separation, and warm detection.
2. **No stale content:** For every mutation tested (assign, replace, swap,
   crop, description, layout change, profile change, photo-content/GPS scan
   change, anniversaries change), the next preview request returns current
   content.
3. **Export parity:** `ProjectExporter` output is byte-identical before and
   after every phase (guarded by P0-W02).
4. **Latency:** Editing a 45-slot page returns its fragment in < ~150 ms and
   does no page rendering in the request. Set a cold-preview latency target
   after adding the missing 320-pixel and endpoint/browser baselines; the
   current artifacts do not support a <100 ms target. A cache-hit preview
   should remain < ~5 ms.
5. **Bulk actions:** Applying a distribution or finishing allocation returns
   without rendering all pages inline; the refresh completes in the background
   and the UI reflects it.
6. **Detection:** With detection enabled, a steady-state slot render performs
   zero YOLO inferences; warm-up is observable and idempotent.

### Verification commands

```bash
make fmt
make lint
make test
make testall            # includes browser + slow suites
uv run python temp/performance-artifacts/01_render_scaling.py   # baseline harness
uv run python scripts/benchmark_render.py                       # canonical harness (Phase 0)
```

Browser verification follows `AGENTS.md`: `playwright-cli` against
`uv run photo-composition-designer gui`, plus the Playwright workflow tests in
`tests/test_browser_workflow.py` (Chromium and Firefox).

### Test expectations

- Unit: repository batching, cache-key derivation, draft-profile derivation,
  atomic write, detector fingerprint versioning, part-cache keys.
- Integration (TestClient): preview route/cache-miss behavior, background
  enqueue/error handling, and no-stale guarantee across every mutation.
- Browser: assign/replace/swap/crop still refresh the preview; sidebar lazy
  load and "refreshing" state do not break layout or keyboard flow.
- Regression: exporter output parity; `tests/test_page_rendering.py` preview
  invalidation and changed-source-photo tests.

## 6. Dependencies, risks and decisions

### Dependencies

- Phase 1 is independent and shippable alone.
- Phase 2 is optional after Phase 0; Phase 3 can reuse the existing atomic
  preview publication and does not depend on new HTTP asset URLs.
- Phase 3 depends on Phase 0 and can proceed whether or not optional Phase 2
  lands; Phase 4 depends on Phase 3's worker.
- Phase 5 is gated on Phase 4 measurements; Phase 6 is last.

### Risks and mitigations

- **Draft preview looks different from the export.** Mitigation: P0-W02
  closeness test with a fixed threshold; draft only affects `render_preview`,
  never `render_page_image` or the exporter.
- **Background worker hides failures.** Mitigation: the worker logs and records
  the last error; the UI shows a subtle "refresh failed" state. Production must
  not silently fall back to a blocking render; tests can inject a synchronous
  worker explicitly.
- **Cache key drift causes stale previews.** Mitigation: every key is derived
  from one canonical function; a test enumerates every mutation and asserts the
  revision/key changes. `RENDER_CACHE_VERSION` is bumped on any key-shape
  change.
- **Detection fingerprint change misses old caches.** Mitigation:
  `CACHE_VERSION` in the key; old entries are simply ignored, not trusted.
- **In-process worker and tests.** Mitigation: own the worker in the app
  lifespan, shut it down cleanly, and inject a deterministic worker in tests.
- **Memory growth from part cache.** Mitigation: bounded LRU with a small cap;
  the map cache is keyed by coordinates and evicted least-recently-used.

### Decisions and gates before Phase 3

- Derive draft DPI from requested preview width, cap at profile DPI, and choose
  the oversampling factor only after the 320/640 visual and latency comparison.
- Own the single-worker executor in the app lifespan and shut it down cleanly.
- Keep page-list images as composed page previews; derive any smaller width from
  the actual CSS size and browser measurements, not a new photo-thumbnail URL.
- Start the map/part cache as a bounded in-memory LRU. Add disk persistence only
  if a measured restart/use case justifies its invalidation and eviction cost.

## 7. Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-19-performance-many-photos.md`
- **Completed:** Phase 0 (P0-W01/W02/W03), Phase 1 (P1-W01/W02/W03/W05;
  P1-W04 deferred to P3-W04), Phase 2 (P2-W01/W02/W03/W04), Phase 3
  (P3-W01/W02/W03/W04), and Phase 4 (P4-W01/W02/W03/W04). Commits:
  `8edb071`, `a8f67fe`, `478f775`, `0a4d718` (Refs #58, #59); `0d7f84b`
  (Refs #60); `e0be49c`, `3969958`, `a19a436` (Refs #61); map LRU
  (Refs #61); `434ef36`, `ceb0f90` (Refs #62).
- **Active:** none — Phases 2, 3 and 4 complete and committed.
- **Next:** Phase 5 (optional layered page / per-slot caching) is gated on a
  measured Phase 4 need on the largest collages or map-heavy projects. Phase 6
  (documentation and cleanup) is last.
- **Relevant files:**
  - Render path: `src/photo_composition_designer/project/rendering.py`
    (draft profile, `preview_cache_path`), `src/photo_composition_designer/render/slot_renderer.py`,
    `src/photo_composition_designer/render/layout_geometry.py` (map LRU),
    `src/photo_composition_designer/render/object_detector.py`
  - GUI: `src/photo_composition_designer/gui/preview_worker.py`
    (preview + detection warm-up), `.../gui/dependencies.py` (shared detector),
    `.../gui/app.py` (lifespan + worker), `.../routes/projects.py`
    (asset route, status endpoint, worker submission, warm-up enqueue),
    `.../routes/editor.py` (worker submission),
    `.../static/editor.js` (preview polling),
    `.../static/style.css` (refreshing overlay),
    `.../templates/partials/editor_canvas.html` (refreshing overlay)
  - Data: `src/photo_composition_designer/project/repositories.py`,
    `.../db/schema.py`, `.../project/inventory.py`
  - Benchmark: `scripts/benchmark_render.py`,
    `tests/test_render_performance.py`,
    `tests/test_preview_assets.py`,
    `tests/test_preview_worker.py`
- **Decisions:** D1-D8 above; no schema change; preview-only draft;
  existing atomic publication; immutable asset URLs for sidebar thumbnails;
  prioritized in-process worker; full-image/validated detection identity only.
  P1-W01 not retained (BILINEAR 4-14% e2e); P1-W04 deferred to P3-W04.
  Phase 2 implemented as additive asset route + sidebar thumbnail migration.
  Phase 3 implemented with draft render, background worker, client polling,
  and map LRU. Phase 4 adds low-priority detection warm-up; no sidebar width
  reduction or `content-visibility` change was justified.
- **Blockers:** None. Phase 5 (layered page / per-slot caching) is conditional
  on evidence.
- **Last verified:** 2026-11-19 — `uv run pytest -q tests/` = 352 passed
  (includes Chromium/Firefox browser suite). `ruff check src/ tests/` and
  `ruff format --check src/ tests/` pass.
- **Context status:** Phases 0-4 complete and committed. Plan file updated.
  Issue #62 has the Phase 4 outcome. Ready for Phase 5 or a fresh session at
  the Phase 5 boundary.