#!/usr/bin/env python3
"""Builds the ROMFS asset tree (fonts + icons) for the picodvi dashboard.

Usage: tools/mkassets.py [outdir]      (default: romfs/)
Then:  mpremote romfs deploy romfs

Font file format (.fnt, little endian), rendered by picodvi.draw_text():
  header  12 B: b"PDF1", u16 line_height, u16 ascent, u16 count, u8 bpp(=4), u8 0
  index   count * 8 B: u32 codepoint, u32 glyph_offset   (sorted by codepoint)
  glyph   u16 advance, u16 w, u16 h, i16 x_off, i16 y_off (top, from line top),
          then h rows of ceil(w/2) bytes, 4-bit alpha, high nibble = left pixel
"""
import json
import re
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
UBUNTU = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
MDI_TTF = CACHE / "materialdesignicons-webfont.ttf"
MDI_CSS = CACHE / "materialdesignicons.css"

LATIN = "".join(chr(c) for c in range(0x20, 0x7F))
UKR = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯабвгґдеєжзиіїйклмнопрстуфхцчшщьюя'’"
EXTRA = "°·–—…«»№"
TEXT = LATIN + UKR + EXTRA
VALUE = "0123456789 .,:-+−%°/kKMWVAhmsгодкВтАч" + "—"

# name, size px, weight, charset
FONTS = [
    ("ui16", 16, 400, TEXT),
    ("ui20", 20, 500, TEXT),
    ("val36", 36, 500, TEXT),
    ("clock96", 96, 300, "0123456789:"),
]

# MDI icons (same names as Home Assistant, without the "mdi:" prefix)
ICONS = [
    "battery", "battery-90", "battery-80", "battery-70", "battery-60", "battery-50",
    "battery-40", "battery-30", "battery-20", "battery-10", "battery-outline",
    "battery-alert-variant-outline", "battery-unknown",
    "battery-charging", "battery-charging-90", "battery-charging-80", "battery-charging-70",
    "battery-charging-60", "battery-charging-50", "battery-charging-40",
    "battery-charging-30", "battery-charging-20", "battery-charging-10",
    "battery-charging-outline",
    "flash", "lightning-bolt", "home-lightning-bolt", "transmission-tower",
    "solar-power", "power-plug", "meter-electric",
    "clock-outline", "calendar", "wifi", "wifi-off", "wifi-strength-1",
    "wifi-strength-2", "wifi-strength-3", "wifi-strength-4",
    "thermometer", "water-percent", "home", "information-outline", "alert",
    "bell", "message-text", "lan-disconnect", "help-circle-outline",
]
ICON_SIZES = (24, 48)


def set_weight(font, weight):
    try:
        axes = font.get_variation_axes()
    except Exception:
        return
    vals = []
    for ax in axes:
        name = ax.get("name", b"")
        name = name.decode() if isinstance(name, bytes) else name
        if name.lower().startswith("weight"):
            vals.append(weight)
        else:
            vals.append(ax.get("default", ax["minimum"]))
    font.set_variation_by_axes(vals)


def render(font, chars, line_height=None):
    ascent, descent = font.getmetrics()
    height = line_height or (ascent + descent)
    glyphs = []
    for ch in sorted(set(chars), key=ord):
        adv = int(round(font.getlength(ch)))
        l, t, r, b = font.getbbox(ch, anchor="ls")
        w, h = max(0, r - l), max(0, b - t)
        data = b""
        if w and h:
            img = Image.new("L", (w, h), 0)
            ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=255, anchor="ls")
            px = img.load()
            rows = []
            for y in range(h):
                row = bytearray((w + 1) // 2)
                for x in range(w):
                    a = (px[x, y] * 15 + 127) // 255
                    row[x // 2] |= a << (4 if x % 2 == 0 else 0)
                rows.append(bytes(row))
            data = b"".join(rows)
        glyphs.append((ord(ch), adv, w, h, l, ascent + t, data))
    return height, ascent, glyphs


def pack(height, ascent, glyphs):
    n = len(glyphs)
    out = bytearray(b"PDF1" + struct.pack("<HHHBB", height, ascent, n, 4, 0))
    index_pos = len(out)
    out += bytes(8 * n)
    for i, (cp, adv, w, h, xo, yo, data) in enumerate(glyphs):
        off = len(out)
        struct.pack_into("<II", out, index_pos + 8 * i, cp, off)
        out += struct.pack("<HHHhh", adv, w, h, xo, yo) + data
        if len(out) % 2:
            out += b"\0"
    return bytes(out)


def mdi_codepoints():
    css = MDI_CSS.read_text()
    return {m.group(1): int(m.group(2), 16)
            for m in re.finditer(r"\.mdi-([a-z0-9-]+)::before\s*\{\s*content:\s*\"\\([0-9A-Fa-f]+)\"", css)}


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "romfs"
    (out / "fonts").mkdir(parents=True, exist_ok=True)
    total = 0
    for name, size, weight, chars in FONTS:
        font = ImageFont.truetype(UBUNTU, size)
        set_weight(font, weight)
        blob = pack(*render(font, chars))
        (out / "fonts" / f"{name}.fnt").write_bytes(blob)
        total += len(blob)
        print(f"{name:10s} {len(set(chars)):4d} glyphs {len(blob):7d} B")

    cps = mdi_codepoints()
    missing = [n for n in ICONS if n not in cps]
    if missing:
        sys.exit(f"unknown MDI icons: {missing}")
    chars = "".join(chr(cps[n]) for n in ICONS)
    for size in ICON_SIZES:
        font = ImageFont.truetype(str(MDI_TTF), size)
        blob = pack(*render(font, chars))
        (out / "fonts" / f"mdi{size}.fnt").write_bytes(blob)
        total += len(blob)
        print(f"mdi{size:<7d} {len(ICONS):4d} glyphs {len(blob):7d} B")
    (out / "icons.json").write_text(json.dumps({n: cps[n] for n in ICONS}, separators=(",", ":")))
    print(f"total {total} B -> {out}")


if __name__ == "__main__":
    main()
