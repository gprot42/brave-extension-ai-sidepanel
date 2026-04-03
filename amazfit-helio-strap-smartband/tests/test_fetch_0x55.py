#!/usr/bin/env python3
"""
Fetch data using type 0x55 — the type that returned status 0x01 (data available).
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
    await asyncio.wait_for(auth_q.get(), 10)
    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
    await asyncio.wait_for(auth_q.get(), 10)
    await client.stop_notify(AUTH_CHAR)
    print("Auth OK\n")

    # Subscribe to fetch chars
    ctrl_q = asyncio.Queue()
    data_chunks = []
    data_bytes_received = [0]

    def on_ctrl(s, d):
        print(f"  [CTRL]: {bytes(d).hex()} ({len(d)}b)")
        ctrl_q.put_nowait(bytes(d))

    def on_data(s, d):
        data_chunks.append(bytes(d))
        data_bytes_received[0] += len(d)
        if len(data_chunks) % 100 == 0:
            print(f"  [DATA]: {data_bytes_received[0]} bytes so far ({len(data_chunks)} chunks)")

    await client.start_notify(FETCH_CTRL, on_ctrl)
    await client.start_notify(FETCH_DATA, on_data)
    await asyncio.sleep(0.5)

    # Step 1: Init fetch for type 0x55, since 1 week ago
    dt = datetime(2026, 3, 25, 0, 0)
    cmd = bytes([0x01, 0x55,
                 dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                 dt.month, dt.day, dt.hour, dt.minute, 0x00, 0x00])
    print(f"Step 1: Init fetch type 0x55 since {dt}")
    print(f"  Cmd: {cmd.hex()}")
    await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

    # Wait for ctrl response
    r = await asyncio.wait_for(ctrl_q.get(), 10)
    print(f"  Response: {r.hex()}")

    if len(r) >= 3 and r[0] == 0x10 and r[1] == 0x01 and r[2] == 0x01:
        # Parse expected data size
        if len(r) >= 7:
            expected = struct.unpack_from("<I", r, 3)[0]
            print(f"  Expected: {expected} bytes")
            if len(r) >= 15:
                year = struct.unpack_from("<H", r, 7)[0]
                month, day = r[9], r[10]
                hour, minute = r[11], r[12]
                print(f"  Data from: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")

        # Step 2: Start fetch
        print("\nStep 2: Start data transfer")
        await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)

        # Collect data
        print("Receiving data...")
        last_count = 0
        stall_counter = 0
        while True:
            await asyncio.sleep(1)
            current = data_bytes_received[0]
            if current == last_count:
                stall_counter += 1
                if stall_counter >= 5:
                    print(f"  No new data for 5s, stopping")
                    break
            else:
                stall_counter = 0
                last_count = current

            # Check for completion notification on ctrl
            while not ctrl_q.empty():
                msg = ctrl_q.get_nowait()
                print(f"  [CTRL during transfer]: {msg.hex()}")

        print(f"\nTotal received: {data_bytes_received[0]} bytes in {len(data_chunks)} chunks")

        # Step 3: ACK
        print("Step 3: ACK")
        await client.write_gatt_char(FETCH_CTRL, bytes([0x03]), response=False)
        await asyncio.sleep(1)

        # Save raw data
        all_data = b"".join(data_chunks)
        with open("raw_fetch_0x55.bin", "wb") as f:
            f.write(all_data)
        print(f"Saved to raw_fetch_0x55.bin ({len(all_data)} bytes)")

        # Print first 256 bytes for analysis
        print(f"\nFirst 256 bytes:")
        for i in range(0, min(256, len(all_data)), 16):
            hex_part = " ".join(f"{b:02x}" for b in all_data[i:i+16])
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in all_data[i:i+16])
            print(f"  {i:04x}: {hex_part:<48s} {ascii_part}")

        # Also print first few chunk boundaries
        print(f"\nFirst 5 chunk sizes: {[len(c) for c in data_chunks[:5]]}")
        print(f"First 5 chunks hex:")
        for i, c in enumerate(data_chunks[:5]):
            print(f"  Chunk {i}: {c.hex()[:100]}{'...' if len(c.hex()) > 100 else ''}")

    else:
        print(f"  Fetch not available (status: 0x{r[2]:02x})")

    # Also scan a few more type codes above 0x55
    print("\n=== Scan types 0x55-0xFF ===")
    for tc in range(0x55, 0x100):
        cmd = bytes([0x01, tc,
                     dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                     dt.month, dt.day, dt.hour, dt.minute, 0x00, 0x00])
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        try:
            r = await asyncio.wait_for(ctrl_q.get(), 1.0)
            status = r[2] if len(r) >= 3 else -1
            if status == 0x01:
                print(f"  Type 0x{tc:02x}: DATA AVAILABLE — {r.hex()}")
            elif status != 0x0b and status != 0x05:
                print(f"  Type 0x{tc:02x}: status=0x{status:02x} — {r.hex()}")
        except asyncio.TimeoutError:
            pass
        while not ctrl_q.empty():
            ctrl_q.get_nowait()

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
