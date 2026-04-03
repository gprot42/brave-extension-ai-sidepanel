#!/usr/bin/env python3
"""
Brute-force auth test: subscribe to ALL notifiable characteristics,
then try every plausible auth method to see what triggers a response.
"""

import asyncio
import os
import struct
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")


async def main():
    client = BleakClient(DEVICE_ID)
    await client.connect(timeout=15.0)
    print(f"Connected: {client.is_connected}\n")

    # Subscribe to ALL notifiable characteristics
    print("=== Subscribing to ALL notifiable chars ===")
    for service in client.services:
        for char in service.characteristics:
            if "notify" in char.properties:
                uuid_short = char.uuid.split("-")[0]
                try:
                    def make_handler(name):
                        def handler(sender, data):
                            print(f"  ** NOTIFY [{name}]: {data.hex()} ({len(data)} bytes)")
                        return handler
                    await client.start_notify(char.uuid, make_handler(uuid_short))
                    print(f"  Subscribed: {uuid_short} ({char.uuid})")
                except Exception as e:
                    print(f"  FAILED: {uuid_short} — {e}")

    await asyncio.sleep(1)
    key = bytes.fromhex(AUTH_KEY) if AUTH_KEY else b"\x00" * 16

    # Test 1: Legacy auth write to 0xFEDD (write-with-response)
    print("\n=== Test 1: Legacy write to 0xFEDD (response=True) ===")
    try:
        await client.write_gatt_char(
            "0000fedd-0000-1000-8000-00805f9b34fb",
            bytes([0x01, 0x00]) + key,
            response=True,
        )
        print("  Write OK")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(2)

    # Read 0xFEDE to check
    print("\n  Reading 0xFEDE...")
    try:
        data = await client.read_gatt_char("0000fede-0000-1000-8000-00805f9b34fb")
        print(f"  0xFEDE = {data.hex()} ({len(data)} bytes)")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 2: Chunked auth on endpoint 0x0082
    print("\n=== Test 2: Chunked endpoint 0x0082 ===")
    payload = bytes([0x01, 0x00]) + key
    header = struct.pack("<I", len(payload)) + struct.pack("<H", 0x0082)
    packet = bytes([0x03, 0x03, 0x01, 0x00]) + header + payload
    try:
        await client.write_gatt_char(
            "00000016-0000-3512-2118-0009af100700", packet, response=False
        )
        print(f"  Sent: {packet.hex()}")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(3)

    # Test 3: Chunked auth on endpoint 0x0001 (some devices use this)
    print("\n=== Test 3: Chunked endpoint 0x0001 ===")
    header = struct.pack("<I", len(payload)) + struct.pack("<H", 0x0001)
    packet = bytes([0x03, 0x03, 0x02, 0x00]) + header + payload
    try:
        await client.write_gatt_char(
            "00000016-0000-3512-2118-0009af100700", packet, response=False
        )
        print(f"  Sent: {packet.hex()}")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(3)

    # Test 4: Write directly to 0x0001 (sensor control, has write+notify)
    print("\n=== Test 4: Direct write to 0x0001 (sensor control) ===")
    try:
        await client.write_gatt_char(
            "00000001-0000-3512-2118-0009af100700",
            bytes([0x01, 0x00]) + key,
            response=True,
        )
        print("  Write OK")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(3)

    # Test 5: Write to 0x0016 (chunked write) — raw auth without chunked framing
    print("\n=== Test 5: Raw auth to 0x0016 (no chunked frame) ===")
    try:
        await client.write_gatt_char(
            "00000016-0000-3512-2118-0009af100700",
            bytes([0x01, 0x00]) + key,
            response=False,
        )
        print("  Write OK")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(3)

    # Test 6: Try writing to 0x0004 (fetch control)
    print("\n=== Test 6: Write to 0x0004 (fetch control) ===")
    try:
        await client.write_gatt_char(
            "00000004-0000-3512-2118-0009af100700",
            bytes([0x01, 0x00]) + key,
            response=False,
        )
        print("  Write OK")
    except Exception as e:
        print(f"  Error: {e}")
    await asyncio.sleep(3)

    # Test 7: Chunked auth with different framing (flags=0x01 first-only, then 0x02 last-only)
    print("\n=== Test 7: Chunked endpoint 0x0082, flags variations ===")
    for flags_byte, desc in [(0x01, "first-only"), (0x07, "first+last+ack"), (0x00, "no-flags")]:
        payload = bytes([0x01, 0x00]) + key
        header = struct.pack("<I", len(payload)) + struct.pack("<H", 0x0082)
        packet = bytes([0x03, flags_byte, 0x10, 0x00]) + header + payload
        try:
            await client.write_gatt_char(
                "00000016-0000-3512-2118-0009af100700", packet, response=False
            )
            print(f"  Sent ({desc}): {packet.hex()}")
        except Exception as e:
            print(f"  Error ({desc}): {e}")
        await asyncio.sleep(2)

    # Read 0xFEDE one more time
    print("\n=== Final read of 0xFEDE ===")
    try:
        data = await client.read_gatt_char("0000fede-0000-1000-8000-00805f9b34fb")
        print(f"  0xFEDE = {data.hex()} ({len(data)} bytes)")
    except Exception as e:
        print(f"  Error: {e}")

    print("\nDone. Disconnecting...")
    await client.disconnect()


asyncio.run(main())
