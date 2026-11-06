# Source reuse and license

This firmware is GPL-3.0-only. Preserve the included LICENSE when distributing it.

Laszlo Daniel's [ChryslerScanner](https://github.com/laszlodaniel/ChryslerScanner),
snapshot `c7229f288e5b3c3be8cb6123bb5958085aa0117c`, supplies the original
USB routing/framing, additive checksum, CCD checksum, PCI CRC and J1850 VPW
symbol conventions. The receive-only core is a bounded adaptation of those
conventions and algorithms; original transmit, bootstrap, eFuse-writing and LED
tasks are deliberately not imported. The inspected paths are
`PlatformIO/ChryslerScanner/src/main.c`, `include/config.h`, `include/enums.h`,
and `lib/AW9523/src/AW9523.h`. This is not a port of the newer binary-only release.

The in-repository `archive/bluetooth-sd-add-on/firmware/include/capture_format.hpp`
supplies the CBSDRAW1/CBR1 CRC32 journal envelope. Type 2 retains exact scanner
frames and type 4 records lifecycle text. No external diagnostic database or
vehicle decoder table is bundled by this firmware.

Hardware authorities:

- `../current/reference/rev-c-safety-contract.md` and the accepted native board/netlist.
- [Espressif PICO datasheet](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html): package GPIO mapping and flash/PSRAM.
- [ESP-IDF 5.5 UART](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/peripherals/uart.html): FIFO/timeout receive events.
- [ESP-IDF 5.5 SD SPI](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/peripherals/sdspi_host.html): explicit SPI pin routing and FATFS mounting.
- [AW9523B manufacturer datasheet](https://doc.awinic.com/doc/202403/deffbf3b-7e7b-4ff6-8e91-fd85e2d845d5.pdf): register and port/pad mapping.

The SDK and build tools retain their own licenses; they are installed separately,
not vendored into this firmware source directory.
