# cmake file for Raspberry Pi Pico 2 W + Waveshare PICO-DVI-LCD

set(PICO_BOARD "pico2_w")

# To change the gpio count for QFN-80
# set(PICO_NUM_GPIOS 48)

set(MICROPY_PY_LWIP ON)
set(MICROPY_PY_NETWORK_CYW43 ON)

# Bluetooth
set(MICROPY_PY_BLUETOOTH ON)
set(MICROPY_BLUETOOTH_BTSTACK ON)
set(MICROPY_PY_BLUETOOTH_CYW43 ON)

# Board specific version of the frozen manifest
set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)

if(NOT DEFINED MICROPY_HW_FLASH_STORAGE_BYTES)
    set(MICROPY_HW_FLASH_STORAGE_BYTES 2621440)  # PICO_FLASH_SIZE_BYTES - 1536 * 1024 = 4MB - 1.5MB
endif()

# libdvi uses calloc() for its scanline queues; MicroPython's C heap is 0 by default.
set(MICROPY_C_HEAP_SIZE 4096)

# Read-only ROMFS for fonts/icons (mpremote romfs deploy romfs), carved from the
# code region so the user filesystem keeps its place.
set(MICROPY_HW_ROMFS_BYTES 524288)

# picodvi.start() overclocks; let it rescale the CYW43 (Wi-Fi) PIO SPI clock.
list(APPEND MICROPY_DEF_BOARD CYW43_PIO_CLOCK_DIV_DYNAMIC=1)
