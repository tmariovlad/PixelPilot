"""Quest 2 backlight flash timing from the panel timing in the kernel device tree (hollywood dsi panel
dtsi: panel-height, v-front-porch, v-back-porch, v-pulse-width, framerate) and the bl_lvl duty scaling
of dsi_panel.c: when each half of the panel flashes, in ms after vsync, for three backlight levels.
Usage: python3 blu.py <va> <vfp> <vbp> <vsw> <hz>     e.g. python3 blu.py 3664 14 7 1 120"""
import sys
va, vfp, vbp, vsw, hz = map(int, sys.argv[1:6])
vt = va + vfp + vbp + vsw
h = 1e9 / (vt * hz)               # ns per line
for bl in (800, 1000, 1200):
    dur = bl * vt * 80 // 1000000   # lines lit (duty 8.0%, bl_lvl scaling as in dsi_panel.c)
    target = vt - vfp + 1200
    right = vt + vsw + vbp - dur
    left = right + va // 2
    right = min(target, right); left = min(target, left)
    # flash start/end in ms after the frame start (line 0 = vsync)
    f = lambda s: s * h / 1e6
    print(f"bl={bl} vt={vt} line={h:.1f}ns scanout(active)={f(va+vbp+vsw):.2f}ms  right(eye?) start={f(right):.2f} mid={f(right+dur/2):.2f}  left start={f(left):.2f} mid={f(left+dur/2):.2f} ms  dur={f(dur):.2f}ms")
