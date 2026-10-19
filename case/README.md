# Корпус для 7" PICO-DVI-LCD + Pico 2 W

Параметричний корпус у FreeCAD. Макрос `make_case.FCMacro` будує `case.FCStd` (таблиця
`Params`), STL у положенні для друку і `case.step`:

```bash
freecadcmd -c "__file__='case/make_case.FCMacro'; exec(open(__file__).read())"
```

Таблиця `Params` у `case.FCStd` має пріоритет над значеннями в макросі. Щоб узяти нові
значення з макроса, видаліть `case.FCStd` перед запуском. Якщо `case.FCStd` відкритий у
FreeCAD GUI, закрийте його **без збереження**, інакше GUI перезапише нову модель старою.

## Деталі

| Файл | Що це | Друк |
|---|---|---|
| `bezel.stl` | Передня рамка з кишенею під панель і вікном | лицем на стіл |
| `back.stl` | Тонка задня частина: боковини до лиця, спинка на стійках плати | спинкою на стіл |
| `cap.stl` | Ковпачок над Pico, защіпається в проріз | дахом на стіл |
| `feet.stl` | Дві ніжки-проставки для стіни | як є |

Усе друкується без підтримок: нависань понад 45° немає (перевірено за нормалями STL),
крім горизонтальних граней гачків защіпок (4 × 8 × 1,2 мм) — їх принтер бере без підтримок.

Габарити: 184,2 × 116,8 × 16,5 мм + ковпачок 10,5 мм. Пластику ~97 см³.

## Збирання

1. Панель лягає в кишеню рамки (`bezel`), шлейф панелі — у виїмку на нижньому краю.
2. Ніжки: прикласти ззовні до отворів унизу задньої частини, зсередини вкрутити M3 × 8
   (гвинт іде в отвір 2,6 мм у ніжці).
3. Кабель USB-C продіти зсередини через отвір 13 × 8 мм у спинці, вставити штекер у плату.
4. Задню частину надіти на рамку (рамка заходить усередину боковин, зазор 0,2 мм).
5. 4 × M3 × 8 у кутах (глибокі потаї, гвинт іде в рамку), 2 × M3 у нижні стійки плати
   (M3 × 6 або M3 × 8 з шайбою: спинка там лише 1,5 мм).
6. Ковпачок вставити в проріз над Pico до клацання: 4 защіпки (по дві на довгих боках)
   чіпляються гачками під край прорізу. Зняти — зсередини відтиснути гачки.
7. На стіну: два «ключі» на 140 мм, гвинти виступають зі стіни на ~13 мм; до стіни
   притуляються ковпачок і ніжки.

## Система координат

X — ширина, Y — висота (вгору), Z — глибина: Z = 0 — лице корпусу, Z росте назад.
**+X — праворуч, якщо дивитися ЗЗАДУ** (ліворуч, якщо дивитися на екран).
Положення на платі (стійки, Pico, радіатор, кнопки OSD) задані в цій самій системі:
вигляд ззаду, шлейф панелі внизу.

## Виміри (штангенциркуль)

- Панель 164,7 × 100 × 3,6 мм; рамки до видимої області: верх 5,6, низ 9,2 (шлейф),
  ліворуч 2,9, праворуч 5,6 (дивлячись спереду).
- Стійки плати драйвера 62 × 70 мм (за пробним друком по горизонталі 63); стійка 1 — 124 мм від лівого і 26,5 мм від нижнього
  краю панелі (ззаду, шлейф донизу).
- Від лиця дисплея: верх стійок 13 мм, радіатор +4–5 мм над стійками, верх роз'єму під
  Pico 20 мм, верх Pico 22 мм.
- Положення Pico, роз'єму USB-C і радіатора оцінені з фото (масштаб за стійками), ±2 мм.
- Штекер USB-C з кабелем вміщається під спинкою (на рівні верху стійок).

## Рішення та їхні причини

- **Вікно точно за видимою областю, корпус розширено на 2,7 мм** (`frame_sym`). Симетричне
  вікно за меншою рамкою (2,9) відкривало 2,7 мм металевої рамки дисплея з боку 5,6.
  Тепер видима біла рамка 12,75 мм з обох боків.
- **Рамка в пазу задньої частини.** Раніше рамка й задня частина стикувались торцями по
  зовнішньому контуру; тепер боковини задньої частини доходять до лиця, шов прихований.
- **Стінки 1,5 мм, спинка на стійках.** Задня частина друкувалась 3+ год і виглядала
  масивною (34,5 мм). Порожнина 26,5 мм потрібна лише над Pico, тому решта — 9,4 мм за
  панеллю, а над Pico окремий ковпачок (у задній частині горб не надрукувати без
  підтримок: спинка висіла б у повітрі).
