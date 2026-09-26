# Move report: Quest / PixelPilotXr material ev300d → pixelpilot-xr (2026-09-26)

Goal: `c:/xampp/htdocs/ev300d` holds only Eachine EV300D / EV200D goggles work. Everything about the Meta Quest 2
and the PixelPilotXr app now lives in `c:/xampp/htdocs/pixelpilot-xr`. Nothing was committed (the coordinator commits).

## 1. What moved where

### Documentation (copied, compared with `cmp`, then the originals deleted)

| Old path (ev300d) | New path (pixelpilot-xr) | Check |
|---|---|---|
| `tasks/quest2-research-2026-09-26/00-INDEX-SYNTHESIS.md` | `docs/xr/research/2026-09-26-quest2/00-INDEX-SYNTHESIS.md` | cmp OK, then 1 link edited |
| `tasks/quest2-research-2026-09-26/01-latency-numbers-and-measurement.md` | `docs/xr/research/2026-09-26-quest2/01-latency-numbers-and-measurement.md` | cmp OK, then paths edited |
| `tasks/quest2-research-2026-09-26/02-apk-low-latency-options.md` | `docs/xr/research/2026-09-26-quest2/02-apk-low-latency-options.md` | cmp OK, then paths edited + note added |
| `tasks/quest2-research-2026-09-26/03-system-tweaks-cfw-status.md` | `docs/xr/research/2026-09-26-quest2/03-system-tweaks-cfw-status.md` | cmp OK, unchanged |
| `tasks/quest2-research-2026-09-26/04-compositor-latch-timing.md` | `docs/xr/research/2026-09-26-quest2/04-compositor-latch-timing.md` | cmp OK, unchanged |
| `tasks/quest2-research-2026-09-26/pixelpilot-xr-final-review.md` | `docs/xr/research/2026-09-26-quest2/pixelpilot-xr-final-review.md` | cmp OK, unchanged |
| `tasks/quest2-research-2026-09-26/tasks/session-checkpoint.json` (hook artifact) | `docs/xr/research/2026-09-26-quest2/tasks/session-checkpoint.json` | cmp OK, unchanged |
| `tasks/wsl-start-failure-2026-09-26.md` | `docs/xr/research/wsl-start-failure-2026-09-26.md` | cmp OK, unchanged |

### Reference clones (`ev300d/repos/` → `pixelpilot-xr/repos/`, ~325 MB)

All were Quest-only, so all of them moved, not just the kernel.

| Item | Origin | HEAD | How |
|---|---|---|---|
| `PixelPilot_quest/` | gpratas-pereira/PixelPilot_quest | `e605749` | `mv` (rename) |
| `openxr-spec-snippets/` | curl'd Khronos `.adoc` files (not a git repo) | n/a | `mv`, 15 entries before and after |
| `REMOVED-CLONES.txt` | record of the deleted `PixelPilot` + `LiveVideo10ms` clones | n/a | `mv`, md5 `8dbc98be…` unchanged |
| `ALVR/` | alvr-org/ALVR | `99d8948` | `cp -a` + `diff -rq` IDENTICAL, then `rm -rf` of the original |
| `FPVue_xr/` | gehee/FPVue_xr | `c0ccfba` | cp + diff IDENTICAL + rm |
| `Meta-OpenXR-SDK/` | meta-quest/Meta-OpenXR-SDK | `bbed2f2` | cp + diff IDENTICAL + rm (it had 8 dirty files; they were copied as-is) |
| `OpenXR-SDK-Source/` | KhronosGroup/OpenXR-SDK-Source | `3ed64d0` | cp + diff IDENTICAL + rm |
| `oculus-linux-kernel-quest2/` | facebookincubator/oculus-linux-kernel (blobless sparse clone) | `e8c2245` | cp + diff IDENTICAL + rm |

- Five directories failed to `mv` with "Permission denied" (Windows would not rename them), so they were copied, compared and then deleted.
- `pixelpilot-xr/.gitignore`: added `/repos/` at the end, matching the file's existing LF ending. `git check-ignore -v repos/ALVR` → `.gitignore:28:/repos/`. Nothing under `repos/` shows in `git status`.
- The note removed from ev300d `CLAUDE.md` about the kernel clone is still useful. Its content: "files are in the git tree but not checked out; read with `git show HEAD:<path>`, e.g. `techpack/display/msm/dsi/dsi_panel.c` for backlight timing". Whoever owns `pixelpilot-xr/CLAUDE.md` may want to add it there. `04-compositor-latch-timing.md` already says "read with `git show`, no checkout".

### Stays in ev300d on purpose

- `repos/AIT8428_CarDV_SDK_r5412/` is the EV200D DVR SDK.
- `tasks/cfw-research-2026-09-26/` is the EV200D CFW research. Its "PixelPilot" mentions are about the OpenIPC ground-station app driving the goggles over HDMI (e.g. "send 1280×720 from PixelPilot"). They are not about the Quest.
- `tasks/session-checkpoint.json` is ev300d's own hook artifact.
- `.playwright-mcp/` holds 37 transient browser console/page logs from the 2026-09-25/26 research sessions. They mix EV200D pages (rcgroups/banggood) with a few Quest pages (e.g. intofpv "quest3 as FPV goggles"). They are tool noise, not documentation, so they were left alone. The coordinator can delete the folder if wanted.

## 2. Links fixed inside the moved files

