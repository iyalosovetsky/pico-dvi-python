#!/usr/bin/env python3
"""Renders the dashboard on the PC with the real device code + host stubs.

Usage: tools/preview.py [out.png] [--scale N]
Shows: clock 14:37:24 on 2026-10-17, battery 76 %, discharging 1840 W, load 612 W, no grid.
"""
import os
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
time.tzset()

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / "hoststub"), str(ROOT / "device" / "lib"), str(ROOT / "device")]

from PIL import Image  # noqa: E402

import picodvi  # noqa: E402
import tz  # noqa: E402
from display import Display  # noqa: E402
from screen import Dashboard  # noqa: E402


def to_png(path, scale):
    w, h = picodvi.size()
    buf = picodvi.framebuffer()
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            i = 2 * (y * w + x)
            c = buf[i] | (buf[i + 1] << 8)
            r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
            px[x, y] = (r * 255 // 31, g * 255 // 63, b * 255 // 31)
    if scale != 1:
        img = img.resize((w * scale, h * scale), Image.NEAREST)
    img.save(path)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scale = 2
    if "--scale" in sys.argv:
        scale = int(sys.argv[sys.argv.index("--scale") + 1])
        args = [a for a in args if a != str(scale)]
    out = args[0] if args else str(ROOT / "preview.png")

    d = Display(rom=str(ROOT / "romfs"))
    ui = Dashboard(d)
    ui.draw_all()
    utc = time.mktime((2026, 10, 17, 11, 37, 24, 0, 0, 0))
    ui.set_wifi(True, -58)
    ui.set_time(tz.localtime(utc), True)
    ui.set_battery(76, charging=False)
    ui.set_power(1840, charging=False)
    ui.set_load(612)
    ui.set_grid(False)
    ui.set_mqtt(True)
    ui.set_weather("partlycloudy", 11.2)
    if "--anim" in sys.argv:
        ui.set_battery(64, charging=False, volts=52.4)
        ui.set_warning(None)
        ui.animate(int(sys.argv[sys.argv.index("--anim") + 1]) if sys.argv[-1].isdigit() else 2400)
    else:
        ui.set_warning({"icon": "rainy", "title": "Дощ", "detail": "3,4 мм/год", "when": "о 15:00"})
    to_png(out, scale)
    print(out)


if __name__ == "__main__":
    main()
