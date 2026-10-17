# Dashboard layout for 400x240: date + status bar, big clock, two sensor tiles.
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
        self._colon = None
        self._clock_box = None
        self._wifi = None
        self.tiles = [
            # x, label, icon, colour
            [8, "Заряд", "battery-unknown", self.FAINT],
            [204, "Споживання", "flash", self.AMBER],
        ]

    # --- full redraw ------------------------------------------------------
    def draw_all(self):
        d = self.d
        d.fill(self.BG)
        self._minute = self._date = self._colon = self._wifi = None
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

    # --- clock ------------------------------------------------------------
    def set_time(self, t, synced=True):
        """t: local time tuple. Redraws only what changed."""
        d = self.d
        date = tz.date_text(t) if synced else "очікую синхронізацію часу…"
        if date != self._date:
            self._date = date
            d.fill_rect(0, 0, d.w - 40, 36, self.BG)
            d.text("ui20", date[0].upper() + date[1:], 12, 8, self.DIM, self.BG)

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
    def set_tile(self, i, value, unit="", icon=None, color=None):
        d = self.d
        x, label, default_icon, default_color = self.tiles[i]
        y, w, h = 148, 188, 84
        d.round_rect(x, y, w, h, 10, self.PANEL)
        d.icon(icon or default_icon, 48, x + 10, y + 18, color or default_color)
        tx = x + 70
        if value is None:
            d.text("val36", "—", tx, y + 12, self.FAINT)
        else:
            vx = tx + d.text("val36", value, tx, y + 12, self.FG)
            if unit:
                d.text("ui20", unit, vx + 4, y + 26, self.DIM)
        d.text("ui16", label, tx, y + 56, self.DIM)

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

    def set_power(self, watts):
        if watts is None:
            self.set_tile(1, None)
        elif abs(watts) >= 1000:
            self.set_tile(1, ("%.2f" % (watts / 1000)).replace(".", ","), "кВт")
        else:
            self.set_tile(1, "%d" % round(watts), "Вт")
