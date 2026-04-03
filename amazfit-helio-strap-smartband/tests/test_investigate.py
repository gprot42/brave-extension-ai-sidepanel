#!/usr/bin/env python3
"""
Investigate remaining data sources on the Helio Strap:
1. Fetch type 0x56 (confirmed data available) and decode it
2. Capture 0x0002 sensor stream and analyze format
3. Try sensor control writes to 0x0006 to trigger SpO2/stress measurements
"""

import asyncio
import os
import struct
from datetime import datetime, timedelta
from collections import Counter
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"
SENSOR_DATA = "00000002-0000-3512-2118-0009af100700"
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
    print("Auth OK\n")

    # ================================================================
    # PART 1: Capture 0x0002 sensor stream for 15 seconds
    # ================================================================
    print("=" * 60)
    print("PART 1: Sensor stream (0x0002) — 15 seconds")
    print("=" * 60)

    sensor_packets = []

    def on_sensor(s, d):
        sensor_packets.append(bytes(d))

    await client.start_notify(SENSOR_DATA, on_sensor)
    await asyncio.sleep(15)
    await client.stop_notify(SENSOR_DATA)

    print(f"Captured {len(sensor_packets)} packets")

    # Analyze packet sizes
    sizes = Counter(len(p) for p in sensor_packets)
    print(f"Packet sizes: {dict(sizes)}")

    # Group by size and analyze
    for size, count in sorted(sizes.items()):
        packets_of_size = [p for p in sensor_packets if len(p) == size]
        print(f"\n--- {size}-byte packets ({count} total) ---")
        print(f"First 5:")
        for p in packets_of_size[:5]:
            print(f"  {p.hex()}")

        if size == 6:
            # Analyze 6-byte packets
            print(f"\nByte analysis (6-byte):")
            for bi in range(6):
                vals = [p[bi] for p in packets_of_size]
                print(f"  byte[{bi}]: min={min(vals)} max={max(vals)} unique={len(set(vals))}")

            # Check if bytes 4-5 are a 16-bit value
            vals_16 = [struct.unpack_from("<H", p, 4)[0] for p in packets_of_size]
            print(f"  bytes[4:6] as uint16 LE: min={min(vals_16)} max={max(vals_16)} diff={max(vals_16)-min(vals_16)}")
            vals_16_2 = [struct.unpack_from("<H", p, 2)[0] for p in packets_of_size]
            print(f"  bytes[2:4] as uint16 LE: min={min(vals_16_2)} max={max(vals_16_2)} unique={len(set(vals_16_2))}")

        elif size == 11:
            # Analyze 11-byte packets
            print(f"\nByte analysis (11-byte):")
            for bi in range(11):
                vals = [p[bi] for p in packets_of_size]
                print(f"  byte[{bi}]: min={min(vals)} max={max(vals)} unique={len(set(vals))}")

            # Check timestamp-like values at offset 3
            ts_vals = [struct.unpack_from("<I", p, 3)[0] for p in packets_of_size]
            print(f"\n  bytes[3:7] as uint32 LE: min={min(ts_vals)} max={max(ts_vals)}")
            if len(ts_vals) > 1:
                diffs = [ts_vals[i+1] - ts_vals[i] for i in range(min(10, len(ts_vals)-1))]
                print(f"  diffs (first 10): {diffs}")

            # Check bytes 7-10
            val_32 = [struct.unpack_from("<I", p, 7)[0] for p in packets_of_size]
            print(f"  bytes[7:11] as uint32 LE: min={min(val_32)} max={max(val_32)}")
            val_16a = [struct.unpack_from("<H", p, 7)[0] for p in packets_of_size]
            val_16b = [struct.unpack_from("<H", p, 9)[0] for p in packets_of_size]
            print(f"  bytes[7:9] as uint16 LE: min={min(val_16a)} max={max(val_16a)}")
            print(f"  bytes[9:11] as uint16 LE: min={min(val_16b)} max={max(val_16b)}")

    # ================================================================
    # PART 2: Try sensor control commands on 0x0006
    # ================================================================
    print("\n" + "=" * 60)
    print("PART 2: Sensor control (0x0006) — trigger measurements")
    print("=" * 60)

    sensor_ctrl_q = asyncio.Queue()
    await client.start_notify(SENSOR_CTRL, lambda s, d: (
        print(f"  [0x0006]: {bytes(d).hex()} ({len(d)}b)"),
        sensor_ctrl_q.put_nowait(bytes(d)),
    ))
    await asyncio.sleep(0.3)

    # Also re-subscribe to 0x0002 to see sensor responses
    sensor_packets.clear()
    await client.start_notify(SENSOR_DATA, on_sensor)

    # Try known Huami sensor control commands
    commands = [
        ("SpO2 start", bytes([0x01, 0x00])),
        ("SpO2 start v2", bytes([0x01, 0x25])),
        ("Stress start", bytes([0x01, 0x12])),
        ("HRV start", bytes([0x01, 0x49])),
        ("Enable continuous HR", bytes([0x15, 0x01, 0x01])),
        ("Enable all sensors", bytes([0x01, 0x01, 0x19, 0x00])),
        ("Sensor read cmd", bytes([0x02])),
    ]

    for label, cmd in commands:
        print(f"\n  {label}: write {cmd.hex()}")
        before = len(sensor_packets)
        try:
            await client.write_gatt_char(SENSOR_CTRL, cmd, response=False)
            await asyncio.sleep(3)
            after = len(sensor_packets)
            print(f"    -> {after - before} new sensor packets")
            # Check 0x0006 responses
            while not sensor_ctrl_q.empty():
                resp = sensor_ctrl_q.get_nowait()
                print(f"    -> 0x0006 response: {resp.hex()}")
        except Exception as e:
            print(f"    -> Error: {e}")

    await client.stop_notify(SENSOR_DATA)
    await client.stop_notify(SENSOR_CTRL)

    # ================================================================
    # PART 3: Fetch type 0x56
    # ================================================================
    print("\n" + "=" * 60)
    print("PART 3: Fetch type 0x56")
    print("=" * 60)

    ctrl_q = asyncio.Queue()
    data_chunks = []
    data_bytes = [0]

    def on_ctrl(s, d):
        ctrl_q.put_nowait(bytes(d))

    def on_data(s, d):
        data_chunks.append(bytes(d))
        data_bytes[0] += len(d)
        if len(data_chunks) % 500 == 0:
            print(f"  [DATA]: {data_bytes[0]} bytes ({len(data_chunks)} chunks)")

    await client.start_notify(FETCH_CTRL, on_ctrl)
    await client.start_notify(FETCH_DATA, on_data)
    await asyncio.sleep(0.3)

    dt = datetime(2026, 3, 25, 0, 0)
    cmd = bytes([0x01, 0x56,
                 dt.year & 0xFF, (dt.year >> 8) & 0xFF,
                 dt.month, dt.day, dt.hour, dt.minute, 0x00, 0x00])
    print(f"Init fetch: {cmd.hex()}")
    await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

    try:
        r = await asyncio.wait_for(ctrl_q.get(), 15)
        print(f"Response: {r.hex()}")

        if len(r) >= 3 and r[0] == 0x10 and r[1] == 0x01 and r[2] == 0x01:
            if len(r) >= 7:
                expected = struct.unpack_from("<I", r, 3)[0]
                print(f"Expected: {expected} bytes")
            if len(r) >= 13:
                year = struct.unpack_from("<H", r, 7)[0]
                month, day = r[9], r[10]
                hour, minute = r[11], r[12]
                print(f"Data from: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")

            # Start transfer
            print("\nStarting transfer...")
            await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)

            last = 0
            stall = 0
            while True:
                await asyncio.sleep(1)
                if data_bytes[0] == last:
                    stall += 1
                    if stall >= 5:
                        break
                else:
                    stall = 0
                    last = data_bytes[0]
                while not ctrl_q.empty():
                    msg = ctrl_q.get_nowait()
                    print(f"  [CTRL]: {msg.hex()}")

            print(f"\nTotal: {data_bytes[0]} bytes in {len(data_chunks)} chunks")

            # ACK
            await client.write_gatt_char(FETCH_CTRL, bytes([0x03]), response=False)

            # Save and analyze
            raw = b"".join(data_chunks)
            with open("raw_fetch_0x56.bin", "wb") as f:
                f.write(raw)
            print(f"Saved to raw_fetch_0x56.bin")

            # Strip chunk sequence bytes and analyze
            payload = bytearray()
            pos = 0
            while pos < len(raw):
                chunk_size = min(241, len(raw) - pos)
                payload.extend(raw[pos + 1:pos + chunk_size])
                pos += chunk_size

            print(f"\nPayload: {len(payload)} bytes")

            # Try 5-byte records (same as 0x55)
            if len(payload) % 5 == 0:
                n = len(payload) // 5
                print(f"5-byte records: {n}")
                print("First 20:")
                for i in range(min(20, n)):
                    rec = payload[i*5:i*5+5]
                    seq = struct.unpack_from("<H", rec, 0)[0]
                    b1, b2, val = rec[2], rec[3], rec[4]
                    print(f"  seq={seq:5d} b1={b1:3d} b2={b2:3d} val={val:3d}")

                # Analyze value distribution
                vals = [payload[i*5+4] for i in range(n)]
                b1s = set(payload[i*5+2] for i in range(n))
                b2s = set(payload[i*5+3] for i in range(n))
                print(f"\nValue range: [{min(vals)}, {max(vals)}] mean={sum(vals)/len(vals):.1f}")
                print(f"Unique b1: {sorted(b1s)}")
                print(f"Unique b2: {sorted(b2s)}")

                # Value distribution
                print("\nValue histogram (top 20):")
                freq = Counter(vals)
                for v, c in freq.most_common(20):
                    print(f"  {v:3d}: {c:6d} ({100*c/n:.1f}%)")

            # Also try other record sizes
            for rs in [3, 4, 6, 7, 8]:
                if len(payload) % rs == 0:
                    print(f"\n{rs}-byte records: {len(payload)//rs}")

            # Print first 256 bytes hex
            print(f"\nFirst 256 bytes:")
            for i in range(0, min(256, len(payload)), 16):
                h = " ".join(f"{b:02x}" for b in payload[i:i+16])
                a = "".join(chr(b) if 32 <= b < 127 else "." for b in payload[i:i+16])
                print(f"  {i:04x}: {h:<48s} {a}")
        else:
            print(f"No data (status: 0x{r[2]:02x})")

    except asyncio.TimeoutError:
        print("No response (timeout)")

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
