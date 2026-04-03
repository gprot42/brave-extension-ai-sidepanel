"""Test challenge-response auth on endpoint 0x0082 (chunked channel).

Discovery: command 0x06 on endpoint 0x0082 returns a 16-byte challenge.
This script attempts to complete the auth by encrypting the challenge
and sending it back via command 0x07.
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
SENSOR_CHAR = "00000002-0000-3512-2118-0009af100700"

_handle = 0


def next_handle():
    global _handle
    _handle += 1
    return _handle & 0xFF


def chunked_frame(endpoint: int, payload: bytes) -> bytes:
    h = next_handle()
    plen = len(payload)
    return bytes([
        0x03, 0x03, 0x00, h, 0x00,
        plen & 0xFF, (plen >> 8) & 0xFF,
        0x00, 0x00,
        endpoint & 0xFF, (endpoint >> 8) & 0xFF,
    ]) + payload


def parse_chunked_response(data: bytes) -> tuple:
    """Parse chunked response frame. Returns (endpoint, payload)."""
    if len(data) < 11:
        return (0, data)
    # byte 0: 0x03 marker
    # byte 1: flags
    # byte 2: reserved
    # byte 3: handle
    # byte 4: chunk index
    # bytes 5-6: payload length (uint16 LE)
    # bytes 7-8: padding
    # bytes 9-10: endpoint (uint16 LE)
    # bytes 11+: payload
    plen = struct.unpack_from('<H', data, 5)[0]
    endpoint = struct.unpack_from('<H', data, 9)[0]
    payload = data[11:11 + plen]
    return (endpoint, payload)


async def main():
    if not AUTH_KEY_HEX:
        print("ERROR: Set AUTH_KEY in .env")
        sys.exit(1)

    auth_key = bytes.fromhex(AUTH_KEY_HEX)

    auth_q: asyncio.Queue[bytes] = asyncio.Queue()
    rx_q: asyncio.Queue[bytes] = asyncio.Queue()
    ctrl_q: asyncio.Queue[bytes] = asyncio.Queue()
    data_chunks: list[bytes] = []
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

        # ── Phase 1: Standard auth ──
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

        # ── Phase 2: Chunked auth on endpoint 0x0082 ──
        print("=== PHASE 2: Chunked Auth (endpoint 0x0082) ===")
        await client.start_notify(CHUNKED_R, on_rx)
        await asyncio.sleep(0.3)

        # Step 1: Request challenge (command 0x06)
        print("  Step 1: Requesting challenge (cmd 0x06)...")
        frame = chunked_frame(0x0082, bytes([0x06]))
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_chunked_response(resp)
        print(f"  Response endpoint=0x{ep:04x} payload={payload.hex()}")

        if len(payload) < 3 or payload[2] != 0x01:
            print(f"  ERROR: Expected status 0x01, got 0x{payload[2]:02x}")
            return

        challenge = payload[3:]
        print(f"  Challenge ({len(challenge)} bytes): {challenge.hex()}")

        if len(challenge) != 16:
            print(f"  WARNING: Expected 16-byte challenge, got {len(challenge)}")
            # Try with what we have, pad if needed
            if len(challenge) < 16:
                challenge = challenge + b'\x00' * (16 - len(challenge))
            else:
                challenge = challenge[:16]

        # Step 2: Encrypt challenge with auth key
        cipher = AES.new(auth_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(challenge)
        print(f"  Encrypted: {encrypted.hex()}")

        # Step 3: Send encrypted response (try command 0x07)
        print("\n  Step 2a: Sending response with cmd 0x07...")
        frame = chunked_frame(0x0082, bytes([0x07]) + encrypted)
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        try:
            resp = await asyncio.wait_for(rx_q.get(), timeout=10)
            ep, payload = parse_chunked_response(resp)
            print(f"  Response endpoint=0x{ep:04x} payload={payload.hex()}")

            if len(payload) >= 3 and payload[2] == 0x01:
                print("\n  *** CHUNKED AUTH SUCCESS (cmd 0x07)! ***")
            else:
                print(f"  Status: 0x{payload[2]:02x}")

                # If 0x07 didn't work, try 0x05
                print("\n  Step 2b: Trying cmd 0x05 instead...")
                # Re-request challenge since it might be single-use
                frame = chunked_frame(0x0082, bytes([0x06]))
                await client.write_gatt_char(CHUNKED_W, frame, response=False)
                resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                ep, payload2 = parse_chunked_response(resp)
                challenge2 = payload2[3:19]
                print(f"  New challenge: {challenge2.hex()}")

                encrypted2 = cipher.encrypt(challenge2)
                frame = chunked_frame(0x0082, bytes([0x05]) + encrypted2)
                await client.write_gatt_char(CHUNKED_W, frame, response=False)

                resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                ep, payload = parse_chunked_response(resp)
                print(f"  Response endpoint=0x{ep:04x} payload={payload.hex()}")

                if len(payload) >= 3 and payload[2] == 0x01:
                    print("\n  *** CHUNKED AUTH SUCCESS (cmd 0x05)! ***")
                else:
                    print(f"  Status: 0x{payload[2]:02x}")

                    # Try 0x03
                    print("\n  Step 2c: Trying cmd 0x03...")
                    frame = chunked_frame(0x0082, bytes([0x06]))
                    await client.write_gatt_char(CHUNKED_W, frame, response=False)
                    resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                    ep, payload3 = parse_chunked_response(resp)
                    challenge3 = payload3[3:19]
                    encrypted3 = cipher.encrypt(challenge3)

                    frame = chunked_frame(0x0082, bytes([0x03]) + encrypted3)
                    await client.write_gatt_char(CHUNKED_W, frame, response=False)

                    resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                    ep, payload = parse_chunked_response(resp)
                    print(f"  Response endpoint=0x{ep:04x} payload={payload.hex()}")

                    if len(payload) >= 3 and payload[2] == 0x01:
                        print("\n  *** CHUNKED AUTH SUCCESS (cmd 0x03)! ***")
                    else:
                        print(f"  Status: 0x{payload[2]:02x}")

                        # Try 0x08
                        print("\n  Step 2d: Trying cmd 0x08...")
                        frame = chunked_frame(0x0082, bytes([0x06]))
                        await client.write_gatt_char(CHUNKED_W, frame, response=False)
                        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                        ep, p4 = parse_chunked_response(resp)
                        c4 = p4[3:19]
                        e4 = cipher.encrypt(c4)

                        frame = chunked_frame(0x0082, bytes([0x08]) + e4)
                        await client.write_gatt_char(CHUNKED_W, frame, response=False)

                        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
                        ep, payload = parse_chunked_response(resp)
                        print(f"  Response endpoint=0x{ep:04x} payload={payload.hex()}")

                        if len(payload) >= 3 and payload[2] == 0x01:
                            print("\n  *** CHUNKED AUTH SUCCESS (cmd 0x08)! ***")
                        else:
                            print(f"  Status: 0x{payload[2]:02x}")

        except asyncio.TimeoutError:
            print("  No response (timeout)")

        # ── Test fetch after auth ──
        print("\n\n=== POST-AUTH FETCH TEST ===")
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        # Activity 0x01
        cmd = bytes([0x01, 0x01, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
        print(f"  Fetch activity (0x01): {cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

        try:
            r = await asyncio.wait_for(ctrl_q.get(), timeout=10)
            print(f"  Response: {r.hex()}")
            if len(r) >= 3:
                status = r[2]
                if status == 0x0b:
                    print(f"  -> 0x0b (still locked)")
                elif status == 0x01:
                    print(f"  -> 0x01 = DATA AVAILABLE!")
                    # Fetch the data
                    print(f"  Expected size: {struct.unpack_from('<I', r, 3)[0] if len(r) > 6 else '?'} bytes")
                    await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
                    await asyncio.sleep(10)
                    print(f"  Received {data_received} bytes in {len(data_chunks)} chunks")
                else:
                    print(f"  -> Status 0x{status:02x}")
        except asyncio.TimeoutError:
            print("  No response")

        # SpO2 0x25
        while not ctrl_q.empty():
            ctrl_q.get_nowait()
        data_chunks.clear()
        data_received = 0

        cmd = bytes([0x01, 0x25, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
        print(f"\n  Fetch SpO2 (0x25): {cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

        try:
            r = await asyncio.wait_for(ctrl_q.get(), timeout=10)
            print(f"  Response: {r.hex()}")
            if len(r) >= 3:
                status = r[2]
                if status == 0x0b:
                    print(f"  -> 0x0b (still locked)")
                elif status == 0x01:
                    print(f"  -> 0x01 = DATA AVAILABLE!")
                else:
                    print(f"  -> Status 0x{status:02x}")
        except asyncio.TimeoutError:
            print("  No response")

        # Stress 0x13
        while not ctrl_q.empty():
            ctrl_q.get_nowait()

        cmd = bytes([0x01, 0x13, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
        print(f"\n  Fetch stress (0x13): {cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)

        try:
            r = await asyncio.wait_for(ctrl_q.get(), timeout=10)
            print(f"  Response: {r.hex()}")
            if len(r) >= 3:
                status = r[2]
                if status == 0x0b:
                    print(f"  -> 0x0b (still locked)")
                elif status == 0x01:
                    print(f"  -> 0x01 = DATA AVAILABLE!")
                else:
                    print(f"  -> Status 0x{status:02x}")
        except asyncio.TimeoutError:
            print("  No response")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
