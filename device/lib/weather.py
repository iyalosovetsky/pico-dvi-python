# Weather helpers: icon choice and "bad weather ahead" detection from a Home
# Assistant weather entity (weather.get_forecasts hourly data).
import time

import config
import tz

LABELS = {
    "sunny": "Сонячно", "clear-night": "Ясно", "partlycloudy": "Хмарно з проясн.",
    "cloudy": "Хмарно", "fog": "Туман", "rainy": "Дощ", "pouring": "Злива",
    "snowy": "Сніг", "snowy-rainy": "Мокрий сніг", "hail": "Град",
    "lightning": "Гроза", "lightning-rainy": "Гроза", "windy": "Вітер",
    "windy-variant": "Вітер", "exceptional": "Небезпечно",
}
ICONS = set(LABELS) | {"partlycloudy-night"}


def parse_iso_utc(s):
    """'2026-10-17T09:00:00+00:00' -> UTC epoch seconds (offset honoured)."""
    t = time.mktime((int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), 0, 0, 0, 0))
    if len(s) >= 25 and s[19] in "+-":
        off = int(s[20:22]) * 3600 + int(s[23:25]) * 60
        t -= off if s[19] == "+" else -off
    return t


def icon_for(condition, night=False):
    if condition == "partlycloudy" and night:
        return "partlycloudy-night"
    if condition == "sunny" and night:
        return "clear-night"
    return condition if condition in ICONS else "cloudy"


def is_night(utc, sun):
    """sun: dict with next_rising / next_setting ISO strings (sun.sun attributes)."""
    try:
        rise = parse_iso_utc(sun["next_rising"]) % 86400
        sett = parse_iso_utc(sun["next_setting"]) % 86400
    except (KeyError, TypeError, ValueError):
        h = tz.localtime(utc)[3]
        return h < 7 or h >= 19
    t = utc % 86400
    return not (rise <= t < sett) if rise < sett else (sett <= t < rise)


def _hazard(f):
    """Returns (icon condition, title, detail) if this forecast hour is bad weather."""
    c = f.get("condition")
    p = f.get("precipitation") or 0
    wind = max(f.get("wind_gust_speed") or 0, f.get("wind_speed") or 0)
    if c in ("lightning", "lightning-rainy"):
        return c, "Гроза", "%s мм/год" % _mm(p) if p else ""
    if c == "hail":
        return c, "Град", ""
    if c == "exceptional":
        return c, "Небезпечно", ""
    if c in ("snowy", "snowy-rainy") and p >= config.WARN_SNOW_MM_H:
        return c, LABELS[c], "%s мм/год" % _mm(p)
    if c == "pouring" or p >= config.WARN_RAIN_MM_H:
        heavy = c == "pouring" or p >= 2 * config.WARN_RAIN_MM_H
        return ("pouring" if heavy else "rainy"), ("Злива" if heavy else "Дощ"), "%s мм/год" % _mm(p)
    if wind >= config.WARN_WIND_KMH:
        return "windy", "Шквал" if wind >= 1.4 * config.WARN_WIND_KMH else "Вітер", "%d км/год" % round(wind)
    return None


def _mm(p):
    return ("%.1f" % p).replace(".", ",").replace(",0", "")


def find_warning(hourly, now_utc):
    """First bad-weather hour within WARN_HOURS. Returns dict or None:
    {"icon": condition, "title": "Дощ", "detail": "5 мм/год", "when": "о 15:00" / "зараз"}"""
    horizon = now_utc + config.WARN_HOURS * 3600
    for f in hourly or ():
        try:
            t = parse_iso_utc(f["datetime"])
        except (KeyError, ValueError):
            continue
        if t + 3600 <= now_utc or t > horizon:
            continue
        hz = _hazard(f)
        if hz:
            lt = tz.localtime(t)
            when = "зараз" if t <= now_utc else "о %02d:00" % lt[3]
            return {"icon": hz[0], "title": hz[1], "detail": hz[2], "when": when}
    return None
