# Layout Catalogue Agent Notes

This directory contains the built-in YAML layout templates.

## Contract

- Coordinates are normalized to the page: `x`, `y`, `width`, `height` in `[0, 1]`.
- Slots must tile the page exactly: no uncovered area and no overlaps.
- Do **not** add spacing gaps to the YAML. `SlotAwareRenderer` creates the
  visible gutter from `layout.spacing` (mm) by insetting touching slot edges.
- Use `crop_mode: cover` unless a layout deliberately needs another mode.
- Every slot key must be unique.

A layout such as `four_quadrants.yaml` is correct even though the photos touch
in the YAML: the renderer adds the spacing afterwards.

## Tile template generation and validation

The helper at `scripts/layouts_helper.py` both validates layout YAML and
generates row-based templates.

Generate a layout from a column count per row and optional row height
percentages (normalized to 100%):

```bash
uv run python scripts/layouts_helper.py generate \
  --columns 4,3,5 --heights 30,40,30 \
  --key my_layout --name "My layout" --output path/to/my_layout.yaml --check
```

Omit `--heights` for equal row heights. Omit `--output` to print YAML to
stdout.

The built-in tile YAML files are generated from presets. Change
`BUILTIN_ROW_TEMPLATES` in `scripts/layouts_helper.py` instead of editing them
by hand, then run:

```bash
uv run python scripts/layouts_helper.py write-templates
```

### Tile template naming

Tile templates are named by row count, not by image count:

- `tiles_3_rows_4col`: 3 rows, 4 columns each.
- `tiles_3_rows_5col`: 3 rows, 5 columns each.
- `tiles_3_rows_mixed`: 3 rows with mixed columns, currently 3-4-5 and
  row heights 40% / 35% / 25%.
- `tiles_4_rows_5col`: 4 rows, 5 columns each.
- `tiles_4_rows_6col`: 4 rows, 6 columns each.
- `tiles_4_rows_mixed`: 4 rows with mixed columns, currently 6-7-5-6 and
  equal row heights.
- `tiles_5_rows_5col`: 5 rows, 5 columns each.
- `tiles_5_rows_6col`: 5 rows, 6 columns each.
- `tiles_5_rows_mixed`: 5 rows with mixed columns, currently 6-7-5-6-7 and
  equal row heights.

## Validation

```bash
uv run python scripts/layouts_helper.py validate --check
uv run python scripts/layouts_helper.py validate --path path/to/layout.yaml
```

The validator checks exact tiling (no gaps, no overlaps) and simulates the
renderer's pixel insets. To reproduce legacy failures caused by the old
`1e-9` neighbour tolerance:

```bash
uv run python scripts/layouts_helper.py validate --path old.yaml --neighbour-tol 1e-9
```

Relevant tests:

```bash
uv run pytest tests/test_layouts.py -q
```
