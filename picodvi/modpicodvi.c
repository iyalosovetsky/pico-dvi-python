// picodvi: DVI output for MicroPython on RP2040/RP2350 (Waveshare PICO-DVI-LCD).
//
// Framebuffer, pixel-doubled: RP2040 8 bpp RGB332 (framebuf.GS8),
// RP2350 16 bpp RGB565 (framebuf.RGB565). Modes (chosen once per boot):
//   MODE_400x240 -> 800x480p60, sys clock 295.2 MHz (default)
//   MODE_320x240 -> 640x480p60, sys clock 252 MHz
// Core 1 is fully dedicated to TMDS encoding; everything it touches after
// start-up lives in RAM, so flash writes from core 0 are safe.
//
// Restrictions while DVI is running:
//   - _thread is disabled in this firmware (it would reset core 1)
//   - don't change machine.freq() (TMDS bit clock = sys clock)
//   - PIO0 SM0..2, PWM slice 4 (GP8/9), DMA_IRQ_1 and 6 DMA channels are taken
//   - machine.I2S is not available (it shares DMA_IRQ_1)
//   - call start() before activating Wi-Fi (it rescales the CYW43 SPI clock)

#include <string.h>

#include "py/runtime.h"
#include "py/mphal.h"

#include "pico/multicore.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "hardware/pwm.h"
#include "hardware/sync.h"

#include "rp2_flash.h"

#if MICROPY_PY_NETWORK_CYW43 && CYW43_PIO_CLOCK_DIV_DYNAMIC
// From pico/cyw43_driver.h (not on the user module include path).
void cyw43_set_pio_clkdiv_int_frac8(uint32_t clock_div_int, uint8_t clock_div_frac8);
#endif

#include "dvi.h"
#include "dvi_serialiser.h"

typedef struct {
    uint16_t width;
    uint16_t height;
    const struct dvi_timing *timing;
} picodvi_mode_t;

enum { MODE_400x240, MODE_320x240 };

static const picodvi_mode_t picodvi_modes[] = {
    [MODE_400x240] = { 400, 240, &dvi_timing_800x480p_60hz },
    [MODE_320x240] = { 320, 240, &dvi_timing_640x480p_60hz },
};

#if PICO_RP2350
#define PICODVI_BPP 16
#else
#define PICODVI_BPP 8
#endif
#define FRAMEBUF_MAX_BYTES (400 * 240 * PICODVI_BPP / 8)

// Waveshare PICO-DVI-LCD pinout (same as Pico DVI Sock).
static const struct dvi_serialiser_cfg picodvi_lcd_cfg = {
    .pio = pio0,
    .sm_tmds = {0, 1, 2},
    .pins_tmds = {10, 12, 14},
    .pins_clk = 8,
    .invert_diffpairs = true
};

static struct dvi_inst dvi0;
static uint8_t framebuf[FRAMEBUF_MAX_BYTES] __attribute__((aligned(4)));
// Active mode; read by the scanline IRQ, so kept as plain RAM copies.
static int cur_mode = MODE_400x240;
static uint frame_width = 400;
static uint frame_height = 240;
static uint32_t core1_stack[512];
static volatile bool dvi_running = false;
// Debug counters: core 1 start-up stage and scanlines handed to the encoder.
static volatile uint32_t dbg_stage = 0;
static volatile uint32_t dbg_lines = 0;

// Called from the DMA IRQ on core 1 once per source scanline.
static void __not_in_flash_func(scanline_callback)(void) {
    static uint scanline = 2; // lines 0 and 1 are queued before start
    uint32_t *bufptr;
    while (queue_try_remove_u32(&dvi0.q_colour_free, &bufptr)) {
    }
    bufptr = (uint32_t *)&framebuf[frame_width * scanline * (PICODVI_BPP / 8)];
    queue_add_blocking_u32(&dvi0.q_colour_valid, &bufptr);
    if (++scanline == frame_height) {
        scanline = 0;
    }
    dbg_lines++;
}

static void core1_main(void) {
    dbg_stage = 1;
    dvi_register_irqs_this_core(&dvi0, DMA_IRQ_1);
    dbg_stage = 2;
    dvi_start(&dvi0);
    dbg_stage = 3;
    #if PICODVI_BPP == 16
    dvi_scanbuf_main_16bpp(&dvi0);
    #else
    dvi_scanbuf_main_8bpp(&dvi0);
    #endif
}

