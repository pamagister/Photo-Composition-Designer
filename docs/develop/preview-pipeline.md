# Preview pipeline and render caches

**Status:** Implemented
**Plan:** `docs/plans/2026-11-19-performance-many-photos.md`

This page documents how page previews are produced, cached and refreshed. It is
the developer-facing reference for the performance work in the many-photo plan
and records the invariants that keep previews fast **and** truthful.

## 1. Goals

- **Editing feels immediate.** Assign, replace, swap and crop return the page
  fragment without rendering a full-resolution page inside the request.
- **Previews are cheap.** A 200/800 px preview costs substantially less than a
  full 300 dpi render.
- **Exports stay full quality.** Draft rendering is a preview-only flag; the
  exporter and the CLI keep the pixel-exact full-resolution path.
- **No stale previews.** A cache hit is impossible after a relevant change.

## 2. Two render paths

| Path | Entry point | Resolution | Used by |
| --- | --- | --- | --- |
| Full render | `ProjectRenderingService.render_page_image` | Project profile (e.g. 300 dpi) | Exporter, CLI, final output |
| Preview render | `ProjectRenderingService.render_preview` | Draft profile (reduced DPI) | Web UI previews and sidebar thumbnails |

The two paths share the same composer and layout geometry. Only the output
profile differs, so a preview is always the same composition as the export at a
smaller working resolution.

## 3. Draft profile (preview-only)

`draft_profile(profile, max_width)` in `project/rendering.py` derives a
preview-only profile from the project profile. It scales **only** `size.dpi`
(`draft_dpi`) to the smallest integer DPI whose rendered page width covers
`max_width * DRAFT_OVERSAMPLE` (1.5x device pixels), capped at the full profile
DPI. Every other profile value (page geometry, calendar, style, geo, layout) is
preserved.

Because only DPI changes, the page is rendered at a lower working resolution
and the slot photos are decoded and resized less. `render_preview` renders with
this draft profile and writes the preview directly. `render_page_image` and the
exporter are untouched.

The draft profile's `profile_hash()` differs from the full profile, so the
preview cache key automatically distinguishes draft from full renders without a
key-shape change.

## 4. Cache key contract

`ProjectRenderingService.preview_cache_key` returns a deterministic 24-hex
SHA-256 digest over:

| Field | Source | Why |
| --- | --- | --- |
| `cache_version` | `RENDER_CACHE_VERSION` | Bump on any key-shape or render-algorithm change |
| `page_index` | Page | Distinguishes pages |
| `revision` | `page.render_revision` | Invalidates on any page edit |
| `layout_id`, `layout_version` | Page layout | Distinguishes layout changes |
| `profile` | `profile.profile_hash()` | Distinguishes profiles, including draft vs. full |
| `anniversaries` | File path, mtime, size, digest | Invalidates on anniversary data changes |
| `mode` | `"preview"` | Distinguishes preview modes |
| `max_width` | Requested width | 200 and 800 are different files |

The preview is stored at `preview_dir/pages/{key}.jpg`. `preview_cache_path`
computes the path without rendering, so callers can check `is_file()`.

### Invariants (no stale previews)

1. **Every key is derived from the same inputs the render used.** A cache hit
   after a change is impossible unless the change is invisible to the key.
2. **Photo content changes invalidate assigned pages.** The inventory scan
   compares mtime and file size and bumps the affected page revisions (P1-W05).
3. **Atomic publication.** `write_preview` writes to a temporary file and
   `os.replace`s it, so a reader never observes a half-written preview.
4. **The worker never serves stale bytes as current.** On a cache miss the
   preview route returns `202 Accepted` with a 1x1 placeholder and the client
   polls the status endpoint until the current revision is ready.

## 5. Background preview worker

`gui/preview_worker.py` owns an in-process, single-thread worker
(`PreviewWorker`) that renders previews off the request path. It is created in
`create_app` and started/stopped by the app lifespan.

- **Priorities.** `0` = visible page (highest), `1` = background page refresh,
  `2` = object-detection warm-up (lowest). Visible-page previews are never
  delayed by bulk refresh or warm-up.
