# Distribution Modes and Layout Reset

**Status:** Complete  
**Created:** 2026-11-22  
**Repository:** `pamagister/Photo-Composition-Designer`  
**Execution mode:** autopilot, phase-boundary handoffs

## 1. Objective and desired outcome

Add a complete “rearrange all photos” workflow to the existing distribution page:

1. A new **Extras** action with a trash-can icon that switches every calendar page to the **Automatic** layout while keeping existing photos and crop settings.
2. A rebuilt **Distribute photos** page with three top-level modes:
   - **Distribute all photos** – assign all available photos across all pages using Automatic layouts.
   - **Distribute the best photos** – select a configurable number of the highest-quality photos per page and distribute them.
   - **Respect current layouts** – the existing slot/layout-aware distribution.
3. Remove the **Automatic layout target slots** setting completely. Distribution computes its own target from the actual photo and page counts.
4. A date-aware distribution algorithm with global look-ahead that keeps same-day or consecutive-day photos together where sensible, while penalising page overfill/underfill and date gaps.
5. A deterministic image-quality heuristic for “best photos” when object detection is unavailable, and a combined detection/quality score when it is available.

The concrete reference case is project 4: **303 photos, 53 pages**, currently all on static layouts. The desired result is 53 Automatic pages with all 303 photos assigned, page sizes near `303 / 53 ≈ 5.7`, and same-day groups kept together where possible.

## 2. Scope, constraints and non-goals

### Mandatory scope

- Remove `auto_target_slots` / `autoTargetSlots` from the profile, legacy settings, project settings form, docs and tests.
- Add a transactional “reset all layouts to Automatic” service and route.
- Add the Extras menu button with confirmation.
- Add `mode` and supporting fields to distribution proposals and previews.
- Implement the date-aware grouping algorithm as a pure, deterministic module.
- Implement the quality heuristic and best-photo selection.
- Update the distribution UI, documentation and automated tests.
- Preserve the existing static-layout distribution path.

### Explicit constraints

- All distribution changes remain server-confirmed and transactional.
- The automatic collage geometry engine (`layouts/auto_layout.py`) is unchanged.
- Rendering, export, cropping and preview caching remain unchanged.
- No database schema migration is required.
- Existing project snapshots that still contain `auto_target_slots` must continue to load; the unknown key is ignored.
- No per-page exclusion feature (the `99_*` collage pages are only in the old reference output).
- No new UI for tuning penalty weights in this iteration.

### Non-goals

- Free-form page editing or manual collage geometry.
- Per-page “exclude from distribution” flags.
- Persisting quality scores across restarts.
- Changing the look of the calendar pages.
- Reworking the automatic layout search algorithm.

## 3. Architecture and decisions

### 3.1 Distribution modes

Introduce a top-level `mode` with three values:

| Mode | Photos considered | Layouts | Target |
| --- | --- | --- | --- |
| `all` | All available project photos, including already assigned ones | All pages reset to Automatic | Computed `total_photos / page_count` |
| `best` | All available photos, ranked; top K selected | All pages reset to Automatic | Computed from the selected range |
| `slots` | Only unassigned available photos | Existing page layouts | Static slot count; computed fallback for Automatic pages |

`slots` preserves the current behaviour and the existing `date_aware` week-matching strategy. The new date-grouping algorithm is exposed internally as `date_grouped` and labelled **Date aware** in the `all` and `best` modes.

Strategy values:

- `equal`
- `random`
- `date_grouped` (new algorithm; `all` and `best` modes)
- `date_aware` (existing week matching; `slots` mode only)

For `all` and `best`, applying a proposal always resets every page to Automatic. This is implicit and shown as a warning in the preview.

### 3.2 Remove `auto_target_slots`, compute the target

Remove:

- `LayoutProfile.auto_target_slots`
- `LayoutConfig.autoTargetSlots`
- Project settings form field and route field
- Generated configuration docs
- Tests that assert the field exists

Add a computed target in `DistributionService`:

```text
target = selected_photo_count / page_count
```

For `date_grouped`, the target is dynamic and recomputed for each page:

```text
target = remaining_photos / remaining_pages
```

For `slots` mode on Automatic pages, use the same computed target as a fallback capacity. Static pages keep their slot count.

Legacy project JSON containing `auto_target_slots` must load without error. Add a regression test for that.

### 3.3 Date-aware grouping algorithm

