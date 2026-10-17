"""Colour weather icons in a soft "phone widget" style, drawn with Pillow.

Each icon is drawn on a 100x100 design grid at 4x supersampling and saved as
.pim (see pack_pim) for picodvi.blit(). Names follow Home Assistant weather
conditions; "-night" variants exist where the sun is replaced by the moon.
"""
import struct

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 4  # supersampling factor
G = 100  # design grid


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _vgrad(size, top, bottom):
    """Vertical gradient image (RGB)."""
    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        col.putpixel((0, y), _lerp(top, bottom, y / max(1, h - 1)))
    return col.resize((w, h))


def _rgrad(size, centre, radius, inner, outer):
    """Radial gradient image (RGB)."""
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy = centre
    for y in range(h):
        for x in range(w):
            t = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / radius)
            px[x, y] = _lerp(inner, outer, t)
    return img


class Canvas:
    def __init__(self, px):
        self.n = px * SS
        self.k = self.n / G  # design units -> supersampled pixels
        self.img = Image.new("RGBA", (self.n, self.n), (0, 0, 0, 0))

    def s(self, *v):
        return [round(x * self.k) for x in v]

    def mask(self):
        return Image.new("L", (self.n, self.n), 0)

    def paint(self, mask, fill, shadow=0):
        """Composites `fill` (RGB image or colour) through `mask`."""
        if shadow:
            sh = mask.filter(ImageFilter.GaussianBlur(self.k * 2.5)).point(lambda v: v * shadow // 255)
            sh = ImageChops.offset(sh, 0, round(self.k * 2))
            self.img.alpha_composite(Image.merge("RGBA", (*[Image.new("L", sh.size, 20)] * 3, sh)))
        layer = Image.new("RGBA", (self.n, self.n), (0, 0, 0, 0))
        src = fill if isinstance(fill, Image.Image) else Image.new("RGB", (self.n, self.n), fill)
        layer.paste(src, (0, 0), mask)
        self.img.alpha_composite(layer)

    def result(self, px):
        return self.img.resize((px, px), Image.LANCZOS)

    # --- elements (design-grid coordinates) --------------------------------
    def sun(self, cx, cy, r, rays=True):
        m = self.mask()
        d = ImageDraw.Draw(m)
        if rays:
            import math
            for i in range(8):
                a = i * math.pi / 4
                x0, y0 = cx + math.cos(a) * (r + 5), cy + math.sin(a) * (r + 5)
                x1, y1 = cx + math.cos(a) * (r + 12), cy + math.sin(a) * (r + 12)
                d.line(self.s(x0, y0, x1, y1), fill=255, width=round(self.k * 4.5))
                for (x, y) in ((x0, y0), (x1, y1)):
                    d.ellipse(self.s(x - 2.2, y - 2.2, x + 2.2, y + 2.2), fill=255)
        d.ellipse(self.s(cx - r, cy - r, cx + r, cy + r), fill=255)
        grad = _rgrad((self.n, self.n), self.s(cx - r * 0.35, cy - r * 0.35), r * self.k * 1.6,
                      (255, 236, 120), (255, 152, 0))
        self.paint(m, grad)

    def moon(self, cx, cy, r):
        m = self.mask()
        d = ImageDraw.Draw(m)
        d.ellipse(self.s(cx - r, cy - r, cx + r, cy + r), fill=255)
        d.ellipse(self.s(cx - r * 0.35, cy - r * 1.25, cx + r * 1.55, cy + r * 0.55), fill=0)
        grad = _rgrad((self.n, self.n), self.s(cx - r * 0.5, cy), r * self.k * 1.4,
                      (255, 248, 196), (240, 196, 70))
        self.paint(m, grad)

    def star(self, cx, cy, r):
        m = self.mask()
        ImageDraw.Draw(m).polygon([tuple(self.s(*p)) for p in (
            (cx, cy - r), (cx + r * 0.28, cy - r * 0.28), (cx + r, cy), (cx + r * 0.28, cy + r * 0.28),
            (cx, cy + r), (cx - r * 0.28, cy + r * 0.28), (cx - r, cy), (cx - r * 0.28, cy - r * 0.28))], fill=255)
        self.paint(m, (255, 241, 170))

    def cloud(self, x, y, w, top=(250, 252, 255), bottom=(200, 212, 224), shadow=110):
        """Cloud whose bounding box starts at (x, y), width w (height ~0.62 w)."""
        h = w * 0.62
        m = self.mask()
        d = ImageDraw.Draw(m)
        base_y = y + h
        r1, r2, r3 = w * 0.22, w * 0.30, w * 0.20
        d.ellipse(self.s(x + w * 0.04, base_y - 2 * r1, x + w * 0.04 + 2 * r1, base_y), fill=255)
        d.ellipse(self.s(x + w * 0.24, y, x + w * 0.24 + 2 * r2, y + 2 * r2), fill=255)
        d.ellipse(self.s(x + w * 0.56, base_y - 2 * r3 - w * 0.12, x + w * 0.56 + 2 * r3 * 1.1, base_y - w * 0.12 + r3 * 0.2), fill=255)
        d.rounded_rectangle(self.s(x + w * 0.04, base_y - w * 0.30, x + w * 0.98, base_y), radius=round(w * 0.15 * self.k), fill=255)
        bb = self.s(x, y, x + w, base_y)
        grad = Image.new("RGB", (self.n, self.n), bottom)
        grad.paste(_vgrad((bb[2] - bb[0] + 1, bb[3] - bb[1] + 1), top, bottom), (bb[0], bb[1]))
        self.paint(m, grad, shadow)

    def drop(self, cx, cy, s=1.0, top=(129, 212, 250), bottom=(2, 136, 209)):
        m = self.mask()
        d = ImageDraw.Draw(m)
        r = 4.2 * s
        d.ellipse(self.s(cx - r, cy - r, cx + r, cy + r), fill=255)
        d.polygon([tuple(self.s(*p)) for p in ((cx - r * 0.92, cy - r * 0.35), (cx + 1.5 * s, cy - r * 3.1), (cx + r * 0.92, cy - r * 0.35))], fill=255)
        m = m.rotate(-18, center=tuple(self.s(cx, cy)), resample=Image.BICUBIC)
        bb = self.s(cx - r, cy - r * 3.2, cx + r, cy + r)
        grad = Image.new("RGB", (self.n, self.n), bottom)
        grad.paste(_vgrad((bb[2] - bb[0] + 1, bb[3] - bb[1] + 1), top, bottom), (bb[0], bb[1]))
        self.paint(m, grad)

    def flake(self, cx, cy, r, colour=(236, 246, 255)):
        import math
        m = self.mask()
        d = ImageDraw.Draw(m)
        for i in range(3):
            a = i * math.pi / 3
            dx, dy = math.cos(a) * r, math.sin(a) * r
            d.line(self.s(cx - dx, cy - dy, cx + dx, cy + dy), fill=255, width=round(self.k * 2.6))
        d.ellipse(self.s(cx - 2, cy - 2, cx + 2, cy + 2), fill=255)
        self.paint(m, colour)

    def hailstone(self, cx, cy, r):
        m = self.mask()
        ImageDraw.Draw(m).ellipse(self.s(cx - r, cy - r, cx + r, cy + r), fill=255)
        grad = _rgrad((self.n, self.n), self.s(cx - r * 0.4, cy - r * 0.4), r * self.k * 1.8,
                      (255, 255, 255), (170, 205, 235))
        self.paint(m, grad)

    def bolt(self, x, y, s=1.0):
        m = self.mask()
        pts = [(x + 9, y), (x, y + 17), (x + 7, y + 17), (x + 3, y + 31), (x + 17, y + 11), (x + 10, y + 11), (x + 15, y)]
        pts = [(x + (px - x) * s, y + (py - y) * s) for px, py in pts]
        ImageDraw.Draw(m).polygon([tuple(self.s(*p)) for p in pts], fill=255)
        bb = self.s(x, y, x + 17 * s, y + 31 * s)
        grad = Image.new("RGB", (self.n, self.n), (255, 160, 0))
        grad.paste(_vgrad((bb[2] - bb[0] + 1, bb[3] - bb[1] + 1), (255, 238, 88), (255, 143, 0)), (bb[0], bb[1]))
        self.paint(m, grad)

    def bars(self, x, y, w, n=3, colour=(176, 190, 204)):
        m = self.mask()
        d = ImageDraw.Draw(m)
        for i in range(n):
            off = (i % 2) * 8
            d.rounded_rectangle(self.s(x + off, y + i * 9, x + w - 8 + off, y + i * 9 + 4.5), radius=round(self.k * 2.3), fill=255)
        self.paint(m, colour)

    def wind(self, x, y, w, colour=(144, 202, 249)):
        m = self.mask()
        d = ImageDraw.Draw(m)
        lw = round(self.k * 4.5)
        for (yy, ww, curl) in ((y, w * 0.85, 9), (y + 15, w, 11), (y + 30, w * 0.6, 7)):
            d.line(self.s(x, yy, x + ww - curl, yy), fill=255, width=lw)
            d.arc(self.s(x + ww - 2 * curl, yy - 2 * curl, x + ww, yy), start=-180, end=90, fill=255, width=lw)
            # rounded ends
            for (ex, ey) in ((x, yy),):
                d.ellipse(self.s(ex - 2.2, ey - 2.2, ex + 2.2, ey + 2.2), fill=255)
        self.paint(m, colour)

    def triangle(self):
        m = self.mask()
        d = ImageDraw.Draw(m)
        d.rounded_rectangle(self.s(46, 30, 54, 62), radius=round(self.k * 4), fill=255)
        tri = self.mask()
        ImageDraw.Draw(tri).polygon([tuple(self.s(*p)) for p in ((50, 12), (90, 84), (10, 84))], fill=255)
        tri = tri.filter(ImageFilter.GaussianBlur(self.k * 1.5)).point(lambda v: 255 if v > 128 else 0)
        grad = Image.new("RGB", (self.n, self.n))
        grad.paste(_vgrad((self.n, self.n), (255, 202, 40), (255, 112, 67)))
        self.paint(tri, grad, 90)
        dot = self.mask()
        ImageDraw.Draw(dot).ellipse(self.s(45.5, 67, 54.5, 76), fill=255)
        self.paint(m, (60, 40, 20))
        self.paint(dot, (60, 40, 20))


GREY_CLOUD = dict(top=(222, 228, 236), bottom=(160, 174, 190))
DARK_CLOUD = dict(top=(176, 186, 200), bottom=(104, 118, 138))


def draw(name, px):
    c = Canvas(px)
    night = name == "partlycloudy-night"
    base = "partlycloudy" if night else name

    def sky(cx, cy, r):
        if night:
            c.moon(cx, cy, r)
        else:
            c.sun(cx, cy, r, rays=r > 14)

    if base == "sunny":
        c.sun(50, 50, 24)
    elif base == "clear-night":
        c.moon(52, 50, 30)
        c.star(20, 26, 6)
        c.star(80, 74, 4.5)
    elif base == "partlycloudy":
        sky(62, 36, 20)
        c.cloud(8, 38, 72)
    elif base == "cloudy":
        c.cloud(36, 18, 58, **GREY_CLOUD)
        c.cloud(6, 36, 74)
    elif base == "fog":
        c.cloud(14, 14, 72, **GREY_CLOUD)
        c.bars(16, 66, 70)
    elif base in ("rainy", "pouring"):
        c.cloud(10, 14, 80, **(DARK_CLOUD if base == "pouring" else GREY_CLOUD))
        drops = ((30, 76), (50, 84), (70, 76)) if base == "rainy" else ((22, 74), (38, 86), (54, 74), (70, 86), (84, 74))
        for x, y in drops:
            c.drop(x, y, 1.0 if base == "rainy" else 0.85)
    elif base == "snowy":
        c.cloud(10, 14, 80, **GREY_CLOUD)
        for x, y in ((28, 78), (50, 86), (72, 78)):
            c.flake(x, y, 7)
    elif base == "snowy-rainy":
        c.cloud(10, 14, 80, **GREY_CLOUD)
        c.flake(30, 80, 7)
        c.drop(52, 84)
        c.flake(74, 80, 7)
    elif base == "hail":
        c.cloud(10, 14, 80, **GREY_CLOUD)
        for x, y in ((30, 78), (50, 86), (70, 78)):
            c.hailstone(x, y, 5)
    elif base == "lightning":
        c.cloud(10, 12, 80, **DARK_CLOUD)
        c.bolt(40, 58, 1.15)
    elif base == "lightning-rainy":
        c.cloud(10, 12, 80, **DARK_CLOUD)
        c.bolt(42, 58, 1.1)
        c.drop(26, 80)
        c.drop(74, 80)
    elif base in ("windy", "windy-variant"):
        if base == "windy-variant":
            c.cloud(30, 8, 62, **GREY_CLOUD)
            c.wind(10, 62, 76)
        else:
            c.wind(10, 30, 80)
    elif base == "exceptional":
        c.triangle()
    else:
        raise ValueError(name)
    return c.result(px)


NAMES = ["sunny", "clear-night", "partlycloudy", "partlycloudy-night", "cloudy", "fog",
         "rainy", "pouring", "snowy", "snowy-rainy", "hail", "lightning",
         "lightning-rainy", "windy", "windy-variant", "exceptional"]


def pack_pim(img):
    """PIM1: b"PIM1", u16 w, u16 h, then w*h * (u16 RGB565 LE, u8 alpha)."""
    w, h = img.size
    out = bytearray(b"PIM1" + struct.pack("<HH", w, h))
    for r, g, b, a in img.getdata():
        c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out += struct.pack("<HB", c, a)
    return bytes(out)
