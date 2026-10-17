# Thin drawing layer over picodvi: fonts and MDI icons from ROMFS, colours, shapes.
import json

import framebuf
import picodvi


def _load(path):
    f = open(path, "rb")
    try:
        return memoryview(f)  # ROMFS file: zero-copy view of flash
    except TypeError:
        return f.read()  # regular filesystem (or host preview)


class Display:
    def __init__(self, rom="/rom", mode=None):
        self.w, self.h = picodvi.start() if mode is None else picodvi.start(mode)
        self.buf = picodvi.framebuffer()
        self.fb = framebuf.FrameBuffer(self.buf, self.w, self.h, picodvi.FORMAT)
        self.rom = rom
        self._fonts = {}
        with open(rom + "/icons.json") as f:
            self._icons = json.load(f)

    rgb = staticmethod(picodvi.rgb)

    def font(self, name):
        f = self._fonts.get(name)
        if f is None:
            f = self._fonts[name] = _load("%s/fonts/%s.fnt" % (self.rom, name))
        return f

    def line_height(self, font):
        return picodvi.font_metrics(self.font(font))[0]

    def text_width(self, font, s):
        return picodvi.text_width(self.font(font), s)

    def text(self, font, s, x, y, color, bg=-1, align="l"):
        """Draws s with its line top at y. align: l / c / r relative to x. Returns width."""
        f = self.font(font)
        w = picodvi.text_width(f, s)
        if align == "c":
            x -= w // 2
        elif align == "r":
            x -= w
        picodvi.draw_text(f, s, x, y, color, bg)
        return w

    def icon(self, name, size, x, y, color, bg=-1):
        cp = self._icons.get(name) or self._icons["help-circle-outline"]
        picodvi.draw_text(self.font("mdi%d" % size), chr(cp), x, y, color, bg)

    def fill(self, c):
        self.fb.fill(c)

    def fill_rect(self, x, y, w, h, c):
        self.fb.fill_rect(x, y, w, h, c)

    def round_rect(self, x, y, w, h, r, c):
        fb = self.fb
        fb.fill_rect(x + r, y, w - 2 * r, h, c)
        fb.fill_rect(x, y + r, r, h - 2 * r, c)
        fb.fill_rect(x + w - r, y + r, r, h - 2 * r, c)
        # quadrant masks: 1 = top-right, 2 = top-left, 4 = bottom-left, 8 = bottom-right
        fb.ellipse(x + w - r - 1, y + r, r, r, c, True, 1)
        fb.ellipse(x + r, y + r, r, r, c, True, 2)
        fb.ellipse(x + r, y + h - r - 1, r, r, c, True, 4)
        fb.ellipse(x + w - r - 1, y + h - r - 1, r, r, c, True, 8)
