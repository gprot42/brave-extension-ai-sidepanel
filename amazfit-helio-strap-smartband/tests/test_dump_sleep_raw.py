#!/usr/bin/env python3
"""Dump raw type 0x48 (sleep) bytes from the device for offline analysis.

Usage:
    source backend/.venv/bin/activate
    python tests/test_dump_sleep_raw.py [output_file.bin]

Connects, authenticates (Phase 1 + ECDH), fetches raw type 0x48 data, and
writes the raw payload bytes to a binary file.  The file can then be analysed
with the companion script below or piped into hexdump / Python.

Offline analysis snippet:
    python3 - <<'EOF'
    import collections
    data = open("sleep_raw.bin", "rb").read()
    print(f"Total bytes: {len(data)}")
    cnt = collections.Counter(data)
    print("Byte distribution (top 20):", cnt.most_common(20))
    non_ff = [b for b in data if b != 0xFF]
    print(f"Non-0xFF bytes: {len(non_ff)}  ({len(non_ff)/len(data)*100:.1f}%)")
    for v in sorted(set(non_ff)):
        print(f"  val={v}  count={cnt[v]}")
    print("First 64 bytes hex:", data[:64].hex())
    EOF
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Locate the saved device UUID (same pattern as the main app)
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DEVICE_CACHE = os.path.join(ROOT_DIR, ".device_cache")
ENV_FILE = os.path.join(ROOT_DIR, ".env")

def _read_env():
    env = {}
    for path in (ENV_FILE, os.path.join(ROOT_DIR, "backend", ".env")):
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = _read_env()
DEVICE_UUID = env.get("DEVICE_UUID") or env.get("BLE_ADDRESS")

if not DEVICE_UUID and os.path.exists(DEVICE_CACHE):
    DEVICE_UUID = open(DEVICE_CACHE).read().strip()

if not DEVICE_UUID:
    print("ERROR: No device UUID found. Set DEVICE_UUID in .env or run the app to cache it.")
    sys.exit(1)

OUTPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "sleep_raw.bin"

# ---------------------------------------------------------------------------
print(f"Device: {DEVICE_UUID}")
print(f"Output: {OUTPUT_FILE}")
print()

# ---------------------------------------------------------------------------
# BLE constants (copied from protocol.py to avoid import issues in test env)
# ---------------------------------------------------------------------------
AUTH_CHAR_UUID    = "0000ffd9-0000-1000-8000-00805f9b34fb"
FETCH_CTRL_CHAR   = "00002a2c-0000-1000-8000-00805f9b34fb"
FETCH_DATA_CHAR   = "00002a2d-0000-1000-8000-00805f9b34fb"
ZEPP_AUTH_SERVICE = "00000055-0000-1000-8000-00805f9b34fb"
ZEPP_AUTH_CHAR    = "00000056-0000-1000-8000-00805f9b34fb"

FETCH_TYPE_SLEEP = 0x48
CMD_INIT_TRANSFER  = 0x01
CMD_START_TRANSFER = 0x02
CMD_ACK            = 0x03

import struct
from bleak import BleakClient

async def phase1_auth(client, auth_key_hex: str):
    """Standard Huami Phase 1 auth (key send + bonded check)."""
    q: asyncio.Queue = asyncio.Queue()
    def handler(_, data: bytearray):
        q.put_nowait(bytes(data))
    await client.start_notify("0000ffd9-0000-1000-8000-00805f9b34fb", handler)
    auth_key = bytes.fromhex(auth_key_hex)
    await client.write_gatt_char(
        "0000ffd9-0000-1000-8000-00805f9b34fb",
        bytes([0x01, 0x00]) + auth_key,
        response=True,
    )
    resp = await asyncio.wait_for(q.get(), timeout=10)
    if resp[:2] != bytes([0x10, 0x01]):
        raise RuntimeError(f"Phase1 step1 failed: {resp.hex()}")
    print(f"  Phase1 key response: {resp.hex()}")
    await client.write_gatt_char(
        "0000ffd9-0000-1000-8000-00805f9b34fb",
        bytes([0x02, 0x00]),
        response=True,
    )
    try:
        resp2 = await asyncio.wait_for(q.get(), timeout=12)
        print(f"  Phase1 challenge response: {resp2.hex()}")
    except asyncio.TimeoutError:
        print("  Phase1: no challenge (bonded — OK)")
    await client.stop_notify("0000ffd9-0000-1000-8000-00805f9b34fb")
    print("  Phase1: OK")

async def phase2_ecdh(client):
    """Zepp OS ECDH Phase 2 auth using the project's zepp_auth module."""
    sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
    from ble.zepp_auth import ZeppAuth
    za = ZeppAuth(client)
    ok = await za.authenticate()
    if not ok:
        raise RuntimeError("ECDH auth failed")
    print("  ECDH: OK")

