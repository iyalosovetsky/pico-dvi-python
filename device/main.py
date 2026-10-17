# Home dashboard on Waveshare PICO-DVI-LCD: clock + Home Assistant tiles
# (REST API if secrets.HA_TOKEN is set, otherwise MQTT statestream).
import asyncio
import sys
import time

sys.path.append("/lib")

from display import Display  # starts DVI first: it rescales the Wi-Fi SPI clock

d = Display()

import config  # noqa: E402
import net  # noqa: E402
import tz  # noqa: E402
import secrets  # noqa: E402
from ha import HomeAssistant, parse_number  # noqa: E402
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


def redraw_battery():
    ch = charging()
    if state["soc"] is not None:
        ui.set_battery(state["soc"], bool(ch))
    else:
        ui.set_voltage(state["volts"], ch)
    ui.set_power(state["power"], ch)


def on_state(entity, payload):
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
        if now != last:
            last = now
            ui.set_time(tz.localtime(now), state["synced"])
        await asyncio.sleep_ms(50)


async def network_task():
    next_sync = 0
    while True:
        ok = await net.connect()
        ui.set_wifi(ok, net.rssi() if ok else None)
        if ok and time.ticks_diff(time.ticks_ms(), next_sync) >= 0:
            if net.sync_time():
                state["synced"] = True
                next_sync = time.ticks_add(time.ticks_ms(), 6 * 3600 * 1000)
            else:
                next_sync = time.ticks_add(time.ticks_ms(), 30 * 1000)
        await asyncio.sleep(5)


async def main():
    entities = (config.BATTERY_SOC, config.BATTERY_VOLTAGE, config.BATTERY_POWER,
                config.BATTERY_STATE, config.LOAD_POWER, config.GRID)
    if getattr(secrets, "HA_TOKEN", None):
        # REST API with a long-lived token: works without any HA configuration
        from ha_rest import HomeAssistantREST
        ha = HomeAssistantREST(entities, on_state, ui.set_mqtt)
    else:
        # MQTT: needs mqtt_statestream in HA's configuration.yaml
        ha = HomeAssistant(entities, on_state, ui.set_mqtt)
    await asyncio.gather(clock_task(), network_task(), ha.run())


asyncio.run(main())
