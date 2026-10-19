# SPDX-License-Identifier: MIT
"""Offline, isolated checks for the downloadable local runtime installer.

Run with ``python3 -m unittest discover -s test -p test_local_runtime_install.py``.
Only the installer's subprocess boundary is mocked; archive validation, extraction,
permissions, markers, backups, and pointer writes use real temporary files.
"""

import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


INSTALLER_PATH = Path(__file__).resolve().parents[1] / "local/install_local_runtime.py"
SPEC = importlib.util.spec_from_file_location("local_runtime_installer_under_test", INSTALLER_PATH)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class LocalRuntimeInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="atopile-installer-test-")
        self.addCleanup(self.temporary.cleanup)
        # macOS spells its temporary directory through the /var -> /private/var
        # system link; use the real path so the fixture has no symbolic parents.
        self.root = Path(self.temporary.name).resolve()
        self.data_root = self.root / "user-data"
        self.target = self.data_root / "runtime-0.4.0"
        self.pointer = self.root / "extension-storage/runtime.json"
        self.previous_pointer = self.pointer.with_suffix(".previous.json")

    def make_archive(self, *, package=None, package_bytes=None, extra=(), omitted=()):
        metadata = {
            "name": "atopile-local",
            "publisher": "local-atopile",
            "version": "0.4.0",
        }
        if package is not None:
            metadata.update(package)
        entries = [
            ("atopile-local/", b"", stat.S_IFDIR | 0o755),
            (
                "atopile-local/local/setup_runtime.py",
                b"# Setup is deliberately mocked in these tests.\n",
                stat.S_IFREG | 0o644,
            ),
            ("atopile-local/local/runtime-lock.txt", b"atopile==0.15.9\n", stat.S_IFREG | 0o644),
            ("atopile-local/bin/ato-local", b"#!/bin/sh\nexit 0\n", stat.S_IFREG | 0o755),
            (
                "atopile-local/src/vscode-atopile/package.json",
                json.dumps(metadata).encode() if package_bytes is None else package_bytes,
                stat.S_IFREG | 0o644,
            ),
        ]
        archive = self.root / "atopile-local-0.4.0-source.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for name, content, mode in entries + list(extra):
                if name in omitted:
                    continue
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                if stat.S_ISDIR(mode):
                    info.external_attr |= 0x10
                handle.writestr(info, content)
        checksum = self.root / "SHA256SUMS.txt"
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksum.write_text("{}  {}\n".format(digest, archive.name), encoding="utf-8")
        return archive, checksum, digest

    def install(self, archive, checksum):
        return installer.install(
            archive,
            checksum,
            data_root=self.data_root,
            pointer=self.pointer,
        )

    def write_pointer(self, content=None):
        if content is None:
            content = {"ato": "/old/runtime/bin/ato-local", "customSetting": {"keep": True}}
        self.pointer.parent.mkdir(parents=True, exist_ok=True)
        self.pointer.write_text(json.dumps(content) + "\n", encoding="utf-8")
        return self.pointer.read_bytes()

    def write_marker(self, digest, *, state="partial", **overrides):
        self.target.mkdir(parents=True, exist_ok=True)
        marker = {
            "installer": "atopile-local",
            "archive_sha256": digest,
            "version": "0.4.0",
            "state": state,
        }
        marker.update(overrides)
        (self.target / installer.MARKER).write_text(json.dumps(marker), encoding="utf-8")

    def marker(self):
        return json.loads((self.target / installer.MARKER).read_text(encoding="utf-8"))

    def successful_process(self, command, **kwargs):
        # A new setup must be recoverable if the process stops before completion.
        if command[-1] != "self-check":
            self.assertEqual(self.marker()["state"], "partial")
        return subprocess.CompletedProcess(command, 0, stdout="Local runtime OK\n", stderr="")

    def assert_setup_then_check(self, process):
        self.assertEqual(process.call_count, 2)
        setup, check = process.call_args_list
        self.assertEqual(
            setup.args[0],
            [sys.executable, str(self.target / "local/setup_runtime.py")],
        )
        self.assertTrue(setup.kwargs["check"])
        self.assertEqual(setup.kwargs["timeout"], 1800)
        self.assert_self_check(check)

    def assert_self_check(self, call):
        self.assertEqual(call.args[0], [str(self.target / "bin/ato-local"), "self-check"])
        self.assertTrue(call.kwargs["check"])
        self.assertEqual(call.kwargs["timeout"], 60)
        self.assertTrue(call.kwargs["capture_output"])
        self.assertTrue(call.kwargs["text"])

    def test_install_preserves_executable_modes_unknown_pointer_fields_and_backup(self):
        archive, checksum, digest = self.make_archive()
        old_runtime = self.root / "old-runtime"
        old_runtime.mkdir()
        (old_runtime / "auth.json").write_text("private old runtime data", encoding="utf-8")
        original = self.write_pointer(
            {"ato": str(old_runtime / "bin/ato-local"), "customSetting": {"keep": True}}
        )

        def pointer_still_unchanged(command, **kwargs):
            self.assertEqual(self.pointer.read_bytes(), original)
            self.assertFalse(self.previous_pointer.exists())
            return self.successful_process(command, **kwargs)

        with patch.object(installer.subprocess, "run", side_effect=pointer_still_unchanged) as process:
            result = self.install(archive, checksum)
        self.assertEqual(result, self.target)
        self.assert_setup_then_check(process)
        self.assertEqual(stat.S_IMODE((self.target / "bin/ato-local").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.target / "local/runtime-lock.txt").stat().st_mode), 0o644)
        self.assertFalse((self.target / "auth.json").exists())
        self.assertEqual((old_runtime / "auth.json").read_text(), "private old runtime data")
        self.assertEqual(self.previous_pointer.read_bytes(), original)
        self.assertEqual(
            json.loads(self.pointer.read_text()),
            {"ato": str(self.target / "bin/ato-local"), "customSetting": {"keep": True}},
        )
        self.assertEqual(
            self.marker(),
            {
                "installer": "atopile-local",
                "archive_sha256": digest,
                "version": "0.4.0",
                "state": "ready",
            },
        )

    def test_checksum_failure_never_runs_setup_or_changes_pointer(self):
        archive, checksum, _ = self.make_archive()
        checksum.write_text("{}  {}\n".format("0" * 64, archive.name), encoding="utf-8")
        original = self.write_pointer()
        with patch.object(installer.subprocess, "run") as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        process.assert_not_called()
        self.assertEqual(self.pointer.read_bytes(), original)
        self.assertFalse(self.previous_pointer.exists())

    def test_setup_environment_is_private_and_does_not_inherit_old_runtime_or_keys(self):
        archive, checksum, _ = self.make_archive()
        ambient = {
            "PATH": "/usr/bin:/bin", "VIRTUAL_ENV": "/old-environment",
            "PYTHONPATH": "/old-source", "PYTHONHOME": "/old-python",
            "UV_PROJECT_ENVIRONMENT": "/old-environment",
            "UV_CACHE_DIR": "/old-cache", "UV_PYTHON_INSTALL_DIR": "/old-python",
            "OPENAI_API_KEY": "fixture-not-a-key", "ATOPILE_API_KEY": "fixture-not-a-key",
            "CODEX_ACCESS_TOKEN": "fixture-not-a-token", "GEMINI_API_KEY": "fixture-not-a-key",
        }
        with patch.dict(installer.os.environ, ambient, clear=True):
            with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as process:
                self.install(archive, checksum)
        for call in process.call_args_list:
            env = call.kwargs["env"]
            for name in ambient.keys() - {"PATH", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"}:
                self.assertNotIn(name, env)
            self.assertEqual(env["UV_CACHE_DIR"], str(self.target / ".runtime-cache"))
            self.assertEqual(env["UV_PYTHON_INSTALL_DIR"], str(self.target / ".python"))
            self.assertEqual(env["ATOPILE_LOCAL_DATA_DIR"], str(self.target / ".state"))
            self.assertEqual(env["PATH"], ambient["PATH"])
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)

    def test_rejects_unsafe_archive_paths(self):
        for name in (
            "../escaped.txt",
            "atopile-local/../../escaped.txt",
            "/atopile-local/escaped.txt",
            "atopile-local\\..\\escaped.txt",
        ):
            with self.subTest(name=name):
                archive, checksum, _ = self.make_archive(
                    extra=[(name, b"must never be extracted", stat.S_IFREG | 0o644)]
                )
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertFalse((self.root / "escaped.txt").exists())
                self.assertFalse((self.data_root / "escaped.txt").exists())
                self.assertFalse(self.pointer.exists())

    def test_rejects_archived_symlinks(self):
        archive, checksum, _ = self.make_archive(
            extra=[("atopile-local/local/escape", b"../../outside", stat.S_IFLNK | 0o777)]
        )
        with patch.object(installer.subprocess, "run") as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        process.assert_not_called()
        self.assertFalse((self.target / "local/escape").exists())

    def test_rejects_mixed_archive_roots(self):
        archive, checksum, _ = self.make_archive(
            extra=[("other-project/readme.txt", b"wrong project", stat.S_IFREG | 0o644)]
        )
        with patch.object(installer.subprocess, "run") as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        process.assert_not_called()
        self.assertFalse((self.data_root / "other-project").exists())

    def test_rejects_archived_runtime_state_and_environment_files(self):
        for name in (
            ".state/auth.json",
            ".venv/bin/python",
            ".python/bin/python",
            ".runtime-cache/cache-entry",
            ".git/config",
            ".env",
        ):
            with self.subTest(name=name):
                archive, checksum, _ = self.make_archive(
                    extra=[("atopile-local/" + name, b"private", stat.S_IFREG | 0o644)]
                )
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertFalse((self.target / name).exists())

    def test_rejects_wrong_package_identity_or_unsafe_version(self):
        for metadata in (
            {"name": "different-extension"},
            {"publisher": "different-publisher"},
            {"version": "../../foreign-runtime"},
            {"version": "0.4"},
            {"version": 4},
        ):
            with self.subTest(metadata=metadata):
                archive, checksum, _ = self.make_archive(package=metadata)
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertFalse(self.pointer.exists())

    def test_verified_future_release_uses_its_own_versioned_directory(self):
        archive, checksum, _ = self.make_archive(package={"version": "0.5.0"})
        self.target = self.data_root / "runtime-0.5.0"
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as process:
            self.assertEqual(self.install(archive, checksum), self.target)
        self.assert_setup_then_check(process)
        self.assertEqual(self.marker()["version"], "0.5.0")
        self.assertEqual(json.loads(self.pointer.read_text())["ato"], str(self.target / "bin/ato-local"))

    def test_rejects_malformed_or_nonobject_package_json(self):
        original = self.write_pointer()
        for content in (b"{", b"[]", b"null", b'"unexpected text"'):
            with self.subTest(content=content):
                archive, checksum, _ = self.make_archive(package_bytes=content)
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertEqual(self.pointer.read_bytes(), original)
                self.assertFalse(self.previous_pointer.exists())

    def test_rejects_malformed_or_nonobject_pointer_without_mutation(self):
        archive, checksum, _ = self.make_archive()
        self.pointer.parent.mkdir(parents=True)
        for content in (b"{", b"[]", b"null", b'"unexpected text"'):
            with self.subTest(content=content):
                self.pointer.write_bytes(content)
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertEqual(self.pointer.read_bytes(), content)
                self.assertFalse(self.previous_pointer.exists())

    def test_rejects_missing_required_source_files(self):
        for missing in (
            "atopile-local/local/setup_runtime.py",
            "atopile-local/local/runtime-lock.txt",
            "atopile-local/bin/ato-local",
            "atopile-local/src/vscode-atopile/package.json",
        ):
            with self.subTest(missing=missing):
                archive, checksum, _ = self.make_archive(omitted=[missing])
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()

    def test_refuses_existing_unmarked_target(self):
        archive, checksum, _ = self.make_archive()
        self.target.mkdir(parents=True)
        foreign_file = self.target / "do-not-overwrite.txt"
        foreign_file.write_text("existing user files", encoding="utf-8")
        original = self.write_pointer()
        with patch.object(installer.subprocess, "run") as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        process.assert_not_called()
        self.assertEqual(foreign_file.read_text(), "existing user files")
        self.assertEqual(self.pointer.read_bytes(), original)
        self.assertFalse((self.target / installer.MARKER).exists())

    def test_refuses_marker_from_different_installer_archive_or_version(self):
        archive, checksum, digest = self.make_archive()
        for overrides in (
            {"installer": "somebody-else"},
            {"archive_sha256": "f" * 64},
            {"version": "0.3.0"},
            {"state": "unknown"},
        ):
            with self.subTest(overrides=overrides):
                self.write_marker(digest, **overrides)
                marker_before = (self.target / installer.MARKER).read_bytes()
                with patch.object(installer.subprocess, "run") as process:
                    with self.assertRaises(installer.InstallError):
                        self.install(archive, checksum)
                process.assert_not_called()
                self.assertEqual((self.target / installer.MARKER).read_bytes(), marker_before)
                self.assertFalse(self.pointer.exists())

    def test_failed_setup_preserves_prior_pointer_and_partial_marker(self):
        archive, checksum, digest = self.make_archive()
        original = self.write_pointer()

        def failed_setup(command, **kwargs):
            self.assertEqual(self.marker()["state"], "partial")
            raise subprocess.CalledProcessError(1, command, stderr="setup failed")

        with patch.object(installer.subprocess, "run", side_effect=failed_setup) as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(self.pointer.read_bytes(), original)
        self.assertFalse(self.previous_pointer.exists())
        self.assertEqual(self.marker()["state"], "partial")
        self.assertEqual(self.marker()["archive_sha256"], digest)

    def test_failed_self_check_is_retryable_without_changing_prior_pointer(self):
        archive, checksum, digest = self.make_archive()
        original = self.write_pointer()

        def fail_health_check(command, **kwargs):
            self.assertEqual(self.marker()["state"], "partial")
            if command[-1] == "self-check":
                raise subprocess.CalledProcessError(1, command, stderr="health check failed")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(installer.subprocess, "run", side_effect=fail_health_check) as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        self.assert_setup_then_check(process)
        self.assertEqual(self.pointer.read_bytes(), original)
        self.assertFalse(self.previous_pointer.exists())
        self.assertEqual(self.marker()["state"], "partial")
        self.assertEqual(self.marker()["archive_sha256"], digest)
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as retry:
            self.assertEqual(self.install(archive, checksum), self.target)
        self.assert_setup_then_check(retry)
        self.assertEqual(self.marker()["state"], "ready")
        self.assertEqual(self.previous_pointer.read_bytes(), original)

    def test_matching_partially_extracted_install_can_be_completed(self):
        archive, checksum, digest = self.make_archive()
        self.write_marker(digest)
        (self.target / "bin").mkdir()
        (self.target / "bin/ato-local").write_bytes(b"#!/bin/sh\nexit 0\n")
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as process:
            self.assertEqual(self.install(archive, checksum), self.target)
        self.assert_setup_then_check(process)
        self.assertTrue((self.target / "local/runtime-lock.txt").is_file())
        self.assertEqual(self.marker()["state"], "ready")

    def test_ready_runtime_is_health_checked_without_reinstall_or_backup_replacement(self):
        archive, checksum, _ = self.make_archive()
        original = self.write_pointer()
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process):
            self.install(archive, checksum)
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as process:
            self.assertEqual(self.install(archive, checksum), self.target)
        self.assertEqual(process.call_count, 1)
        self.assert_self_check(process.call_args)
        self.assertEqual(self.previous_pointer.read_bytes(), original)
        self.assertEqual(self.marker()["state"], "ready")

    def test_unhealthy_ready_runtime_becomes_partial_and_retries_setup(self):
        archive, checksum, _ = self.make_archive()
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process):
            self.install(archive, checksum)
        pointer_before = self.pointer.read_bytes()
        with patch.object(
            installer.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["ato-local", "self-check"]),
        ) as failed:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        self.assertEqual(failed.call_count, 1)
        self.assertEqual(self.pointer.read_bytes(), pointer_before)
        self.assertEqual(self.marker()["state"], "partial")
        with patch.object(installer.subprocess, "run", side_effect=self.successful_process) as retry:
            self.install(archive, checksum)
        self.assert_setup_then_check(retry)

    def test_retry_refuses_modified_existing_source_instead_of_overwriting_it(self):
        archive, checksum, digest = self.make_archive()
        self.write_marker(digest)
        setup = self.target / "local/setup_runtime.py"
        setup.parent.mkdir()
        setup.write_text("# Local edits that the installer must preserve.\n", encoding="utf-8")
        original = setup.read_bytes()
        with patch.object(installer.subprocess, "run") as process:
            with self.assertRaises(installer.InstallError):
                self.install(archive, checksum)
        process.assert_not_called()
        self.assertEqual(setup.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
