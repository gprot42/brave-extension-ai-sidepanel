#!/usr/bin/env python3
"""
Trigger on-device SpO2/stress/HRV measurements via BLE and monitor
the sensor stream (0x0002) and chunked responses for new data patterns.
"""

import asyncio
import os
import struct
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
SENSOR = "00000002-0000-3512-2118-0009af100700"
SENSOR_CTRL = "00000006-0000-3512-2118-0009af100700"

seq_counter = [0]


def build_chunked(endpoint, payload):
    seq_counter[0] += 1
    seq = seq_counter[0] & 0xFF
    frame = bytes([0x03, 0x03, seq, 0x00])
    frame += struct.pack("<H", len(payload))
    frame += bytes([0x00, 0x00])
    frame += struct.pack("<H", endpoint)
    frame += payload
    return frame


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

    # Collect all sensor + chunked data
    sensor_packets = []
    chunked_packets = []

    def on_sensor(s, d):
        data = bytes(d)
        sensor_packets.append(data)
        print(f"  [SENSOR]: {data.hex()} ({len(data)}b)")

    def on_chunked(s, d):
        data = bytes(d)
        chunked_packets.append(data)
        print(f"  [CHUNKED]: {data.hex()} ({len(data)}b)")

    await client.start_notify(SENSOR, on_sensor)
    await client.start_notify(CHUNKED_W, on_chunked)
    await asyncio.sleep(0.5)

    # Baseline: capture 5 seconds of normal sensor data
    print("=" * 60)
    print("BASELINE: Normal sensor stream (5 seconds)")
    print("=" * 60)
    baseline_count = len(sensor_packets)
    await asyncio.sleep(5)
    baseline_end = len(sensor_packets)
    print(f"  Baseline: {baseline_end - baseline_count} packets\n")

    # === TEST 1: Trigger SpO2 via chunked endpoint 0x002A ===
    print("=" * 60)
    print("TEST 1: SpO2 trigger via chunked endpoint 0x002A")
    print("=" * 60)
    
    triggers_002a = [
        (bytes([0x01]), "start measurement"),
        (bytes([0x01, 0x01]), "start v2"),
        (bytes([0x04]), "CMD_START"),
        (bytes([0x04, 0x01]), "CMD_START with param"),
    ]
    
    for payload, desc in triggers_002a:
        before = len(sensor_packets)
        frame = build_chunked(0x002A, payload)
        print(f"\n  [{desc}] Write: {frame.hex()}")
        try:
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
        except Exception as e:
            print(f"    Write error: {e}")
            continue
        await asyncio.sleep(5)
        after = len(sensor_packets)
        new_packets = sensor_packets[before:after]
        unique_sizes = set(len(p) for p in new_packets)
        print(f"    -> {after - before} sensor packets, sizes: {unique_sizes}")
        # Look for any non-standard sensor data
        for p in new_packets:
            if len(p) not in (6, 11):
                print(f"    ** NEW PATTERN: {p.hex()}")

    # === TEST 2: Trigger stress via health endpoint 0x000A ===
    print("\n" + "=" * 60)
    print("TEST 2: Stress trigger via health endpoint 0x000A")
    print("=" * 60)

    triggers_000a = [
        (bytes([0x01, 0x12]), "stress trigger"),
        (bytes([0x04, 0x12]), "stress CMD_START"),
        (bytes([0x01, 0x13]), "auto stress trigger"),
        (bytes([0x01, 0x25]), "SpO2 via health"),
        (bytes([0x01, 0x49]), "HRV via health"),
    ]

    for payload, desc in triggers_000a:
        before = len(sensor_packets)
        frame = build_chunked(0x000A, payload)
        print(f"\n  [{desc}] Write: {frame.hex()}")
        try:
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
        except Exception as e:
            print(f"    Write error: {e}")
            continue
        await asyncio.sleep(5)
        after = len(sensor_packets)
        new_packets = sensor_packets[before:after]
        unique_sizes = set(len(p) for p in new_packets)
        print(f"    -> {after - before} sensor packets, sizes: {unique_sizes}")
        for p in new_packets:
            if len(p) not in (6, 11):
                print(f"    ** NEW PATTERN: {p.hex()}")

    # === TEST 3: Direct sensor control via 0x0006 ===
    print("\n" + "=" * 60)
    print("TEST 3: Sensor control via 0x0006")
    print("=" * 60)

    sensor_cmds = [
        (bytes([0x15, 0x01, 0x01]), "enable continuous HR"),
        (bytes([0x15, 0x02, 0x01]), "enable SpO2 sensor"),
        (bytes([0x15, 0x03, 0x01]), "enable stress sensor"),
        (bytes([0x01, 0x00, 0x25, 0x00]), "SpO2 measurement start"),
        (bytes([0x01, 0x00, 0x12, 0x00]), "stress measurement start"),
        (bytes([0x01, 0x00, 0x49, 0x00]), "HRV measurement start"),
    ]

    for cmd, desc in sensor_cmds:
        before = len(sensor_packets)
        print(f"\n  [{desc}] Write 0x0006: {cmd.hex()}")
        try:
            await client.write_gatt_char(SENSOR_CTRL, cmd, response=False)
        except Exception as e:
            print(f"    Write error: {e}")
            continue
        await asyncio.sleep(8)
        after = len(sensor_packets)
        new_packets = sensor_packets[before:after]
        unique_sizes = set(len(p) for p in new_packets)
        print(f"    -> {after - before} sensor packets, sizes: {unique_sizes}")
        for p in new_packets:
            if len(p) not in (6, 11):
                print(f"    ** NEW PATTERN: {p.hex()}")

    # === TEST 4: HR service 0x001D ===
    print("\n" + "=" * 60)
    print("TEST 4: Heart rate service 0x001D")
    print("=" * 60)

    hr_cmds = [
        (bytes([0x01]), "query"),
        (bytes([0x04, 0x01]), "start realtime"),
        (bytes([0x01, 0x01, 0x19, 0x00]), "enable continuous HR + interval"),
    ]

    for payload, desc in hr_cmds:
        frame = build_chunked(0x001D, payload)
        print(f"\n  [{desc}] Write: {frame.hex()}")
        try:
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
        except Exception as e:
            print(f"    Write error: {e}")
            continue
        await asyncio.sleep(3)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # Analyze all sensor packets for unique patterns
    size_counts = {}
    for p in sensor_packets:
        size_counts[len(p)] = size_counts.get(len(p), 0) + 1

    print(f"  Total sensor packets: {len(sensor_packets)}")
    print(f"  Packet size distribution: {size_counts}")
    print(f"  Total chunked responses: {len(chunked_packets)}")

    non_standard = [p for p in sensor_packets if len(p) not in (6, 11)]
    if non_standard:
        print(f"\n  NON-STANDARD SENSOR PACKETS ({len(non_standard)}):")
        for p in non_standard[:20]:
            print(f"    {p.hex()}")
    else:
        print("  No non-standard sensor packets detected")

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
