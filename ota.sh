#!/usr/bin/env bash
# Over-the-air update of the dashboard on the Pico (see tools/ota.py, device/lib/ota.py).
# Needs OTA_TOKEN and OTA_HOST in ./secrets.py (and the same OTA_TOKEN on the device).
#
#   ./ota.sh            upload changed files from device/ and reboot (same as "push")
#   ./ota.sh push       same
#   ./ota.sh romfs      rebuild nothing, just upload romfs/ (fonts, icons) and reboot
#   ./ota.sh assets     regenerate romfs/ (tools/mkassets.py), upload it and reboot
#   ./ota.sh all        assets + code: mkassets, romfs upload, then push
#   ./ota.sh info       files on the device, free RAM / flash
#   ./ota.sh reset      reboot the device
#   ./ota.sh put LOCAL REMOTE   upload one file, e.g. ./ota.sh put secrets.py /secrets.py
#
# The MicroPython firmware (.uf2) still has to be flashed over USB.
set -euo pipefail
cd "$(dirname "$0")"

# -I: the local secrets.py would otherwise shadow Python's own "secrets" module
ota() { python3 -I tools/ota.py "$@"; }

wait_online() {
    # after a reboot the device needs a few seconds for Wi-Fi + the OTA server
    for _ in $(seq 1 30); do
        if ota info >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "device did not come back online" >&2
    return 1
}

cmd="${1:-push}"
case "$cmd" in
    push)   ota push ;;
    romfs)  ota romfs ;;
    assets) python3 tools/mkassets.py && ota romfs ;;
    all)    python3 tools/mkassets.py && ota romfs && wait_online && ota push ;;
    info)   ota info ;;
    reset)  ota reset ;;
    put)    shift; ota put "$@" ;;
    *)      sed -n '2,15p' "$0"; exit 1 ;;
esac