async def fetch_raw_sleep(client, since_days=7):
    """Fetch raw type 0x48 data and return the raw bytes."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    ts = int(since.timestamp())
    # Build init command: [CMD_INIT, type, year_lo, year_hi, month, day, hour, min, 0, 0]
    year = since.year
    cmd = bytes([CMD_INIT_TRANSFER, FETCH_TYPE_SLEEP,
                 year & 0xFF, (year >> 8) & 0xFF,
                 since.month, since.day, since.hour, since.minute, 0, 0])
    print(f"  Fetch cmd: {cmd.hex()}")

    ctrl_q: asyncio.Queue = asyncio.Queue()
    data_chunks: list[bytes] = []

    def ctrl_handler(_, data: bytearray):
        ctrl_q.put_nowait(bytes(data))

    def data_handler(_, data: bytearray):
        # Strip per-notification sequence byte (first byte)
        if len(data) > 1:
            data_chunks.append(bytes(data[1:]))
        else:
            data_chunks.append(bytes(data))

    await client.start_notify(FETCH_CTRL_CHAR, ctrl_handler)
    await client.start_notify(FETCH_DATA_CHAR, data_handler)

    await client.write_gatt_char(FETCH_CTRL_CHAR, cmd, response=True)

    # Wait for ctrl response
    try:
        ctrl_resp = await asyncio.wait_for(ctrl_q.get(), timeout=10)
    except asyncio.TimeoutError:
        print("  CTRL: timeout — no response")
        await client.stop_notify(FETCH_CTRL_CHAR)
        await client.stop_notify(FETCH_DATA_CHAR)
        return b""

    print(f"  CTRL response: {ctrl_resp.hex()}")
    if len(ctrl_resp) < 2 or ctrl_resp[1] != 0x01:
        print(f"  CTRL status={ctrl_resp[1] if len(ctrl_resp)>1 else 'N/A'} — no data")
        await client.stop_notify(FETCH_CTRL_CHAR)
        await client.stop_notify(FETCH_DATA_CHAR)
        return b""

    if len(ctrl_resp) >= 5:
        expected = struct.unpack_from("<I", ctrl_resp, 1)[0]
        print(f"  Expecting ~{expected} bytes")

    # Start transfer
    await client.write_gatt_char(FETCH_CTRL_CHAR, bytes([CMD_START_TRANSFER]), response=False)

    # Collect until stall
    last_count = 0
    stalls = 0
    while True:
        await asyncio.sleep(1)
        cur = sum(len(c) for c in data_chunks)
        if cur == last_count:
            stalls += 1
            if stalls >= 5:
                break
        else:
            stalls = 0
            last_count = cur

    raw = b"".join(data_chunks)
    print(f"  Received {len(raw)} bytes in {len(data_chunks)} chunks")

    # ACK
    try:
        await client.write_gatt_char(FETCH_CTRL_CHAR, bytes([CMD_ACK]), response=False)
    except Exception:
        pass

    await client.stop_notify(FETCH_CTRL_CHAR)
    await client.stop_notify(FETCH_DATA_CHAR)
    return raw


async def main():
    auth_key = env.get("AUTH_KEY", "")
    if not auth_key:
        print("WARNING: No AUTH_KEY in .env — Phase1 auth may fail")

    print("Connecting...")
    async with BleakClient(DEVICE_UUID) as client:
        if not client.is_connected:
            print("ERROR: failed to connect")
            return

        print("Connected")
        print("\n=== Phase 1 Auth ===")
        if auth_key:
            await phase1_auth(client, auth_key)

        print("\n=== Phase 2 ECDH ===")
        await phase2_ecdh(client)

        print(f"\n=== Fetching raw type 0x{FETCH_TYPE_SLEEP:02X} (sleep) ===")
        raw = await fetch_raw_sleep(client, since_days=14)

    if not raw:
        print("\nNo data received.")
        return

    # Analyse
    import collections
    cnt = collections.Counter(raw)
    non_ff = [b for b in raw if b != 0xFF]
    print(f"\n=== Analysis ===")
    print(f"Total bytes  : {len(raw)}")
    print(f"Non-0xFF     : {len(non_ff)} ({len(non_ff)/len(raw)*100:.1f}%)")
    print(f"Byte dist (top 20): {dict(cnt.most_common(20))}")
    print(f"Non-0xFF values:")
    for v in sorted(set(non_ff)):
        print(f"  val={v:3d} (0x{v:02x})  count={cnt[v]:5d}")
    print(f"First 64 bytes hex: {raw[:64].hex()}")

    # Write raw file
    with open(OUTPUT_FILE, "wb") as f:
        f.write(raw)
    print(f"\nRaw bytes written to: {OUTPUT_FILE}")

asyncio.run(main())
