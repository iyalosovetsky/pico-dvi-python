# Waveshare PICO-DVI-LCD demo for MicroPython (picodvi module).
# Framebuffer: 400x240 (800x480 DVI, default) or 320x240 (640x480 DVI);
# RGB332 on RP2040, RGB565 on RP2350.
import array
import math
import random
import time

import framebuf
import micropython
import picodvi

rgb = picodvi.rgb

W, H = picodvi.start()  # or picodvi.start(picodvi.MODE_320x240)
buf = picodvi.framebuffer()
fb = framebuf.FrameBuffer(buf, W, H, picodvi.FORMAT)

BLACK = rgb(0, 0, 0)
WHITE = rgb(255, 255, 255)
YELLOW = rgb(255, 255, 0)


def text_center(s, y, c=WHITE, bg=None):
    x = (W - len(s) * 8) // 2
    if bg is not None:
        fb.fill_rect(x - 4, y - 3, len(s) * 8 + 8, 14, bg)
    fb.text(s, x, y, c)


def fps_label(frames, t0):
    dt = time.ticks_diff(time.ticks_ms(), t0)
    if dt > 0:
        s = "%d fps" % (frames * 1000 // dt)
        fb.fill_rect(W - 8 * len(s) - 6, H - 13, 8 * len(s) + 6, 13, BLACK)
        fb.text(s, W - 8 * len(s) - 3, H - 11, YELLOW)


# --- Scene 1: colour test ---------------------------------------------------------
def hsv(h, s, v):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return rgb(int(r * 255), int(g * 255), int(b * 255))


def scene_palette(duration_ms=5000):
    fb.fill(BLACK)
    if picodvi.BPP == 8:
        cw, ch = W // 16, (H - 40) // 16
        for i in range(256):
            fb.fill_rect((i % 16) * cw, 40 + (i // 16) * ch, cw, ch, i)
    else:
        # hue across, brightness down: shows off the 65k colours
        rows = H - 40
        for x in range(0, W, 2):
            for y in range(0, rows, 4):
                fb.fill_rect(x, 40 + y, 2, 4, hsv(x / W, 1 - max(0, y - rows // 2) / (rows // 2), min(1, (y + 8) / (rows // 2))))
    text_center("Raspberry Pi Pico W", 6, WHITE)
    text_center("MicroPython + DVI  %dx%d  %d bpp" % (W, H, picodvi.BPP), 22, YELLOW)
    time.sleep_ms(duration_ms)


# --- Scene 2: plasma (viper, full-screen per frame) -----------------------------
SIN = bytearray(int(127.5 + 127.5 * math.sin(i * 2 * math.pi / 256)) for i in range(256))


def make_plasma_palette():
    pal = bytearray(256) if picodvi.BPP == 8 else array.array("H", bytes(512))
    for i in range(256):
        a = i * 2 * math.pi / 256
        pal[i] = rgb(int(128 + 127 * math.sin(a)),
                     int(128 + 127 * math.sin(a + 2.094)),
                     int(128 + 127 * math.sin(a + 4.188)))
    return pal


PAL = make_plasma_palette()


@micropython.viper
def plasma(dst: ptr8, sint: ptr8, pal: ptr8, t: int, w: int, h: int):
    i = 0
    for y in range(h):
        sy = sint[(y + t) & 255] + sint[((y >> 1) + 3 * t) & 255]
        for x in range(w):
            v = sint[(x + 2 * t) & 255] + sy + sint[(x + y + t) & 255]
            dst[i] = pal[((v >> 2) + t) & 255]
            i += 1


@micropython.viper
def plasma16(dst: ptr16, sint: ptr8, pal: ptr16, t: int, w: int, h: int):
    i = 0
    for y in range(h):
        sy = sint[(y + t) & 255] + sint[((y >> 1) + 3 * t) & 255]
        for x in range(w):
            v = sint[(x + 2 * t) & 255] + sy + sint[(x + y + t) & 255]
            dst[i] = pal[((v >> 2) + t) & 255]
            i += 1


def scene_plasma(duration_ms=10000):
    draw = plasma if picodvi.BPP == 8 else plasma16
    t0 = time.ticks_ms()
    frames = 0
    t = 0
    while time.ticks_diff(time.ticks_ms(), t0) < duration_ms:
        draw(buf, SIN, PAL, t, W, H)
        text_center(" PLASMA ", 8, WHITE, BLACK)
        frames += 1
        fps_label(frames, t0)
        t += 2


# --- Scene 3: bouncing balls -------------------------------------------------
def scene_balls(duration_ms=10000, n=14):
    balls = []
    for _ in range(n):
        r = random.randint(6, 18)
        balls.append([random.randint(r, W - r), random.randint(r, H - r),
                      random.choice((-3, -2, 2, 3)), random.choice((-3, -2, 2, 3)),
                      r, rgb(random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))])
    bg = rgb(0, 0, 64)
    t0 = time.ticks_ms()
    frames = 0
    while time.ticks_diff(time.ticks_ms(), t0) < duration_ms:
        fb.fill(bg)
        for b in balls:
            b[0] += b[2]
            b[1] += b[3]
            if b[0] < b[4] or b[0] > W - b[4]:
                b[2] = -b[2]
            if b[1] < b[4] or b[1] > H - b[4]:
                b[3] = -b[3]
            fb.ellipse(b[0], b[1], b[4], b[4], b[5], True)
            fb.ellipse(b[0] - b[4] // 3, b[1] - b[4] // 3, b[4] // 4, b[4] // 4, WHITE, True)
        text_center("framebuf.ellipse()", 8, WHITE)
        frames += 1
        fps_label(frames, t0)


# --- Scene 4: 3D starfield ---------------------------------------------------
def scene_stars(duration_ms=10000, n=180):
    stars = [[random.randint(-1000, 1000), random.randint(-1000, 1000), random.randint(1, 1000)]
             for _ in range(n)]
    shades = [rgb(v, v, v) for v in (255, 200, 150, 100, 60)]
    cx, cy = W // 2, H // 2
    t0 = time.ticks_ms()
    frames = 0
    while time.ticks_diff(time.ticks_ms(), t0) < duration_ms:
        fb.fill(BLACK)
        for s in stars:
            s[2] -= 12
            if s[2] <= 1:
                s[0] = random.randint(-1000, 1000)
                s[1] = random.randint(-1000, 1000)
                s[2] = 1000
            x = cx + s[0] * 128 // s[2]
            y = cy + s[1] * 128 // s[2]
            if 0 <= x < W - 1 and 0 <= y < H - 1:
                c = shades[min(4, s[2] // 200)]
                if s[2] < 300:
                    fb.fill_rect(x, y, 2, 2, c)
                else:
                    fb.pixel(x, y, c)
        text_center("STARFIELD", 8, YELLOW)
        frames += 1
        fps_label(frames, t0)


while True:
    scene_palette()
    scene_plasma()
    scene_balls()
    scene_stars()
