# What the dashboard shows. The entities must be published to MQTT by Home
# Assistant's mqtt_statestream integration (topic: <base>/<domain>/<object_id>/state).
STATESTREAM_BASE = "ha"

# Entity names follow the ha-solarman Deye hybrid profile (device "Inverter").
BATTERY_SOC = "sensor.inverter_battery"  # %; until it arrives the voltage is shown
BATTERY_VOLTAGE = "sensor.inverter_battery_voltage"  # V
BATTERY_POWER = "sensor.inverter_battery_power"  # W
BATTERY_STATE = "sensor.inverter_battery_state"  # charging / idle / discharging (or 0 / 1 / 2)
LOAD_POWER = "sensor.inverter_load_power"  # W, house consumption
GRID = "binary_sensor.inverter_grid"  # on / off

# BATTERY_STATE value -> True (charging), False (discharging), None (idle).
# ha-solarman: options ["charging", "idle", "discharging"] (index 0 / 1 / 2).
BATTERY_STATE_MAP = {"0": True, "1": None, "2": False,
                     "charge": True, "charging": True, "discharge": False,
                     "discharging": False, "stand-by": None, "standby": None, "idle": None}

# Used only when BATTERY_STATE is not available:
# sign convention of BATTERY_POWER, True if a positive value means charging.
POWER_POSITIVE_IS_CHARGING = False
# Below this |W| the battery is shown as idle.
POWER_IDLE_W = 20

# MQTT client id and availability topic (picodvi/status: online / offline).
DEVICE_ID = "picodvi"

# --- Weather (Home Assistant REST only) ------------------------------------
WEATHER = "weather.forecast_golovna"
SUN = "sun.sun"
WEATHER_REFRESH_S = 600  # forecast refresh period
# Show a warning on the right of the clock if within WARN_HOURS any hour has:
WARN_HOURS = 12
WARN_RAIN_MM_H = 2.0  # rain, mm per hour ("significant")
WARN_SNOW_MM_H = 0.5  # snow / sleet, mm per hour (water equivalent)
WARN_WIND_KMH = 30  # wind or gusts, km/h; "Шквал" from 1.4x (42 km/h)
# thunderstorm, hail and "exceptional" always warn

# --- Fractal animation -------------------------------------------------------
# Right of the clock, whenever there is no bad-weather warning. Rotates:
# Julia set, plasma, lava lamp, water ripples, kaleidoscope flower.
ANIM_RIGHT = True
ANIM_SWITCH_S = 20  # seconds per animation
ANIM_FRAME_MS = 40

# Battery tile: show the voltage next to the SOC when it is below this (V).
BATTERY_VOLT_SHOW_BELOW = 53.0
