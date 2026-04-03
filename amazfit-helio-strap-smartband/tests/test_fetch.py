#!/usr/bin/env python3
"""
Data fetch test — uses characteristics 0x0004 (control) and 0x0005 (data)
for the Huami activity fetch protocol, plus 0x0016/0x0017 chunked protocol.
Subscribes to ALL notifiable chars to see every response.
"""

import asyncio
import os
import struct
from datetime import datetime, timezone
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")

AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"
CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"

FETCH_TYPES = {
    0x01: "Activity (steps/cal)",
    0x06: "Activity (detailed)",
    0x07: "Sleep",
    0x12: "Stress (manual)",
    0x13: "Stress (auto)",
    0x25: "SpO2 (normal)",
    0x26: "SpO2 (sleep)",
    0x2E: "Temperature",
    0x3A: "Resting HR",
    0x48: "Sleep Session",
    0x49: "HRV",
}


async def authenticate(client):
    """Auth via 0x0001."""
    key = bytes.fromhex(AUTH_KEY)
    q = asyncio.Queue()

    def on_auth(s, d):
        q.put_nowait(bytes(d))

    await client.start_notify(AUTH_CHAR, on_auth)
    await asyncio.sleep(0.2)

    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + key, response=True)
    r = await asyncio.wait_for(q.get(), 10)
    print(f"  Step 1: {r.hex()} — {'OK' if r[2] == 0x01 else 'FAIL'}")
    if r[2] != 0x01:
        return False

    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
    r = await asyncio.wait_for(q.get(), 10)
    print(f"  Step 2: {r.hex()} — bonded (no challenge)")
    return True


async def main():
    client = BleakClient(DEVICE_ID)
    await client.connect(timeout=15.0)
    print(f"Connected: {client.is_connected}")

    # Auth
    print("\n[Auth]")
    if not await authenticate(client):
        print("Auth failed")
        await client.disconnect()
        return
    print("Auth OK\n")

    # Subscribe to ALL notifiable chars to see every response
    all_notifications = asyncio.Queue()

    for service in client.services:
        for char in service.characteristics:
            if "notify" in char.properties and char.uuid != AUTH_CHAR:
                short = char.uuid.split("-")[0]
                try:
                    def mk(name):
                        def h(s, d):
                            print(f"  ** [{name}]: {bytes(d).hex()} ({len(d)}b)")
                            all_notifications.put_nowait((name, bytes(d)))
                        return h
                    await client.start_notify(char.uuid, mk(short))
                except Exception as e:
                    print(f"  Subscribe {short} failed: {e}")
    await asyncio.sleep(0.5)

    since = datetime(2025, 1, 1, tzinfo=timezone.utc)
    since_ts = int(since.timestamp())

    # === Method A: Direct fetch via 0x0004 / 0x0005 ===
    print("=" * 60)
    print("METHOD A: Direct fetch via 0x0004 (control) / 0x0005 (data)")
    print("=" * 60)

    for fetch_type, name in FETCH_TYPES.items():
        print(f"\n--- {name} (0x{fetch_type:02x}) ---")

        # Format: [0x01, type, year_lo, year_hi, month, day, hour, min]
        dt = since
        payload = bytes([0x01, fetch_type,
                         dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                         dt.month, dt.day, dt.hour, dt.minute])
        print(f"  Write 0x0004: {payload.hex()}")
        try:
            await client.write_gatt_char(FETCH_CTRL, payload, response=False)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        # Wait for responses
        await asyncio.sleep(3)

        # Drain queue
        while not all_notifications.empty():
            try:
                all_notifications.get_nowait()
            except:
                break

    # === Method B: Fetch via 0x0004 with Unix timestamp ===
    print("\n" + "=" * 60)
    print("METHOD B: 0x0004 with unix timestamp (4 bytes LE)")
    print("=" * 60)

    for fetch_type in [0x01, 0x07, 0x25]:
        name = FETCH_TYPES.get(fetch_type, "?")
        print(f"\n--- {name} (0x{fetch_type:02x}) ---")
        payload = bytes([0x01, fetch_type]) + struct.pack("<I", since_ts)
        print(f"  Write 0x0004: {payload.hex()}")
        try:
            await client.write_gatt_char(FETCH_CTRL, payload, response=False)
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(3)

    # === Method C: Chunked protocol on 0x0016, listen on BOTH 0x0016 and 0x0017 ===
    print("\n" + "=" * 60)
    print("METHOD C: Chunked protocol (0x0016 write, listen both)")
    print("=" * 60)

    for fetch_type in [0x01, 0x07, 0x25]:
        name = FETCH_TYPES.get(fetch_type, "?")
        print(f"\n--- {name} (0x{fetch_type:02x}) ---")
        payload = bytes([0x01, fetch_type]) + struct.pack("<I", since_ts)
        header = struct.pack("<I", len(payload)) + struct.pack("<H", 0x004B)
        packet = bytes([0x03, 0x03, 0x01, 0x00]) + header + payload
        print(f"  Write 0x0016: {packet.hex()}")
        try:
            await client.write_gatt_char(CHUNKED_W, packet, response=False)
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(3)

    # === Method D: Try various endpoints on chunked protocol ===
    print("\n" + "=" * 60)
    print("METHOD D: Chunked protocol — various endpoints")
    print("=" * 60)

    for ep, ep_name in [(0x0001, "0x0001"), (0x0004, "0x0004"), (0x0005, "0x0005"),
                         (0x000A, "0x000A"), (0x0050, "0x0050"), (0x00FD, "0x00FD")]:
        payload = bytes([0x01, 0x01]) + struct.pack("<I", since_ts)  # Activity
        header = struct.pack("<I", len(payload)) + struct.pack("<H", ep)
        packet = bytes([0x03, 0x03, 0x01, 0x00]) + header + payload
        print(f"\n  Endpoint {ep_name}: {packet.hex()}")
        try:
            await client.write_gatt_char(CHUNKED_W, packet, response=False)
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(2)

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
