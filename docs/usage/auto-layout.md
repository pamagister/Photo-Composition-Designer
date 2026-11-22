# Automatic collage layout

The automatic layout arranges the photos that are already on a page into a
full-bleed collage. It is the first entry in the new-project layout list and in
**Change layout**, labelled **Automatic (from photos)**. No template or slot
count has to be chosen up front: the grid is derived from the photos.

## How the geometry is chosen

1. Photos are grouped by orientation: portrait, square, then landscape. The
   input order is preserved inside each orientation class.
2. A deterministic top-down search splits the page into rows, columns or
   recursive rectangles. Each candidate is scored by how much each photo would
   have to be cropped to fit its cell, plus a fairness term that prevents a
   large photo from being squeezed into a sliver.
3. The result is a set of normalized slot rectangles that covers the collage
   content box exactly, with no overlaps.

The same photos and page geometry always produce the same layout. There is no
randomness and no time-based decision.

Typical results:

- One photo fills the whole collage area.
- Two photos split along the better axis for the canvas and photo orientation.
- One portrait plus two landscapes on a landscape page puts the portrait on
  one side and stacks the two landscapes next to it.

## Managing photos on an automatic page

* **Add photo** fills the first empty slot. When every slot is occupied, the
  page is reflowed for one additional photo.
* **Remove** clears a slot but leaves the grid untouched. The remaining cells
  keep their position and size.
* **Reflow** rebuilds the page with exactly one slot per assigned photo.
* **Remove empty slots** is the explicit cleanup for holes left by removals.

Cropping, replacement, swapping and the keyboard crop controls work exactly as
on static layouts.

## Content-aware importance

When object detection is enabled, the layout biases cell areas toward photos
with more relevant content. Detections for `person`, `cat`, `dog`, `horse`,
`cow` and `bird` contribute to a score. The score is capped and scaled by the
project's **Image score factor** setting:

```text
importance = 1 + min(detection score, cap) * image score factor
```

A value of `0` disables weighting and produces the plain geometric layout. If
the model or its detections are unavailable, every photo receives the neutral
value `1.0`, so automatic layouts still work without object detection.

## Distribution and page settings

Automatic pages do not have a fixed slot count. In the distribution page the
capacity of an automatic page is computed from the photo and page counts
(`photos / pages`), and the layout is regenerated from the photos each page
receives. The **Distribute all photos** and **Distribute the best photos** modes
always switch every page to the Automatic layout; **Respect current layouts**
keeps static pages as they are. **Extras → Reset layouts** rebuilds every page
as an Automatic layout while keeping the current photos and crops.

Changing the output profile (page size, DPI, spacing or the image score factor)
or rescanning a source directory regenerates the automatic snapshots for the
project. The existing preview cache keys change automatically because every
regeneration creates a new snapshot version and increments the page revision.

## Limits

* The automatic layout is not a free-form canvas editor. There is no free
  dragging, arbitrary resizing or rotation.
* Individual photos cannot override their slot geometry; use a static YAML
  layout when a precise composition is required.
* The engine is optimized for 1–30 photos per page. Larger sets are supported
  but take longer to search.
* Regeneration is deterministic but not incremental: every change writes a new
  automatic snapshot. Old snapshots remain in the workspace for traceability.