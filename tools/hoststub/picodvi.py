# CPython stand-in for the picodvi C module (RP2350 flavour: RGB565), used by
# tools/preview.py. Mirrors the rendering in picodvi/modpicodvi.c.
import struct

MODE_400x240, MODE_320x240 = 0, 1
BPP = 16
FORMAT = 1  # framebuf.RGB565
_size = (400, 240)
_buf = None


def start(mode=MODE_400x240):
    global _size, _buf
    _size = (400, 240) if mode == MODE_400x240 else (320, 240)
    _buf = bytearray(_size[0] * _size[1] * 2)
    return _size


def size():
    return _size


def active():
    return _buf is not None


def framebuffer():
    return _buf


def rgb(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def _glyph(font, cp):
    n = struct.unpack_from("<H", font, 8)[0]
    lo, hi = 0, n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c, off = struct.unpack_from("<II", font, 12 + 8 * mid)
        if c == cp:
            return off
        if c < cp:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def _blend(bg, fg, a):
    br, bgg, bb = bg >> 11, (bg >> 5) & 63, bg & 31
    fr, fgg, fb = fg >> 11, (fg >> 5) & 63, fg & 31
    r = (fr * a + br * (15 - a) + 7) // 15
    g = (fgg * a + bgg * (15 - a) + 7) // 15
    b = (fb * a + bb * (15 - a) + 7) // 15
    return (r << 11) | (g << 5) | b


def _px_get(x, y):
    return struct.unpack_from("<H", _buf, 2 * (y * _size[0] + x))[0]


def _px_set(x, y, c):
    struct.pack_into("<H", _buf, 2 * (y * _size[0] + x), c)


def draw_text(font, text, x, y, color, bg=-1):
    W, H = _size
    for ch in text:
        off = _glyph(font, ord(ch))
        if off is None:
            continue
        adv, w, h, xo, yo = struct.unpack_from("<HHHhh", font, off)
        stride = (w + 1) // 2
        for row in range(h):
            py = y + yo + row
            if not 0 <= py < H:
                continue
            for col in range(w):
                px = x + xo + col
                if not 0 <= px < W:
                    continue
                v = font[off + 10 + row * stride + col // 2]
                a = (v >> (0 if col & 1 else 4)) & 15
                if a == 15:
                    _px_set(px, py, color)
                elif bg >= 0:
                    _px_set(px, py, _blend(bg, color, a) if a else bg)
                elif a:
                    _px_set(px, py, _blend(_px_get(px, py), color, a))
        x += adv
    return x


def text_width(font, text):
    w = 0
    for ch in text:
        off = _glyph(font, ord(ch))
        if off is not None:
            w += struct.unpack_from("<H", font, off)[0]
    return w


def font_metrics(font):
    return struct.unpack_from("<HH", font, 4)


def blit(img, x0, y0):
    if bytes(img[:4]) != b"PIM1":
        raise ValueError("not a PIM1 image")
    w, h = struct.unpack_from("<HH", img, 4)
    W, H = _size
    i = 8
    for row in range(h):
        for col in range(w):
            c, a = struct.unpack_from("<HB", img, i)
            i += 3
            x, y = x0 + col, y0 + row
            if a == 0 or not (0 <= x < W and 0 <= y < H):
                continue
            if a >= 248:
                _px_set(x, y, c)
            else:
                b = _px_get(x, y)
                bb = (b | (b << 16)) & 0x07E0F81F
                ff = (c | (c << 16)) & 0x07E0F81F
                r = (((((ff - bb) * (a >> 3)) & 0xFFFFFFFF) >> 5) + bb) & 0x07E0F81F  # uint32 wrap like C
                _px_set(x, y, (r | (r >> 16)) & 0xFFFF)


def julia(x0, y0, w, h, cre, cim, step, palette, shift, maxit, mul, inside,
          rad=0, ex=0, ey=0, ew=0, eh=0):
    Q = 13
    four = 4 << Q
    W, H = _size
    ex -= x0
    ey -= y0
    for j in range(h):
        py = y0 + j
        if not 0 <= py < H:
            continue
        skip = 0
        if rad:
            dy = rad - j if j < rad else (j - (h - rad - 1) if j >= h - rad else 0)
            if dy:
                k = 0
                while k < rad and (rad - k) ** 2 + dy * dy > rad * rad:
                    k += 1
                skip = k
        zi0 = (j - h // 2) * step
        for i in range(skip, w - skip):
            px = x0 + i
            if not 0 <= px < W or (ex <= i < ex + ew and ey <= j < ey + eh):
                continue
            zr, zi, it = (i - w // 2) * step, zi0, 0
            while it < maxit:
                if abs(zr) > (2 << Q) or abs(zi) > (2 << Q):
                    break
                zr2, zi2 = (zr * zr) >> Q, (zi * zi) >> Q
                if zr2 + zi2 > four:
                    break
                zi = ((zr * zi) >> (Q - 1)) + cim
                zr = zr2 - zi2 + cre
                it += 1
            _px_set(px, py, inside if it >= maxit else palette[(it * mul + shift) & 255])


import math as _math

_sin8 = [int(127.0 * _math.sin(i * 6.2831853 / 256)) for i in range(256)]


def _isin(a):
    return _sin8[a & 255]


def _round_skip(j, h, rad):
    if not rad:
        return 0
    dy = rad - j if j < rad else (j - (h - rad - 1) if j >= h - rad else 0)
    k = 0
    if dy:
        while k < rad and (rad - k) ** 2 + dy * dy > rad * rad:
            k += 1
    return k


def effect(kind, x0, y0, w, h, t, palette, rad=0):
    nb = 5 if kind == 1 else 3
    bx, by = [], []
    for k in range(nb):
        ph = k * 51
        bx.append(w // 2 + int(_isin((t >> (4 + (k & 1))) + ph) * (w // 2 - 6) / 127))
        by.append(h // 2 + int(_isin((t >> 5) * (k + 2) // 2 + ph * 3 + 64) * (h // 2 - 6) / 127))
    tt = t >> 4
    W, H = _size
    for j in range(h):
        py = y0 + j
        if not 0 <= py < H:
            continue
        skip = _round_skip(j, h, rad)
        for i in range(skip, w - skip):
            px = x0 + i
            if not 0 <= px < W:
                continue
            if kind == 0:
                d = int(_math.isqrt((i - bx[0]) ** 2 + (j - by[0]) ** 2))
                v = _isin(i * 3 + tt) + _isin(j * 4 - tt * 2 // 3) + _isin((i + j) * 2 + tt // 2) + _isin(d * 6 - tt)
                v = ((v + 508) >> 2) + (tt >> 1)
            elif kind == 1:
                f = 0
                for k in range(nb):
                    f += (150 * 1024) // ((i - bx[k]) ** 2 + (j - by[k]) ** 2 + 1)
                v = 190 + (65 if f - 1024 > 4095 else (f - 1024) >> 6) if f >= 1024 else (f * 150) >> 10
            else:
                v = 0
                for k in range(3):
                    v += _isin(_math.isqrt((i - bx[k]) ** 2 + (j - by[k]) ** 2) * 7 - tt * 3)
                v = (v + 381) * 255 // 762
            _px_set(px, py, palette[v & 255])


_effect_base = effect


def effect(kind, x0, y0, w, h, t, palette, rad=0):
    if kind != 3:
        return _effect_base(kind, x0, y0, w, h, t, palette, rad)
    tt = t >> 4
    W, H = _size
    R = min(w, h) // 2
    for j in range(h):
        py = y0 + j
        if not 0 <= py < H:
            continue
        skip = _round_skip(j, h, rad)
        for i in range(skip, w - skip):
            px = x0 + i
            if not 0 <= px < W:
                continue
            dx, dy = i - w // 2 + 0.5, j - h // 2 + 0.5
            a = _math.atan2(dy, dx) * 256 / 6.2831853
            a = int(a + 256 if a < 0 else a) & 255
            r = min(255, int(_math.sqrt(dx * dx + dy * dy)))
            b1 = R * 3 // 4 + ((_isin(a * 8 + tt) * (R // 6)) >> 7)
            b2 = R * 2 // 5 + ((_isin(a * 12 - tt * 2) * (R // 9)) >> 7)
            d1, d2 = abs(r - b1), abs(r - b2)
            blue = red = green = 0
            if r < b1:
                blue += 50 + r * 90 // (b1 + 1)
                if _isin(a * 20 + r * 9 + tt) * _isin(r * 13 - a * 6 - tt) > 7000:
                    green += 110
            if d1 < 4:
                blue += (4 - d1) * 45
                red += (4 - d1) * 30
            if r < b2:
                blue += 40
            if d2 < 3:
                blue += (3 - d2) * 60
                green += (3 - d2) * 25
            core = R // 3
            if r < core and _isin(a * 24 + tt * 3) > 70:
                blue += (core - r) * 200 // core
                red += (core - r) * 70 // core
            if r < 4:
                blue += 255
                red += 120
                green += 60
            if r > b1 + 2:
                fade = 150 - (r - b1) * 10
                if fade > 0 and _isin(a * 48 + r * 6 - tt * 2) > 105:
                    green += fade
                    blue += fade // 4
            _px_set(px, py, rgb(min(255, red), min(255, green + blue // 6), min(255, blue)))
