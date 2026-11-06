#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C passive USB client and CRC-checked CBSDRAW1 recovery/export."""
import argparse
import json
import struct
import sys
import time
import zlib
from pathlib import Path

MAX_WIRE = 518


def packet(mode, payload=b"", route=4):
    body = bytes([0x3D]) + struct.pack(">HBB", len(payload) + 2, route, mode) + payload
    return body + bytes([sum(body) & 255])


def valid_frame(data):
    return (6 <= len(data) <= MAX_WIRE and data[0] == 0x3D
            and int.from_bytes(data[1:3], "big") + 4 == len(data)
            and sum(data[:-1]) & 255 == data[-1])


class Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0
        self.last_byte = None

    def expire(self, now):
        if not self.buffer or self.last_byte is None or now - self.last_byte <= 0.1:
            return
        # A plausible but truncated head must not hide a complete good reply
        # forever. On expiry scan every later sync, not just the first one.
        self.errors += 1
        pending = bytes(self.buffer)
        self.buffer.clear()
        offset = 1
        while offset + 6 <= len(pending):
            size = int.from_bytes(pending[offset+1:offset+3], "big") + 4
            frame = pending[offset:offset+size]
            if pending[offset] == 0x3D and valid_frame(frame):
                yield frame
                offset += size
            else:
                offset += 1

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        yield from self.expire(now)
        if data:
            self.last_byte = now
        # Incremental bound also holds for arbitrarily large caller chunks.
        for byte in data:
            self.buffer.append(byte)
            while self.buffer:
                if self.buffer[0] != 0x3D:
                    del self.buffer[0]
                    continue
                if len(self.buffer) < 3:
                    break
                n = int.from_bytes(self.buffer[1:3], "big") + 4
                if not 6 <= n <= MAX_WIRE:
                    del self.buffer[0]
                    self.errors += 1
                    continue
                if len(self.buffer) < n:
                    break
                frame = bytes(self.buffer[:n])
                if not valid_frame(frame):
                    del self.buffer[0]
                    self.errors += 1
                    continue
                del self.buffer[:n]
                yield frame


def describe(frame):
    route, mode = frame[3:5]
    bus = (route >> 4) & 7
    result = {"bus": bus, "command": route & 15, "mode": mode}
    if bus and route & 15 == 7 and len(frame) >= 10:
        result.update(ms=int.from_bytes(frame[5:9], "big"), data=frame[9:-1].hex(),
                      validated=mode == 1)
        if bus == 2 and mode == 0x92:
            if len(frame) < 12 or frame[9] not in (7, 15) or frame[10] > 3:
                raise ValueError("Invalid SCI source metadata")
            result.update(obd_pin=frame[9], baud=(976, 7812, 62500, 125000)[frame[10]],
                          data=frame[11:-1].hex())
    elif route == 0x85 and mode in (0x7F, 0x80):
        result["status"] = json.loads(frame[5:-1])
    else:
        result["data"] = frame[5:-1].hex()
    return result


def recover(path):
    """Scan CRC-valid records, resync across corruption; report all skipped bytes.

    Never changes the original. A clean-stop event is not inferred from EOF.
    """
    data = Path(path).read_bytes()
    if data[:8] != b"CBSDRAW1":
        raise ValueError("Not a CBSDRAW1 recording")
    offset, skipped, count = 8, 0, 0
    expected = 0
    sequence_gaps = 0
    clean = False
    while offset < len(data):
        if data[offset:offset+4] != b"CBR1" or offset+40 > len(data):
            offset += 1
            skipped += 1
            continue
        header = data[offset:offset+36]
        kind, flags, header_size, size, seq, us, utc, lost = struct.unpack("<4xBBHIIQQI", header)
        end = offset + 40 + size
        if (header_size != 36 or size > MAX_WIRE or end > len(data)
                or zlib.crc32(data[offset:end-4]) != int.from_bytes(data[end-4:end], "little")):
            offset += 1
            skipped += 1
            continue
        payload = data[offset+36:end-4]
        record = {"sequence": seq, "us": us, "lost": lost, "type": kind}
        if seq != expected:
            record["sequence_gap"] = True
            sequence_gaps += 1
        expected = (seq + 1) & 0xFFFFFFFF
        clean = False
        if kind == 2:
            if not valid_frame(payload):
                record["invalid_scanner_frame"] = payload.hex()
            else:
                record["frame"] = describe(payload)
        elif kind == 4:
            record["event"] = payload.decode("utf-8", errors="replace")
            clean = payload == b"session_clean_stop"
        else:
            record["payload"] = payload.hex()
        if flags & 1:
            record["utc_us"] = utc
        yield record
        count += 1
        offset = end
    yield {"summary": {"records": count, "skipped_bytes": skipped,
                       "sequence_gaps": sequence_gaps,
                       "clean_stop": clean and skipped == 0 and sequence_gaps == 0}}


def serial_action(args):
    import serial  # pyserial; offline recovery needs only Python's standard library.
    parser = Parser()
    port = serial.Serial(port=None, baudrate=250000, timeout=0.05, write_timeout=1)
    port.dtr = False
    port.rts = False
    port.port = args.port
    with port:
        # Levels are set before opening; OS/adapter glitches still need testing.
        mode, payload = {
            "caps": (0x7F, b""), "status": (0x80, b""),
            "start": (0x81, b"\x01"), "stop": (0x81, b"\x00"),
            "sci": (0x82, bytes([args.route, args.speed])),
            "monitor": (0x7F, b""),
        }[args.action]
        port.write(packet(mode, payload))
        deadline = time.monotonic() + (args.seconds if args.action == "monitor" else 10 if args.action == "stop" else 3)
        response = False
        status_queried = False
        next_status = float("inf")
        while time.monotonic() < deadline:
            if args.action == "stop" and time.monotonic() >= next_status:
                port.write(packet(0x80))
                status_queried = True
                next_status = time.monotonic() + 0.1
            for frame in parser.feed(port.read(512)):
                print(json.dumps(describe(frame)))
                if frame[3] == 0x8F:
                    raise RuntimeError(f"Scanner rejected request: 0x{frame[4]:02x}")
                if frame[3] == 0x85 and frame[4] == mode:
                    response = True
                    if args.action == "stop":
                        next_status = time.monotonic()
                    elif args.action != "monitor":
                        return
                if args.action == "stop" and response and status_queried and frame[3:5] == b"\x85\x80":
                    status = json.loads(frame[5:-1])
                    if status.get("sd_error"):
                        raise RuntimeError("SD reported an error; inspect/recover the recording")
                    if status.get("logging") == 0 and status.get("sd_busy") == 0 and status.get("requested") == 0:
                        return
        if args.action == "stop":
            raise TimeoutError("SD stop did not complete; do not remove the card yet")
        if not response:
            raise TimeoutError("No matching response; check power, UART and startup/fault status")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    offline = sub.add_parser("recover")
    offline.add_argument("file")
    for action in ("caps", "status", "start", "stop", "sci", "monitor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--port", required=True)
        cmd.add_argument("--seconds", type=float, default=30)
        cmd.add_argument("--route", type=int, choices=(0, 1, 2), default=0,
                         help="0 disconnected, 1 OBD7, 2 OBD15")
        cmd.add_argument("--speed", type=int, choices=(0, 1, 2, 3), default=1,
                         help="0=976, 1=7812, 2=62500, 3=125000 baud")
    args = parser.parse_args()
    if args.action == "recover":
        for record in recover(args.file):
            print(json.dumps(record))
    else:
        serial_action(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
