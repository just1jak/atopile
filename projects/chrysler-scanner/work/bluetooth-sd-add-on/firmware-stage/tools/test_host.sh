#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
build_dir="${TMPDIR:-/tmp}/chrysler-firmware-host"
mkdir -p "$build_dir"
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -fsanitize=address,undefined -fno-omit-frame-pointer -g \
  -Iinclude src/protocol.cpp test/test_firmware.cpp -o "$build_dir/test_firmware"
"$build_dir/test_firmware"
