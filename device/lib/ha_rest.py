# Home Assistant over its REST API: polls /api/states/<entity> with a long-lived
# access token (secrets.HA_TOKEN). No Home Assistant configuration needed.
import asyncio

import requests

import net
import secrets


class HomeAssistantREST:
    def __init__(self, entities, on_state, on_status, interval_s=5):
        self.entities = [e for e in entities if e]
        self.on_state = on_state  # (entity_id, state str)
        self.on_status = on_status  # (connected bool)
        self.interval_s = interval_s
        url = getattr(secrets, "HA_URL", None) or "http://%s:8123" % secrets.MQTT_HOST
        self.base = url.rstrip("/") + "/api/states/"
        self.headers = {"Authorization": "Bearer " + secrets.HA_TOKEN}

    def _fetch(self, entity):
        r = requests.get(self.base + entity, headers=self.headers, timeout=5)
        try:
            if r.status_code == 200:
                return r.json()["state"]
            if r.status_code == 401:
                raise OSError("HA token rejected (401)")
            return None  # 404: no such entity
        finally:
            r.close()

    async def run(self):
        while True:
            if not net.wlan.isconnected():
                self.on_status(False)
                await asyncio.sleep(2)
                continue
            ok = True
            for e in self.entities:
                try:
                    state = self._fetch(e)
                    if state is not None:
                        self.on_state(e, state)
                except (OSError, ValueError, KeyError) as ex:
                    print("ha rest:", e, repr(ex))
                    ok = False
                    break
                await asyncio.sleep_ms(0)  # let the clock tick between requests
            self.on_status(ok)
            await asyncio.sleep(self.interval_s)
