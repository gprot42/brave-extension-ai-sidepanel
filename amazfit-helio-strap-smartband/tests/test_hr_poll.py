#!/usr/bin/env python3
"""Test HR polling via re-subscribe cycle on 0x2A37."""

import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = bytes.fromhex(os.getenv("AUTH_KEY", ""))

HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
SENSOR_CTRL = "00000006-0000-3512-2118-0009af100700"

hr_readings = []


def on_hr(sender, data):
    raw = bytes(data)
    bpm = raw[1] if len(raw) >= 2 else 0
    ts = datetime.now().strftime("%H:%M:%S")
    hr_readings.append(bpm)
    print(f"  [{ts}] HR: {bpm} bpm  raw={raw.hex()}")


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
        ok = r3[:3] == bytes([0x10, 0x03, 0x01])
        print(f"Auth: {'OK' if ok else 'FAILED'}")
        return ok
    return False


async def main():
    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")
        await do_auth(client)

        # === TEST A: Re-subscribe polling (10 cycles, ~5s each) ===
        print("\n=== TEST A: Re-subscribe polling on 0x2A37 (10 cycles) ===")
        for i in range(10):
            try:
                await client.start_notify(HR_CHAR, on_hr)
                await asyncio.sleep(2)
                await client.stop_notify(HR_CHAR)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"  Cycle {i+1} error: {e}")
                await asyncio.sleep(2)
        print(f"  Result: {len(hr_readings)} readings in 10 cycles")

        # === TEST B: Sensor ctrl + subscribe (enable first, then subscribe) ===
        print("\n=== TEST B: Enable via 0x0006 then re-subscribe (5 cycles) ===")
        count_before = len(hr_readings)
        try:
            await client.write_gatt_char(SENSOR_CTRL, bytes([0x15, 0x01, 0x01]), response=False)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  Sensor ctrl write error: {e}")
        for i in range(5):
            try:
                await client.start_notify(HR_CHAR, on_hr)
                await asyncio.sleep(2)
                await client.stop_notify(HR_CHAR)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"  Cycle {i+1} error: {e}")
                await asyncio.sleep(2)
        print(f"  Result: {len(hr_readings) - count_before} readings in 5 cycles")

        # === TEST C: Subscribe once + write trigger repeatedly ===
        print("\n=== TEST C: Subscribe once + write sensor ctrl repeatedly (10 cycles) ===")
        count_before = len(hr_readings)
        await client.start_notify(HR_CHAR, on_hr)
        for i in range(10):
            try:
                # Try triggering a measurement
                await client.write_gatt_char(SENSOR_CTRL, bytes([0x15, 0x01, 0x01]), response=False)
            except Exception:
                pass
            await asyncio.sleep(3)
        await client.stop_notify(HR_CHAR)
        print(f"  Result: {len(hr_readings) - count_before} readings in 10 cycles")

        # === TEST D: Read 0x2A37 directly (GATT read, not notify) ===
        print("\n=== TEST D: Direct GATT read of 0x2A37 (10 reads, 3s apart) ===")
        for i in range(10):
            try:
                data = await client.read_gatt_char(HR_CHAR)
                raw = bytes(data)
                bpm = raw[1] if len(raw) >= 2 else 0
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"  [{ts}] Read: bpm={bpm} raw={raw.hex()}")
            except Exception as e:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Read error: {e}")
            await asyncio.sleep(3)

        print(f"\nTotal HR readings from notifications: {len(hr_readings)}")
        print("Done.")


asyncio.run(main())
