# pico-dvi-python

MicroPython v1.29.0 для Raspberry Pi Pico 2 W (RP2350) і Pico W (RP2040) з DVI-виходом на Waveshare **PICO-DVI-LCD**
(PicoDVI): **400×240 → 800×480@60** за замовчуванням, або 320×240 → 640×480@60.
Колір: RGB565 на RP2350, RGB332 на RP2040.

## Структура

| Шлях | Що це |
|---|---|
| `picodvi/` | C-модуль `picodvi` + вендорна копія `libdvi` з [Wren6991/PicoDVI](https://github.com/Wren6991/PicoDVI) (commit `dccd738`, BSD-3) з патчами під MicroPython |
| `boards/PICO2_W_DVI/` | Конфіг Pico 2 W (копія `RPI_PICO2_W` + хук soft-reset, 4 КБ C-heap, без `_thread`) |
| `boards/PICO_W_DVI/` | Те саме для Pico W |
| `device/` | Дашборд: `main.py` + `lib/` (display, screen, tz, net) |
| `romfs/` | Згенеровані шрифти `.fnt` і піктограми MDI (ROMFS, `tools/mkassets.py`) |
| `tools/` | `mkassets.py` (TTF/MDI → `.fnt`), `preview.py` (рендер екрана в PNG на ПК), `hoststub/` |
| `demo/main.py` | Демка: палітра, plasma (viper), м'ячики, зоряне поле |
| `firmware/` | Готові прошивки `micropython-pico2-w-dvi.uf2`, `micropython-pico-w-dvi.uf2` |
| `build.sh` | Збірка прошивки |

## Прошивка

1. Затиснути BOOTSEL, підключити Pico (або `mpremote bootloader`).
2. Скопіювати відповідний `.uf2` з `firmware/` на диск `RP2350` / `RPI-RP2`.
3. Залити демку:

```bash
mpremote cp demo/main.py :main.py + reset
```

## Дашборд

```bash
python3 tools/mkassets.py                 # шрифти/піктограми -> romfs/
mpremote romfs deploy romfs               # у ROMFS (512 КБ, читається без копіювання в RAM)
mpremote mkdir :lib
mpremote cp device/lib/*.py :lib/ + cp device/main.py :main.py
mpremote cp secrets.py :secrets.py        # WIFI_SSID, WIFI_PASS, MQTT_* (не в git)
python3 tools/preview.py preview.png      # той самий код екрана, відрендерений на ПК
```

Годинник синхронізується з NTP, час — Europe/Kyiv (EU DST без бази часових поясів).

## API

```python
import picodvi, framebuf
W, H = picodvi.start()                # MODE_400x240 (295.2 МГц) за замовчуванням
# W, H = picodvi.start(picodvi.MODE_320x240)   # 640x480, 252 МГц
buf = picodvi.framebuffer()           # bytearray W*H, живий кадровий буфер
fb = framebuf.FrameBuffer(buf, W, H, picodvi.FORMAT)   # RGB565 (RP2350) / GS8 (RP2040)
fb.text("Hello", 10, 10, picodvi.rgb(255, 255, 0))
picodvi.size()                        # (W, H) поточного режиму
picodvi.active()                      # True, якщо DVI запущено
picodvi.draw_text(font, "Привіт", x, y, color, bg=-1)   # згладжений текст/піктограма, -> x після тексту
picodvi.text_width(font, s); picodvi.font_metrics(font)   # (line_height, ascent)
picodvi.debug()                       # (stage, lines, irqs, encoded, q_tmds_valid, q_tmds_free, q_col_valid, q_col_free, late)
```

DVI після `start()` працює до апаратного ресету, переживає Ctrl-C / soft reset і запис файлів.
Режим обирається один раз на завантаження: інший режим → `RuntimeError`, потрібен `machine.reset()`.
Здоровий стан: `debug()[1]` росте на ~14300/с у 400×240 (59.5 Гц) і ~14400/с у 320×240.

## Обмеження, поки DVI активний

- `machine.freq()` не міняти (sys clock = TMDS bit clock: 295.2 або 252 МГц).
- `_thread` вимкнено у прошивці: core1 повністю віддано DVI (інакше кожен soft reset робить `multicore_reset_core1()`).
- Зайнято: PIO0 SM0–2, піни GP8–GP15, PWM slice 4, DMA_IRQ_1, 6 DMA-каналів.
- `machine.I2S` недоступний (ділить DMA_IRQ_1).
- Wi-Fi: `start()` перераховує дільник PIO-SPI для CYW43 під нову частоту, тому **DVI треба запускати до `WLAN.active(True)`**. Перевірено на Pico 2 W.

## Пінаут (з Waveshare `common_dvi_pin_configs.h`, `pico_sock_cfg`)

| Сигнал | GPIO |
|---|---|
| CLK± | GP8/9 |
| D0± (blue) | GP10/11 |
| D1± (green) | GP12/13 |
| D2± (red) | GP14/15 |

Пари інвертовані (`invert_diffpairs = true`).

## Збірка

Потрібні `arm-none-eabi-gcc`, `cmake`, `git`.

```bash
./build.sh                  # Pico 2 W; клонує MicroPython v1.29.0 у ./micropython
./build.sh PICO_W_DVI       # Pico W
```

Увага: генератор qstr у MicroPython створює файли з іменами з повного шляху, тому
дуже довгий шлях до проєкту дає `File name too long`. Після зміни конфігу плати
(`mpconfigboard.*`) видаліть `micropython/ports/rp2/build-PICO_W_DVI`.

## Що змінено в libdvi / чому

- `__scratch_x/__scratch_y` → `__not_in_flash` (у MicroPython SCRATCH_X має розмір 0).
- TMDS-буфери статичні замість `malloc` (C-heap MicroPython за замовчуванням 0; для черг виділено 4 КБ).
- Прибрано `interp_save/restore` (core1 повністю наш; а ці функції живуть у флеші).
- `util_queue_u32_inline.h`: `static inline` → `__force_inline`, файли DVI збираються з `-O2`.
  MicroPython збирає з `-Os`, і без цього хелпери черг/DMA лягали у флеш; IRQ на core1
  запізнювався через XIP-конкуренцію з core0, DMA-ланцюжок збивався і вивід зупинявся
  через ~10 кадрів.
- Лічильники `dvi_dbg_irq` / `dvi_dbg_enc` для `picodvi.debug()`.
- PIO-заголовки згенеровані заздалегідь (`*.pio.h`), бо qstr-прохід MicroPython іде до генерації.

## Пастка RP2350: таблиця розділів

Якщо на платі лишилась таблиця розділів (`picotool partition info` показує partition 0 з
`00002000`), MicroPython стартує зі зсувом і **файлова система не працює** (`ENODEV`,
`mkfs` → `ENOSPC`): читання йде через трансляцію адрес, запис — за фізичними адресами.
Лікується повним стиранням (видаляє все з флешу):

```bash
picotool erase -a
# плата сама повернеться в BOOTSEL; потім
picotool load -v firmware/micropython-pico2-w-dvi.uf2 && picotool reboot
```
