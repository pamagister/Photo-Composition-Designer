# Command line interface

The `photo-composition-designer` command manages projects in the local SQLite
workspace. Running it without arguments starts the local web editor. Supplying a
command runs the project-oriented CLI instead.

Run it through `uv` inside the repository:

```bash
uv run photo-composition-designer --help
```

All commands except `gui` and `doctor` take a project ID. The workspace file and
cache live under the platform data directory; set `PCD_DATA_DIR` and
`PCD_CACHE_DIR` to isolate a run.

## Commands

| Command | Purpose |
|---|---|
| `gui` | Start the local web editor. |
| `scan` | Reconcile a project's source inventory. |
| `distribute` | Preview or apply a photo distribution proposal. |
| `render` | Render a project's pages to PNG and optionally PDF. |
| `export` | Render pages and always write a combined PDF. |
| `duplicate` | Copy a project, including pages, layouts and assignments. |
| `doctor` | Check workspace paths, schema, sources, photos and profiles. |

## `gui`

```bash
uv run photo-composition-designer
uv run photo-composition-designer gui
uv run photo-composition-designer gui --open-browser
uv run photo-composition-designer gui --host 0.0.0.0 --port 8767 --log-level info
```

Options: `--host` (default `127.0.0.1`), `--port` (default `8767`),
`--log-level` (default `info`) and `--open-browser`. Calling the command without
arguments is the same as the explicit `gui` command. With `--open-browser`, the
command opens the web UI in the default browser once the local server accepts a
connection.

## `scan`

```bash
uv run photo-composition-designer scan 1
uv run photo-composition-designer scan 1 --source-root-id 3
```

Scans the active source root, or the root given by `--source-root-id`, and
records added, updated and unavailable photos. Source files are read only.

## `distribute`

```bash
uv run photo-composition-designer distribute 1 --dry-run
uv run photo-composition-designer distribute 1 --strategy date_aware
uv run photo-composition-designer distribute 1 --strategy random --seed 42
```

Strategies are `equal` (default), `random` and `date_aware`. `--dry-run`
prints the proposal counts and per-page photo counts without changing
assignments.

## `render` and `export`

```bash
uv run photo-composition-designer render 1 --output-dir ./out
uv run photo-composition-designer render 1 --no-pdf
uv run photo-composition-designer export 1
```

Both commands use the project's stored output profile and page order. `render`
writes PNG pages and, by default, a combined PDF; `export` always writes the
PDF. Without `--output-dir` the output goes to
`<data directory>/exports/project_<id>`.

## `duplicate`

```bash
uv run photo-composition-designer duplicate 1
uv run photo-composition-designer duplicate 1 --name "Calendar 2028"
```

The copy is independent: pages, layouts, assignments, source roots, inventory
and output profile are copied, while the original project is unchanged.

## `doctor`

```bash
uv run photo-composition-designer doctor
```

Reports workspace paths, schema version mismatches, missing source roots,
missing photo files, unavailable assignments, cache directories and invalid
output profiles. It exits with status `1` when a blocking error is found and
does not modify project data.