Add a pure module, for example `project/date_grouping.py`, with no I/O.

Inputs:

- Photos with `(photo_id, captured_at)`.
- Page count.
- Optional minimum and maximum page size.
- Penalty weights.

Algorithm:

1. Sort photos by `(captured_at or datetime.max, filename, photo_id)`.
2. Compute per-photo day and gap values:
   - `gap[i] = max(0, (day[i] - day[i-1]).days - 1)`.
   - Same-day and consecutive-day photos therefore have zero gap penalty.
3. Use dynamic programming:
   - `dp[p][i]` = minimum cost of assigning the first `i` photos to the first `p` pages.
   - For a candidate page containing `photos[j:i]`:
     - `target = (n - j) / (P - p + 1)` (moving average of remaining photos per remaining page).
     - Segment cost:
       - `w_dev * (size - target)^2` – penalise deviation from the moving target.
       - `w_gap * sum(gap[j+1:i])` – penalise non-consecutive dates; the farther apart, the higher.
       - `w_split` if `day[j] == day[j-1]` – penalise splitting one day across two pages.
       - Optional `w_min * max(0, min_size - size)^2` and `w_max * max(0, size - max_size)^2` for best mode.
4. Reconstruct the best partition.
5. Use a banded DP for performance: only consider page sizes around the current target, initially `target ± max(2, ceil(target))`. Fall back to the existing greedy date grouping for very large inputs if the band becomes impractical.

The DP is global, so it naturally provides look-ahead. It replaces the old one-pass greedy algorithm for `all` and `best` modes.

Expected behaviour:

- 12 same-day photos, 2 pages, target 6 → **6 + 6**.
- 10 same-day photos, 2 pages, target 5 → **5 + 5**.
- 7 same-day photos with target 6 → keep **7 on one page** when that avoids a split and the overfill penalty is smaller than the split penalty.
- Consecutive-day photos → balanced groups at the moving target.
- Large date gaps → the algorithm prefers to start a new page rather than bridge the gap.

Suggested initial weights:

```text
deviation_weight = 1.0
gap_weight       = 1.0
split_weight     = 6.0
below_min_weight = 2.0
above_max_weight = 2.0
band             = max(2, ceil(target))
```

The weights are internal constants. Tests must cover the examples above.

### 3.4 Equal and Random

For `all` and `best` modes:

- **Equal**: sort the selected photos by capture date, then split into `P` contiguous groups as equally as possible (`floor` / `ceil` sizes). All selected photos are assigned.
- **Random**: seeded shuffle with `random.Random(seed)` (default seed `11`, as in 1.0.7), then split equally. Reproducible for a given seed.

For `slots` mode, the existing capacity-limited behaviour remains.

### 3.5 Best-photo selection and quality heuristic

Add `project/quality.py` with a `QualityScorer`:

- Open each image, downscale to a maximum long edge of about 512 px.
- Compute:
  - Resolution score from pixel dimensions.
  - Sharpness score from the variance of a 3×3 Laplacian on the grayscale thumbnail.
- Normalise both to `(0, 1]` across the batch.
- Combine as `quality = 0.6 * resolution + 0.4 * sharpness` (initial weights).
- Cache by `(path, mtime, file_size)` in memory for the request.
- Unreadable images receive the lowest score.

Add a `SelectionScorer` that combines detection and quality:

```text
score = importance * quality
```

`importance` comes from the existing `ImportanceScorer` and is `1.0` when object detection is disabled or unavailable. Therefore:

- Detection enabled: detection boosts the score, quality breaks ties.
- Detection disabled: quality alone decides.

Best-mode selection:

1. Compute a target average from the selected preset:
   - `2–5` → 4
   - `3–5` → 4
   - `3–6` → 5
   - `3–7` → 5
2. `K = min(total_photos, round(page_count * target_average))`.
3. Sort all available photos by `(-score, captured_at or datetime.max, photo_id)`.
4. Select the top `K`.
5. Distribute the selected photos with the chosen strategy (`equal`, `random` or `date_grouped`).
6. For `date_grouped`, pass the preset min/max as soft page-size bounds.
7. Photos not selected remain in the unused pool and are reported as `not_selected`.

Example: 53 pages, preset `3–5`, target 4 → select about 212 photos, distribute 4 per page on average, leave about 91 unused.

### 3.6 Reset layouts to Automatic

