"""Render docs/xr/option-costs.md from app/xr/src/main/res/raw/option_costs.json (the canonical table the headset menu
reads; the doc is only its human view). Never edit the doc by hand: change the JSON, then run this.

Usage: python3 option_costs_md.py           writes the doc
       python3 option_costs_md.py --check   exits 1 if the doc differs from what the JSON renders (used by the test)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
JSON_PATH = os.path.join(ROOT, "app", "xr", "src", "main", "res", "raw", "option_costs.json")
DOC_PATH = os.path.join(ROOT, "docs", "xr", "option-costs.md")

GROUP_TITLES = [
    ("mode", "Video mode"), ("bitrate", "Bitrate"),
    ("link", "Link states (MCS × bitrate × FEC)"), ("mcs", "MCS / guard interval"), ("fec", "FEC"),
    ("streams", "Spatial streams (1SS / 2SS)"), ("txpower", "Air TX power"), ("channel", "Channel"),
    ("lever", "App levers"), ("codec", "Codec"),
]

HEADER = """# Option costs (generated)

**Canonical source: [`app/xr/src/main/res/raw/option_costs.json`](../../app/xr/src/main/res/raw/option_costs.json).**
This page is generated from it by [option_costs_md.py](../../scripts/quest/option_costs_md.py); do not edit it by hand.
The headset menu (pixelpilot-xr-25) reads the JSON through `OptionCosts` (app/xr) and shows the cost next to each
option. Keywords: option costs, menu labels, cost table, latency cost, fps, post-FEC loss, bitrate, MCS, FEC, 2SS,
TX power, FIF, IDR, FRZ, codec, costuri opțiuni, meniu, etichete, latență.

**One place per number.** The G2G and FOV of the presets the air unit lists (`{list_presets}`) come only from the air's
VMODE1 `list` ([presets-design.md](presets-design.md)); this table never copies them, and the JVM test
(`OptionCostsTest`) enforces it. A preset the air does not list yet (e.g. HD) carries its numbers here until it does;
then they move to the air's `list` and leave this table. Moving G2G/FOV between the air and this table is an open
question for the owner of the air's preset receiver (vmoded).

Updated {updated}. Tags: [PROVEN] measured, [INFERRED] derived from measurements, [SPECULATION] not measured.
Empty cells = not measured. `a…b` = the spread over runs. In a link or lever delta, p95 is the p95 of the
same latency metric (not a difference of p95s).
"""


def fmt(v, unit="", sign=False):
    """One number, or a [lo, hi] range over runs, or empty when not measured."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    f = "{:+g}" if sign else "{:g}"
    if isinstance(v, list):
        return f"{f.format(v[0])}…{f.format(v[1])}{unit}"
    return f"{f.format(v)}{unit}"


def pair(c, name, unit=""):
    """A cost that is a value or {off, on}."""
    v = c.get(name)
    if isinstance(v, dict):
        return f"{fmt(v.get('off'), unit)} → {fmt(v.get('on'), unit)}"
    return fmt(v, unit)


def latency(c):
    parts = []
    if c.get("g2g_ms") is not None:
        parts.append(f"G2G {fmt(c['g2g_ms'])} ms")
    d = c.get("delta_ms")
    if d:
        s = fmt(d.get("mean"), sign=True)
        if d.get("p95") is not None:
            s += f" (p95 {fmt(d['p95'])})"
        parts.append(f"Δ {s} ms vs `{d.get('vs', '?')}`")
    return "; ".join(parts)


def row(o):
    c = o["costs"]
    notes = "; ".join(x for x in (o.get("note", ""), c.get("range_note", ""), c.get("fov", "") and f"FOV {c['fov']} %") if x)
    cells = [
        f"`{o['id']}`", o["label"], f"`{o['key']}`", o.get("conditions", ""), latency(c), pair(c, "fps"),
        pair(c, "post_fec_pct", " %"), notes, f"[{o['tag']}]", f"{o['source']} ({o['measured']})",
    ]
    return "| " + " | ".join(x.replace("|", "\\|").replace("\n", " ") for x in cells) + " |"


def render(table):
    out = [HEADER.format(list_presets="`, `".join(table["list_presets"]), updated=table["updated"])]
    for group, title in GROUP_TITLES:
        rows = [o for o in table["options"] if o["group"] == group]
        if not rows:
            continue
        out.append(f"\n## {title}\n")
        out.append("| id | option | key | measured under | latency | decoded fps | post-FEC | notes | tag | source |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        out.extend(row(o) for o in rows)
    return "\n".join(out) + "\n"


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        text = render(json.load(f))
    if "--check" in sys.argv:
        current = open(DOC_PATH, encoding="utf-8").read() if os.path.exists(DOC_PATH) else ""
        if current.replace("\r\n", "\n") != text:
            print("docs/xr/option-costs.md is out of date: run python3 scripts/quest/option_costs_md.py")
            sys.exit(1)
        print("option-costs.md matches the JSON")
        return
    with open(DOC_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", DOC_PATH)


if __name__ == "__main__":
    main()
