# WSL2 start failure `Wsl/Service/CreateInstance/E_FAIL`: 2026-09-26 (PC-VLAD)

## TL;DR

- **Root cause [PROVEN]: drive C: was full.** At the first measurement it had **26,886,144 bytes (about 26 MB) free**, and a moment later `Get-PSDrive` showed `C Free 0.00 GB`. In the same minutes `tr` failed with `No space left on device` and `usbipd list` crashed with `Unhandled exception`. With no free space, WSL could not bring the VM or disks up, so `Error code: 6, failure step: 2`, `E_FAIL`.
- **Fix:** no config change was needed. Once about 1 GB of C: came free, `wsl.exe -d Ubuntu-22.04 -- echo alive` → **`alive`** [PROVEN, run twice]. The idle Gradle 8.7 daemon of pixelpilot-xr was also stopped (1.5 GB commit) to slow the growth of the pagefile.
- **⚠️ The state is still FRAGILE:** C: has **0.2–0.4 GB free** at the end. The next heavy write (cmake/NDK build, pagefile growth) will reproduce the error. Space must be freed on C: (see "Recommendations"). The user decides; nothing was deleted.

## Diagnosis (commands + output)

| Check | Result | Tag |
|---|---|---|
| `hostname` | `PC-VLAD` (run locally, no SSH) | PROVEN |
| Free C: | 26 MB → 0.00 GB → 1.17 GB → 1.04 GB → 0.21 GB → 0.395 GB (it fluctuated during the session) | PROVEN (`Get-PSDrive C`, `cmd dir` = `210,640,896 bytes free`) |
| Commit charge | 95,147 MB / limit 113,151 MB → later 94,699 / **115,015** (the limit went UP = the pagefile grew during the session) → at the end 92,905 / 114,809 | PROVEN (`Get-Counter \Memory\*`) |
| Pagefile | `C:\pagefile.sys` **50.66 GB**, system-managed (`AutomaticManagedPagefile=True`), alloc 50,010 → 51,668 MB during the session | PROVEN (`Win32_PageFileUsage`) |
| Services | `WslService` Running/Automatic, `vmcompute` Running, `hns` Running. `LxssManager` does not exist (normal on the Store WSL, replaced by WslService) | PROVEN |
| WSL | `wsl --version` = **2.7.14.0**, kernel 6.18.33.2-2. Default = Ubuntu-22.04 | PROVEN |
| vmmem | not running at the start (VM down). After the fix `vmmemWSL` is about 0.9 GB | PROVEN |
| `usbipd list` | first attempt: `Unhandled exception` (disk full). Second: **NO device is Attached** (4-3 USB Mass Storage = *Shared*, the rest *Not shared*) | PROVEN |
| Event Viewer | not checked separately. The cause was already proven by the disk-full state + the start working again after space came free | — |

### Where the space on C: goes [PROVEN: `Get-Item`/`Measure-Object`]

| Item | Size |
|---|---|
| `C:\pagefile.sys` (system-managed, grown by the high commit charge) | **50.7 GB** |
| Ubuntu-22.04 `ext4.vhdx` (LastWrite 12:56:50 today) | **69.75 GB** (inside: 68 GB used, of which `/home/vlad` 43 GB, `/tmp` **13 GB**, `/usr` 12 GB) |
| Ubuntu-20.04 `ext4.vhdx` (LastWrite 12:40 today) | 26.56 GB |
| kali-linux / Arch vhdx | 5.39 / 2.3 GB |
| `C:\Users\vlad_\Downloads` | 28.6 GB |
| `C:\Users\vlad_\AppData\Local\Android` (SDK/NDK) | 14.2 GB |
| `C:\Users\vlad_\AppData\Local\Temp\claude` (scratchpads of other sessions; `c--xampp-htdocs-electro` = 4.6 GB, `bash-edit-diff` = 0.84 GB) | 6.7 GB |
| `C:\Users\vlad_\.gradle` / `.cache` / `.android` | 5.3 / 4.6 / 1.2 GB |
| `MEMORY.DMP` / `hiberfil.sys` | none (only 2 minidumps of ~5 MB from the 09-24 BSOD) |

