# Home Assistant over its REST API: polls /api/states/<entity> with a long-lived
# access token (secrets.HA_TOKEN). No Home Assistant configuration needed.
import asyncio
import json

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
        self.api = url.rstrip("/") + "/api/"
        self.base = self.api + "states/"
        self.headers = {"Authorization": "Bearer " + secrets.HA_TOKEN,
                        "Content-Type": "application/json"}

    def _check(self, r):
        if r.status_code == 401:
            raise OSError("HA token rejected (401)")
        return r.status_code == 200

    def get_state(self, entity):
        """Full state object {"state": ..., "attributes": {...}} or None."""
        r = requests.get(self.base + entity, headers=self.headers, timeout=5)
        try:
            return r.json() if self._check(r) else None
        finally:
            r.close()

    def _fetch(self, entity):
        st = self.get_state(entity)
        return st["state"] if st else None

    def forecast(self, entity, kind="hourly"):
        """weather.get_forecasts -> list of forecast dicts (or None)."""
        r = requests.post(self.api + "services/weather/get_forecasts?return_response",
                          headers=self.headers, timeout=10,
                          data=json.dumps({"entity_id": entity, "type": kind}))
        try:
            if not self._check(r):
                return None
            return r.json()["service_response"][entity]["forecast"]
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
