include("$(PORT_DIR)/boards/manifest.py")

require("bundle-networking")

# Bluetooth
require("aioble")

# MQTT client for the Home Assistant dashboard
require("umqtt.simple")
