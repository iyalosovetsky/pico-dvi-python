# Home dashboard on Waveshare PICO-DVI-LCD: clock now, Home Assistant tiles next.
import asyncio
import sys
import time

sys.path.append("/lib")

import net
import tz
from display import Display
from screen import Dashboard

d = Display()
ui = Dashboard(d)
ui.draw_all()
state = {"synced": False}


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
    await asyncio.gather(clock_task(), network_task())


asyncio.run(main())
