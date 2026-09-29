# Quality grade 2026-09-29: FRZ_on (set B) vs FIF_on (set A)

Stills: `scripts/quest/out/quality_private/quality-2026-09-29-FRZ_on-{1..12}.jpg` (set B) and
`quality-2026-09-29-FIF_on-{1..10}.jpg` (set A). All 1253x1171 crops of the Quest 2 left-eye view.
Graded by eye with the fixed rubric (scores 1-10, 10 = best). Artefact source: **enc** = encoder
(uniform softness/blockiness everywhere), **link** = localised macroblock damage / smear from lost
packets, **opt** = optical (defocus, motion blur, flare) and not a video-chain artefact.

Supporting measurement (script run this turn, PIL, greyscale mean absolute difference between
consecutive stills, and max brightness of the band y=900-970 under the video where the overlay sits):

| Set | Consecutive-still diff | Overlay band max |
|-----|------------------------|------------------|
| B FRZ_on | 1.63-2.84 on every pair (no two stills identical) | 59-70 on all 12 (no text: overlay text reaches ~250) |
| A FIF_on | 0.00, 0.00, 0.34 for 1→2→3→4 (frozen), then 2.6-8.5 | 66 for stills 1-4 (overlay drawn higher, inside the picture), 250-253 for 5-10 |

[PROVEN: the script output above] So in set B **the stats overlay is not present in any still**
(it was not rendered, or the crop missed it), and **no two set-B stills are the same frame**, so no
capture landed inside a hold longer than the ~3 s capture interval. Short holds between captures
cannot be seen in stills.

## Set B: FRZ_on (16 Mbit/s, MCS7, FEC 4/8, drop-until-keyframe + keyframe request)

Scene for all 12: indoor, low light, warm artificial light; camera static on a desk; large dark
out-of-focus foreground object fills the lower ~40 % of the frame; one moving subject in the
mid-ground; bright wall and a lamp near clipping on the right.

| Still | Artefacts | Sharpness | Noise | Exposure | Overall | Overlay (lost / fec / fps / Mbit/s / sig / headline) | Artefact source |
|-------|-----------|-----------|-------|----------|---------|------------------------------------------------------|-----------------|
| 1 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay in the still) | none visible; foreground blur = opt; mild softness in dark areas = enc |
| 2 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 3 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 4 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 5 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 6 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 7 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 8 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 9 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |
| 10 | 9 | 5 | 6 | 5 | 7 | unreadable (no overlay) | subject motion blur = opt; no blocks |
| 11 | 9 | 5 | 6 | 5 | 7 | unreadable (no overlay) | subject motion blur = opt; no blocks |
| 12 | 9 | 6 | 6 | 5 | 7 | unreadable (no overlay) | as 1 |

No macroblock damage, smear or bands in any of the 12 stills. The 9 (not 10) reflects the slight
compression softness in the dark foreground and dark chair, which is uniform and would be there with
lost=0 (encoder-type) [INFERRED: uniform across all 12 stills, no localised edge].

**Means (n=12):** artefacts **9.0**, sharpness 5.83, noise 6.0, exposure 5.0, overall **7.0**.

## Set A: FIF_on (30 Mbit/s, truncated frames fed to decoder, no keyframe request, walking)

Scene for all 10: same home interior, low light; camera tilted ~60°; strong purple horizontal flare
band across the left half (lens/light, not codec); left third very dark.

