# Minimal CPython stand-in for MicroPython's framebuf (RGB565 only), enough for
# the dashboard code: fill, fill_rect, rect, hline, vline, pixel, line, ellipse.
import struct

RGB565 = 1
GS8 = 6


class FrameBuffer:
    def __init__(self, buf, w, h, fmt):
        assert fmt == RGB565
        self.buf, self.w, self.h = buf, w, h

    def pixel(self, x, y, c=None):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = 2 * (y * self.w + x)
            if c is None:
                return struct.unpack_from("<H", self.buf, i)[0]
            struct.pack_into("<H", self.buf, i, c)

    def fill_rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0:
            return
        row = struct.pack("<H", c) * (x1 - x0)
        for yy in range(y0, y1):
            i = 2 * (yy * self.w + x0)
            self.buf[i:i + len(row)] = row

    def fill(self, c):
        self.fill_rect(0, 0, self.w, self.h, c)

    def hline(self, x, y, w, c):
        self.fill_rect(x, y, w, 1, c)

    def vline(self, x, y, h, c):
        self.fill_rect(x, y, 1, h, c)

    def rect(self, x, y, w, h, c, f=False):
        if f:
            return self.fill_rect(x, y, w, h, c)
        self.hline(x, y, w, c)
        self.hline(x, y + h - 1, w, c)
        self.vline(x, y, h, c)
        self.vline(x + w - 1, y, h, c)

    def line(self, x0, y0, x1, y1, c):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.pixel(x0, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def ellipse(self, cx, cy, xr, yr, c, f=False, m=0xF):
        # quadrants: 1 = +x-y (top-right), 2 = -x-y, 4 = -x+y, 8 = +x+y
        for dy in range(-yr, yr + 1):
            for dx in range(-xr, xr + 1):
                if xr and yr and (dx * dx) * yr * yr + (dy * dy) * xr * xr > xr * xr * yr * yr:
                    continue
                q = (1 if dx >= 0 and dy <= 0 else 0) | (2 if dx <= 0 and dy <= 0 else 0) | \
                    (4 if dx <= 0 and dy >= 0 else 0) | (8 if dx >= 0 and dy >= 0 else 0)
                if q & m:
                    self.pixel(cx + dx, cy + dy, c)
