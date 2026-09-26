# Doc restructure report (2026-09-26)

Back to [CLAUDE.md](../../CLAUDE.md) · [entry guide](../xr-quest.md)

Goal: make this repo the single, complete home of the Quest work, navigable from a root `CLAUDE.md`.
Reorganisation only: the dated result sections of `docs/xr-quest.md` were moved **verbatim** (only heading level
and relative links changed). Nothing was committed (the coordinator commits).

## New tree (files this restructure owns)

```
CLAUDE.md                              NEW  root of the doc tree: what the fork is, doc tree, working rules
docs/xr-quest.md                       KEPT (same path) entry guide: overview, build/install, use, levers,
                                            smoke checklist, measuring, "Results and deep dives" index, open questions
docs/xr/decoder-levers.md              NEW  moved: first on-device results, key isolation, clean-stream recheck,
                                            codec/component/resolution
docs/xr/compositor-phase.md            NEW  moved: compositor phase measured, phase lock (incl. "Known issue" hot-plug)
docs/xr/real-link.md                   NEW  moved: first real link (APFPV vs wfb, keys, link id, picture order)
docs/xr/g2g-budget.md                  NEW  moved: G2G budget per branch
docs/xr/troubleshooting.md             NEW  build traps, Horizon OS quirks, app/adapter/link problems
docs/xr/data/*.csv                     MOVED with git mv (5 files, names unchanged)
docs/xr/RESTRUCTURE-REPORT-2026-09-26.md  this file
```

Owned by the parallel agents and only linked from here: `docs/xr/research/**` (synthesis, WSL incident,
MOVE-REPORT) and `scripts/quest/**`.

## What moved where (source = `git show HEAD:docs/xr-quest.md`)

| Old lines | Old section | New home | Heading change |
|---|---|---|---|
| 1-94 | title … Measuring | `docs/xr-quest.md` (unchanged text) | — |
| 95-114 | First on-device results | `docs/xr/decoder-levers.md` | stays `##` |
| 116-136 | Which low-latency key … (key isolation) | `docs/xr/decoder-levers.md` | `###` → `##` |
| 138-151 | Clean-stream recheck | `docs/xr/decoder-levers.md` | `###` → `##` |
| 153-170 | Codec, component and resolution | `docs/xr/decoder-levers.md` | `###` → `##` |
| 172-216 | Compositor phase, measured | `docs/xr/compositor-phase.md` | `###` → `##` |
| 218-252 | Phase lock (+ "Known issue" hot-plug crashes) | `docs/xr/compositor-phase.md` | `###` → `##` |
| 254-280 | First real link | `docs/xr/real-link.md` | `###` → `##` |
| 282-310 | G2G budget per branch | `docs/xr/g2g-budget.md` | `###` → `##` |
| 312-319 | Open questions | `docs/xr-quest.md` (stays) | — |

Each topic file starts with a `#` title, a navigation line (guide, sibling topics, troubleshooting, `data/`,
`CLAUDE.md`), a "moved verbatim" note and a 1-2 line intro. In `docs/xr-quest.md` the moved sections are
replaced by **"Results and deep dives"**: per topic a link (plus section anchors) and a short summary with the
headline numbers (LL+OR 1.56 / 1.79 / 2.32 ms; latch ~2.1–2.2 ms before vsync, latch → light ~11.9 ms,
119.70 Hz, phase lock −2.4 ms; picture order ~96 → ~1.4 ms; G2G ≈ 30.7 ms), links to the 5 CSVs and to the
research synthesis. A dated "Update" line under the old status line says the mode has since run on a Quest 2
(the original status line is kept as written).

## Link fixes

- CSV links in moved text: `](measurements-…csv)` → `](data/measurements-…csv)` (5 links).
- Script links in moved text: `](../scripts/quest-latch/…)` → `](../../scripts/quest-latch/…)` (7 links).
- `docs/xr-quest.md` Measuring: the plain path `c:/xampp/htdocs/ev300d/tasks/quest2-research-2026-09-26/01-latency-numbers-and-measurement.md`
  → link [research report 01](research/2026-09-26-quest2/01-latency-numbers-and-measurement.md) (old path kept as "moved from").