Add to `PageEditingService`:

```python
reset_all_layouts_to_auto(
    project_id: int,
    *,
    preserve_assignments: bool = True,
) -> int
```

Behaviour:

- **Preserve mode** (Extras button): for each page, rebuild an Automatic snapshot from the photos currently assigned to that page. Existing assignments and crop settings are kept. Empty pages receive an empty Automatic snapshot.
- **Clear mode** (distribution apply): clear assignments and set every page to an empty Automatic snapshot before applying the proposal.

Implementation detail: use a private `_reset_layouts_in_transaction(connection, ...)` helper so the distribution `apply` can call it inside its existing transaction without nesting `with connection:` blocks.

Route:

```text
POST /projects/{project_id}/layouts/reset-auto
```

It calls the preserve-mode reset, increments page revisions, enqueues previews for all pages, and redirects to `/projects/{id}?layouts=1`.

UI:

- Add a trash-can button to the Extras dropdown, labelled **Reset layouts**.
- Confirmation text: “Reset all pages to the Automatic layout? Existing photos and crops are kept.”
- Add a project-page notice for `?layouts=1`.

### 3.7 Data and API changes

Extend `DistributionProposal`:

```python
mode: str = "slots"
reset_layouts: bool = False
not_selected: list[int] = field(default_factory=list)
target: float | None = None
```

Extend `ProposalSummary` with `not_selected` and `target`.

Extend the service API:

```python
propose(
    project_id,
    *,
    mode="slots",
    strategy="equal",
    seed=None,
    best_range="3-5",
    object_detector=None,
)
```

`apply` must:

- Reset all layouts when `proposal.reset_layouts` is true.
- Clear existing assignments before applying the new groups.
- Preserve the existing orientation matching for static layouts.
- Regenerate Automatic snapshots from the assigned photos.

The proposal digest must include `mode`, `strategy`, `seed`, `best_range`, `pages`, `unassigned` and `not_selected`, so stale previews are rejected across modes.

### 3.8 UI changes

`distribution_area.html`:

- Add a mode selector:
  - **Distribute all photos**
  - **Distribute the best photos**
  - **Respect current layouts**
- Show strategy and seed for all modes.
- Show the range preset only for best mode.
- Show a note for `all` and `best`: “All pages will be switched to Automatic.”
- Keep the existing preview/apply buttons.

`distribution_preview.html`:

- Show mode, strategy and computed target.
- For Automatic pages, show `X photos (target Y)` rather than `X of Y slots filled`.
- For static pages, keep `X of Y slots filled`.
- Report:
  - Assigned
  - Not selected (best mode)
  - Overflow (slots mode)
  - Unassigned
- Include `mode`, `strategy`, `seed`, `best_range` and the digest in the apply form.

`project_distribution.py`:

- Parse and validate `mode`, `strategy`, `seed` and `best_range`.
- Pass the object detector into `propose` for best mode.
- Default the distribution page to `mode=all`, `strategy=date_grouped` to match the primary use case.
- Preserve the existing stale-digest and repeat-confirmation behaviour.

## 4. Phases and work packages

### Phase 1: Remove `auto_target_slots` and add computed capacity (done)

**Objective:** Make the old target-slot setting disappear without breaking existing projects.

- [x] P1-W01: Remove `auto_target_slots` from `LayoutProfile` and `autoTargetSlots` from `LayoutConfig`; update `to_dict`, `from_dict`, `from_settings`, `apply_to_settings`.
- [x] P1-W02: Remove the field from the project settings route and template; update tests.
- [x] P1-W03: Add computed-target helpers to `DistributionService` and update `capacity_for_page` / `propose`.
- [x] P1-W04: Update `tests/test_auto_distribution.py`, `tests/test_project_settings.py` and generated docs; run `make fmt`.

**Acceptance criteria**

- No source reference to `auto_target_slots` or `autoTargetSlots` remains except historical plan documents.
- A project JSON containing the legacy key still loads.
- Automatic-page capacity is derived from photo/page counts.

**Phase gate:** `make test` is green.

### Phase 2: Reset layouts action

**Objective:** Provide the non-destructive Extras reset.

- [x] P2-W01: Implement `reset_all_layouts_to_auto` and `_reset_layouts_in_transaction`.
- [x] P2-W02: Add the POST route and preview enqueueing.
- [x] P2-W03: Add the Extras trash-can button, confirmation and `?layouts=1` notice.
- [x] P2-W04: Add service and route tests for assignment/crop preservation, empty pages, revisions and preview jobs.

