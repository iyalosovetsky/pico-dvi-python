# Home Assistant over MQTT: subscribes to mqtt_statestream topics of the
# configured entities and reports their states to a callback.
import asyncio
import time

from umqtt.simple import MQTTClient

import config
import net
import secrets


def state_topic(entity):
    domain, obj = entity.split(".", 1)
    return "%s/%s/%s/state" % (config.STATESTREAM_BASE, domain, obj)


def parse_number(payload):
    try:
        return float(payload)
    except ValueError:
        return None  # "unavailable", "unknown", ...


class HomeAssistant:
    def __init__(self, entities, on_state, on_status):
        self.topics = {state_topic(e).encode(): e for e in entities if e}
        self.on_state = on_state  # (entity_id, payload str)
        self.on_status = on_status  # (connected bool)
        self.status_topic = ("%s/status" % config.DEVICE_ID).encode()

    def _cb(self, topic, msg):
        entity = self.topics.get(bytes(topic))
        if entity:
            self.on_state(entity, msg.decode())

    def _connect(self):
        c = MQTTClient(config.DEVICE_ID, secrets.MQTT_HOST,
                       port=getattr(secrets, "MQTT_PORT", 1883),
                       user=getattr(secrets, "MQTT_USER", None),
                       password=getattr(secrets, "MQTT_PASS", None),
                       keepalive=60)
        c.set_last_will(self.status_topic, b"offline", retain=True)
        c.set_callback(self._cb)
        c.connect()
        c.publish(self.status_topic, b"online", retain=True)
        for t in self.topics:
            c.subscribe(t)
        return c

    async def run(self):
        while True:
            if not net.wlan.isconnected():
                await asyncio.sleep(2)
                continue
            c = None
            try:
                c = self._connect()
                self.on_status(True)
                last_ping = time.ticks_ms()
                while True:
                    c.check_msg()
                    if time.ticks_diff(time.ticks_ms(), last_ping) > 30000:
                        c.ping()
                        last_ping = time.ticks_ms()
                    await asyncio.sleep_ms(100)
            except (OSError, IndexError) as e:
                print("mqtt:", repr(e))
            finally:
                if c:
                    try:
                        c.sock.close()
                    except Exception:
                        pass
                self.on_status(False)
            await asyncio.sleep(5)
