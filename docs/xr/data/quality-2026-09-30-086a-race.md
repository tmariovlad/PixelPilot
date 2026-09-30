# Still grading, 2026-09-30: APK 086a64aa (display-crop fix) at 640x480 "race" vs the old build's r480

Stills (private, not committed): new build `scripts/quest/out/quality_private/crop-086a-2026-09-30/`
(`full-race-086a.png`, `quality-2026-09-30-race-086a-{1,2}.jpg`, 19:48); old build
`scripts/quest/out/quality_private/s2-2026-09-30/` (`full-r480.png`, `quality-2026-09-30-s2-r480-1.jpg`, ~17:56).
Graded by a subagent against the fixed rubric (artefacts / sharpness / noise / exposure, 1–10). No people are described.

> **Main caveat: the new build has no live 640x480 still.** Its full screencap shows the layer at 640x480, but under
> **NO SIGNAL (3.3 s)**: `sig 0 pkt 0`, `640x480 0 fps 0.0 Mbit/s`. What it shows is the last decoded 640x480 frame
> held on screen. Both crops labelled "race" are **1280x720 at 120 fps**: -1 is `VIDEO STALLED (0.4 s)` at 0.6 Mbit/s
> and -2 is live at 8.0 Mbit/s. The air was therefore not in race mode when the crops were taken; it was probably
> back in its 720p default. This is [INFERRED] from the overlay lines; the air-side mode log was not checked. The
> geometry and edge checks below apply to the 640x480 layer and a held 640x480 frame. They do not show live
> 640x480 video.

## Method

- Every image was viewed at native brightness. The old r480 frame was also viewed with gain (x12), because it is
  almost black. Helper scripts (`geom.py`, `geom2.py`, `geom3.py`, `crops.py`) and resized or zoomed copies are in
  the session scratchpad, not the repo.
- Geometry: left eye only (x < 1832 of the 3664x1920 frame). A pixel counts as part of the layer when max(R,G,B) > 0,
  because the compositor background is exactly 0. For each build this gives the top edge y per column, the
  left/right edge x per row and the bottom edge y per column. The lens pre-distortion curves the edges (the outline
  is a pincushion), so screen extents are not the quad's 4:3 ratio. The check is therefore **edge-by-edge identity
  between builds**, not a measured ratio.
- The old build's bottom edge cannot be seen: the lower part of its scene is pure black (0), the same colour as the
  background. It was located through the stats panel instead. When no alert is shown, the panel's top edge sits
  exactly on the video's bottom edge (`LayerLayout.java:103`, `-(height/2 + statsH/2)`). The first text line starts
  a fixed image offset below the panel top (`XrStatsRenderer.java:54-66`). In the new frame, the gap between the
  bottom of the red headline band and the top of the first text line was measured at 6–8 px per 40-px column band.
  Subtracting that gap from the old frame's first-line top, band by band, gives the old video's bottom edge.
- Edges: zoomed crops (x2, gain x3) of the top and bottom edges of the new layer. Mean |row-to-row| vs
  |column-to-column| luma differences were compared inward from the bottom edge. Repeated rows would show as
  dy ≈ 0 with dx > 0.

## Overlay (read from the stills)

| Still | State | pkt | lost | fec | bad | decerr | size | fps | Mbit/s | hw decode |
|---|---|---|---|---|---|---|---|---|---|---|
| old full-r480 | live | 73 | 0 | 1 | 0 | 0 | 640x480 | 167 | 2.2 | 1.48 ms |
| old r480-1 (crop) | live | 75 | 0 | 0 | 0 | 0 | 640x480 | 167 | 2.2 | 1.47 ms |
| **new full-race-086a** | **NO SIGNAL 3.3 s** (held frame) | 0 | 0 | 0 | 0 | 0 | 640x480 | 0 | 0.0 | 1.43 ms |
| new race-086a-1 (crop) | VIDEO STALLED 0.4 s | 417 | 0 | 36 | 0 | 0 | **1280x720** | 120 | 0.6 | 1.47 ms |
| new race-086a-2 (crop) | live | 412 | 0 | 9 | 0 | 0 | **1280x720** | 120 | 8.0 | 1.49 ms |

[PROVEN: overlay text in each still.] Where decoding ran, lost = 0, bad = 0 and decerr = 0. The new build's
decoder showed no errors.

## Scores (1–10, higher is better)

| Still | Artefacts | Sharpness/detail | Noise | Exposure/contrast | Overall |
|---|---|---|---|---|---|
| old full-r480 / r480-1 (640x480 live) | 5 | 3 | 5 | 2 | 3 |
| new full-race-086a (640x480, held frame) | 5 | 3 | 5 | 6 | 4 |
| new race-086a-1 (720p, stalled, 0.6 Mbit/s) | 6 | 4 | 6 | 6 | 5 |
| new race-086a-2 (720p live, 8 Mbit/s) | 7 | 4 | 5 | 4 | 5 |

- **Artefacts.**
  - Old r480 and the new 640x480 frame: coarse 8–16 px blocking across the whole layer at ~2 Mbit/s. In the old
    frame it only shows under gain; in the new frame it shows under a x4 zoom.
  - The 720p crops show no visible blocking at native size.
  - No still has torn, frozen-half, corrupted or macroblock-band areas.
