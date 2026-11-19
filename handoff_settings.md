# Settings defaults: duplicated sources of truth

Status: investigation note and refactor plan (2026-11-19).
Scope: `core/settings.py` and `core/output_profile.py`.
This document is a plan only; no code has been changed for it yet.

## Problem

The same default values are currently defined twice, in two different shapes.

1. `src/photo_composition_designer/core/settings.py`
   - `Settings` aggregates `GeneralConfig`, `CalendarConfig`, `StyleConfig`,
     `GeoConfig`, `SizeConfig` and `LayoutConfig`.
   - Every field is a `Param` wrapper (`param.value`) with a literal default.
   - This is the legacy `config_cli_gui` access shape kept for the renderers.

2. `src/photo_composition_designer/core/output_profile.py`
   - `OutputProfile` aggregates `CalendarProfile`, `StyleProfile`, `GeoProfile`,
     `SizeProfile` and `LayoutProfile` (plus `FontSpec`).
   - These dataclasses carry their own literal defaults and are the format that
     is persisted per project in `projects.output_profile_json`.

Conversion paths:

- `OutputProfile.default()` calls `from_settings(Settings())`, so a new project
  gets the `Settings` defaults.
- `OutputProfile.from_dict()` fills missing keys from the *profile* dataclass
  defaults, not from `Settings`.
- `OutputProfile.to_settings()` converts a stored profile back into the legacy
  `Settings` shape for the renderers.

### Why this is a problem

- **Drift risk.** A default changed in `core/settings.py` affects new projects;
  the same value changed in `core/output_profile.py` affects only missing-key
  fallbacks. The two can silently diverge.
- **Documentation gap.** `scripts/generate_config_docs.py` renders
  `docs/usage/config.md` only from `Settings`. Defaults that exist only in
  `OutputProfile` are not documented, and vice versa.
- **Non-1:1 mapping.** The two shapes do not line up, which makes a mechanical
  comparison impossible without a mapping table:
  - `settings.general.compositionTitle` -> `profile.calendar.title`
  - `settings.calendar.holidayCountries` (comma string) ->
    `profile.calendar.holiday_countries` (tuple)
  - `settings.layout.useShortDayNames` / `useShortMonthNames` ->
    `profile.calendar.use_short_day_names` / `use_short_month_names`
  - `settings.size.mapSize` -> `profile.geo.map_size`
- **Legacy-only fields in `Settings`.** These are not part of the persisted
  profile and are not used by the web workflow:
  - `general.photoDirectory`, `general.anniversariesConfig`,
    `general.locationsConfig`
  - `calendar.startDate`, `calendar.collagesToGenerate`
  - `persist_last_used` and `get_cli_parameters()`

  Paths come from `preferences.json` (`gui/settings.py`), source roots and page
  dates come from the SQLite workspace. The only remaining users are the legacy
  `CalendarRenderer.from_config()` path and the demo `main()` in
  `render/calendar.py`.
- **Renderer coupling.** The renderers still accept `Settings`
  (`render/map.py`, `render/calendar.py`, `render/description.py`,
  `render/slot_renderer.py`, `io/export.py`), so `Settings` cannot simply be
  deleted without changing those call signatures.

## Options

### Option A (recommended): make `OutputProfile` the single source of truth

- Keep the literal defaults only in the `OutputProfile` dataclasses.
- Remove the duplicated defaults from `core/settings.py`. Either:
  - delete `Settings` and let renderers consume `OutputProfile` directly, or
  - keep `Settings` purely as a legacy adapter produced by
    `OutputProfile.to_settings()`, with no independent defaults.
- Generate `docs/usage/config.md` from the profile defaults.
- Remove the legacy-only fields listed above.

Pros: one definition per value, documentation and persistence use the same
source, and the eventual renderer refactor removes the adapter entirely.
Cons: touches the renderer API and its tests.

### Option B: keep `Settings` canonical

- Make `OutputProfile` derive its defaults from a module-level default
  `Settings` instance instead of repeating literals.

Pros: smaller change, renderers stay untouched.
Cons: keeps two shapes and an awkward dependency from the persisted profile to
the legacy settings object; documentation still needs a decision.

## Proposed plan (Option A)

1. **Lock current behavior with a parity test.**
   - Assert `OutputProfile.default() == OutputProfile.from_settings(Settings())`.
   - Add field-by-field assertions for the mapped values (see the mapping
     table above) so the refactor cannot change a default unnoticed.
2. **Choose the canonical definition.**
   - Move all defaults into `core/output_profile.py`.
   - Reduce `core/settings.py` to an adapter or delete it.
3. **Remove legacy-only surface.**
   - Drop `general.photoDirectory`, `general.anniversariesConfig`,
     `general.locationsConfig`, `calendar.startDate`,
     `calendar.collagesToGenerate`, `persist_last_used` and
     `get_cli_parameters()` once no production caller needs them.
   - Update `tests/test_CalendarRenderer.py`, which constructs
     `Settings(persist_last_used=False)`.
4. **Refactor renderers.**
   - Let renderers accept `OutputProfile` (or a small explicit render-config
     object) instead of `Settings`.
   - Update `io/export.py`, `render/map.py`, `render/calendar.py`,
     `render/description.py`, `render/slot_renderer.py` and
     `project/rendering.py`.
   - Keep `OutputProfile.to_settings()` only as long as an external caller needs
     it, then remove it.
5. **Update documentation generation.**
   - Point `scripts/generate_config_docs.py` at the canonical defaults.
   - Regenerate `docs/usage/config.md` and adjust `AGENTS.md` wording.
6. **Verify.**
   - `make fmt`, `make lint`, `make test`.
   - Re-render representative pages and compare against the current output to
     confirm pixel-identical behavior.

## Acceptance criteria

- Each default value is defined exactly once.
- The parity test passes before and after the refactor.
- No production code constructs `Settings()` just to obtain defaults.
- `docs/usage/config.md` is generated from the canonical defaults.
- Existing rendering tests pass unchanged, or are updated only where the
  renderer API intentionally changed.

## Risks and constraints

- **Persisted project JSON.** `OutputProfile.from_dict()` must keep tolerating
  stored profiles with missing keys. Do not rename or remove persisted keys.
- **Behavior must not change.** The refactor is structural; defaults and mapping
  must stay identical.
- **Test surface.** `tests/test_page_rendering.py`, `tests/test_layouts.py`,
  `tests/test_output_profile.py` and `tests/test_CalendarRenderer.py` construct
  `Settings` directly and will need updating with the API change.
- **Rollout.** Land the parity test first, then refactor in small commits so a
  regression is easy to isolate.

## Open questions

- Keep `Settings` as a deprecated adapter, or remove it completely?
- Should `docs/usage/config.md` document the per-project output profile, the
  renderer settings, or both?