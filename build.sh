#!/usr/bin/env bash
# Builds MicroPython with the picodvi module.
# Usage: ./build.sh [PICO2_W_DVI|PICO_W_DVI]   (default: PICO2_W_DVI)
#        MP_DIR=/path/to/micropython ./build.sh
# Clones MicroPython into ./micropython if MP_DIR is not given.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOARD="${1:-PICO2_W_DVI}"
MP_VERSION="${MP_VERSION:-v1.29.0}"
MP_DIR="${MP_DIR:-$HERE/micropython}"

if [ ! -d "$HERE/boards/$BOARD" ]; then
    echo "unknown board $BOARD" >&2
    exit 1
fi

if [ ! -d "$MP_DIR" ]; then
    git clone --depth 1 -b "$MP_VERSION" https://github.com/micropython/micropython.git "$MP_DIR"
fi

make -C "$MP_DIR/mpy-cross" -j"$(nproc)"
make -C "$MP_DIR/ports/rp2" BOARD_DIR="$HERE/boards/$BOARD" submodules
make -C "$MP_DIR/ports/rp2" BOARD_DIR="$HERE/boards/$BOARD" \
    USER_C_MODULES="$HERE/picodvi/micropython.cmake" -j"$(nproc)"

mkdir -p "$HERE/firmware"
OUT="$HERE/firmware/micropython-$(echo "$BOARD" | tr 'A-Z_' 'a-z-').uf2"
cp "$MP_DIR/ports/rp2/build-$BOARD/firmware.uf2" "$OUT"
echo "-> ${OUT#$HERE/}"
