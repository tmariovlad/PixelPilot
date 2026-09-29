"""PPXR_STATS logcat lines (what the in-headset Stats page showed, one line per 2 s) -> a TSV next to link_audit.

Usage: python3 stats_log.py <logcat file> [out.tsv]      (stdout without out.tsv)

The app logs a line every 2 s while the Stats page is open, or always with the slot pref stats_log
(app stats/StatsLine.java defines the keys and their order; this parser takes whatever keys it finds). Capture it
DETACHED, never streamed over adb-over-Wi-Fi (streaming makes the Quest's own Wi-Fi transmit next to the RTL):
scripts/quest/ab_detached.sh captures the PPXR_STATS tag with the wfb-ng/devourer lines; pull the file.
Columns: epoch (logcat -v epoch, Quest wall clock), then the line's keys in first-seen order; "-" (unknown)
becomes empty. t is the Quest's CLOCK_MONOTONIC ms, the clock of the Perfetto traces.
"""
import sys

TAG = " PPXR_STATS: "


def parse_line(line):
    """(epoch, {key: value}) for a PPXR_STATS line, or None."""
    i = line.find(TAG)
    if i < 0:
        return None
    head = line[:i].split()
    if not head:
        return None
    return head[0], parse_kv(line[i + len(TAG):])


def parse_kv(text):
    """{key: value} of the "k=v k=v" tokens in text; "-" (unknown) becomes empty. Shared with health_log."""
    kv = {}
    for token in text.split():
        k, sep, v = token.partition("=")
        if sep:
            kv[k] = "" if v == "-" else v
    return kv


def to_tsv(lines):
    rows, keys = [], []
    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            continue
        rows.append(parsed)
        for k in parsed[1]:
            if k not in keys:
                keys.append(k)
    out = ["\t".join(["epoch"] + keys)]
    for epoch, kv in rows:
        out.append("\t".join([epoch] + [kv.get(k, "") for k in keys]))
    return "\n".join(out) + "\n"


def main():
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        tsv = to_tsv(fh)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as fh:
            fh.write(tsv)
        print(f"{tsv.count(chr(10)) - 1} stats lines -> {sys.argv[2]}")
    else:
        sys.stdout.write(tsv)


if __name__ == "__main__":
    main()
