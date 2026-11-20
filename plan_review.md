# Plan: Correct Preview Status and Refactor Project Routes

## Objective and desired outcome

Fix two confirmed project issues and improve the maintainability of the web
project routes without changing user-visible behavior:

1. Make preview failures specific to the render job they came from, so an old or
   unrelated worker error cannot report a current preview as failed.
2. Correct the invalid `uv lock` option in the `make lock` target.
3. Split the oversized project router by responsibility while preserving route
   URLs, request/response behavior, and existing service boundaries.

## Scope and constraints

- Keep the change limited to preview status reporting, the lock target, and
  project-route organization.
- Preserve existing preview cache and polling behavior, including the frontend's
  handling of ready, refreshing, and error states.
- Keep HTTP handlers thin and reuse existing application services and
  repositories; do not introduce a new abstraction layer without a concrete
  need.
- Preserve all existing route paths, template names, response codes, query and
  form contracts, and user-facing messages.
- Do not include broader UI redesign, undo/redo, unrelated exception cleanup,
  or changes to rendering behavior.

## Architecture and decisions

- Associate worker failures with an identifiable preview job (at minimum its
  project, page, width, and mode) rather than exposing one persistent global
  `last_error` as the status for every page.
- Ensure successful completion clears or supersedes only the corresponding
  job's prior failure. Keep the public status response compatible with the
  existing `ready`, `refreshing`, and `error` states.
- Split `gui/routes/projects.py` into responsibility-focused route modules
  (project lifecycle, preview, source/inventory, and distribution) using the
  existing router inclusion pattern. Place shared context-building code only
  where its ownership and reuse are clear.
- Correct the `uv lock` option to the supported `--no-cache` spelling; do not
  change dependency resolution or install behavior otherwise.

## Phase 1: Correct preview job status

- [x] P1-W01: Trace preview submission, coalescing, completion, and status
  polling to define a job identity that matches the preview cache dimensions.
- [x] P1-W02: Replace the worker's global stale error reporting with status
  that is associated with the relevant preview job and cleared or superseded
  after a successful retry.
- [x] P1-W03: Update the preview status endpoint and, only if needed, its
  client-side consumer to report errors for the requested job without changing
  the established response states.
- [x] P1-W04: Add regression tests for a failed preview followed by a successful
  retry and for a failure on one page not affecting another page's status.

**Acceptance criteria**

- An error from one page or preview width does not incorrectly fail another
  preview request.
- A successful retry is reported as ready and does not inherit a stale error.
- A current render failure remains visible to the relevant client.
- Existing cache-hit, queued-render, and synchronous-worker behavior remains
  covered and unchanged.

**Phase gate:** Focused preview-worker and preview-status tests pass before
route modules are moved.

## Phase 2: Fix the lock target

- [x] P2-W01: Replace the unsupported `--no-cacke` argument in `Makefile` with
  the supported uv option.
- [x] P2-W02: Verify the `lock` target and, if practical without unnecessary
  dependency changes, the `install` target's lock step.

**Acceptance criteria**

- `make lock` no longer fails because of an unrecognized command-line option.
- The target does not alter project dependency declarations as part of this fix.

## Phase 3: Split project routes by responsibility

- [x] P3-W01: Group current `projects.py` handlers by project lifecycle,
  preview, source/inventory, and distribution responsibilities; identify shared
  helpers and their callers before moving code.
- [x] P3-W02: Move the preview routes and preview-specific helpers into a
  focused route module, preserving their paths and endpoint behavior.
- [x] P3-W03: Move source/inventory and distribution routes into focused
  modules, retaining shared helpers only where they are genuinely common.
- [x] P3-W04: Keep project listing, creation, and lifecycle routes in a
  focused project module and update route exports and application registration.
- [x] P3-W05: Update directly affected tests or documentation if module
  references or route ownership are documented; do not change generated docs.

**Acceptance criteria**

- Route URLs, endpoint behavior, template output, and form/query contracts are
  unchanged.
- No new SQL, distribution algorithm, or rendering logic is added to route
  handlers.
- Each new module has a cohesive responsibility, and shared context code has a
  clear owner.
- The complete existing GUI test coverage passes.

**Phase gate:** Review the route diff for behavior-only moves; resolve accidental
behavior changes before final verification.

## Phase 4: Verification

- [x] P4-W01: Run the focused preview-worker, preview-status, and GUI tests.
- [x] P4-W02: Run `make lint` and `make test`.
- [x] P4-W03: Run any additional route or browser workflow tests required by
  changes uncovered during implementation.

**Acceptance criteria**

- Focused regression tests cover both confirmed preview-status failure modes.
- Linting and the repository's fast test suite pass.
- Any test or validation that could not be run is recorded explicitly in the
  handoff.

## Deferred work

- Browser end-to-end testing in CI.
- Enabling mypy in the standard quality gate.
- Broad CSS or UI cleanup and unrelated route/service refactoring.

## Dependencies, risks, and unresolved questions

- Route extraction depends on the existing route behavior remaining stable;
  move one cohesive area at a time and verify it before proceeding.
- The worker currently handles jobs in one background thread. Status tracking
  must remain thread-safe and must distinguish jobs sufficiently to avoid
  stale errors while respecting the current job coalescing behavior.
- No product decision is currently unresolved. If implementation reveals a
  need to change the preview status contract or user-facing failure behavior,
  pause and confirm that change rather than silently expanding scope.

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `plan_review.md`
- **Completed:** Phase 1 preview job-scoped errors, Phase 2 lock option fix, Phase 3 route split, Phase 4 verification
- **Active:** None
- **Next:** Push batches and monitor CI
- **Relevant files:** `src/photo_composition_designer/gui/preview_worker.py`,
  `src/photo_composition_designer/gui/routes/project_context.py`,
  `src/photo_composition_designer/gui/routes/project_lifecycle.py`,
  `src/photo_composition_designer/gui/routes/project_preview.py`,
  `src/photo_composition_designer/gui/routes/project_inventory.py`,
  `src/photo_composition_designer/gui/routes/project_distribution.py`,
  `src/photo_composition_designer/gui/routes/projects.py`,
  `src/photo_composition_designer/gui/app.py`, `tests/test_preview_worker.py`,
  `tests/test_preview_assets.py`, `tests/test_gui.py`, `Makefile`
- **Decisions:** Keep preview response states and route contracts stable;
  associate worker errors with relevant preview jobs; split routes by
  responsibility; leave optional CI and typing improvements deferred.
- **Blockers:** None
- **Last verified:** 2026-11-20; `make lock` resolved 104 packages; `make lint` passed; `make test` passed (280 tests).
- **Context status:** clean
