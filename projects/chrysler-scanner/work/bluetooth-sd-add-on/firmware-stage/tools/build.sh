#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
build_tools="${LOGGER_BUILD_TOOLS:-${TMPDIR:-/tmp}/chrysler-bluetooth-sd-build}"
export PLATFORMIO_CORE_DIR="${PLATFORMIO_CORE_DIR:-$build_tools/pio-core}"
if [ ! -x "$build_tools/venv/bin/pio" ]; then
    python3 -m venv "$build_tools/venv"
    "$build_tools/venv/bin/python" -m pip install platformio==6.1.18
fi
"$build_tools/venv/bin/python" -c 'import platformio; assert platformio.__version__ == "6.1.18", "Use pinned PlatformIO 6.1.18"'
"$build_tools/venv/bin/pio" run -e xiao_esp32s3