- `00-INDEX-SYNTHESIS.md:103`: `](../cfw-research-2026-09-26/00-INDEX-SYNTHESIS.md)` → `](c:/xampp/htdocs/ev300d/tasks/cfw-research-2026-09-26/00-INDEX-SYNTHESIS.md)`. The file is CRLF. Git Bash `sed -i` turned it into LF, so CRLF was restored with Python. Final size is 10121 bytes: the original 10095 plus exactly the 26 characters added to the link.
- `01-latency-numbers-and-measurement.md` (lines 57, 536, 538, 539) and `02-apk-low-latency-options.md` (lines 17–24): `C:/xampp/htdocs/ev300d/repos/` → `C:/xampp/htdocs/pixelpilot-xr/repos/`. Both files are LF and stayed LF.
- `02-apk-low-latency-options.md`: added a one-line "Path note (2026-09-26)" after the clone table. It says the clones moved, and that `PixelPilot` and `LiveVideo10ms` no longer exist on disk; their URL and commit are in `pixelpilot-xr/repos/REMOVED-CLONES.txt`.
- Relative mentions such as `repos/openxr-spec-snippets/…`, `repos/oculus-linux-kernel-quest2` and `repos/PixelPilot_quest/app/...` need no change. They now resolve from the pixelpilot-xr root.
- The only `ev300d` mentions left in the moved files are the cfw-research link above (correct: that file stays in ev300d) and the historical `cwd` inside `tasks/session-checkpoint.json`.

## 3. ev300d edits

`c:/xampp/htdocs/ev300d/CLAUDE.md` is LF and stayed LF. Changes:
- Removed the Quest 2 research line from "Documentation".
- Removed the `repos/oculus-linux-kernel-quest2/` line from "Layout".
- Replaced the two "Related project" lines (PixelPilot XR and the WSL incident) with one line: "All Meta Quest 2 / **PixelPilotXr** work (Quest research, the native OpenXR app, measurements, Quest repos) lives in `c:/xampp/htdocs/pixelpilot-xr/` (entry: `CLAUDE.md` there)."
- No other ev300d doc linked to the moved files (grep for `quest2-research|wsl-start` → 0).
- No empty folders are left. `tasks/` = `cfw-research-2026-09-26/` + `session-checkpoint.json`. `repos/` = `AIT8428_CarDV_SDK_r5412/`.

## 4. Verification

- (a) grep in ev300d (`CLAUDE.md README.md docs tasks tools`, `*.md`) for `quest|oculus|openxr|pixelpilot|horizon|alvr|fpvue|wsl-start`, ignoring "request/question":
  - `CLAUDE.md:25` is the single pointer line.
  - `cfw-research/00-INDEX-SYNTHESIS.md:76`, `04-hdmi-lcos-path-latency-levers.md:4` and `:251` mention the OpenIPC PixelPilot ground-station app in an EV200D context. They are incidental and correct.
  - No `quest|oculus|openxr` hits in `docs/ analysis/ ev200d/ firmware/ tools/ repos/AIT…`.
- (b) BFS link check from ev300d `CLAUDE.md` (script: session scratchpad `bfs.py`): reachable=7, `.md` files under `tasks/`+`docs/`=5, **unreachable=0, broken=0**.
- (c) Links in the moved files (`chk_moved.py`): 7 markdown links, **7 resolve, 0 broken**. Absolute paths in backticks: all exist except `pixelpilot-xr/repos/PixelPilot` and `pixelpilot-xr/repos/LiveVideo10ms`. Those clones had already been deleted before this move, which the path note explains.
- Reachability inside pixelpilot-xr: at the end of this move, the parallel agent's `pixelpilot-xr/CLAUDE.md` (lines 26–28) already links the quest2 synthesis, the WSL incident and this report. `docs/xr-quest.md` (lines 86 and 123) links the research too.

## 5. External references still pointing at the old ev300d paths (NOT edited, to update)

| File | Line | Old reference → new target |
|---|---|---|
| `c:/xampp/htdocs/openipc-low-latency-and-others-video/docs/DECISIONS.md` | 261 | `ev300d/tasks/quest2-research-2026-09-26/00-INDEX-SYNTHESIS.md` → `pixelpilot-xr/docs/xr/research/2026-09-26-quest2/00-INDEX-SYNTHESIS.md` |
| `c:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/hardware-research/07-meta-quest-2-display.md` | 3 | same → same |
| `c:/xampp/htdocs/openipc-low-latency-and-others-video/repos/tasks/research/47-quest2-compositor-bypass-deep-research.md` | 3 | same → same |
| `c:/xampp/htdocs/pixelpilot-xr/docs/superpowers/specs/2026-09-26-quest-openxr-viewer-design.md` | 5 | same → same (relative: `../../xr/research/2026-09-26-quest2/00-INDEX-SYNTHESIS.md`) |
| `c:/xampp/htdocs/pixelpilot-xr/docs/xr-quest.md` (owned by another agent) | 86 | already fixed by its owner: the link now points at `xr/research/2026-09-26-quest2/01-…`, and the old path is only mentioned as history |
| `C:/Users/vlad_/.claude/projects/c--xampp-htdocs-ev300d/memory/pixelpilot-xr-build-env.md` | 19 | `ev300d/tasks/wsl-start-failure-2026-09-26.md` → `pixelpilot-xr/docs/xr/research/wsl-start-failure-2026-09-26.md` |

Also consider moving the memory `pixelpilot-xr-build-env.md` itself (listed in ev300d `MEMORY.md`) to the pixelpilot-xr project memory, since it is Quest-only.

Searched: `openipc-low-latency-and-others-video/{docs,CLAUDE.md,repos/tasks}`, `pixelpilot-xr/{docs,CLAUDE.md,README.md}`, ev300d + pixelpilot-xr project memory, `~/.claude/skills`. The search covered `ev300d/tasks/quest2-research`, `ev300d/tasks/wsl-start-failure` and `ev300d/repos/<every moved clone>`. No references to the old `ev300d/repos/…` clone paths were found outside the moved files.
