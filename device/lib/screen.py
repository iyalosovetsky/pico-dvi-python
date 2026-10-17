# Dashboard layout for 400x240: date + status bar, big clock, three sensor tiles.
import tz


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
            wh = d.text_width("clock96", hh)
            wc = d.text_width("clock96", ":")
            wm = d.text_width("clock96", mm)
            x = (d.w - (wh + wc + wm)) // 2
            y = 30
            if self._clock_box:
                bx, bw = self._clock_box
                d.fill_rect(bx, y, bw, 100, self.BG)
            d.text("clock96", hh, x, y, self.FG, self.BG)
            d.text("clock96", mm, x + wh + wc, y, self.FG, self.BG)
            self._clock_box = (x, wh + wc + wm)
            self._colon_x = x + wh
            self._colon = None

        colon = (t[5] % 2 == 0) or not synced
        if colon != self._colon:
            self._colon = colon
            d.text("clock96", ":", self._colon_x, 30, self.FG if colon else self.FAINT, self.BG)

        # thin seconds progress line under the clock
        if synced:
            y = 134
            full = d.w - 120
            x0 = 60
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
        else:
            vx = x + 10 + d.text("val36", value, x + 10, y + 38, self.FG)
            if unit:
                d.text("ui16", unit, vx + 3, y + 55, self.DIM)

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

    def set_voltage(self, volts, charging=None):
        if volts is None:
            self.set_tile(0, None)
            return
        icon = "battery-charging" if charging else "battery"
        color = self.GREEN if charging else self.AMBER if charging is False else self.DIM
        self.set_tile(0, ("%.1f" % volts).replace(".", ","), "В", icon, color)

    def set_battery(self, percent, charging=False):
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
        self.set_tile(0, "%d" % p, "%", icon, color)

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
