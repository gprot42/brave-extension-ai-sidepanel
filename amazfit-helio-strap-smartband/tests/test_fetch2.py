#!/usr/bin/env python3
"""
Focused fetch test — subscribes only to necessary chars to avoid
macOS CoreBluetooth notification limits.
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
SENSOR_DATA = "00000002-0000-3512-2118-0009af100700"


async def main():
    client = BleakClient(DEVICE_ID)
    await client.connect(timeout=15.0)
    print(f"Connected: {client.is_connected}")

    # Auth
    key = bytes.fromhex(AUTH_KEY)
    auth_q = asyncio.Queue()
    await client.start_notify(AUTH_CHAR, lambda s, d: auth_q.put_nowait(bytes(d)))
    await asyncio.sleep(0.2)

    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + key, response=True)
    r = await asyncio.wait_for(auth_q.get(), 10)
    print(f"Auth step 1: {r.hex()} — {'OK' if len(r) >= 3 and r[2] == 0x01 else 'FAIL'}")

    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
    r = await asyncio.wait_for(auth_q.get(), 10)
    print(f"Auth step 2: {r.hex()} — bonded")
    print()

    # Stop auth notifications to free up a slot
    await client.stop_notify(AUTH_CHAR)
    await asyncio.sleep(0.2)

    # Subscribe ONLY to fetch-relevant chars
    ctrl_q = asyncio.Queue()
    data_q = asyncio.Queue()
    sensor_q = asyncio.Queue()

    await client.start_notify(FETCH_CTRL, lambda s, d: (
        print(f"  [0x0004 CTRL]: {bytes(d).hex()} ({len(d)}b)"),
        ctrl_q.put_nowait(bytes(d))
    ))
    await client.start_notify(FETCH_DATA, lambda s, d: (
        print(f"  [0x0005 DATA]: {bytes(d).hex()} ({len(d)}b)"),
        data_q.put_nowait(bytes(d))
    ))
    await client.start_notify(SENSOR_DATA, lambda s, d: (
        print(f"  [0x0002 SENS]: {bytes(d).hex()} ({len(d)}b)"),
        sensor_q.put_nowait(bytes(d))
    ))
    await asyncio.sleep(0.5)

    # Drain initial sensor data
    print("Draining sensor stream (2s)...")
    await asyncio.sleep(2)
    while not sensor_q.empty():
        sensor_q.get_nowait()
    while not ctrl_q.empty():
        ctrl_q.get_nowait()

    FETCH_TYPES = {
        0x01: "Activity",
        0x07: "Sleep",
        0x13: "Stress (auto)",
        0x25: "SpO2",
        0x49: "HRV",
    }

    now = datetime.now()

    for fetch_type, name in FETCH_TYPES.items():
        print(f"\n{'='*50}")
        print(f"Fetching: {name} (0x{fetch_type:02x})")
        print(f"{'='*50}")

        # Format A: 8-byte (Gadgetbridge old style)
        # [0x01, type, year_lo, year_hi, month, day, hour, minute]
        dt = datetime(2025, 1, 1)
        cmd_a = bytes([0x01, fetch_type,
                       dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                       dt.month, dt.day, dt.hour, dt.minute])

        # Format B: 10-byte with timezone
        tz_h = 0  # UTC
        tz_m = 0
        cmd_b = cmd_a + bytes([tz_h, tz_m])

        # Format C: 12-byte with timezone + extra
        cmd_c = cmd_b + bytes([0x00, 0x00])

        for label, cmd in [("8-byte", cmd_a), ("10-byte+tz", cmd_b), ("12-byte+tz", cmd_c)]:
            print(f"\n  [{label}] Write 0x0004: {cmd.hex()}")
            try:
                await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
            except Exception as e:
                print(f"  Error: {e}")
                continue

            # Wait for ctrl response
            try:
                resp = await asyncio.wait_for(ctrl_q.get(), timeout=5.0)
                print(f"  CTRL response: {resp.hex()}")

                # If response indicates data available, send fetch command
                if len(resp) >= 3 and resp[0] == 0x10 and resp[2] == 0x01:
                    print(f"  -> Data available! Sending fetch command...")
                    await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)

                    # Collect data from 0x0005
                    total = bytearray()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(data_q.get(), timeout=3.0)
                            total.extend(chunk)
                        except asyncio.TimeoutError:
                            break

                    print(f"  -> Received {len(total)} bytes of data")
                    if total:
                        print(f"  -> First 64 bytes: {bytes(total[:64]).hex()}")

                    # ACK
                    await client.write_gatt_char(FETCH_CTRL, bytes([0x03]), response=False)
                    await asyncio.sleep(0.5)
                    break  # Found working format for this type

                elif len(resp) >= 3 and resp[0] == 0x10:
                    print(f"  -> Status: 0x{resp[2]:02x} (not data-ready)")

            except asyncio.TimeoutError:
                print(f"  No CTRL response (timeout)")

            # Drain queues
            while not ctrl_q.empty():
                ctrl_q.get_nowait()
            while not data_q.empty():
                data_q.get_nowait()
            while not sensor_q.empty():
                sensor_q.get_nowait()

    print("\n\nDone.")
    await client.disconnect()


asyncio.run(main())