- **Sharpness.** All stills are soft: out-of-focus light blobs and motion blur. The 720p crops keep some edges on the
  props in the top-left corner. High-frequency energy in the centre window: old 0.17–0.20, new 640x480 0.70,
  720p 1.6–2.3. This measure tracks scene brightness at least as much as resolution.
- **Noise.** Mostly crushed into blocks at 640x480. The live 720p crop has visible grain in its dark areas.
- **Exposure.** The old frame is almost black: mean luma 3.2–3.5/255, max 28. The new frames are much brighter:
  mean ~45 (640x480 and 720p-2) and ~90 (720p-1, warm orange). The lighting or auto-exposure state was different,
  so exposure cannot be compared between the builds.

## Geometry, old vs new (left eye, 3664x1920 frame coordinates)

| | Old build, full-r480 (live) | New build 086a, full-race-086a (held frame) |
|---|---|---|
| Top edge (centre, x=860) | y = 431 | y = 431 |
| Top edge y at x = 360…1360 (11 columns) | 461 449 441 435 432 431 433 437 445 455 468 | **identical** |
| Right edge x at y = 450…1230 (14 rows) | 1222 1433 1441 1448 1453 1457 1460 1462 1462 1461 1459 1455 1450 1444 | **identical** |
| Left edge, rows where old is lit | 448 (y450) · 245 (y690) · 240 (y1050) · 244 (y1110) | **identical**; widest point 237 at y≈930, where the old frame is dark |
| Bottom edge (centre band x 560–1079) | not visible (black scene); from the panel anchor: 1384–1393 | 1384–1393 (measured) |
| Old bottom (from panel) − new bottom, per 40-px band | — | **0 to −4 px, mean −0.7** (13 bands) |
| Bounding box | x 240–1462, y 431–≈1393 | x 237–1462 (1226 px), y 431–1393 (963 px) |
| Screen ratio (distorted outline) | ≈1.27 | 1.273 |
| Position | centred horizontally at x ≈ 850, top at 431 | same |

- **The layer is the same size and position** [PROVEN: every measured top/right/left edge point is identical to the
  pixel. The bottom is INFERRED from the stats-panel anchor and agrees within 0–4 px].
- **Aspect.** The screen ratio of 1.27 is not the 4:3 of the quad, because the pincushion pre-distortion bends it. A
  cross-check from the same build: its 1280x720 layer (crop -2) has the same width (x ≈ 242–1458 at >30 % column
  coverage). At the centre column its height is ≈ 743 px (y 539–1282), which is 0.77 of the 640x480 layer's 963 px.
  The expected ratio for 16:9 vs 4:3 is 0.75 [INFERRED: difference within the distortion's non-linearity]. So the
  640x480 layer is 4:3 and the 720p layer is 16:9. No stretch or squash.
- The stats panel sits over the lower part of the new layer rather than under it. That is the alert placement
  (`LayerLayout.java:101-102`, bottom edge at 6 % of the height above the video's bottom) triggered by NO SIGNAL,
  not a geometry change. The measured banner top at y = 1181 fits that formula: 1393 − 0.227 × 963 ≈ 1175, within
  the distortion.

## Edge check (new build)

- **Bottom edge: clean.** Content stays continuous down to the cut, and the cut goes straight to black, following
  the layer's curved outline. There are no streaks, green/grey lines or repeated rows. Near the bottom,
  |dy| (0.3–0.5) ≥ |dx| (0.2–0.3), luma fades smoothly from 14 to 0 over y 1320–1380, and no row has dy ≈ 0 with
  dx > 0 [PROVEN: `geom2.py` output]. Rows 1340–1390 have mean RGB ≈ (12, 3, 13) → (0, 0, 0), a purple scene tone
  with no green or grey cast.
- **Top edge: clean.** The top rows are scene content (props, a warm wall) with ordinary 8–16 px blocking. No band
  and no garbage.
- **The old build** shows no band at the top either. Its bottom is black scene, so no band is visible there
  (matching the s2 report: r480 had no bottom smear; only r360 did,
  [quality-2026-09-30-s2-res360.md](quality-2026-09-30-s2-res360.md)).
- The same holds for the new build's 720p crops: clean top and bottom edges (at 1280x720 the coded size is also the
  visible size).

## Verdict

**Yes for geometry and edges, with one open point.** At 640x480 the new build draws a layer identical to the old
one: 4:3, same size and position to the pixel, no stretch, and no garbage band at the top or bottom. The frame it
shows looks normal. However, the only 640x480 image is a frame held under NO SIGNAL, and the "race" crops are 720p.
**Live 640x480 video on 086a has not been observed yet.** One recapture with the air confirmed in race mode (live
`640x480 167 fps` on the overlay) would close this.

## Limits

- The two builds were captured in different light and scene states: the old frame is almost black, the new frames
  are much brighter. Exposure and noise scores are therefore not comparable between the builds.
- The scene is static (bench, props in a corner, blurred light sources), so there is no motion to judge smear or
  sharpness on.
- There is only one full frame per build. The old bottom edge is inferred, not seen.
- The screencap is the compositor output after lens pre-distortion. Pixel extents are only comparable between
  captures with the same layer and FOV settings, which holds here: same top/right/left curves.
