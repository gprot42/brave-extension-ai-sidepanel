"""Test: 0x06 challenge + 0x09 AES response on endpoint 0x0082, then fetch data.

Discovery: cmd 0x09 + AES_ECB(challenge, auth_key) returned status 0x01.
This might be the correct auth response command. Verify by fetching after auth.
"""

import asyncio
import logging
import os
import struct
import sys
from dotenv import load_dotenv
from bleak import BleakClient
from Crypto.Cipher import AES

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(message)s")

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY_HEX = os.getenv("AUTH_KEY", "")
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"

_handle = 0


def next_handle():
    global _handle
    _handle += 1
    return _handle & 0xFF


def chunked_frame(endpoint, payload):
    h = next_handle()
    plen = len(payload)
    return bytes([
        0x03, 0x03, 0x00, h, 0x00,
        plen & 0xFF, (plen >> 8) & 0xFF,
        0x00, 0x00,
        endpoint & 0xFF, (endpoint >> 8) & 0xFF,
    ]) + payload


def parse_resp(data):
    if len(data) < 11:
        return (0, data)
    plen = struct.unpack_from('<H', data, 5)[0]
    ep = struct.unpack_from('<H', data, 9)[0]
    return (ep, data[11:11 + plen])


async def main():
    if not AUTH_KEY_HEX:
        print("Set AUTH_KEY"); sys.exit(1)
    auth_key = bytes.fromhex(AUTH_KEY_HEX)
    cipher = AES.new(auth_key, AES.MODE_ECB)

    auth_q: asyncio.Queue = asyncio.Queue()
    rx_q: asyncio.Queue = asyncio.Queue()
    ctrl_q: asyncio.Queue = asyncio.Queue()
    data_chunks: list = []
    data_received = 0

    def on_auth(_s, d): auth_q.put_nowait(bytes(d))
    def on_rx(_s, d):
        print(f"  [0x0017]: {bytes(d).hex()} ({len(d)}b)")
        rx_q.put_nowait(bytes(d))
    def on_ctrl(_s, d):
        print(f"  [CTRL]: {bytes(d).hex()} ({len(d)}b)")
        ctrl_q.put_nowait(bytes(d))
    def on_data(_s, d):
        nonlocal data_received
        data_chunks.append(bytes(d))
        data_received += len(d)

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}\n")

        # Phase 1: Standard auth
        print("=== PHASE 1: Standard Auth ===")
        await client.start_notify(AUTH_CHAR, on_auth)
        await asyncio.sleep(0.3)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"  Step 1: {r.hex()}")
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"  Step 2: {r.hex()}")
        await client.stop_notify(AUTH_CHAR)
        print("  OK\n")

        # Phase 2: Chunked auth
        print("=== PHASE 2: Chunked Auth (0x0082) ===")
        await client.start_notify(CHUNKED_R, on_rx)
        await asyncio.sleep(0.3)

        # First: test cmd 0x09 bare (no payload) to see if it always returns 0x01
        print("  Test: cmd 0x09 bare (no payload)...")
        frame = chunked_frame(0x0082, bytes([0x09]))
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        try:
            resp = await asyncio.wait_for(rx_q.get(), timeout=5)
            ep, payload = parse_resp(resp)
            print(f"  -> 0x09 bare: {payload.hex()}")
            bare_status = payload[2] if len(payload) >= 3 else None
        except asyncio.TimeoutError:
            print(f"  -> 0x09 bare: timeout")
            bare_status = None

        # Now do the real auth: challenge + response
        print("\n  Step 1: Get challenge (cmd 0x06)...")
        while not rx_q.empty():
            rx_q.get_nowait()

        frame = chunked_frame(0x0082, bytes([0x06]))
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        print(f"  Response: {payload.hex()}")
        challenge = payload[3:19]
        print(f"  Challenge: {challenge.hex()}")

        encrypted = cipher.encrypt(challenge)
        print(f"  AES_ECB(challenge): {encrypted.hex()}")

        # Step 2: Send response with cmd 0x09
        print("\n  Step 2: Send cmd 0x09 + AES(challenge)...")
        while not rx_q.empty():
            rx_q.get_nowait()

        frame = chunked_frame(0x0082, bytes([0x09]) + encrypted)
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        print(f"  Response: {payload.hex()}")
        auth_status = payload[2] if len(payload) >= 3 else None

        if auth_status == 0x01:
            print(f"\n  *** AUTH STATUS 0x01 ***")
            if bare_status == 0x01:
                print(f"  WARNING: 0x09 bare also returned 0x01 — might not be real auth")
            else:
                print(f"  0x09 bare returned 0x{bare_status:02x}, so auth response IS different!")
        else:
            print(f"  Auth status: 0x{auth_status:02x}")

        # Phase 3: Test data fetch
        print("\n\n=== PHASE 3: Data Fetch Test ===")
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        test_types = [
            (0x01, "Activity"),
            (0x25, "SpO2"),
            (0x13, "Stress (auto)"),
            (0x48, "Sleep"),
            (0x49, "HRV"),
        ]

        for type_code, name in test_types:
            while not ctrl_q.empty():
                ctrl_q.get_nowait()
            data_chunks.clear()
            data_received = 0

            cmd = bytes([0x01, type_code, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
            print(f"\n  Fetch {name} (0x{type_code:02x}): {cmd.hex()}")
            await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

            try:
                r = await asyncio.wait_for(ctrl_q.get(), timeout=10)
                if len(r) >= 3:
                    status = r[2]
                    if status == 0x0b:
                        print(f"  -> 0x0b (locked/not available)")
                    elif status == 0x01:
                        print(f"  -> 0x01 = DATA AVAILABLE!")
                        if len(r) >= 7:
                            size = struct.unpack_from('<I', r, 3)[0]
                            print(f"  -> Expected {size} bytes")
                        # Start transfer
                        await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
                        await asyncio.sleep(5)
                        print(f"  -> Received {data_received} bytes in {len(data_chunks)} chunks")
                    elif status == 0x05:
                        print(f"  -> 0x05 (unsupported type)")
                    else:
                        print(f"  -> Status 0x{status:02x}")
            except asyncio.TimeoutError:
                print(f"  -> No response (timeout)")

        print("\n\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
