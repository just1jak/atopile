#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bundle an already-built passive development image with its matching sources.

Does not build, flash, upload, change CAD or claim bench validation.
"""
import hashlib
import json
import platform
import zipfile
from pathlib import Path
import build

FW = Path(__file__).resolve().parents[1]
BUILD = FW/".pio/build/rev_c_passive"
OUTPUT = FW.parent/"work/firmware-port-rev-c"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    recorded = json.loads((BUILD/"verified-build.json").read_text())
    build.verify(FW, recorded)  # Hash checks remain active under python -O.
    sources = sorted(p for p in FW.rglob("*") if p.is_file()
                     and not any(part in {".pio", "build", "__pycache__"} for part in p.relative_to(FW).parts)
                     and (not p.name.startswith("sdkconfig") or p.name == "sdkconfig.defaults"))
    images = {name: BUILD/name for name in ("bootloader.bin", "partitions.bin", "firmware.bin", "firmware.elf")}
    manifest = {
        "name": "rev-c-passive-0.1.1", "state": "built; see software-check logs; bench qualification pending",
        "verified_build": recorded,
        "python": platform.python_version(),
        "platformio": "6.1.19", "espressif32": "6.12.0", "esp_idf": "5.5.0",
        "pcb_sha256": "e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4",
        "flashed": False, "bench_validated": False, "active_vehicle_tx": False,
        "flash_offsets": {"bootloader.bin": "0x1000", "partitions.bin": "0x8000", "firmware.bin": "0x10000"},
        "sources": {str(p.relative_to(FW)).replace("\\", "/"): digest(p) for p in sources},
        "images": {name: digest(path) for name, path in images.items()},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT/"manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    target = OUTPUT/"rev-c-passive-0.1.1-development.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for p in sources:
            bundle.write(p, "source/"+p.relative_to(FW).as_posix())
        for name, p in images.items():
            bundle.write(p, "images/"+name)
        bundle.write(manifest_path, "manifest.json")
        bundle.write(BUILD/"config/sdkconfig.h", "build/sdkconfig.h")
        for name in ("build-final.log", "python-tests.log", "board-check.log", "host-core.log"):
            log = FW.parent/"work/firmware-tooling"/name
            if log.exists():
                bundle.write(log, "build/"+name)
    target.with_suffix(".zip.sha256").write_text(digest(target)+"  "+target.name+"\n", encoding="ascii")
    print(target)
    print("SHA256", digest(target))


if __name__ == "__main__":
    main()