// Hooked into MICROPY_BOARD_END_SOFT_RESET: soft reset disables every PWM
// slice, including the one generating the TMDS clock.
void picodvi_soft_reset_hook(void) {
    if (dvi_running) {
        pwm_set_enabled(pwm_gpio_to_slice_num(picodvi_lcd_cfg.pins_clk), true);
    }
}

static mp_obj_t picodvi_size(void) {
    mp_obj_t t[2] = { MP_OBJ_NEW_SMALL_INT(frame_width), MP_OBJ_NEW_SMALL_INT(frame_height) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(picodvi_size_obj, picodvi_size);

// start(mode=MODE_400x240) -> (width, height)
// The mode can only be chosen once per boot: changing it needs a different
// sys clock while core 1 is streaming, so machine.reset() first.
static mp_obj_t picodvi_start(size_t n_args, const mp_obj_t *args) {
    int mode = n_args > 0 ? mp_obj_get_int(args[0]) : MODE_400x240;
    if (mode < 0 || mode >= (int)MP_ARRAY_SIZE(picodvi_modes)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid mode"));
    }
    if (dvi_running) {
        if (mode != cur_mode) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("DVI already running in another mode; machine.reset() to change"));
        }
        return picodvi_size();
    }

    const picodvi_mode_t *m = &picodvi_modes[mode];
    cur_mode = mode;
    frame_width = m->width;
    frame_height = m->height;

    vreg_set_voltage(VREG_VOLTAGE_1_20);
    mp_hal_delay_ms(10);
    uint32_t freq = m->timing->bit_clk_khz * 1000;
    rp2_flash_set_timing_for_freq(MAX(freq, clock_get_hz(clk_sys)));
    if (!set_sys_clock_khz(m->timing->bit_clk_khz, false)) {
        mp_raise_ValueError(MP_ERROR_TEXT("cannot set DVI clock"));
    }
    #if MICROPY_HW_ENABLE_UART_REPL
    setup_default_uart();
    #endif
    #if MICROPY_PY_NETWORK_CYW43 && CYW43_PIO_CLOCK_DIV_DYNAMIC
    // The Wi-Fi chip's PIO SPI is clocked from sys clock (div 2 at <=150 MHz);
    // keep the PIO clock <= 75 MHz. Takes effect when Wi-Fi is (re)initialised,
    // so start DVI before activating the WLAN.
    cyw43_set_pio_clkdiv_int_frac8((freq + 74999999) / 75000000, 0);
    #endif

    memset(framebuf, 0, sizeof(framebuf));

    dvi0.timing = m->timing;
    dvi0.ser_cfg = picodvi_lcd_cfg;
    dvi0.scanline_callback = scanline_callback;
    dvi_init(&dvi0, next_striped_spin_lock_num(), next_striped_spin_lock_num());

    uint32_t *bufptr = (uint32_t *)framebuf;
    queue_add_blocking_u32(&dvi0.q_colour_valid, &bufptr);
    bufptr += frame_width * (PICODVI_BPP / 8) / 4;
    queue_add_blocking_u32(&dvi0.q_colour_valid, &bufptr);

    multicore_reset_core1();
    multicore_launch_core1_with_stack(core1_main, core1_stack, sizeof(core1_stack));
    dvi_running = true;
    return picodvi_size();
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(picodvi_start_obj, 0, 1, picodvi_start);

static mp_obj_t picodvi_active(void) {
    return mp_obj_new_bool(dvi_running);
}
static MP_DEFINE_CONST_FUN_OBJ_0(picodvi_active_obj, picodvi_active);

// Returns a bytearray that aliases the framebuffer (use with picodvi.FORMAT).
static mp_obj_t picodvi_framebuffer(void) {
    return mp_obj_new_bytearray_by_ref(frame_width * frame_height * (PICODVI_BPP / 8), framebuf);
}
static MP_DEFINE_CONST_FUN_OBJ_0(picodvi_framebuffer_obj, picodvi_framebuffer);

// rgb(r, g, b) with 0..255 components -> native pixel value (RGB332 or RGB565).
static mp_obj_t picodvi_rgb(mp_obj_t r_in, mp_obj_t g_in, mp_obj_t b_in) {
    mp_int_t r = mp_obj_get_int(r_in) & 0xff;
    mp_int_t g = mp_obj_get_int(g_in) & 0xff;
    mp_int_t b = mp_obj_get_int(b_in) & 0xff;
    #if PICODVI_BPP == 16
    return MP_OBJ_NEW_SMALL_INT(((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3));
    #else
    return MP_OBJ_NEW_SMALL_INT((r & 0xe0) | ((g & 0xe0) >> 3) | (b >> 6));
    #endif
}
static MP_DEFINE_CONST_FUN_OBJ_3(picodvi_rgb_obj, picodvi_rgb);

// ---------------------------------------------------------------------------
// Anti-aliased text/icon rendering from .fnt blobs (see tools/mkassets.py).
// Fonts are normally memoryviews of /rom files, i.e. read straight from flash.

#define FNT_HDR 12

static inline uint32_t rd16(const uint8_t *p) {
    return p[0] | (p[1] << 8);
}

static inline uint32_t rd32(const uint8_t *p) {
    return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

typedef struct {
    const uint8_t *data;
    size_t len;
    uint32_t count;
} fnt_t;

static void fnt_get(mp_obj_t obj, fnt_t *f) {
    mp_buffer_info_t bi;
    mp_get_buffer_raise(obj, &bi, MP_BUFFER_READ);
    const uint8_t *d = bi.buf;
    if (bi.len < FNT_HDR || memcmp(d, "PDF1", 4) != 0 || d[10] != 4) {
        mp_raise_ValueError(MP_ERROR_TEXT("not a PDF1 font"));
    }
    f->data = d;
    f->len = bi.len;
    f->count = rd16(d + 8);
}

// Binary search the index; returns pointer to the glyph record or NULL.
static const uint8_t *fnt_glyph(const fnt_t *f, uint32_t cp) {
    int lo = 0, hi = (int)f->count - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        const uint8_t *e = f->data + FNT_HDR + 8 * mid;
        uint32_t c = rd32(e);
        if (c == cp) {
            return f->data + rd32(e + 4);
        } else if (c < cp) {
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return NULL;
}

// Decode one UTF-8 code point, advancing *s.
static uint32_t utf8_next(const uint8_t **s, const uint8_t *end) {
    const uint8_t *p = *s;
    uint32_t c = *p++;
    int extra = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc0 ? 1 : 0;
    c &= extra == 3 ? 0x07 : extra == 2 ? 0x0f : extra == 1 ? 0x1f : 0x7f;
    while (extra-- && p < end) {
        c = (c << 6) | (*p++ & 0x3f);
    }
    *s = p;
    return c;
}

#if PICODVI_BPP == 16
typedef uint16_t pix_t;
static inline pix_t blend(pix_t bg, pix_t fg, uint a) {
    uint br = bg >> 11, bgg = (bg >> 5) & 0x3f, bb = bg & 0x1f;
    uint fr = fg >> 11, fgg = (fg >> 5) & 0x3f, fb = fg & 0x1f;
    uint r = (fr * a + br * (15 - a) + 7) / 15;
    uint g = (fgg * a + bgg * (15 - a) + 7) / 15;
    uint b = (fb * a + bb * (15 - a) + 7) / 15;
    return (r << 11) | (g << 5) | b;
}
#else
typedef uint8_t pix_t;
static inline pix_t blend(pix_t bg, pix_t fg, uint a) {
    uint r = ((fg >> 5) * a + (bg >> 5) * (15 - a) + 7) / 15;
    uint g = (((fg >> 2) & 7) * a + ((bg >> 2) & 7) * (15 - a) + 7) / 15;
    uint b = ((fg & 3) * a + (bg & 3) * (15 - a) + 7) / 15;
    return (r << 5) | (g << 2) | b;
}
#endif

// Draws one glyph with its line top at (x, y). With bg >= 0 the whole glyph
// box is painted (alpha blended against bg), so text can be redrawn in place
// without clearing first; with bg < 0 it is blended over the framebuffer.
static void draw_glyph(const uint8_t *g, int x, int y, pix_t fg, int bg) {
    int w = rd16(g + 2), h = rd16(g + 4);
    int x0 = x + (int16_t)rd16(g + 6), y0 = y + (int16_t)rd16(g + 8);
    const uint8_t *bits = g + 10;
    int stride = (w + 1) / 2;
    pix_t *fb = (pix_t *)framebuf;
    for (int row = 0; row < h; ++row) {
        int py = y0 + row;
        if (py < 0 || py >= (int)frame_height) {
            continue;
        }
        const uint8_t *src = bits + row * stride;
        pix_t *dst = fb + py * frame_width;
        for (int col = 0; col < w; ++col) {
            int px = x0 + col;
            if (px < 0 || px >= (int)frame_width) {
                continue;
            }
            uint a = (src[col >> 1] >> ((col & 1) ? 0 : 4)) & 0xf;
            if (a == 15) {
                dst[px] = fg;
            } else if (bg >= 0) {
                dst[px] = a ? blend((pix_t)bg, fg, a) : (pix_t)bg;
            } else if (a) {
                dst[px] = blend(dst[px], fg, a);
            }
        }
    }
}

// draw_text(font, text, x, y, color, bg=-1) -> x after the last glyph.
// (x, y) is the top-left of the text line. Unknown characters are skipped.
static mp_obj_t picodvi_draw_text(size_t n_args, const mp_obj_t *args) {
    fnt_t f;
    fnt_get(args[0], &f);
    size_t len;
    const uint8_t *s = (const uint8_t *)mp_obj_str_get_data(args[1], &len);
    const uint8_t *end = s + len;
    int x = mp_obj_get_int(args[2]);
    int y = mp_obj_get_int(args[3]);
    pix_t fg = mp_obj_get_int(args[4]);
    int bg = n_args > 5 ? mp_obj_get_int(args[5]) : -1;
    while (s < end) {
        const uint8_t *g = fnt_glyph(&f, utf8_next(&s, end));
        if (g) {
            draw_glyph(g, x, y, fg, bg);
            x += rd16(g);
        }
    }
    return MP_OBJ_NEW_SMALL_INT(x);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(picodvi_draw_text_obj, 5, 6, picodvi_draw_text);

// text_width(font, text) -> advance width in pixels.
static mp_obj_t picodvi_text_width(mp_obj_t font_in, mp_obj_t text_in) {
    fnt_t f;
    fnt_get(font_in, &f);
    size_t len;
    const uint8_t *s = (const uint8_t *)mp_obj_str_get_data(text_in, &len);
    const uint8_t *end = s + len;
    int w = 0;
    while (s < end) {
        const uint8_t *g = fnt_glyph(&f, utf8_next(&s, end));
        if (g) {
            w += rd16(g);
        }
    }
    return MP_OBJ_NEW_SMALL_INT(w);
}
static MP_DEFINE_CONST_FUN_OBJ_2(picodvi_text_width_obj, picodvi_text_width);

// font_metrics(font) -> (line_height, ascent)
static mp_obj_t picodvi_font_metrics(mp_obj_t font_in) {
    fnt_t f;
    fnt_get(font_in, &f);
    mp_obj_t t[2] = { MP_OBJ_NEW_SMALL_INT(rd16(f.data + 4)), MP_OBJ_NEW_SMALL_INT(rd16(f.data + 6)) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_1(picodvi_font_metrics_obj, picodvi_font_metrics);

// blit(img, x, y): draws a PIM1 image (tools/wxicons.py: RGB565 + 8-bit alpha
// per pixel) alpha-blended over the framebuffer, clipped to the screen.
static inline uint32_t blend565_a8(uint32_t bg, uint32_t fg, uint32_t a) {
    // blend all three channels at once in a spread 32-bit word (0x07e0f81f trick)
    uint32_t b = (bg | (bg << 16)) & 0x07e0f81f;
    uint32_t f = (fg | (fg << 16)) & 0x07e0f81f;
    uint32_t r = ((((f - b) * (a >> 3)) >> 5) + b) & 0x07e0f81f;
    return (r | (r >> 16)) & 0xffff;
}

static mp_obj_t picodvi_blit(mp_obj_t img_in, mp_obj_t x_in, mp_obj_t y_in) {
    mp_buffer_info_t bi;
    mp_get_buffer_raise(img_in, &bi, MP_BUFFER_READ);
    const uint8_t *d = bi.buf;
    if (bi.len < 8 || memcmp(d, "PIM1", 4) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("not a PIM1 image"));
    }
    int w = rd16(d + 4), h = rd16(d + 6);
    if (bi.len < 8 + (size_t)w * h * 3) {
        mp_raise_ValueError(MP_ERROR_TEXT("truncated image"));
    }
    int x0 = mp_obj_get_int(x_in), y0 = mp_obj_get_int(y_in);
    const uint8_t *src = d + 8;
    pix_t *fb = (pix_t *)framebuf;
    for (int row = 0; row < h; ++row) {
        int py = y0 + row;
        if (py < 0 || py >= (int)frame_height) {
            src += w * 3;
            continue;
        }
        pix_t *dst = fb + py * frame_width;
        for (int col = 0; col < w; ++col, src += 3) {
            int px = x0 + col;
            uint32_t a = src[2];
            if (px < 0 || px >= (int)frame_width || a == 0) {
                continue;
            }
            uint32_t c = src[0] | (src[1] << 8);
            #if PICODVI_BPP == 16
            dst[px] = a >= 248 ? c : blend565_a8(dst[px], c, a);
            #else
            // RP2040: 565 -> 332, alpha quantised to 4 bits
            pix_t c8 = ((c >> 8) & 0xe0) | ((c >> 6) & 0x1c) | ((c >> 3) & 0x03);
            uint a4 = a >> 4;
            dst[px] = a4 >= 15 ? c8 : a4 ? blend(dst[px], c8, a4) : dst[px];
            #endif
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(picodvi_blit_obj, picodvi_blit);

// julia(x, y, w, h, c_re, c_im, step, palette, shift, maxit, mul, inside,
//       radius=0, ex_x=0, ex_y=0, ex_w=0, ex_h=0)
// Renders a Julia set z -> z^2 + c straight into the framebuffer region,
// fixed point Q13 (c_re, c_im, step are Q13 ints: 8192 = 1.0; the region is
// centred on 0). Colour = palette[(iterations * mul + shift) & 255] (palette:
// 256 native pixels as array('H')); points that do not escape get `inside`.
// radius rounds the region corners; the ex_* rectangle is left untouched
// (e.g. for a text overlay), so animation never flickers over it.
#define Q 13

// Pixels to skip at both ends of row j of a w x h rectangle with corner radius rad.
static int round_skip(int j, int h, int rad) {
    if (!rad) {
        return 0;
    }
    int dy = j < rad ? rad - j : (j >= h - rad ? j - (h - rad - 1) : 0);
    int k = 0;
    if (dy) {
        while (k < rad && (rad - k) * (rad - k) + dy * dy > rad * rad) {
            ++k;
        }
    }
    return k;
}

static mp_obj_t picodvi_julia(size_t n_args, const mp_obj_t *args) {
    int x0 = mp_obj_get_int(args[0]), y0 = mp_obj_get_int(args[1]);
    int w = mp_obj_get_int(args[2]), h = mp_obj_get_int(args[3]);
    int32_t cre = mp_obj_get_int(args[4]), cim = mp_obj_get_int(args[5]);
    int32_t step = mp_obj_get_int(args[6]);
    mp_buffer_info_t pal;
    mp_get_buffer_raise(args[7], &pal, MP_BUFFER_READ);
    if (pal.len < 512) {
        mp_raise_ValueError(MP_ERROR_TEXT("palette needs 256 entries"));
    }
    const uint16_t *palette = pal.buf;
    uint32_t shift = mp_obj_get_int(args[8]);
    int maxit = mp_obj_get_int(args[9]);
    uint32_t mul = mp_obj_get_int(args[10]);
    pix_t inside = mp_obj_get_int(args[11]);
    int rad = n_args > 12 ? mp_obj_get_int(args[12]) : 0;
    int ex = 0, ey = 0, ew = 0, eh = 0;
    if (n_args > 16) {
        ex = mp_obj_get_int(args[13]) - x0;
        ey = mp_obj_get_int(args[14]) - y0;
        ew = mp_obj_get_int(args[15]);
        eh = mp_obj_get_int(args[16]);
    }
    const int32_t four = 4 << Q;
    pix_t *fb = (pix_t *)framebuf;
    for (int j = 0; j < h; ++j) {
        int py = y0 + j;
        if (py < 0 || py >= (int)frame_height) {
            continue;
        }
        int skip = round_skip(j, h, rad);
        pix_t *dst = fb + py * frame_width;
        int32_t zi0 = (j - h / 2) * step;
        for (int i = skip; i < w - skip; ++i) {
            int px = x0 + i;
            if (px < 0 || px >= (int)frame_width) {
                continue;
            }
            if (i >= ex && i < ex + ew && j >= ey && j < ey + eh) {
                continue;
            }
            int32_t zr = (i - w / 2) * step, zi = zi0;
            int it = 0;
            const int32_t two = 2 << Q;
            while (it < maxit) {
                // |z| > 2 escapes; checking first also keeps the squares in int32
                if (zr > two || zr < -two || zi > two || zi < -two) {
                    break;
                }
                int32_t zr2 = (zr * zr) >> Q, zi2 = (zi * zi) >> Q;
                if (zr2 + zi2 > four) {
                    break;
                }
                zi = ((zr * zi) >> (Q - 1)) + cim;
                zr = zr2 - zi2 + cre;
                ++it;
            }
            dst[px] = it >= maxit ? inside : (pix_t)palette[(it * mul + shift) & 255];
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(picodvi_julia_obj, 12, 17, picodvi_julia);

// effect(kind, x, y, w, h, t, palette, radius=0)
// Palette-mapped procedural animations for small regions; t = time in ms.
//   0 plasma     - sum of travelling sine waves
//   1 metaballs  - "lava lamp" blobs on Lissajous paths
//   2 ripples    - interference of circular waves from moving sources
//   3 bloom      - kaleidoscope flower: counter-rotating petal layers with
//                  glowing rims, central rays and green filaments (own colours)
static int8_t sin8[256];  // sin(2*pi*i/256) * 127

static void sin8_init(void) {
    if (sin8[64]) {
        return;
    }
    // quarter-wave by integer recurrence would be overkill: use libm once
    for (int i = 0; i < 256; ++i) {
        float a = i * (6.2831853f / 256.0f);
        sin8[i] = (int8_t)(127.0f * __builtin_sinf(a));
    }
}

static inline int isin(int a) {
    return sin8[a & 255];
}

static uint32_t isqrt32(uint32_t v) {
    uint32_t r = 0, bit = 1u << 30;
    while (bit > v) {
        bit >>= 2;
    }
    while (bit) {
        if (v >= r + bit) {
            v -= r + bit;
            r = (r >> 1) + bit;
        } else {
            r >>= 1;
        }
        bit >>= 2;
    }
    return r;
}

// Polar coordinates of the effect region, computed once per region size.
#define POLAR_MAX (100 * 100)
static uint8_t polar_a[POLAR_MAX], polar_r[POLAR_MAX];
static int polar_w, polar_h;

static void polar_init(int w, int h) {
    if (w == polar_w && h == polar_h) {
        return;
    }
    for (int j = 0; j < h; ++j) {
        for (int i = 0; i < w; ++i) {
            float dx = i - w / 2 + 0.5f, dy = j - h / 2 + 0.5f;
            float a = __builtin_atan2f(dy, dx) * (256.0f / 6.2831853f);
            polar_a[j * w + i] = (uint8_t)(int)(a < 0 ? a + 256.0f : a);
            float r = __builtin_sqrtf(dx * dx + dy * dy);
            polar_r[j * w + i] = r > 255 ? 255 : (uint8_t)r;
        }
    }
    polar_w = w;
    polar_h = h;
}

static inline pix_t rgb_pix(int r, int g, int b) {
    r = r > 255 ? 255 : r;
    g = g > 255 ? 255 : g;
    b = b > 255 ? 255 : b;
    #if PICODVI_BPP == 16
    return ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3);
    #else
    return (r & 0xe0) | ((g & 0xe0) >> 3) | (b >> 6);
    #endif
}

static mp_obj_t picodvi_effect(size_t n_args, const mp_obj_t *args) {
    int kind = mp_obj_get_int(args[0]);
    int x0 = mp_obj_get_int(args[1]), y0 = mp_obj_get_int(args[2]);
    int w = mp_obj_get_int(args[3]), h = mp_obj_get_int(args[4]);
    uint32_t t = mp_obj_get_int(args[5]);
    mp_buffer_info_t pal;
    mp_get_buffer_raise(args[6], &pal, MP_BUFFER_READ);
    if (pal.len < 512) {
        mp_raise_ValueError(MP_ERROR_TEXT("palette needs 256 entries"));
    }
    const uint16_t *palette = pal.buf;
    int rad = n_args > 7 ? mp_obj_get_int(args[7]) : 0;
    sin8_init();
    if (kind == 3) {
        if (w * h > POLAR_MAX) {
            mp_raise_ValueError(MP_ERROR_TEXT("region too large"));
        }
        polar_init(w, h);
    }

    // per-frame parameters (positions in pixels, relative to the region)
    int bx[5], by[5];
    int nb = kind == 1 ? 5 : 3;
    for (int k = 0; k < nb; ++k) {
        int ph = k * 51;
        bx[k] = w / 2 + isin((t >> (4 + (k & 1))) + ph) * (w / 2 - 6) / 127;
        by[k] = h / 2 + isin((t >> 5) * (k + 2) / 2 + ph * 3 + 64) * (h / 2 - 6) / 127;
    }
    uint32_t tt = t >> 4;  // slow time base, 1 unit = 16 ms

    pix_t *fb = (pix_t *)framebuf;
    for (int j = 0; j < h; ++j) {
        int py = y0 + j;
        if (py < 0 || py >= (int)frame_height) {
            continue;
        }
        int skip = round_skip(j, h, rad);
        pix_t *dst = fb + py * frame_width;
        for (int i = skip; i < w - skip; ++i) {
            int px = x0 + i;
            if (px < 0 || px >= (int)frame_width) {
                continue;
            }
            int v;
            if (kind == 3) {
                int a = polar_a[j * w + i], r = polar_r[j * w + i];
                int R = (w < h ? w : h) / 2;
                // outer layer: 8 breathing petals, rotating
                int b1 = R * 3 / 4 + (isin(a * 8 + tt) * R / 6 >> 7);
                // inner layer: 12 petals, counter-rotating
                int b2 = R * 2 / 5 + (isin(a * 12 - tt * 2) * R / 9 >> 7);
                int d1 = r - b1 < 0 ? b1 - r : r - b1;
                int d2 = r - b2 < 0 ? b2 - r : r - b2;
                int blue = 0, red = 0, green = 0;
                if (r < b1) {
                    blue += 50 + r * 90 / (b1 + 1);  // translucent petal body
                    // speckled texture inside the petals
                    if (isin(a * 20 + r * 9 + tt) * isin(r * 13 - a * 6 - tt) > 7000) {
                        green += 110;
                    }
                }
                if (d1 < 4) {  // glowing outer rim, violet
                    blue += (4 - d1) * 45;
                    red += (4 - d1) * 30;
                }
                if (r < b2) {
                    blue += 40;
                }
                if (d2 < 3) {  // inner rim, brighter and cyan-ish
                    blue += (3 - d2) * 60;
                    green += (3 - d2) * 25;
                }
                int core = R / 3;
                if (r < core && isin(a * 24 + tt * 3) > 70) {  // central rays
                    blue += (core - r) * 200 / core;
                    red += (core - r) * 70 / core;
                }
                if (r < 4) {
                    blue += 255;
                    red += 120;
                    green += 60;
                }
                if (r > b1 + 2) {  // green filaments around the flower
                    int fade = 150 - (r - b1) * 10;
                    if (fade > 0 && isin(a * 48 + r * 6 - tt * 2) > 105) {
                        green += fade;
                        blue += fade / 4;
                    }
                }
                dst[px] = rgb_pix(red, green + blue / 6, blue);
                continue;
            }
            if (kind == 0) {
                // plasma: four waves in different directions and speeds
                v = isin(i * 3 + tt) + isin(j * 4 - tt * 2 / 3)
                    + isin((i + j) * 2 + tt / 2) + isin(isqrt32((i - bx[0]) * (i - bx[0]) + (j - by[0]) * (j - by[0])) * 6 - tt);
                v = (v + 508) >> 2;  // -508..508 -> 0..254
                v = (v + (tt >> 1)) & 255;
            } else if (kind == 1) {
                // metaballs: field = sum r^2 / d^2, banded into the palette
                int32_t f = 0;
                for (int k = 0; k < nb; ++k) {
                    int dx = i - bx[k], dy = j - by[k];
                    int32_t d2 = dx * dx + dy * dy + 1;
                    f += (int32_t)(150 * 1024) / d2;
                }
                // crisp blob surface at f = 1024, soft glow outside
                v = f >= 1024 ? 190 + (f - 1024 > 4095 ? 65 : (f - 1024) >> 6) : f * 150 >> 10;
            } else {
                // ripples: three circular wave sources
                v = 0;
                for (int k = 0; k < 3; ++k) {
                    int dx = i - bx[k], dy = j - by[k];
                    v += isin(isqrt32(dx * dx + dy * dy) * 7 - tt * 3);
                }
                v = (v + 381) * 255 / 762;
            }
            dst[px] = (pix_t)palette[v & 255];
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(picodvi_effect_obj, 7, 8, picodvi_effect);

// debug() -> (core1 stage, scanlines delivered, DMA IRQs, scanlines encoded,
//             q_tmds_valid, q_tmds_free, q_colour_valid, q_colour_free, late scanlines)
static mp_obj_t picodvi_debug(void) {
    extern volatile uint32_t dvi_dbg_irq, dvi_dbg_enc;
    mp_obj_t t[9] = {
        mp_obj_new_int_from_uint(dbg_stage),
        mp_obj_new_int_from_uint(dbg_lines),
        mp_obj_new_int_from_uint(dvi_dbg_irq),
        mp_obj_new_int_from_uint(dvi_dbg_enc),
        MP_OBJ_NEW_SMALL_INT(queue_get_level(&dvi0.q_tmds_valid)),
        MP_OBJ_NEW_SMALL_INT(queue_get_level(&dvi0.q_tmds_free)),
        MP_OBJ_NEW_SMALL_INT(queue_get_level(&dvi0.q_colour_valid)),
        MP_OBJ_NEW_SMALL_INT(queue_get_level(&dvi0.q_colour_free)),
        MP_OBJ_NEW_SMALL_INT(dvi0.late_scanline_ctr),
    };
    return mp_obj_new_tuple(9, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(picodvi_debug_obj, picodvi_debug);

static const mp_rom_map_elem_t picodvi_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_picodvi) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&picodvi_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&picodvi_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_framebuffer), MP_ROM_PTR(&picodvi_framebuffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_rgb), MP_ROM_PTR(&picodvi_rgb_obj) },
    { MP_ROM_QSTR(MP_QSTR_debug), MP_ROM_PTR(&picodvi_debug_obj) },
    { MP_ROM_QSTR(MP_QSTR_draw_text), MP_ROM_PTR(&picodvi_draw_text_obj) },
    { MP_ROM_QSTR(MP_QSTR_text_width), MP_ROM_PTR(&picodvi_text_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_font_metrics), MP_ROM_PTR(&picodvi_font_metrics_obj) },
    { MP_ROM_QSTR(MP_QSTR_blit), MP_ROM_PTR(&picodvi_blit_obj) },
    { MP_ROM_QSTR(MP_QSTR_julia), MP_ROM_PTR(&picodvi_julia_obj) },
    { MP_ROM_QSTR(MP_QSTR_effect), MP_ROM_PTR(&picodvi_effect_obj) },
    { MP_ROM_QSTR(MP_QSTR_size), MP_ROM_PTR(&picodvi_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_MODE_400x240), MP_ROM_INT(MODE_400x240) },
    { MP_ROM_QSTR(MP_QSTR_MODE_320x240), MP_ROM_INT(MODE_320x240) },
    { MP_ROM_QSTR(MP_QSTR_BPP), MP_ROM_INT(PICODVI_BPP) },
    // framebuf format constant matching the pixel layout (framebuf.GS8 / framebuf.RGB565)
    #if PICODVI_BPP == 16
    { MP_ROM_QSTR(MP_QSTR_FORMAT), MP_ROM_INT(1) },
    #else
    { MP_ROM_QSTR(MP_QSTR_FORMAT), MP_ROM_INT(6) },
    #endif
};
static MP_DEFINE_CONST_DICT(picodvi_module_globals, picodvi_module_globals_table);

const mp_obj_module_t picodvi_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&picodvi_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_picodvi, picodvi_user_cmodule);
