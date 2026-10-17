# cmake file for Raspberry Pi Pico W + Waveshare PICO-DVI-LCD

set(PICO_BOARD "pico_w")

set(MICROPY_PY_LWIP ON)
set(MICROPY_PY_NETWORK_CYW43 ON)

# Bluetooth
set(MICROPY_PY_BLUETOOTH ON)
set(MICROPY_BLUETOOTH_BTSTACK ON)
set(MICROPY_PY_BLUETOOTH_CYW43 ON)

# Board specific version of the frozen manifest
set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)

if(NOT DEFINED MICROPY_HW_FLASH_STORAGE_BYTES)
    set(MICROPY_HW_FLASH_STORAGE_BYTES 868352)  # 848 * 1024
endif()

# libdvi uses calloc() for its scanline queues; MicroPython's C heap is 0 by default.
set(MICROPY_C_HEAP_SIZE 4096)

# picodvi.start() overclocks; let it rescale the CYW43 (Wi-Fi) PIO SPI clock.
list(APPEND MICROPY_DEF_BOARD CYW43_PIO_CLOCK_DIV_DYNAMIC=1)
