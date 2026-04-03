#!/usr/bin/env python3
"""Test which method produces continuous real-time HR readings."""

import asyncio
import os
import struct
from datetime import datetime, timezone
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = bytes.fromhex(os.getenv("AUTH_KEY", ""))

HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
SENSOR_DATA = "00000002-0000-3512-2118-0009af100700"
SENSOR_CTRL = "00000006-0000-3512-2118-0009af100700"

hr_count = 0
sensor_hr_count = 0


def on_hr(sender, data):
    global hr_count
    hr_count += 1
    bpm = data[1] if len(data) >= 2 else 0
    print(f"  [0x2A37 HR] bpm={bpm} raw={bytes(data).hex()} (#{hr_count})")


def on_sensor(sender, data):
    global sensor_hr_count
    raw = bytes(data)
    # Log ALL packet types, not just 11-byte and 6-byte
    if len(raw) not in (6, 11):
        sensor_hr_count += 1
        print(f"  [0x0002 NEW] len={len(raw)} raw={raw.hex()} (#{sensor_hr_count})")


def on_ctrl(sender, data):
    print(f"  [0x0006 RESP] raw={bytes(data).hex()}")


async def do_auth(client):
    from Crypto.Cipher import AES
    q = asyncio.Queue()
    await client.start_notify(AUTH_CHAR, lambda s, d: q.put_nowait(bytes(d)))
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + AUTH_KEY, response=True)
    r = await asyncio.wait_for(q.get(), 5)
    if r[:3] == bytes([0x10, 0x01, 0x01]):
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        r2 = await asyncio.wait_for(q.get(), 5)
        if r2[:3] == bytes([0x10, 0x02, 0x01]):
            print("Auth: OK (bonded)")
            return True
        challenge = r2[3:]
        cipher = AES.new(AUTH_KEY, AES.MODE_ECB)
        response = cipher.encrypt(challenge)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x03, 0x00]) + response, response=True)
        r3 = await asyncio.wait_for(q.get(), 5)
        print(f"Auth: {'OK' if r3[:3] == bytes([0x10, 0x03, 0x01]) else 'FAILED'}")
        return r3[:3] == bytes([0x10, 0x03, 0x01])
    return False


async def main():
    global hr_count, sensor_hr_count

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")
        await do_auth(client)

        # Subscribe to ALL relevant characteristics
        await client.start_notify(HR_CHAR, on_hr)
        await client.start_notify(SENSOR_DATA, on_sensor)
        await client.start_notify(SENSOR_CTRL, on_ctrl)
        await asyncio.sleep(0.5)

        # === TEST 1: Just wait (some devices auto-send HR) ===
        print("\n=== TEST 1: Passive wait (5s) ===")
        hr_count = 0
        await asyncio.sleep(5)
        print(f"  Result: {hr_count} HR readings")

        # === TEST 2: Write [0x15, 0x01, 0x01] to 0x0006 ===
        print("\n=== TEST 2: Sensor ctrl [0x15, 0x01, 0x01] on 0x0006 (10s) ===")
        hr_count = 0
        await client.write_gatt_char(SENSOR_CTRL, bytes([0x15, 0x01, 0x01]), response=False)
        await asyncio.sleep(10)
        print(f"  Result: {hr_count} HR readings")

        # === TEST 3: Write [0x01, 0x01, 0x19, 0x00] to 0x0006 ===
        print("\n=== TEST 3: Sensor ctrl [0x01, 0x01, 0x19, 0x00] on 0x0006 (10s) ===")
        hr_count = 0
        await client.write_gatt_char(SENSOR_CTRL, bytes([0x01, 0x01, 0x19, 0x00]), response=False)
        await asyncio.sleep(10)
        print(f"  Result: {hr_count} HR readings")

        # === TEST 4: Write [0x01, 0x03, 0x19] to AUTH char 0x0001 ===
        print("\n=== TEST 4: Auth char [0x01, 0x03, 0x19] on 0x0001 (10s) ===")
        hr_count = 0
        try:
            await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x03, 0x19]), response=True)
        except Exception as e:
            print(f"  Write error: {e}")
        await asyncio.sleep(10)
        print(f"  Result: {hr_count} HR readings")

        # === TEST 5: Write various HR enable commands ===
        print("\n=== TEST 5: Additional enable attempts (5s each) ===")
        cmds = [
            ("0x0006: [0x15, 0x02, 0x01]", SENSOR_CTRL, bytes([0x15, 0x02, 0x01])),
            ("0x0006: [0x15, 0x00, 0x01]", SENSOR_CTRL, bytes([0x15, 0x00, 0x01])),
            ("0x0006: [0x01, 0x00]", SENSOR_CTRL, bytes([0x01, 0x00])),
            ("0x0006: [0x02]", SENSOR_CTRL, bytes([0x02])),
        ]
        for desc, char, cmd in cmds:
            hr_count = 0
            print(f"\n  {desc}")
            try:
                await client.write_gatt_char(char, cmd, response=False)
            except Exception as e:
                print(f"    Write error: {e}")
                continue
            await asyncio.sleep(5)
            print(f"    Result: {hr_count} HR readings")

        print("\nDone.")


asyncio.run(main())