**Acceptance criteria**

- All pages use the Automatic layout after the action.
- Existing photos and crop settings remain assigned.
- Empty pages receive an empty Automatic snapshot.
- The action is transactional and refreshes previews.

**Phase gate:** Manual check on a copy of project 4.

### Phase 3: Date-aware engine and mode integration

**Objective:** Implement the new distribution algorithms and proposal model.

- [x] P3-W01: Add `project/date_grouping.py` with the pure DP.
- [x] P3-W02: Add unit tests for 12→6+6, 10→5+5, 7 same-day, consecutive days, date gaps, determinism and full assignment.
- [x] P3-W03: Extend `DistributionProposal` and `ProposalSummary`.
- [x] P3-W04: Integrate `all` and `best` modes into `propose`, including computed target and all-available-photo collection.
- [x] P3-W05: Update `apply` to reset layouts and clear assignments when required.
- [x] P3-W06: Add service tests for mode `all`, mode `best`, `equal`, `random`, `date_grouped` and digest changes.

**Acceptance criteria**

- `all` mode assigns every available photo across Automatic pages.
- `date_grouped` produces the documented grouping examples.
- `equal` and `random` produce balanced page sizes.
- Applying `all` or `best` switches every page to Automatic.

**Phase gate:** Project 4 dry run produces 53 Automatic pages with all 303 photos assigned.

### Phase 4: Quality heuristic and best-photo selection

**Objective:** Make “best photos” meaningful with or without object detection.

- [x] P4-W01: Add `QualityScorer` with downscaled resolution and sharpness scoring.
- [x] P4-W02: Add `SelectionScorer` combining importance and quality.
- [x] P4-W03: Add tests for ranking, fallback and unreadable images.
- [x] P4-W04: Implement best-mode selection (range → K → top K → distribute).
- [x] P4-W05: Add tests for K, range behaviour and `not_selected`.

**Acceptance criteria**

- A sharp, high-resolution photo ranks above a blurry, low-resolution one.
- Detection-disabled mode still produces a deterministic ranking.
- Best mode selects approximately `page_count * midpoint(range)` photos.
- Unselected photos remain in the unused pool.

**Phase gate:** `best` with `3–5` on project 4 selects about 212 photos and produces Automatic pages.

### Phase 5: Distribution UI and routes

**Objective:** Expose the new modes cleanly.

- [x] P5-W01: Update `distribution_area.html` with mode, strategy, seed and range controls.
- [x] P5-W02: Update `distribution_preview.html` with target/assigned/not-selected/overflow reporting.
- [x] P5-W03: Update `project_distribution.py` for mode parsing, detector passing, digest and notices.
- [x] P5-W04: Update `docs/usage/web-ui.md` and `docs/usage/auto-layout.md`; run `make fmt`.
- [x] P5-W05: Add TestClient/browser tests for all modes, stale previews and reset notice.

**Acceptance criteria**

- All three modes can be previewed and applied.
- The preview clearly distinguishes target, assigned, not selected and overflow.
- Stale previews are rejected.
- Documentation matches the UI.

**Phase gate:** End-to-end browser run through all three modes.

### Phase 6: Verification and manual validation

**Objective:** Prove the feature on the real data set.

- [x] P6-W01: Run `make fmt`, `make lint`, `make test`; run targeted slow tests.
- [x] P6-W02: Validate on project 4:
  - Reset layouts → 53 Automatic pages, photos kept.
  - Distribute all → date-aware → 303 assigned, page sizes near 6, same-day groups preserved where possible.
  - Distribute all → equal and random → balanced page sizes.
  - Distribute best `3–5` → about 212 selected, automatic layouts.
  - Existing slots mode on a static-layout project still works.
- [x] P6-W03: Update the handoff block and report results.

**Acceptance criteria**

- All automated checks pass.
- Manual results are comparable to the `Kalender 2025` reference folders.
- No regression in static-layout distribution, cropping, preview or export.

## 5. Acceptance criteria and verification

### Functional

