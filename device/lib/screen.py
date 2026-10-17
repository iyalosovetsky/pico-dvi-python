# Dashboard layout for 400x240: date + status bar; weather now | clock | warning;
# three sensor tiles.
import array
import math

import picodvi

import config
import tz


def make_palette(rgb, stops, cyclic=True):
    """256-entry gradient through colour stops (cyclic, or a linear ramp)."""
    pal = array.array("H", bytes(512))
    n = len(stops) if cyclic else len(stops) - 1
    for i in range(256):
        f = i * n / (256 if cyclic else 255)
        k = min(int(f), n - 1) if not cyclic else int(f)
        t = f - k
        t = t * t * (3 - 2 * t)  # smoothstep between stops
        a, b = stops[k], stops[(k + 1) % n]
        pal[i] = rgb(*(int(a[j] + (b[j] - a[j]) * t) for j in range(3)))
    return pal


class Dashboard:
    def __init__(self, d):
        self.d = d
        rgb = d.rgb
        self.BG = rgb(14, 17, 22)
        self.PANEL = rgb(28, 33, 41)
        self.FG = rgb(236, 239, 244)
        self.DIM = rgb(130, 142, 156)
        self.FAINT = rgb(70, 78, 90)
        self.ACCENT = rgb(79, 195, 247)
        self.AMBER = rgb(255, 179, 0)
        self.GREEN = rgb(102, 187, 106)
        self.YELLOW = rgb(253, 216, 53)
        self.RED = rgb(239, 83, 80)
        self._minute = None
        self._date = None
        self._date_w = 0
        self._colon = None
        self._clock_box = None
        self._wifi = None
        self._mqtt = None
        self._grid = None
        self._wx = None
        self._warn = None
        self._anim_right = config.ANIM_RIGHT  # no warning yet -> animate

        self.PAL_SKY = make_palette(rgb, ((20, 24, 70), (64, 40, 160), (190, 70, 200),
                                          (255, 140, 120), (80, 200, 255), (30, 90, 200)))
        self.PAL_PLASMA = make_palette(rgb, ((40, 10, 90), (200, 40, 160), (255, 150, 60),
                                             (255, 230, 120), (60, 200, 220), (20, 60, 160)))
        self.PAL_LAVA = make_palette(rgb, ((14, 17, 22), (50, 8, 40), (120, 20, 60), (200, 40, 50),
                                           (250, 120, 40), (255, 200, 80), (255, 245, 200)), False)
        self.PAL_OCEAN = make_palette(rgb, ((5, 20, 60), (10, 80, 150), (40, 170, 220),
                                            (200, 245, 255), (40, 170, 220), (10, 80, 150)))
        self.tiles = [
            # x, label, icon, colour
            [8, "Батарея", "battery-unknown", self.FAINT],
            [138, "Батарея", "flash", self.FAINT],
            [268, "Будинок", "home-lightning-bolt", self.ACCENT],
        ]

    # --- full redraw ------------------------------------------------------
    def draw_all(self):
        d = self.d
        d.fill(self.BG)
        self._minute = self._date = self._colon = self._wifi = self._mqtt = self._grid = None
        self._wx = self._warn = None
        self._anim_right = config.ANIM_RIGHT
        self._date_w = 0
        for i in range(len(self.tiles)):
            self.set_tile(i, None)

    # --- top bar ----------------------------------------------------------
    def set_wifi(self, ok, rssi=None):
        state = (ok, rssi is not None and rssi > -67)
        if state == self._wifi:
            return
        self._wifi = state
        if not ok:
            name, c = "wifi-off", self.RED
        elif rssi is None:
            name, c = "wifi", self.DIM
        else:
            name = "wifi-strength-4" if rssi > -55 else "wifi-strength-3" if rssi > -67 else "wifi-strength-2" if rssi > -75 else "wifi-strength-1"
            c = self.DIM
        self.d.icon(name, 24, self.d.w - 32, 6, c, self.BG)

    def set_mqtt(self, ok):
        if ok == self._mqtt:
            return
        self._mqtt = ok
        x = self.d.w - 62
        if ok:
            self.d.fill_rect(x, 6, 24, 24, self.BG)
        else:
            self.d.icon("lan-disconnect", 24, x, 6, self.RED, self.BG)

    def set_grid(self, on):
        """Grid presence: True / False / None (unknown)."""
        if on == self._grid:
            return
        self._grid = on
        d = self.d
        x = d.w - 92
        d.fill_rect(x - 110, 6, 134, 24, self.BG)
        if on is None:
            return
        if on:
            d.icon("transmission-tower", 24, x, 6, self.DIM, self.BG)
        else:
            d.icon("transmission-tower-off", 24, x, 6, self.RED, self.BG)
            d.text("ui16", "немає мережі", x - 4, 10, self.RED, self.BG, "r")

    # --- weather (left: now, right: bad-weather warning) -------------------
    CLOCK_Y = 40
    SIDE_W = 100

    def set_weather(self, icon, temp):
        """icon: weather.icon_for() name or None; temp in °C or None."""
        key = (icon, None if temp is None else round(temp))
        if key == self._wx:
            return
        self._wx = key
        d = self.d
        d.fill_rect(0, 38, self.SIDE_W, 104, self.BG)
        if icon:
            d.image("wx/%s_56.pim" % icon, (self.SIDE_W - 56) // 2, 40)
        if temp is not None:
            d.text("val36", "%d°" % round(temp), self.SIDE_W // 2 + 4, 96, self.FG, self.BG, "c")

    def set_warning(self, w):
        """w: weather.find_warning() dict or None (area left empty)."""
        key = None if w is None else (w["icon"], w["title"], w["detail"], w["when"])
        if key == self._warn:
            return
        self._warn = key
        d = self.d
        x0 = d.w - self.SIDE_W
        d.fill_rect(x0, 38, self.SIDE_W, 104, self.BG)
        if w is None:
            self._anim_right = config.ANIM_RIGHT
            return
        self._anim_right = False
        cx = x0 + self.SIDE_W // 2
        d.image("wx/%s_44.pim" % w["icon"], cx - 22, 40)
        d.text("ui16", w["title"], cx, 86, self.AMBER, self.BG, "c")
        if w["detail"]:
            d.text("ui16", w["detail"], cx, 104, self.FG, self.BG, "c")
        d.text("ui16", w["when"], cx, 122 if w["detail"] else 104, self.DIM, self.BG, "c")

    # --- clock ------------------------------------------------------------
    def set_time(self, t, synced=True):
        """t: local time tuple. Redraws only what changed."""
        d = self.d
        date = tz.date_text(t) if synced else "синхронізація часу…"
        if date != self._date:
            self._date = date
            # clear exactly what the previous text covered (it may be wider)
            d.fill_rect(12, 6, self._date_w, 26, self.BG)
            self._date_w = d.text("ui20", date[0].upper() + date[1:], 12, 8, self.DIM, self.BG)

        minute = (t[3], t[4]) if synced else None
        if minute != self._minute or self._clock_box is None:
            self._minute = minute
            hh, mm = ("%02d" % t[3], "%02d" % t[4]) if synced else ("--", "--")
            wh = d.text_width("clock80", hh)
            wc = d.text_width("clock80", ":")
            wm = d.text_width("clock80", mm)
            x = (d.w - (wh + wc + wm)) // 2
            y = self.CLOCK_Y
            if self._clock_box:
                bx, bw = self._clock_box
                d.fill_rect(bx, y, bw, 90, self.BG)
            d.text("clock80", hh, x, y, self.FG, self.BG)
            d.text("clock80", mm, x + wh + wc, y, self.FG, self.BG)
            self._clock_box = (x, wh + wc + wm)
            self._colon_x = x + wh
            self._colon = None

        colon = (t[5] % 2 == 0) or not synced
        if colon != self._colon:
            self._colon = colon
            d.text("clock80", ":", self._colon_x, self.CLOCK_Y, self.FG if colon else self.FAINT, self.BG)

        # thin seconds progress line under the clock
        if synced:
            y = 132
            x0 = 108
            full = d.w - 2 * x0
            done = full * t[5] // 59
            d.fill_rect(x0, y, done, 2, self.ACCENT)
            d.fill_rect(x0 + done, y, full - done, 2, self.PANEL)

    # --- tiles ------------------------------------------------------------
    TILE_Y, TILE_W, TILE_H = 148, 124, 84

    def set_tile(self, i, value, unit="", icon=None, color=None, label=None):
        d = self.d
        x, default_label, default_icon, default_color = self.tiles[i]
        y = self.TILE_Y
        d.round_rect(x, y, self.TILE_W, self.TILE_H, 10, self.PANEL)
        d.icon(icon or default_icon, 24, x + 8, y + 9, color or default_color)
        d.text("ui16", label or default_label, x + 36, y + 13, self.DIM)
        if value is None:
            d.text("val36", "—", x + 10, y + 38, self.FAINT)
            return x + 10
        vx = x + 10 + d.text("val36", value, x + 10, y + 38, self.FG)
        if unit:
            vx += 3 + d.text("ui16", unit, vx + 3, y + 55, self.DIM)
        return vx

    def _fits(self, value, unit):
        return self.d.text_width("val36", value) + 3 + self.d.text_width("ui16", unit) <= self.TILE_W - 16

    def _power_text(self, watts):
        w = abs(watts)
        if w < 1000:
            return "%d" % round(w), "Вт"
        for fmt in ("%.2f", "%.1f", "%.0f"):
            v = (fmt % (w / 1000)).replace(".", ",")
            if self._fits(v, "кВт"):
                break
        return v, "кВт"

    def animate(self, t_ms):
        """Draws one frame of the current animation into the right slot."""
        if not self._anim_right:
            return
        x0, y0, w, h = self.d.w - self.SIDE_W + 4, 40, self.SIDE_W - 8, 96
        kind = (t_ms // (config.ANIM_SWITCH_S * 1000)) % 5
        if kind == 0:
            a = (t_ms % 9000) * (2 * math.pi / 9000)
            cre, cim = int(0.7885 * 8192 * math.cos(a)), int(0.7885 * 8192 * math.sin(a))
            picodvi.julia(x0, y0, w, h, cre, cim, 230, self.PAL_SKY,
                          (t_ms // 30) & 255, 40, 10, self.BG, 14)
        else:
            # 1 plasma, 2 lava lamp, 3 ripples, 4 bloom (own colours)
            pal = (self.PAL_PLASMA, self.PAL_LAVA, self.PAL_OCEAN, self.PAL_PLASMA)[kind - 1]
            picodvi.effect(kind - 1, x0, y0, w, h, t_ms, pal, 14)

    def set_voltage(self, volts, charging=None):
        if volts is None:
            self.set_tile(0, None)
            return
        icon = "battery-charging" if charging else "battery"
        color = self.GREEN if charging else self.AMBER if charging is False else self.DIM
        self.set_tile(0, ("%.1f" % volts).replace(".", ","), "В", icon, color)

    def set_battery(self, percent, charging=False, volts=None):
        """SOC tile; below BATTERY_VOLT_SHOW_BELOW the voltage is shown next to it."""
        if percent is None:
            self.set_tile(0, None)
            return
        p = max(0, min(100, int(percent + 0.5)))
        step = (p + 5) // 10 * 10
        if charging:
            icon = "battery-charging" if step >= 100 else "battery-charging-outline" if step == 0 else "battery-charging-%d" % step
        else:
            icon = "battery" if step >= 100 else "battery-alert-variant-outline" if step == 0 else "battery-%d" % step
        color = self.GREEN if p > 50 else self.YELLOW if p > 20 else self.RED
        show_v = volts is not None and volts < config.BATTERY_VOLT_SHOW_BELOW
        vtext = ("%.1f В" % volts).replace(".", ",") if show_v else None
        x = self.tiles[0][0]
        label = None
        # voltage next to the percent if it fits, otherwise instead of the label
        if show_v and self.d.text_width("val36", "%d" % p) + self.d.text_width("ui16", "% " + vtext) + 16 > self.TILE_W - 16:
            label, vtext = vtext, None
        end = self.set_tile(0, "%d" % p, "%", icon, color, label)
        if vtext:
            self.d.text("ui16", vtext, end + 6, self.TILE_Y + 55, self.YELLOW)

    def set_power(self, watts, charging=None):
        """Battery power in W; charging: True / False / None (idle)."""
        if watts is None:
            self.set_tile(1, None)
            return
        if charging is None:
            label, color = "Простій", self.DIM
        elif charging:
            label, color = "Заряд", self.GREEN
        else:
            label, color = "Розряд", self.AMBER
        v, unit = self._power_text(watts)
        self.set_tile(1, v, unit, "flash", color, label)

    def set_load(self, watts):
        if watts is None:
            self.set_tile(2, None)
            return
        v, unit = self._power_text(watts)
        self.set_tile(2, v, unit)
