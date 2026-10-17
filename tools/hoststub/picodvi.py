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