`/tmp` inside Ubuntu-22.04 (13 GB): `fifo_grc_uchar_static` 2.5G, `android-sdk-dummy` 2.1G, `magisk_byd_build` 1.6G, `fifo_grc_short_static` 1.3G, `fifo_grc3` 1.1G. Today's cmake build (`/tmp/ppxr-tests`) = only 17 MB, so **the build itself did NOT fill the disk** [PROVEN: `du`]. What did fill it [INFERRED]: a C: that was already close to 0 plus the system-managed **pagefile** growing under a commit charge of about 95 GB (visible live: the commit limit rose by 1.8 GB during the session while free C: fell by about 0.8 GB). The ~1 GB that came free between the failure and the fix most likely came from a process that deleted temp files (a build/Gradle finishing) [SPECULATION: the writer was not caught; a 15 s write-rate sample showed no active large writer].

### Who holds the commit charge (about 93–95 GB of 64 GB physical RAM) [PROVEN: `Get-Process` grouped]

`node` ×204 = 18.0 GB · `python` ×94 = 14.7 GB (one python PID 54168 alone = 5.17 GB, started at 02:07) · `Code` ×47 = 12.7 GB · `java` ×11 = 9.6 GB · `claude` ×8 = 5.1 GB · `chrome` ×42 = 4.9 GB · `cmd` ×199. The hundreds of node/python/cmd processes are most likely MCP servers left over from the many Claude/VSCode sessions [SPECULATION: command lines not checked].

`Win32 error 299` (ERROR_PARTIAL_COPY) at the Git Bash fork (`child_copy: cygheap read copy failed`) fits the same memory/pagefile pressure [INFERRED].

## Actions taken

1. `wsl.exe -d Ubuntu-22.04 -- echo alive` after about 1 GB came free on C: → `alive` (plus the pre-existing warning about `sparseVhd`).
2. `cd C:\xampp\htdocs\pixelpilot-xr && JAVA_HOME='C:\Program Files\Java\jdk-17' ./gradlew --stop` → `1 Daemon stopped` (the Gradle **8.7** daemon, PID 14596, 1.52 GB private, idle: CPU delta 0 s over 10 s).
   - Other idle Gradle daemons **left running** (other projects, outside the allowed scope): 8.4 (PID 54076, 1.28 GB), 9.2.0 (PID 15804), 7.4 (PID 26060). 3 Kotlin daemons (idle) + 4 SonarLint JVMs (up to 1.9 GB) also still run.
3. Re-verified at the end: `alive`, free C: 0.395 GB, commit 92,905 / 114,809 MB.
4. **NOT done:** `wsl --shutdown` (not needed), restarting WslService, rebooting, editing `.wslconfig`, unregister/reset, deleting any file.

## The `.wslconfig` warning: `Unknown key 'wsl2.sparseVhd'`

[PROVEN: WSL 2.7.14 reports the key as unknown at line 5] so **`sparseVhd=true` under `[wsl2]` has NEVER taken effect**. The vhdx files do not shrink by themselves. That explains why Ubuntu-22.04 has reached 69.75 GB. In WSL 2.x the key lives under the **`[experimental]`** section (`[experimental]` + `sparseVhd=true`) [INFERRED: Microsoft WSL config docs. Only the "unknown under [wsl2]" part was verified live]. I did NOT edit the file. The proposed change: move the line `sparseVhd=true` under a new `[experimental]` section. It only affects distros created after the change. For the existing ones: `wsl --manage Ubuntu-22.04 --set-sparse true` (with the distro stopped), then `sudo fstrim -av` inside the distro.

## Recommendations (in order of impact vs risk; each is the user's decision)

1. **Free space on C: now.** The quickest, lowest-risk sources: `Downloads` (28.6 GB), old scratchpads in `AppData\Local\Temp\claude\c--xampp-htdocs-electro` (4.6 GB, from other sessions), `/tmp` inside Ubuntu-22.04 (13 GB, but it only returns space to C: after sparse+fstrim or `Optimize-VHD` as admin).
2. **Lower the commit charge** (the pagefile only shrinks at reboot, but at least it stops growing): close the stale MCP servers/sessions (204 node, 94 python, 199 cmd), stop the remaining idle Gradle daemons (`gradlew --stop` in the projects with Gradle 8.4 / 9.2.0 / 7.4), and check python PID 54168 (5.2 GB).
3. **Fix `sparseVhd`** (see above), so the vhdx files return space automatically.
4. Optional: after a reboot the system-managed pagefile returns to its normal size. Consider a fixed cap (e.g. 16–32 GB) if the high commit is recurring.

## Final verification

```
$ MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- echo alive
wsl: Unknown key 'wsl2.sparseVhd' in C:\Users\vlad_\.wslconfig:5
alive
FreeC_GB=0.395
committed bytes = 92905 MB ; commit limit = 114809 MB ; pagefile alloc=51668MB
```
Ubuntu-22.04 is left **Running** (started by the test). No usbip device was affected.
