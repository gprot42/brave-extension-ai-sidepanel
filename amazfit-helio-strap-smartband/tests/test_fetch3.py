#!/usr/bin/env python3
"""
Test: set time on device, then try fetch with recent dates.
Many Huami devices require time sync before allowing data fetch.
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
TIME_CHAR = "00002a2b-0000-1000-8000-00805f9b34fb"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"
SENSOR_CTRL = "00000006-0000-3512-2118-0009af100700"


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

    # Read current time from device
    print("=== TIME ===")
    try:
        time_data = await client.read_gatt_char(TIME_CHAR)
        print(f"Current time on device: {time_data.hex()} ({len(time_data)}b)")
        if len(time_data) >= 7:
            year = struct.unpack_from("<H", time_data, 0)[0]
            month, day = time_data[2], time_data[3]
            hour, minute, second = time_data[4], time_data[5], time_data[6]
            print(f"  Parsed: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
    except Exception as e:
        print(f"Read time error: {e}")

    # Set current time
    now = datetime.now()
    time_bytes = struct.pack("<H", now.year) + bytes([
        now.month, now.day, now.hour, now.minute, now.second,
        now.weekday(),  # day of week
        0x00,  # fractions
        0x00,  # adjust reason
    ])
    print(f"\nSetting time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Bytes: {time_bytes.hex()}")
    try:
        await client.write_gatt_char(TIME_CHAR, time_bytes, response=True)
        print("  Time set OK")
    except Exception as e:
        print(f"  Error: {e}")

    await asyncio.sleep(1)

    # Read 0x0006 (sensor config/control)
    print("\n=== SENSOR CONTROL 0x0006 ===")
    try:
        data = await client.read_gatt_char(SENSOR_CTRL)
        print(f"Sensor control: {data.hex()} ({len(data)}b)")
    except Exception as e:
        print(f"Read error: {e}")

    # Subscribe to fetch chars
    ctrl_q = asyncio.Queue()
    data_q = asyncio.Queue()

    await client.start_notify(FETCH_CTRL, lambda s, d: (
        print(f"  [CTRL]: {bytes(d).hex()} ({len(d)}b)"),
        ctrl_q.put_nowait(bytes(d)),
    ))
    await client.start_notify(FETCH_DATA, lambda s, d: (
        print(f"  [DATA]: {bytes(d).hex()} ({len(d)}b)"),
        data_q.put_nowait(bytes(d)),
    ))
    await asyncio.sleep(0.5)

    # Try fetch with RECENT dates (last 24 hours, last 7 days)
    dates = [
        ("1 hour ago", datetime(now.year, now.month, now.day, now.hour - 1 if now.hour > 0 else 23, 0)),
        ("Today midnight", datetime(now.year, now.month, now.day, 0, 0)),
        ("Yesterday", datetime(now.year, now.month, now.day - 1 if now.day > 1 else 1, 0, 0)),
        ("1 week ago", datetime(2026, 3, 25, 0, 0)),
        ("1 month ago", datetime(2026, 3, 1, 0, 0)),
    ]

    for label, dt in dates:
        print(f"\n=== FETCH: Activity since {label} ({dt}) ===")
        cmd = bytes([0x01, 0x01,
                     dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                     dt.month, dt.day, dt.hour, dt.minute, 0x00, 0x00])
        print(f"  Cmd: {cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

        try:
            r = await asyncio.wait_for(ctrl_q.get(), 5)
            print(f"  Response: {r.hex()}")
            if len(r) >= 3 and r[0] == 0x10 and r[2] == 0x01:
                print("  DATA AVAILABLE! Fetching...")
                await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
                total = bytearray()
                while True:
                    try:
                        chunk = await asyncio.wait_for(data_q.get(), 3)
                        total.extend(chunk)
                    except asyncio.TimeoutError:
                        break
                print(f"  Got {len(total)} bytes")
                if total:
                    print(f"  Data: {bytes(total[:100]).hex()}")
                await client.write_gatt_char(FETCH_CTRL, bytes([0x03]), response=False)
        except asyncio.TimeoutError:
            print("  No response")

        while not ctrl_q.empty():
            ctrl_q.get_nowait()
        while not data_q.empty():
            data_q.get_nowait()

    # Try different fetch type codes
    print("\n\n=== TRY ALL TYPE CODES (last 7 days) ===")
    dt = datetime(2026, 3, 25, 0, 0)
    for type_code in range(0x00, 0x60):
        cmd = bytes([0x01, type_code,
                     dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                     dt.month, dt.day, dt.hour, dt.minute, 0x00, 0x00])
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        try:
            r = await asyncio.wait_for(ctrl_q.get(), 1.0)
            status = r[2] if len(r) >= 3 else -1
            if status != 0x0b:  # Only print non-0x0b responses
                print(f"  Type 0x{type_code:02x}: {r.hex()} — status=0x{status:02x}")
        except asyncio.TimeoutError:
            pass
        while not ctrl_q.empty():
            ctrl_q.get_nowait()

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
