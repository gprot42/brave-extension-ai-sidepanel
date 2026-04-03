#!/usr/bin/env python3
"""
Try different auth step 2 variants to get a challenge from the device.
The '05' in response 10010105 might indicate required auth method.
"""

import asyncio
import os
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"


async def main():
    key = bytes.fromhex(AUTH_KEY)
    client = BleakClient(DEVICE_ID)
    await client.connect(timeout=15.0)
    print(f"Connected: {client.is_connected}\n")

    q = asyncio.Queue()

    def on_notify(s, d):
        print(f"  NOTIFY: {bytes(d).hex()} ({len(d)}b)")
        q.put_nowait(bytes(d))

    await client.start_notify(AUTH_CHAR, on_notify)
    await asyncio.sleep(0.3)

    # Step 1: Send key (standard)
    print("Step 1: Send key [0x01, 0x00] + key")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + key, response=True)
    r = await asyncio.wait_for(q.get(), 10)
    print(f"  -> {r.hex()}\n")

    # Try many step 2 variants
    variants = [
        ([0x02, 0x00], "standard"),
        ([0x02, 0x05], "auth-type-05 (from step1 response)"),
        ([0x02, 0x08], "new-auth (0x08)"),
        ([0x02, 0x01], "variant 0x01"),
        ([0x02, 0x02], "variant 0x02"),
        ([0x02, 0x04], "variant 0x04"),
        ([0x02, 0x82], "variant 0x82"),
        ([0x02, 0x10], "variant 0x10"),
    ]

    for cmd, desc in variants:
        print(f"Step 2: {desc} — {bytes(cmd).hex()}")
        await client.write_gatt_char(AUTH_CHAR, bytes(cmd), response=True)

        try:
            r = await asyncio.wait_for(q.get(), 5)
            print(f"  -> {r.hex()} ({len(r)}b)")
            if len(r) > 3:
                print(f"  -> HAS EXTRA DATA! Challenge bytes: {r[3:].hex()}")
        except asyncio.TimeoutError:
            print(f"  -> No response (timeout)")
        print()

    # Also try step 1 with different second byte, then step 2
    print("=" * 50)
    print("Trying step 1 with [0x01, 0x05] + key")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x05]) + key, response=True)
    try:
        r = await asyncio.wait_for(q.get(), 5)
        print(f"  -> {r.hex()}")
    except asyncio.TimeoutError:
        print(f"  -> No response")

    print("\nStep 2: [0x02, 0x05]")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x05]), response=True)
    try:
        r = await asyncio.wait_for(q.get(), 5)
        print(f"  -> {r.hex()} ({len(r)}b)")
        if len(r) > 3:
            print(f"  -> Challenge: {r[3:].hex()}")
    except asyncio.TimeoutError:
        print(f"  -> No response")

    print("\n" + "=" * 50)
    print("Trying step 1 with [0x01, 0x08] + key")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x08]) + key, response=True)
    try:
        r = await asyncio.wait_for(q.get(), 5)
        print(f"  -> {r.hex()}")
    except asyncio.TimeoutError:
        print(f"  -> No response")

    print("\nStep 2: [0x02, 0x08]")
    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x08]), response=True)
    try:
        r = await asyncio.wait_for(q.get(), 5)
        print(f"  -> {r.hex()} ({len(r)}b)")
        if len(r) > 3:
            print(f"  -> Challenge: {r[3:].hex()}")
    except asyncio.TimeoutError:
        print(f"  -> No response")

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
