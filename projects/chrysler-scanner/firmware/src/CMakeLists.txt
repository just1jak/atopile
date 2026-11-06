idf_component_register(SRCS "main.cpp" "ble_transport.cpp" INCLUDE_DIRS "../include"
    REQUIRES driver esp_timer fatfs sdmmc esp_system efuse bt nvs_flash)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -Wno-deprecated-declarations)
target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_17)