- Extras → **Reset layouts** switches all pages to Automatic and keeps photos/crops.
- **Automatic layout target slots** no longer exists anywhere in the UI or settings.
- Distribution page offers **all**, **best** and **current layouts** modes.
- `all` mode assigns every available photo using Automatic layouts.
- `best` mode supports `2–5`, `3–5`, `3–6`, `3–7` and leaves unselected photos unused.
- Date-aware mode:
  - Uses `remaining_photos / remaining_pages` as the moving target.
  - Keeps same-day photos together when the penalty trade-off allows.
  - Splits large same-day groups into balanced pages.
  - Penalises date gaps and same-day splits.
  - Is deterministic.
- Existing static-layout distribution still works.

### Verification commands

```bash
make fmt
make lint
make test
uv run pytest tests/test_distribution.py tests/test_distribution_ui.py \
  tests/test_auto_distribution.py tests/test_project_settings.py -q
```

Manual checks:

```bash
uv run photo-composition-designer gui
# http://127.0.0.1:8767/projects/4/distribute
```

## 6. Dependencies, risks and unresolved questions

### Dependencies

- Existing `DistributionService`, `PageEditingService`, `ImportanceScorer` and automatic layout engine.
- `numpy` and `Pillow` are already dependencies for the quality heuristic.
- No database schema changes.

### Risks and mitigations

- **Removing `auto_target_slots` may break old configurations.** `LayoutProfile.from_dict` ignores unknown keys; add a regression test. Update all source references and generated docs.
- **Quality scoring may be slow on very large JPEGs.** Downscale to 512 px, use JPEG draft decoding, cache by `(path, mtime, size)`, and show a progress indicator.
- **Date-aware DP cost on large projects.** Use a banded DP around the moving target and a greedy fallback for very large inputs.
- **Penalty weights may need tuning.** Keep them as named constants and verify against project 4 and the reference folders.
- **Best-mode global top-K may omit some days.** This is the chosen interpretation of “Min-Max per calendar page”. If per-day coverage becomes important, it can be added later.
- **Digest changes may invalidate old previews.** This is intentional; stale previews must be rejected.

### Resolved decisions

- Reset layouts keeps photos and crops.
- `all` mode redistributes already assigned photos.
- Best range means min–max photos per calendar page.
- Quality heuristic is required as the fallback.
- No per-page exclusion feature.
- `auto_target_slots` is removed completely.
- `date_aware` remains for slots mode; `date_grouped` is the new algorithm for all/best modes.

### Remaining open items

- Exact penalty weights and band width will be validated during Phase 3.
- The quality formula weights (`0.6` resolution / `0.4` sharpness) are initial values and may be tuned after inspecting project 4.

## Progress / Handoff

```markdown
- **Mode:** autopilot
- **Plan:** docs/plans/2026-11-22-distribution-modes.md
- **Completed:** all phases (P1-P6) and work packages
- **Active:** none
- **Next:** none
- **Relevant files:**
  - src/photo_composition_designer/project/distribution.py
  - src/photo_composition_designer/project/date_grouping.py
  - src/photo_composition_designer/project/quality.py
  - src/photo_composition_designer/project/editing.py
  - src/photo_composition_designer/project/importance.py
  - src/photo_composition_designer/core/output_profile.py
  - src/photo_composition_designer/core/settings.py
  - src/photo_composition_designer/gui/routes/project_distribution.py
  - src/photo_composition_designer/gui/routes/project_settings.py
  - src/photo_composition_designer/gui/routes/editor.py
  - src/photo_composition_designer/gui/templates/partials/distribution_area.html
  - src/photo_composition_designer/gui/templates/partials/distribution_preview.html
  - src/photo_composition_designer/gui/templates/base.html
  - src/photo_composition_designer/gui/templates/project_settings.html
  - tests/test_distribution.py, tests/test_distribution_ui.py,
    tests/test_auto_distribution.py, tests/test_project_settings.py,
    tests/test_date_grouping.py, tests/test_quality.py
- **Decisions:** remove auto_target_slots; computed target; modes all/best/slots; date_grouped DP; quality heuristic fallback; best range is min-max per page; reset layouts preserves photos.
- **Blockers:** none
- **Last verified:** 2026-11-22, `make fmt`, `make lint` and `make test` green (523 passed).
- **Validation:** synthetic 303-photo / 53-page dry run -> 53 automatic pages, 303 assigned,
  date_grouped 5-6 per page, equal/random balanced, best 3-5 selected 212 (91 not_selected),
  static slots mode unchanged.
- **Context status:** complete
```