| Still | Artefacts | Sharpness | Noise | Exposure | Overall | Overlay (lost / fec / fps / Mbit/s / sig / headline) | Artefact source |
|-------|-----------|-----------|-------|----------|---------|------------------------------------------------------|-----------------|
| 1 | 6 | 4 | 5 | 4 | 3 | lost 0 / fec 0 / 0 fps / 0.0 / sig 0 / **NO ADAPTER - plug in the RTL8812AU** | frozen last frame; small grey/purple blocks near the top (window/plant) and faint block edges on the right wall = link (damage already in the held frame) |
| 2 | 6 | 4 | 5 | 4 | 3 | same as 1, NO ADAPTER | identical frame to 1 (diff 0.00) |
| 3 | 6 | 4 | 5 | 4 | 3 | same as 1, NO ADAPTER | identical frame to 2 (diff 0.00) |
| 4 | 6 | 4 | 5 | 4 | 3 | lost 0 / fec 0 / 0 fps / 0.0 / sig 0 / **NO SIGNAL (25.8 s)** | same held frame (diff 0.34 = headline text change) |
| 5 | 2 | 3 | 4 | 4 | 2 | lost 12 / fec 23 / 44 fps / 12.7 / sig 67 / none | heavy link damage: macroblock grid over the centre and right wall, green blocks lower left, smeared blocks around the window and bright area |
| 6 | 8 | 5 | 5 | 4 | 6 | lost 9 / fec 17 / 87 fps / 29.2 / sig 72 / none | essentially clean; small blocky patch at the top (window corner) = link, minor; left-side blur = opt (motion) |
| 7 | 7 | 5 | 5 | 4 | 6 | lost 13 / fec 16 / 89 fps / 29.4 / sig 71 / none | small block patches at the top-left (near the window/plant) = link; rest clean |
| 8 | 7 | 5 | 5 | 4 | 6 | lost 3 / fec 17 / 84 fps / 27.3 / sig 73 / none | one small grey block at left of the table and one small coloured block mid-frame = link |
| 9 | 8 | 5 | 5 | 4 | 6 | lost 5 / fec 16 / 72 fps / 23.6 / sig 72 / none | no visible blocks; motion smear on the left = opt |
| 10 | 3 | 3 | 4 | 4 | 3 | lost 16 / fec 18 / 80 fps / 25.8 / sig 73 / none | heavy link damage: macroblock mess in the centre (window/floor region), grey blocks on the right wall, green blocks lower left |

**Means, all 10:** artefacts **5.9**, sharpness 4.2, noise 4.8, exposure 4.0, overall **4.1**.
**Means, working link only (stills 5-10, n=6):** artefacts **5.83**, sharpness 4.33, noise 4.67,
exposure 4.0, overall **4.83**.

## Comparison (indicative only)

| | Set B FRZ_on (n=12) | Set A FIF_on, working link (n=6) |
|---|---|---|
| Stills with any visible link artefact | **0 / 12** | **4 / 6** (5, 7, 8, 10) |
| Stills with heavy link damage | 0 / 12 | 2 / 6 (5, 10) |
| Mean artefact score | 9.0 | 5.83 |
| Mean overall score | 7.0 | 4.83 |

Set B shows fewer link artefacts per still with a working link: none in 12 stills, against 4 of 6 in
set A (2 of them heavy). This is consistent with what FRZ is designed to do (hold the last good frame
instead of decoding damaged slices) [INFERRED: stills + app settings as given].

**The conditions differ, so this is not an A/B of the setting alone:**
- Bitrate 16 vs 30 Mbit/s: at 30 Mbit/s each frame spans roughly twice the packets, so a given
  packet-loss rate hits more frames [INFERRED].
- Set A camera was moving (walking, tilted view); set B camera was static on a desk. With a static
  scene P-frames are small and damage propagates less visibly; motion makes smeared macroblocks much
  more visible [INFERRED].
- Set B has **no overlay in any still**, so its lost/fec/fps/Mbit/s are unknown: it is not shown that
  set B had lost>0 at all. Set A's working-link stills all had lost 3-16 per stats window.
- FRZ trades damage for freezes. A still cannot show a freeze unless two stills are identical; none are
  (diffs 1.6-2.8), but holds shorter than the ~3 s capture interval are invisible here. The cost of FRZ
  (freeze count/duration, fps dips) needs the overlay/PPXR_STATS fps and a same-conditions run.
- Set A stills 1-4 are an outage (NO ADAPTER / NO SIGNAL 25.8 s, 0 fps), not a quality sample; they are
  excluded from the working-link means.

A fair comparison needs both modes at the same bitrate, same (static or same-motion) scene, overlay
visible, alternated N>=2 per state.

## Scene limits (cap scores regardless of the link)

- **Low light, warm tungsten light:** both sets. Dark regions crush to black, bright wall and lamp near
  clipping; exposure capped at ~4-5 and noise at ~5-6 whatever the link does.
- **Set B:** a large out-of-focus foreground object fills ~40 % of the frame (optical defocus, not
  codec), and the scene is low-texture (plain walls). Sharpness capped at ~6. The static camera also
  makes link damage less likely to be visible.
- **Set A:** strong purple flare band across the left half, heavy camera motion blur from walking, very
  dark left third, tilted framing. Sharpness capped at ~5 even on clean stills.
- Stills are photographs of the headset view (lens distortion, vignetting at the edges), so fine detail
  is below what the decoder actually produced.