- `docs/xr-quest.md` Open questions: `(see "Compositor phase, measured")` → link to `xr/compositor-phase.md#compositor-phase-measured-2026-09-26`.
- `docs/xr/compositor-phase.md` intro links "research report 04" to `research/2026-09-26-quest2/04-compositor-latch-timing.md`.
- Code comments (comment text only, no code; files kept LF as they were):
  - `app/videonative/src/main/java/com/openipc/videonative/LatencyExperiments.java` lines 42, 83, 86, 90 →
    `docs/xr/compositor-phase.md` ("Phase lock"), `docs/xr/decoder-levers.md` ×2, `docs/xr/real-link.md`.
  - `app/videonative/src/test/java/com/openipc/videonative/LatencyExperimentsTest.java` lines 84, 92, 101 →
    `docs/xr/decoder-levers.md` ×2, `docs/xr/real-link.md`.
  - `app/xr/src/main/java/com/openipc/xr/PhaseMeter.java` line 7 → `docs/xr/compositor-phase.md`.
- Left unchanged on purpose: `README.md:111` (links the entry guide, whose path is kept) and
  `scripts/quest-latch/rtp_pace.py:104` (`see docs/xr-quest.md` for Wi-Fi power save: the guide's index still
  carries that fact; editing scripts was out of scope).

## Troubleshooting sources

Written out in full (no previous home in the repo): JDK 25 vs 17, `local.properties` backslashes, non-recursive
submodules (cites `.github/workflows/build.yml:21-26`), "Could not move temporary workspace", C: full → WSL
`E_FAIL` (links the WSL incident report), Ubuntu-20.04 without CMake, emulator notes (`-gpu host`, UDP redir),
"Controller required" (cites `app/xr/src/main/AndroidManifest.xml:16-22`), Guardian/proximity commands (links
research report 03), USB-permission dialog blocking immersive launch, `cmd wifi connect-network` ignored,
`USB_DEVICE_ATTACHED` opening the `.xr` app's 2D `VideoActivity` (cites `app/src/main/AndroidManifest.xml:52-72`).
Sources for the build/emulator items: the session's build-environment notes (ev300d project memory
`pixelpilot-xr-build-env`). The device quirks come from the coordinator's brief (observed 2026-09-26); no log of
them is stored in the repo.

**Linked only** (single source of truth stays in the measured section): 0.21.0 crash while asleep (guide, Build
and install), RTL8812AU hot-plug crashes (compositor-phase.md, end of Phase lock), Wi-Fi power save and
`xr_thread_hints` (decoder-levers.md, first on-device), no `c2.android.*` and multi-slice H.264 (decoder-levers.md,
codec section), APFPV/keys/link id and the ~96 ms picture-order delay (real-link.md), 120 Hz setting (guide, smoke
checklist), flip toggle (guide, Use), LDR rig through the lenses (guide, Measuring).

## Verification (script run after the edits)

Script: a temporary `verify_docs.py` in the session scratchpad (BFS, link and anchor resolution, number sets).

1. **BFS from `CLAUDE.md`** over `[..](x.md)` links: all 17 `.md` files under `docs/` (this report included) are reachable, including the
   6 research files, `MOVE-REPORT-2026-09-26.md` and the WSL incident (all three linked directly from `CLAUDE.md`).
   Unreachable: none.
2. **Relative links** in `CLAUDE.md`, `docs/xr-quest.md` and `docs/xr/*.md` (files and `#anchors`, GitHub slug
   rules; code blocks and inline code skipped): 134 resolve, **0 broken**. Pending: `CLAUDE.md → scripts/quest/README.md`
   (the scripts agent writes it; the folder `scripts/quest/` already exists with its scripts).
3. **Numbers** (`\d+\.\d+`): old `docs/xr-quest.md` has 180 distinct numbers; the union of the new guide + 4 topic
   files has 181. **Missing: none**; no number occurs fewer times than before. Line-level diff: 19 old lines are not
   verbatim in the new files, and all 19 are expected: 7 headings promoted `###` → `##`, 10 lines whose relative links
   were re-rooted, the Measuring protocol path turned into a link, and the Open-questions line that got a link.

## Notes for the coordinator

- Line endings: `core.autocrlf=true` and the index is LF everywhere, so the commit is LF regardless. The new and
  rewritten docs were written CRLF (like `README.md` in the working tree); the three Java files were LF in the
  working tree and stay LF.
- The CSV moves are already staged (`git mv`); everything else is unstaged.
- The research files (other agent) still cite old guide sections in plain text, e.g. `00-INDEX-SYNTHESIS.md:74,85,90,97`
  and `04-compositor-latch-timing.md:14` (`docs/xr-quest.md §"Phase lock"` / `§"First real link"` /
  `§"G2G budget…"` / `§"Compositor phase, measured"`). They still resolve through the guide's index. To point them
  straight at `docs/xr/compositor-phase.md`, `real-link.md` and `g2g-budget.md`, the owner of those files must edit them.
- `scripts/quest/mkcsv.py` (other agent) takes the CSV output directory as an argument or `env.OUT_DIR`; new CSVs
  belong in `docs/xr/data/`.
