#!/usr/bin/env python3
"""
Probe all known Zepp OS service endpoints via the chunked protocol (0x0016/0x0017).
Sends CMD_QUERY (0x00), CMD_GET (0x01), CMD_LIST (0x02) to each endpoint.
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
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"
SENSOR = "00000002-0000-3512-2118-0009af100700"

ENDPOINTS = {
    0x0001: "Generic/Config",
    0x0004: "Fetch Control",
    0x0005: "Fetch Data",
    0x000A: "Health Service",
    0x0015: "Config Service",
    0x001D: "Heart Rate Service",
    0x001E: "Workout Service",
    0x002A: "SpO2 Service",
    0x002E: "Calendar/Alarm",
    0x004B: "Activity Fetch",
    0x0050: "File Transfer",
    0x0082: "Auth (Zepp OS)",
    0x00FD: "Unknown FD",
}

CMDS = {
    0x00: "QUERY",
    0x01: "GET",
    0x02: "LIST",
    0x03: "SET",
    0x04: "START",
    0x05: "STOP",
}

seq_counter = [0]


def build_chunked(endpoint, payload):
    """Build a chunked protocol frame for 0x0016."""
    seq_counter[0] += 1
    seq = seq_counter[0] & 0xFF
    flags = 0x03  # first + last
    plen = len(payload)
    # Frame: 03 {flags} {seq} 00 {len_lo} {len_hi} 00 00 {ep_lo} {ep_hi} {payload}
    frame = bytes([0x03, flags, seq, 0x00])
    frame += struct.pack("<H", plen)
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

    # Subscribe to chunked response chars and sensor stream
    responses = asyncio.Queue()

    def on_chunked_r(s, d):
        data = bytes(d)
        print(f"  [0x0016 RESP]: {data.hex()} ({len(data)}b)")
        responses.put_nowait(("0x0016", data))

    def on_chunked_r2(s, d):
        data = bytes(d)
        print(f"  [0x0017 RESP]: {data.hex()} ({len(data)}b)")
        responses.put_nowait(("0x0017", data))

    def on_sensor(s, d):
        pass  # Suppress sensor noise

    await client.start_notify(CHUNKED_W, on_chunked_r)
    await client.start_notify(CHUNKED_R, on_chunked_r2)
    try:
        await client.start_notify(SENSOR, on_sensor)
    except Exception:
        pass
    await asyncio.sleep(0.5)

    # Drain any startup notifications
    while not responses.empty():
        responses.get_nowait()

    print("=" * 70)
    print("Probing Zepp OS service endpoints via chunked protocol")
    print("=" * 70)

    results = {}

    for ep, ep_name in sorted(ENDPOINTS.items()):
        print(f"\n--- Endpoint 0x{ep:04X} ({ep_name}) ---")
        ep_results = {}

        for cmd_id, cmd_name in sorted(CMDS.items()):
            payload = bytes([cmd_id])
            frame = build_chunked(ep, payload)
            print(f"  [{cmd_name}] Write: {frame.hex()}")

            try:
                await client.write_gatt_char(CHUNKED_W, frame, response=False)
            except Exception as e:
                print(f"    Write error: {e}")
                ep_results[cmd_name] = f"WRITE_ERROR: {e}"
                continue

            # Collect responses for 2 seconds
            collected = []
            try:
                deadline = asyncio.get_event_loop().time() + 2.0
                while asyncio.get_event_loop().time() < deadline:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        src, data = await asyncio.wait_for(responses.get(), timeout=remaining)
                        collected.append((src, data))
                    except asyncio.TimeoutError:
                        break
            except Exception:
                pass

            if collected:
                ep_results[cmd_name] = [(s, d.hex()) for s, d in collected]
                for src, data in collected:
                    # Try to decode endpoint from response
                    if len(data) >= 5:
                        resp_byte = data[1]
                        print(f"    -> {src}: {data.hex()} (resp_byte=0x{resp_byte:02x})")
                    else:
                        print(f"    -> {src}: {data.hex()}")
            else:
                ep_results[cmd_name] = "NO_RESPONSE"
                print(f"    -> No response")

        results[f"0x{ep:04X} {ep_name}"] = ep_results

    # Also try some raw payloads on key endpoints
    print("\n" + "=" * 70)
    print("Extended probes on promising endpoints")
    print("=" * 70)

    # Try activity fetch endpoint with proper fetch command
    print("\n--- 0x004B: Fetch activity with data type ---")
    for dtype in [0x01, 0x07, 0x12, 0x25, 0x49, 0x55, 0x56]:
        payload = bytes([dtype])
        frame = build_chunked(0x004B, payload)
        print(f"  Type 0x{dtype:02X}: {frame.hex()}")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        await asyncio.sleep(1.5)
        while not responses.empty():
            src, data = responses.get_nowait()
            print(f"    -> {src}: {data.hex()}")

    # Try health service with measurement triggers
    print("\n--- 0x000A: Health service measurement triggers ---")
    for trigger in [bytes([0x01]), bytes([0x01, 0x12]), bytes([0x01, 0x25]),
                    bytes([0x01, 0x49]), bytes([0x02]), bytes([0x03])]:
        frame = build_chunked(0x000A, trigger)
        print(f"  Trigger {trigger.hex()}: {frame.hex()}")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        await asyncio.sleep(1.5)
        while not responses.empty():
            src, data = responses.get_nowait()
            print(f"    -> {src}: {data.hex()}")

    # Try SpO2 service
    print("\n--- 0x002A: SpO2 service ---")
    for cmd in [bytes([0x00]), bytes([0x01]), bytes([0x02]), bytes([0x03]),
                bytes([0x01, 0x01]), bytes([0x01, 0x00])]:
        frame = build_chunked(0x002A, cmd)
        print(f"  Cmd {cmd.hex()}: {frame.hex()}")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        await asyncio.sleep(1.5)
        while not responses.empty():
            src, data = responses.get_nowait()
            print(f"    -> {src}: {data.hex()}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for ep_name, cmds in results.items():
        responsive = [c for c, v in cmds.items() if v != "NO_RESPONSE" and not str(v).startswith("WRITE_ERROR")]
        if responsive:
            print(f"  {ep_name}: responded to {', '.join(responsive)}")
        else:
            print(f"  {ep_name}: no responses")

    print("\nDone.")
    await client.disconnect()


asyncio.run(main())
