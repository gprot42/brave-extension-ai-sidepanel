#!/usr/bin/env python3
"""
Fetch type 0x56 (and scan 0x57-0x60) using the same protocol as 0x55.
If data is available, download it all and attempt to decode.
"""

import asyncio
import os
import struct
from datetime import datetime
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"


async def fetch_type(client, ctrl_q, type_code, since_dt):
    """Attempt to fetch a data type. Returns (raw_data, status) or (None, status)."""
    cmd = bytes([0x01, type_code,
                 since_dt.year & 0xFF, (since_dt.year >> 8) & 0xFF,
                 since_dt.month, since_dt.day, since_dt.hour, since_dt.minute,
                 0x00, 0x00])
    print(f"\n  Init fetch type 0x{type_code:02X}: {cmd.hex()}")
    await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

    try:
        r = await asyncio.wait_for(ctrl_q.get(), 5)
    except asyncio.TimeoutError:
        print("  -> No response (timeout)")
        return None, -1

    print(f"  Response: {r.hex()}")
    if len(r) < 3:
        return None, -1

    status = r[2]
    if status != 0x01:
        print(f"  -> Status 0x{status:02X} (not available)")
        return None, status

    # Parse expected size
    expected = 0
    if len(r) >= 7:
        expected = struct.unpack_from("<I", r, 3)[0]
        print(f"  -> DATA AVAILABLE: {expected} bytes expected")
        if len(r) >= 15:
            year = struct.unpack_from("<H", r, 7)[0]
            month, day = r[9], r[10]
            hour, minute = r[11], r[12]
            print(f"  -> Data from: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")

    # Start transfer
    data_chunks = []
    data_bytes = [0]

    data_q = asyncio.Queue()

    def on_data(s, d):
        chunk = bytes(d)
        data_chunks.append(chunk)
        data_bytes[0] += len(chunk)
        if len(data_chunks) % 200 == 0:
            print(f"  [DATA]: {data_bytes[0]} bytes ({len(data_chunks)} chunks)")

    await client.start_notify(FETCH_DATA, on_data)
    await asyncio.sleep(0.2)

    print("  Starting transfer...")
    await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)

    # Collect until stall
    last_count = 0
    stall = 0
    while True:
        await asyncio.sleep(1)
        current = data_bytes[0]
        if current == last_count:
            stall += 1
            if stall >= 5:
                break
        else:
            stall = 0
            last_count = current

        # Drain ctrl
        while not ctrl_q.empty():
            msg = ctrl_q.get_nowait()
            print(f"  [CTRL]: {msg.hex()}")

    await client.stop_notify(FETCH_DATA)

    # ACK
    await client.write_gatt_char(FETCH_CTRL, bytes([0x03]), response=False)
    await asyncio.sleep(0.5)

    raw = b"".join(data_chunks)
    print(f"  Total: {len(raw)} bytes in {len(data_chunks)} chunks")
    return raw, status


def try_decode(raw, type_code):
    """Attempt various decodings of the raw data."""
    if not raw or len(raw) < 10:
        print("  Too small to decode")
        return

    fname = f"raw_fetch_0x{type_code:02X}.bin"
    with open(fname, "wb") as f:
        f.write(raw)
    print(f"  Saved to {fname}")

    # Hex dump first 256 bytes
    print(f"\n  First 256 bytes:")
    for i in range(0, min(256, len(raw)), 16):
        h = " ".join(f"{b:02x}" for b in raw[i:i + 16])
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in raw[i:i + 16])
        print(f"    {i:04x}: {h:<48s} {a}")

    # Strip chunk headers (first byte of each 241-byte chunk)
    payload = bytearray()
    for i in range(0, len(raw), 241):
        chunk = raw[i:i + 241]
        if len(chunk) > 1:
            payload.extend(chunk[1:])

    print(f"\n  Payload (headers stripped): {len(payload)} bytes")

    # Try 5-byte records (like type 0x55 HR)
    print(f"\n  === Decode as 5-byte records (like HR) ===")
    n_records = len(payload) // 5
    print(f"  {n_records} records")
    for i in range(min(20, n_records)):
        rec = payload[i * 5:(i + 1) * 5]
        counter = struct.unpack_from("<H", rec, 0)[0]
        b2, b3, b4 = rec[2], rec[3], rec[4]
        print(f"    [{i:4d}] counter={counter:5d} b2=0x{b2:02x} b3=0x{b3:02x} b4={b4:3d}")

    # Try 4-byte records
    print(f"\n  === Decode as 4-byte records ===")
    n4 = len(payload) // 4
    for i in range(min(20, n4)):
        rec = payload[i * 4:(i + 1) * 4]
        val32 = struct.unpack_from("<I", rec, 0)[0]
        val16a = struct.unpack_from("<H", rec, 0)[0]
        val16b = struct.unpack_from("<H", rec, 2)[0]
        print(f"    [{i:4d}] u32={val32:10d} u16a={val16a:5d} u16b={val16b:5d} raw={rec.hex()}")

    # Try 6-byte records
    print(f"\n  === Decode as 6-byte records ===")
    n6 = len(payload) // 6
    for i in range(min(20, n6)):
        rec = payload[i * 6:(i + 1) * 6]
        print(f"    [{i:4d}] {rec.hex()}")

    # Look for timestamp patterns (bytes that look like year 2026 = 0x07EA)
    print(f"\n  === Scan for timestamp patterns ===")
    count = 0
    for i in range(len(payload) - 1):
        if payload[i] == 0xEA and payload[i + 1] == 0x07:
            context = payload[max(0, i - 4):min(len(payload), i + 8)]
            print(f"    Offset {i}: ...{context.hex()}...")
            count += 1
            if count >= 20:
                print(f"    ... ({count}+ matches)")
                break


async def main():
    key = bytes.fromhex(AUTH_KEY)
    client = BleakClient(DEVICE_ID)
    await client.connect(timeout=15.0)
    print(f"Connected: {client.is_connected}")

    # Auth
    auth_q = asyncio.Queue()
    await client.start_notify(AUTH_CHAR, lambda s, d: auth_q.put_nowait(bytes(d)))
    await asyncio.sleep(0.2)
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + key, response=True)
    r = await asyncio.wait_for(auth_q.get(), 10)
    print(f"Auth step 1: {r.hex()}")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
    r = await asyncio.wait_for(auth_q.get(), 10)
    print(f"Auth step 2: {r.hex()}")
    await client.stop_notify(AUTH_CHAR)
    print("Auth done\n")

    # Subscribe to ctrl
    ctrl_q = asyncio.Queue()
    await client.start_notify(FETCH_CTRL, lambda s, d: ctrl_q.put_nowait(bytes(d)))
    await asyncio.sleep(0.3)

    since = datetime(2026, 3, 25, 0, 0)

    # Try types 0x56 through 0x60
    print("=" * 60)
    print("Fetching types 0x56 - 0x60")
    print("=" * 60)

    for tc in range(0x56, 0x61):
        raw, status = await fetch_type(client, ctrl_q, tc, since)
        if raw and len(raw) > 0:
            try_decode(raw, tc)

    # Also re-check 0x55 status
    print("\n" + "=" * 60)
    print("Re-checking type 0x55 status")
    print("=" * 60)
    cmd = bytes([0x01, 0x55,
                 since.year & 0xFF, (since.year >> 8) & 0xFF,
                 since.month, since.day, since.hour, since.minute, 0x00, 0x00])
    await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
    try:
        r = await asyncio.wait_for(ctrl_q.get(), 5)
        print(f"  0x55 status: {r.hex()}")
    except asyncio.TimeoutError:
        print("  0x55: no response")

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
