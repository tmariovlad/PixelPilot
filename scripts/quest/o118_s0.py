"""OpenIPC O118 S0 decoder tests on the Quest, air off: GDR (intra-refresh) streams with no IDR, replayed over Wi-Fi
(openipc repo repos/tasks/intra-refresh-slices-2026-09-29/R4-quest-decoder.md, table T1-T5).
Per run: relaunch XR with the given prefs, replay one or more streams back to back, then read the app's log (epoch
timestamps): each 'Configuring decoder' (a decoder (re)built), the first output after it (the output format change),
the largest 'N Decoded Frames', decode ms, errors.
- T1 cold start without an IDR: the *_noidr.rtp cut (starts at an SPS before a non-IDR frame, no IDR anywhere).
  Pass = output within ~1-2 frames of the configure, and frames decoded ~ frames sent. Fail = 0 outputs.
- T4 multi-slice: the 4-slice stream with au_aggregation off vs on (decode ms, output count).
- T5 codec switch under GDR: the H.264 cut then the H.265 cut in one run: rebuild -> first output.
The user's prefs are backed up first and restored at the end (set_prefs keeps only gs.key).
Usage: python3 o118_s0.py <out.txt>   (Quest awake: guardian_pause 1 + prox_close; air off)
"""
import os
import re
import subprocess
import sys
import time

import quest_adb as q
import quest_env as env

N = 3
FRAME_60 = 1000 / 60


def replay(*streams):
    for s in streams:
        subprocess.run([sys.executable, os.path.join(env.HERE, "rtp_play.py"), env.stream_path(s), str(env.VIDEO_PORT),
                        "1", env.QUEST_HOST], capture_output=True, env={**os.environ, "KEEPAWAKE": "1"})


def run(label, prefs, *streams):
    q.adb("shell", "am", "force-stop", env.PKG)
    q.set_prefs(prefs)
    q.adb("logcat", "-c")
    q.prox_close()
    q.start_xr(wait=True)
    time.sleep(4)
    replay(*streams)
    time.sleep(2)
    log = q.adb("logcat", "-d", "-v", "epoch", "-s", "VideoDecoder:*")
    events = []
    for line in log.splitlines():
        m = re.match(r"\s*(\d+\.\d+)\s", line)
        if not m:
            continue
        t = float(m.group(1))
        if "Configuring decoder" in line:
            comp = (re.findall(r"Configuring decoder (\S+)", line) or ["?"])[0]
            events.append(("config", t, comp))
        elif "Actual Width and Height in output" in line:
            events.append(("output", t, line.split("output", 1)[1].strip()[:40]))
    frames = [int(x) for x in re.findall(r"N Decoded Frames:([0-9]+)", log)]
    dec = [float(x) for x in re.findall(r"\| Decoding:([0-9.]+)", log)][1:]
    errs = len(re.findall(r"Input buffer too small|AMediaCodec_(?:configure|start) failed|FATAL|error", log, re.I))
    gaps = []
    for i, (kind, t, info) in enumerate(events):
        if kind != "config":
            continue
        nxt = next(((t2, inf2) for k2, t2, inf2 in events[i + 1:] if k2 == "output"), None)
        gaps.append((info, round((nxt[0] - t) * 1000, 1) if nxt else None, nxt[1] if nxt else "-"))
    res = {"label": label, "configs": gaps, "frames": max(frames) if frames else 0,
           "decode_ms": round(sum(dec) / len(dec), 2) if dec else None, "errors": errs}
    print(f"{label:34s} frames={res['frames']:5d} decode_ms={res['decode_ms']} errors={errs} "
          f"config->output ms: {[(c, g) for c, g, _ in gaps]}", flush=True)
    return res


def main(out_path):
    backup = os.path.join(env.OUT_DIR, "o118_prefs_backup.xml")
    q.backup_prefs(backup)
    base = {"rtp_tight_reorder": True, "wifi-channel": 165, "stats_log": True}
    lines = []
    try:
        for codec in ("h264", "h265"):
            for i in range(N):
                lines.append(run(f"T1 {codec} 720p60 noidr #{i + 1}", base, f"gdr_{codec}_720p60_noidr.rtp"))
            lines.append(run(f"T1 {codec} 1080p90 noidr", base, f"gdr_{codec}_1080p90_noidr.rtp"))
            lines.append(run(f"T1 control {codec} 720p60 full", base, f"gdr_{codec}_720p60.rtp"))
            c2 = "c2.qti.avc.decoder" if codec == "h264" else "c2.qti.hevc.decoder"
            lines.append(run(f"T1 {codec} noidr dec={c2}", {**base, "dec_component": c2}, f"gdr_{codec}_720p60_noidr.rtp"))
        for au in (False, True):
            lines.append(run(f"T4 4-slice noidr au_aggregation={au}", {**base, "au_aggregation": au},
                             "gdr_h264_720p60_4slice_noidr.rtp"))
        for i in range(2):
            lines.append(run(f"T5 h264 noidr -> h265 noidr #{i + 1}", base,
                             "gdr_h264_720p60_noidr.rtp", "gdr_h265_720p60_noidr.rtp"))
    finally:
        q.adb("shell", "am", "force-stop", env.PKG)
        q.restore_prefs(backup)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# O118 S0 on the Quest (o118_s0.py), APK 086a64aa, air off, Wi-Fi RTP replay; one line per run\n")
        for r in lines:
            fh.write(f"{r['label']}\tframes={r['frames']}\tdecode_ms={r['decode_ms']}\terrors={r['errors']}\t"
                     f"config->output_ms={[(c, g, o) for c, g, o in r['configs']]}\n")
    print("written", out_path)


if __name__ == "__main__":
    main(sys.argv[1])