- **Coalescing.** A job with the same `(project_id, page_id, max_width, mode)`
  that is already pending is skipped, so a second bulk action while a refresh is
  pending does not queue a duplicate.
- **Thread-owned DB access.** The worker creates and closes its own SQLite
  connections; the request thread never holds a connection while a render runs.
- **Failure capture.** The last error is recorded and surfaced through the
  status endpoint. Production never silently falls back to a blocking render.
  Tests inject `SynchronousPreviewWorker` for deterministic timing.

Routes that mutate a page (assign / replace / swap / crop / live) enqueue a
high-priority job for the affected page and return the fragment immediately.
`_render_project_previews`, `preview_project` and `apply_distribution` submit
jobs instead of rendering every page inline.

### Client contract

| Endpoint | Behaviour |
| --- | --- |
| `GET .../pages/{page_id}/preview` | Returns the cached image if present; otherwise `202 Accepted` + placeholder and enqueues a priority-0 job. Never renders inline. |
| `GET .../pages/{page_id}/preview-status` | `{"status": "ready"\|"refreshing"\|"error", "revision": N}` |
| `GET .../preview-assets/{cache_key}.jpg` | Immutable asset URL (see below) |

`editor.js` polls the status endpoint, shows a refreshing overlay and reloads
the image with a cache-busting timestamp when ready.

## 6. Immutable asset URLs (sidebar thumbnails)

`GET /projects/{project_id}/preview-assets/{cache_key}.jpg` resolves an opaque
cache key to `preview_dir/pages/{key}.jpg` without consulting mutable page
state. It never renders and never touches the database. The route serves
`Cache-Control: public, max-age=31536000, immutable`.

Sidebar page thumbnails (10-30 per project) use these immutable URLs, so the
browser caches them without revalidation. The large selected-page preview stays
on the database-resolved `/preview` route, which keeps `no-cache` and renders on
a miss. Old revisions are retained on disk, so an in-flight request for an old
key always receives the original complete bytes.

## 7. Composite sub-image caches

- **Map (D4).** `render/layout_geometry.py` keeps a bounded 16-entry `OrderedDict`
  LRU keyed by `(profile_hash, map_width, map_height, sorted(gps_coordinates))`.
  `_render_map` checks the cache before rendering and stores the result after.
  A repeat render with the same coordinates is a cache hit. `clear_map_cache()`
  is exported for tests. Custom renderers (test doubles) bypass the cache.
- **Calendar strip and description** are not cached: their repeat cost is small
  and their per-date/per-text hit rate is low.

## 8. Object detection

`render/object_detector.py` uses a full-image BILINEAR downsample as the cache
fingerprint (about 2.8x faster than the previous LANCZOS 32x32 thumbnail while
still covering the whole image). The cache key includes a `CACHE_VERSION`, so old
entries are ignored, not trusted. A same-size edit in a corner changes the
fingerprint (regression-tested).

Detection warm-up runs as a priority-2 worker job per available photo when
object-aware cropping is enabled. It is idempotent, coalesced per photo identity
and skipped when the detector is unavailable. The app shares one cached ONNX
detector between requests and the worker, so a steady-state slot render performs
zero YOLO inferences.

## 9. Measuring the pipeline

The canonical, repeatable benchmark is:

```bash
uv run python scripts/benchmark_render.py              # row + grid geometries
uv run python scripts/benchmark_render.py --gps        # also exercise the map path
uv run python scripts/benchmark_render.py --geometry row
```

It builds a throwaway project from real JPEG fixtures in `images/`, measures full
render, cold/warm preview at 200/800, bulk refresh and editor context cost, and
prints run metadata. Shared seeding helpers live in `scripts/harness_common.py`.
Browser click-to-visible-preview latency is a separate manual verification.

## 10. Non-goals

- Draft rendering never changes export pixels.
- No new job queue, broker or cross-process scheduler.
- No schema change: invalidation rides on existing revisions and content hashes.
- Page previews stay composed page images, not per-photo thumbnails.