- **Притискна рамка — порожниста 45° пластина**, а не суцільний клин (клин давав більшу
  частину об'єму).
- **Ковпачок — простий прямокутник лише над Pico.** Г-подібний варіант із «апендиксом» над
  штекером USB-C прибрано: штекер вміщається під спинкою.
- **Ніжки на гвинтах**, а не на клею.
- **Защіпки ковпачка** лише на довгих боках: під короткими під спинкою роз'єм USB,
  верхні стійки й кнопка Power. Язичок 1,2 мм завтовшки, ~9 мм завдовжки, гачок
  заходить під спинку на 1,0 мм і починається на 0,4 мм нижче неї (перший друк із
  0,6 мм і 0,1 мм не фіксувався: на допусках друку гачок не заскакував під спинку); гвинтами ковпачок не прикрутити (лише M3 × 8 є).
- **Гвинти лише M3 × 8** (довгих немає): глибокі потаї з 45° конусом замість плоского
  уступу — і короткий гвинт, і друк без підтримок.
- **Зона безпеки над платою** (`board_margin`): нічого з задньої частини не заходить у
  контур плати нижче верху стійок (раніше уступ притискної рамки не давав плату поставити).
- **Виїмка під шлейф** 4,5 мм за край панелі: згин шлейфу випирає на 3–4 мм.
- **Щілина OSD 18 мм** під палець (12 мм + запас): кнопки на краю плати натискаються вбік.
- **Радіатор** виходить у вікно 18 × 20 у спинці (після пробного друку розширене на 2 мм униз); вентиляційні щілини — у даху ковпачка.

## Параметри (`DEFAULTS` у макросі)

| Параметр | Значення | Опис |
|---|---|---|
| `panel_w` | 164.7 | LCD module outline width (Waveshare: 164.70) |
| `panel_h` | 100 | LCD module outline height (Waveshare: 100.00) |
| `panel_t` | 3.6 | LCD module thickness (measured) |
| `border_top` | 5.6 | panel edge to visible area, top (measured, seen from the front) |
| `border_bottom` | 9.2 | panel edge to visible area, bottom (FPC side) |
| `border_left` | 2.9 | panel edge to visible area, left |
| `border_right` | 5.6 | panel edge to visible area, right |
| `frame_sym` | 1 | 1 = window exactly over the visible area, case widened on the narrow border side so the visible frame is symmetric |
| `window_margin` | 0.3 | window larger than the visible area on each side |
| `fit` | 0.4 | clearance around the panel |
| `fpc_x` | 0.5 | panel FPC (flat cable) centre X on the bottom edge (seen from the back), from photo |
| `fpc_w` | 36 | FPC relief width (FPC ~28 mm + margin) |
| `fpc_out` | 4.5 | FPC relief past the panel edge (FPC bend sticks out 3-4 mm) |
| `fpc_relief` | 1.2 | FPC relief in the back cover clamp where the FPC lies on the panel back |
| `border` | 8 | frame width outside the panel pocket (room for screw bosses) |
| `front_t` | 2 | front plate thickness |
| `wall` | 1.5 | side wall / back plate thickness |
| `lid_fit` | 0.2 | gap between the bezel and the back walls around it |
| `press_skirt` | 4.5 | panel clamp: flat ring width (3 mm on the panel border), then a hollow 45 deg skirt of the same horizontal thickness up to the wall |
| `corner_r` | 6 | outer corner radius |
| `cavity` | 9.4 | panel back to the back plate = top of the board standoffs (measured 13 from the panel front minus panel_t) |
| `ledge` | 3 | back cover rim pressing on the panel border |
| `cable_side` | 4 | cable exit: 0 = bottom wall, 1 = left, 2 = right (seen from the back), 3 = hole in the back + snake groove, 4 = hole in the back only (the cable goes down in the gap between the case and the wall) |
| `snake_x` | -62 | rear cable hole centre X (seen from the back): past the end of the USB-C plug, which points -X from the board edge at ~-25 |
| `snake_y` | 35 | rear cable hole centre Y (USB-C at ~33.5, clear of the keyhole) |
| `snake_hole_w` | 13 | rear cable hole size so the USB-C plug passes |
| `snake_hole_h` | 8 | snake: hole height |
| `snake_w` | 5 | snake: groove width (cable dia ~3.5-4.5 mm, press in) |
| `snake_d` | 5 | snake: groove depth (45 deg roof; a 4 mm cable still fits) |
| `snake_amp` | 8 | snake: zigzag amplitude (X) |
| `snake_n` | 3 | snake: number of zigzag bends |
| `cable_pos` | -5.5 | cable slot centre along that wall (X for bottom, Y for sides); -5.5 = in line with the driver board's USB-C (photo, relative to standoffs) |
| `cable_w` | 9 | cable slot width (cable is laid in from the back, plug stays inside) |
| `cable_h` | 15 | cable slot depth from the back face (cable rises over the panel clamp) |
| `cable_rear` | 0 | 1 = also a cable hole in the back plate (desk use) |
| `cable_y` | -20 | rear cable hole centre Y from case centre |
| `key_span` | 140 | distance between the two wall keyholes |
| `key_from_top` | 35 | keyhole (narrow end) distance from the top edge |
| `key_head_d` | 9 | keyhole: screw head entry diameter |
| `key_slot_w` | 4.6 | keyhole: slot width (screw shank) |
| `key_slot_l` | 10 | keyhole: slot length upwards from the entry |
| `feet_angle` | 0 | desk tilt (deg); 0 = no feet (wall mount) |
| `osd_on` | 1 | 1 = slot in the back over the OSD buttons |
| `osd_x` | 52.5 | OSD slot centre X (seen from the back, + right); buttons at ~42..44, push outwards |
| `osd_y_top` | 41.5 | OSD slot top Y (buttons -12.5 .. +33.5; >= 2 mm from standoff 4 boss) |
| `osd_y_bot` | -18.5 | OSD slot bottom Y (>= 2 mm from standoff 1 boss) |
| `osd_w` | 18 | OSD slot width: a 12 mm finger + 6 mm, presses the buttons sideways |
| `feet_span` | 110 | distance between the two desk feet |
| `screw_d` | 3.4 | screw clearance hole in the back |
| `screw_head_d` | 6.2 | screw head counterbore diameter |
| `screw_pilot` | 2.6 | pilot hole in the bezel boss (2.6 self-tap M3, 4.0 insert) |
| `vent_n` | 0 | number of vent slots in the back (0: the heatsink has its own window) |
| `vent_x` | 6 | vent slots centre X (over the driver chip heatsink at ~(6, -2.4)) |
| `vent_y` | -2.4 | vent slots centre Y |
| `stand_on` | 1 | 1 = holes + bosses at the 4 driver-board standoffs |
| `stand_cx` | 10.65 | standoff rectangle centre X (seen from the back, + right) |
| `stand_cy` | 11.5 | standoff rectangle centre Y (+ up) |
| `stand_dx` | 63 | standoff spacing, horizontal (measured 62; +1 after the test print) |
| `stand_dy` | 70 | standoff spacing, vertical (measured) |
| `board_margin` | 6 | keep-out around the driver board (standoffs +/- this + 4.5 mm board overhang) |
| `board_top` | 9.4 | height of the standoff tops above the panel back (13 from the panel front) |
| `stand_hole` | 3.4 | screw hole over the two lower standoffs (M3 x 6, or M3 x 8 + washer) |
| `rad_x` | 7.7 | heatsink centre X (14 x 14 mm, 4-5 mm above the standoffs) |
| `rad_y` | -0.8 | heatsink window centre Y |
| `rad_win` | 18 | heatsink window width (X) |
| `rad_win_h` | 20 | heatsink window height (Y): 2 mm more downwards after the test print |
| `pico_x0` | -17 | cap clear area over the Pico: X from (microUSB end) |
| `pico_x1` | 40.5 | ... X to (next to standoff 4) |
| `pico_y0` | 24 | ... Y from |
| `pico_y1` | 52 | ... Y to (the Pico sits at the panel edge) |
| `pico_top` | 22 | top of the Pico above the panel front (measured) |
| `cap_clear` | 1.5 | air above the Pico under the cap roof |
| `cap_lip` | 1.4 | cap lip width (goes into the opening, wall is wall + lip thick) |
| `cap_fit` | 0.2 | gap between the cap lip and the opening |
| `snap_n` | 2 | snap fingers per long side of the cap (0 = glue it) |
| `snap_w` | 8 | snap finger width |
| `snap_pitch` | 28 | distance between the fingers on one side |
| `snap_hook` | 1.2 | hook depth past the finger (1.0 past the opening edge; 0.8 did not hold) |
| `snap_play` | 0.4 | hook top below the plate (print tolerance; 0.1 did not snap in) |
| `feet_on` | 1 | 1 = two spacer feet for the wall, screwed from inside (M3 x 8) |
| `foot_w` | 14 | foot size |
| `foot_y` | -42 | foot centre Y (X = +/- key_span / 2) |
| `boss_d` | 9 | corner screw boss outer diameter in the back cover |
| `corner_floor` | 3.9 | plastic under the corner head cones: M3 x 8 goes ~4.4 mm into the 4.8 mm pilot |
| `screw_inset` | 6 | corner screws from both outer edges (= corner_r keeps them concentric) |
| `press_t` | 1.6 | thickness of the frame pressing the panel border |
