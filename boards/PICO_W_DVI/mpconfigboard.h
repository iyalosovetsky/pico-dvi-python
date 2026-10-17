// Board and hardware specific configuration
#define MICROPY_HW_BOARD_NAME                   "Raspberry Pi Pico W + Waveshare PICO-DVI-LCD"

// todo: We need something to check our binary size

// Enable networking.
#define MICROPY_PY_NETWORK 1
#define MICROPY_PY_NETWORK_HOSTNAME_DEFAULT     "PicoW"

// CYW43 driver configuration.
#define CYW43_USE_SPI (1)
#define CYW43_LWIP (1)
#define CYW43_GPIO (1)
#define CYW43_SPI_PIO (1)

// For debugging mbedtls - also set
// Debug level (0-4) 1=warning, 2=info, 3=debug, 4=verbose
// #define MODUSSL_MBEDTLS_DEBUG_LEVEL 1

#define MICROPY_HW_PIN_EXT_COUNT    CYW43_WL_GPIO_COUNT

// If this returns true for a pin then its irq will not be disabled on a soft reboot
int mp_hal_is_pin_reserved(int n);
#define MICROPY_HW_PIN_RESERVED(i) mp_hal_is_pin_reserved(i)

// PICO-DVI-LCD: soft reset disables all PWM slices, re-enable the TMDS clock.
void picodvi_soft_reset_hook(void);
#define MICROPY_BOARD_END_SOFT_RESET() picodvi_soft_reset_hook()

// Core 1 belongs to DVI. With threads enabled, every soft reset calls
// multicore_reset_core1() (mp_thread_deinit) and kills the DVI output.
#define MICROPY_PY_THREAD (0)
