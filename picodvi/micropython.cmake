add_library(usermod_picodvi INTERFACE)

set(PICODVI_LIBDVI ${CMAKE_CURRENT_LIST_DIR}/libdvi)

target_sources(usermod_picodvi INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/modpicodvi.c
    ${PICODVI_LIBDVI}/dvi.c
    ${PICODVI_LIBDVI}/dvi_serialiser.c
    ${PICODVI_LIBDVI}/dvi_timing.c
    ${PICODVI_LIBDVI}/tmds_encode.c
    ${PICODVI_LIBDVI}/tmds_encode.S
)

target_include_directories(usermod_picodvi INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${PICODVI_LIBDVI}
)

target_compile_definitions(usermod_picodvi INTERFACE
    DVI_VERTICAL_REPEAT=2
    DVI_SYMBOLS_PER_WORD=2
)

target_link_libraries(usermod INTERFACE usermod_picodvi)

# MicroPython builds with -Os, which leaves SDK "static inline" helpers (queues,
# DMA config) out of line in flash. The DVI IRQ path must stay entirely in RAM,
# otherwise XIP contention with core 0 delays the IRQ and the DMA chain dies.
set_source_files_properties(
    ${CMAKE_CURRENT_LIST_DIR}/modpicodvi.c
    ${PICODVI_LIBDVI}/dvi.c
    ${PICODVI_LIBDVI}/dvi_timing.c
    ${PICODVI_LIBDVI}/tmds_encode.c
    PROPERTIES COMPILE_OPTIONS "-O2"
)

target_link_libraries(usermod_picodvi INTERFACE hardware_interp hardware_pwm hardware_vreg)
