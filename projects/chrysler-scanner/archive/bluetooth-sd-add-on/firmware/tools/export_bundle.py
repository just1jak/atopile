"""SCons post-build bundle; records actual platform-generated flash image offsets."""
Import("env")  # type: ignore[name-defined]  # provided by PlatformIO/SCons


def package(source, target, env):
    import hashlib
    import json
    import shutil
    from pathlib import Path

    project = Path(env.subst("$PROJECT_DIR"))
    output = project / "dist"
    output.mkdir(exist_ok=True)
    images = []
    inputs = list(env.get("FLASH_EXTRA_IMAGES", []))
    inputs.append((env.subst("$ESP32_APP_OFFSET"), str(target[0])))
    for offset, path in inputs:
        original = Path(env.subst(str(path)))
        if not original.is_file():
            raise RuntimeError(f"Missing generated flash image: {original}")
        destination = output / original.name
        shutil.copyfile(original, destination)
        raw = destination.read_bytes()
        images.append({"offset": hex(int(str(offset), 0)), "file": destination.name,
                       "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    if len({entry["offset"] for entry in images}) != len(images):
        raise RuntimeError("Duplicate flash image offsets")
    board = env.BoardConfig()
    mode = env.subst("${__get_board_flash_mode(__env__)}")
    frequency = env.subst("${__get_board_f_image(__env__)}")
    if "$" in mode + frequency:
        raise RuntimeError("Unable to resolve build flash settings")
    args = ["--chip", board.get("build.mcu"), "write_flash", "-z",
            "--flash_mode", mode, "--flash_freq", frequency,
            "--flash_size", board.get("upload.flash_size", "detect")]
    for image in images:
        args += [image["offset"], image["file"]]
    manifest = {"firmware": "chrysler-bluetooth-sd-0.1.0", "board": env.subst("$BOARD"),
                "platform": "espressif32@6.12.0", "platformio_core": "6.1.18",
                "nimble_arduino": "2.5.1", "images": images,
                "esptool_arguments": args,
                "hardware_tested": False, "flashed_by_build": False}
    manifest["build_packages"] = {}
    for name in ("framework-arduinoespressif32", "toolchain-xtensa-esp32s3", "tool-esptoolpy"):
        directory = env.PioPlatform().get_package_dir(name)
        metadata = Path(directory) / "package.json" if directory else None
        if not metadata or not metadata.is_file():
            raise RuntimeError(f"Missing installed package metadata: {name}")
        manifest["build_packages"][name] = json.loads(metadata.read_text())["version"]
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "flash_args.json").write_text(json.dumps(args, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{x['sha256']}  {x['file']}\n" for x in images))
    print(f"Created firmware image bundle ({len(images)} images), no device flashed")


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", package)
