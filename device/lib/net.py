# Wi-Fi + NTP helpers (credentials come from secrets.py on the device).
import asyncio
import time

import network
import ntptime

import secrets

wlan = network.WLAN(network.STA_IF)


async def connect(timeout_s=20):
    if wlan.isconnected():
        return True
    wlan.active(True)
    wlan.config(pm=wlan.PM_NONE)  # no power save: lower latency for MQTT
    hostname = getattr(secrets, "HOSTNAME", "picodvi")
    try:
        network.hostname(hostname)
    except Exception:
        pass
    wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
    for _ in range(timeout_s * 4):
        if wlan.isconnected():
            return True
        await asyncio.sleep_ms(250)
    return False


def rssi():
    try:
        return wlan.status("rssi")
    except Exception:
        return None


def sync_time():
    """Sets the RTC to UTC from NTP. Returns True on success."""
    ntptime.host = getattr(secrets, "NTP_HOST", "pool.ntp.org")
    try:
        ntptime.settime()
        return time.gmtime()[0] >= 2025
    except Exception:
        return False
