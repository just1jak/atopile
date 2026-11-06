# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import json
import random
import struct
import tempfile
import unittest
import zlib
import os
import sys
import types
import contextlib
import io
from unittest.mock import patch
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("scanner", Path(__file__).parents[1]/"tools/scanner.py")
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)
BUILD_SPEC = importlib.util.spec_from_file_location("build", Path(__file__).parents[1]/"tools/build.py")
build = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(build)


def record(kind, seq, payload):
    header = struct.pack("<4sBBHIIQQI", b"CBR1", kind, 0, 36, len(payload), seq, 123, 0, 0)
    body = header + payload
    return body + struct.pack("<I", zlib.crc32(body))


class ToolsTest(unittest.TestCase):
    def recover(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"record.cbr"
            path.write_bytes(b"CBSDRAW1" + body)
            before = path.read_bytes()
            result = list(scanner.recover(path))
            self.assertEqual(before, path.read_bytes())
            return result

    def test_clean_and_torn_stop(self):
        frame = scanner.packet(1, b"\0\0\0\x7b\x01\x02\x03", 0x97)
        first = record(2, 0, frame)
        stop = record(4, 1, b"session_clean_stop")
        result = self.recover(first + stop)
        self.assertEqual(result[0]["frame"]["data"], "010203")
        self.assertTrue(result[-1]["summary"]["clean_stop"])
        for cut in range(len(stop)):
            result = self.recover(first + stop[:cut])
            self.assertFalse(result[-1]["summary"]["clean_stop"])
            self.assertEqual(result[-1]["summary"]["records"], 1)

    def test_corruption_resync_and_gap(self):
        a = record(4, 0, b"start")
        bad = bytearray(record(4, 1, b"damaged"))
        bad[36] ^= 0x80
        c = record(4, 2, b"session_clean_stop")
        result = self.recover(a + bad + c)
        self.assertTrue(result[1]["sequence_gap"])
        self.assertEqual(result[-1]["summary"]["skipped_bytes"], len(bad))
        self.assertFalse(result[-1]["summary"]["clean_stop"])

    def test_every_record_truncation(self):
        whole = record(2, 0, scanner.packet(0x80, b"\0"*100, 0xa7))
        for cut in range(len(whole)):
            result = self.recover(whole[:cut])
            self.assertEqual(result[-1]["summary"]["records"], 0)
            self.assertFalse(result[-1]["summary"]["clean_stop"])

    def test_missing_complete_record(self):
        result = self.recover(record(4, 0, b"start") + record(4, 2, b"session_clean_stop"))
        self.assertTrue(result[1]["sequence_gap"])
        self.assertFalse(result[-1]["summary"]["clean_stop"])

    def test_serial_parser(self):
        parser = scanner.Parser()
        valid = scanner.packet(0x7f, b'{"tx":false}', 0x85)
        out = []
        for byte in b"noise\x3d\xff\xff" + valid*3:
            out.extend(parser.feed(bytes([byte])))
        self.assertEqual(out, [valid]*3)
        self.assertEqual(scanner.describe(out[0])["status"], {"tx": False})
        rng = random.Random(42)
        list(parser.feed(rng.randbytes(100000)))
        self.assertLessEqual(len(parser.buffer), scanner.MAX_WIRE)

    def test_parser_expiry_recovers_hidden_reply(self):
        parser = scanner.Parser()
        reply = scanner.packet(0x7f, b'{"tx":false}', 0x85)
        self.assertEqual(list(parser.feed(b"\x3d\x01\x00"+reply, now=1)), [])
        self.assertEqual(list(parser.feed(b"", now=1.101)), [reply])
        self.assertEqual(parser.buffer, b"")

    def test_sci_provenance_survives_recording(self):
        frames = [scanner.packet(0x92, b"\0\0\0\1"+bytes([pin, speed, 0xbb]), 0xa7)
                  for pin, speed in ((7, 1), (15, 3))]
        rows = self.recover(b"".join(record(2, i, frame) for i, frame in enumerate(frames)))
        self.assertEqual([(r["frame"]["obd_pin"], r["frame"]["baud"], r["frame"]["data"])
                          for r in rows[:-1]], [(7, 7812, "bb"), (15, 125000, "bb")])

    def test_stop_waits_for_actual_completion(self):
        class FakePort:
            is_open = True
            def __init__(self, **kwargs):
                self.pending = []
                self.status_requests = 0
                self.completed = False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.completed = self.status_requests >= 3
            def write(self, data):
                if data[4] == 0x81:
                    # A stale pre-stop idle status must not authorize removal.
                    self.pending.append(scanner.packet(0x80, b'{"logging":0,"sd_busy":0,"requested":0,"sd_error":0}', 0x85))
                    self.pending.append(scanner.packet(0x81, b"\0", 0x85))
                else:
                    self.status_requests += 1
                    self.pending.append(scanner.packet(0x80, json.dumps({
                        "logging": int(self.status_requests == 2),
                        "sd_busy": int(self.status_requests < 3),
                        "requested": 0, "sd_error": 0}).encode(), 0x85))
            def read(self, count):
                import time
                time.sleep(0.005)
                return self.pending.pop(0) if self.pending else b""
        port = FakePort()
        args = types.SimpleNamespace(action="stop", route=0, speed=1, port="fake", seconds=1)
        with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=lambda **kw: port)}), contextlib.redirect_stdout(io.StringIO()):
            scanner.serial_action(args)
        self.assertTrue(port.completed)

    def test_build_stamp_rejects_edits_and_image_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"include").mkdir()
            header = root/"include/test.hpp"
            header.write_text("old")
            for name in ("CMakeLists.txt", "platformio.ini", "sdkconfig.defaults", "partitions.csv"):
                (root/name).write_text("config")
            out = root/".pio/build/rev_c_passive"
            (out/"config").mkdir(parents=True)
            (out/"config/sdkconfig.h").write_text("sdk")
            for name in build.IMAGES:
                (out/name).write_bytes(b"image")
            before = build.inputs(root)
            recorded = build.stamp(root, before)
            build.verify(root, recorded)
            previous_time = header.stat().st_mtime
            header.write_text("new")
            os.utime(header, (previous_time-1000, previous_time-1000))
            with self.assertRaises(RuntimeError):
                build.verify(root, recorded)
            with self.assertRaises(RuntimeError):
                build.stamp(root, before) # Concurrent edit, even with old mtime.
            header.write_text("old")
            (out/"firmware.bin").write_bytes(b"different")
            with self.assertRaises(RuntimeError):
                build.verify(root, recorded)


if __name__ == "__main__":
    unittest.main()
