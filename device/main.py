# Home dashboard on Waveshare PICO-DVI-LCD: clock + Home Assistant tiles
# (REST API if secrets.HA_TOKEN is set, otherwise MQTT statestream).
import asyncio
import gc
import sys
import time

sys.path.append("/lib")

from display import Display  # starts DVI first: it rescales the Wi-Fi SPI clock

d = Display()

import config  # noqa: E402
import net  # noqa: E402
import ota  # noqa: E402
import tz  # noqa: E402
import secrets  # noqa: E402
from ha import HomeAssistant, parse_number  # noqa: E402
import weather  # noqa: E402
from screen import Dashboard  # noqa: E402

ui = Dashboard(d)
ui.draw_all()
state = {"synced": False, "soc": None, "volts": None, "power": None, "status": None}


def charging():
    """True / False / None (idle or unknown), from the status sensor if present."""
    status = state["status"]
    if status is not None and status in config.BATTERY_STATE_MAP:
        return config.BATTERY_STATE_MAP[status]
    power = state["power"]
    if power is None or abs(power) < config.POWER_IDLE_W:
        return None
    return (power > 0) == config.POWER_POSITIVE_IS_CHARGING


def set_link(ok):
    if not ota.busy:
        ui.set_mqtt(ok)


def redraw_battery():
    ch = charging()
    if state["soc"] is not None:
        ui.set_battery(state["soc"], bool(ch), state["volts"])
    else:
        ui.set_voltage(state["volts"], ch)
    ui.set_power(state["power"], ch)


def on_state(entity, payload):
    if ota.busy:
        return
    if entity == config.BATTERY_STATE:
        status = payload.strip().lower()
        n = parse_number(status)
        state["status"] = str(int(n)) if n is not None else status  # "0.0" -> "0"
    elif entity == config.BATTERY_POWER:
        state["power"] = parse_number(payload)
    elif entity == config.BATTERY_VOLTAGE:
        state["volts"] = parse_number(payload)
    elif entity == config.BATTERY_SOC:
        state["soc"] = parse_number(payload)
    elif entity == config.LOAD_POWER:
        ui.set_load(parse_number(payload))
        return
    elif entity == config.GRID:
        p = payload.strip().lower()
        ui.set_grid(True if p == "on" else False if p == "off" else None)
        return
    redraw_battery()


async def clock_task():
    last = None
    while True:
        now = time.time()
        if now != last and not ota.busy:
            last = now
            ui.set_time(tz.localtime(now), state["synced"])
        await asyncio.sleep_ms(50)


async def network_task():
    next_sync = 0
    while True:
        ok = await net.connect()
        if not ota.busy:
            ui.set_wifi(ok, net.rssi() if ok else None)
        if ok and time.ticks_diff(time.ticks_ms(), next_sync) >= 0:
            if net.sync_time():
                state["synced"] = True
                next_sync = time.ticks_add(time.ticks_ms(), 6 * 3600 * 1000)
            else:
                next_sync = time.ticks_add(time.ticks_ms(), 30 * 1000)
        await asyncio.sleep(5)


async def anim_task():
    while True:
        t0 = time.ticks_ms()
        if not ota.busy:
            ui.animate(t0)
        spent = time.ticks_diff(time.ticks_ms(), t0)
        await asyncio.sleep_ms(max(5, config.ANIM_FRAME_MS - spent))


async def weather_task(ha):
    hourly, sun, next_fetch = None, None, 0
    while True:
        if ota.busy:
            await asyncio.sleep(1)
            continue
        if net.wlan.isconnected() and time.ticks_diff(time.ticks_ms(), next_fetch) >= 0:
            try:
                st = ha.get_state(config.WEATHER)
                sun_st = ha.get_state(config.SUN)
                sun = sun_st["attributes"] if sun_st else None
                hourly = None  # free the old forecast before parsing the new one
                gc.collect()
                hourly = ha.forecast(config.WEATHER, "hourly")
                # keep only what the warning logic needs
                hourly = [{k: f.get(k) for k in ("datetime", "condition", "precipitation",
                                                 "wind_speed", "wind_gust_speed")}
                          for f in hourly[:config.WARN_HOURS + 1]] if hourly else None
                gc.collect()
                if st:
                    night = weather.is_night(time.time(), sun)
                    ui.set_weather(weather.icon_for(st["state"], night),
                                   st["attributes"].get("temperature"))
                next_fetch = time.ticks_add(time.ticks_ms(), config.WEATHER_REFRESH_S * 1000)
            except (OSError, ValueError, KeyError) as e:
                print("weather:", repr(e))
                next_fetch = time.ticks_add(time.ticks_ms(), 60 * 1000)
        if state["synced"] and hourly is not None:
            ui.set_warning(weather.find_warning(hourly, time.time()))
        # retry quickly until the first forecast arrives, then once a minute
        await asyncio.sleep(60 if hourly is not None else 5)


async def main():
    entities = (config.BATTERY_SOC, config.BATTERY_VOLTAGE, config.BATTERY_POWER,
                config.BATTERY_STATE, config.LOAD_POWER, config.GRID)
    tasks = [clock_task(), network_task(), anim_task(), ota.serve()]
    if getattr(secrets, "HA_TOKEN", None):
        # REST API with a long-lived token: works without any HA configuration
        from ha_rest import HomeAssistantREST
        ha = HomeAssistantREST(entities, on_state, set_link)
        tasks.append(weather_task(ha))
    else:
        # MQTT: needs mqtt_statestream in HA's configuration.yaml (no weather)
        ha = HomeAssistant(entities, on_state, set_link)
    tasks.append(ha.run())
    await asyncio.gather(*tasks)


asyncio.run(main())
