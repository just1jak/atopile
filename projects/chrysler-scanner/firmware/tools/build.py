#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the pinned target and bind unchanged input hashes to its output images."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

FW = Path(__file__).resolve().parents[1]
IMAGES = ("bootloader.bin", "partitions.bin", "firmware.bin", "firmware.elf")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(root):
    paths = [*root.glob("include/*.hpp"), *root.glob("src/*.cpp"), *root.glob("src/CMakeLists.txt"),
             root/"CMakeLists.txt", root/"platformio.ini", root/"sdkconfig.defaults",
             root/"partitions.csv", *root.glob("boards/*.json")]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def stamp(root, before):
    if inputs(root) != before:
        raise RuntimeError("Compiled inputs changed during the build; rebuild before export")
    build = root/".pio/build/rev_c_passive"
    return {"inputs": before, "images": {name: digest(build/name) for name in IMAGES},
            "sdkconfig_sha256": digest(build/"config/sdkconfig.h")}


def verify(root, recorded):
    if stamp(root, recorded["inputs"]) != recorded:
        raise RuntimeError("Build images or SDK configuration changed after the verified build")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    before = inputs(FW)
    # Hash stamps alone cannot make an mtime-based compiler rebuild a backdated
    # edit. Clean the declared build target before producing an attested image.
    subprocess.run([sys.executable, "-m", "platformio", "run", "-d", str(FW),
                    "-e", "rev_c_passive", "-t", "clean"], check=True)
    result = subprocess.run([sys.executable, "-m", "platformio", "run", "-d", str(FW),
                             "-e", "rev_c_passive", "-j", str(args.jobs)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, end="")
    log = FW.parent/"work/firmware-tooling/build-final.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)
    recorded = stamp(FW, before)
    target = FW/".pio/build/rev_c_passive/verified-build.json"
    target.write_text(json.dumps(recorded, indent=2)+"\n", encoding="utf-8")
    print("PASS: unchanged build inputs bound to image/config hashes")


if __name__ == "__main__":
    main()
