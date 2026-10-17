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
