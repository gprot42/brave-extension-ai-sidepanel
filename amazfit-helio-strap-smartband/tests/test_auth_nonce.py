"""Test: Send phone nonce with cmd 0x06, then respond with cmd 0x08.

Theory: The auth flow on endpoint 0x0082 might be:
  1. Phone → Device: [0x06] + phone_random_16B  (send our nonce)
  2. Device → Phone: [0x06, 0x01] + device_challenge_16B
  3. Phone → Device: [0x08] + AES_ECB(device_challenge, auth_key)
  4. Device → Phone: [0x08, 0x01] = success

Previous tests showed:
  - 0x06 bare → challenge (status 0x01 + 16B)
  - 0x08 + AES → status 0x02 (unique, not 0x06 like other failures)
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
    data_chunks = []
    data_received = 0

    def on_auth(_s, d): auth_q.put_nowait(bytes(d))
    def on_rx(_s, d):
        print(f"  [RX]: {bytes(d).hex()} ({len(d)}b)")
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

        # Standard auth
        await client.start_notify(AUTH_CHAR, on_auth)
        await asyncio.sleep(0.3)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"Auth step 1: {r.hex()}")
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"Auth step 2: {r.hex()}")
        await client.stop_notify(AUTH_CHAR)

        await client.start_notify(CHUNKED_R, on_rx)
        await asyncio.sleep(0.3)

        phone_nonce = os.urandom(16)

        # ── TEST A: [0x06] + phone_nonce, then [0x08] + AES(challenge) ──
        print("\n" + "=" * 60)
        print("TEST A: [0x06]+nonce → [0x08]+AES(challenge)")
        print("=" * 60)

        print(f"  Phone nonce: {phone_nonce.hex()}")
        frame = chunked_frame(0x0082, bytes([0x06]) + phone_nonce)
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        print(f"  Response: {payload.hex()}")

        if len(payload) >= 19 and payload[2] == 0x01:
            challenge = payload[3:19]
            print(f"  Device challenge: {challenge.hex()}")

            encrypted = cipher.encrypt(challenge)
            while not rx_q.empty(): rx_q.get_nowait()

            frame = chunked_frame(0x0082, bytes([0x08]) + encrypted)
            await client.write_gatt_char(CHUNKED_W, frame, response=False)

            resp = await asyncio.wait_for(rx_q.get(), timeout=10)
            ep, payload = parse_resp(resp)
            print(f"  Auth response: {payload.hex()}")
            if len(payload) >= 3:
                print(f"  Status: 0x{payload[2]:02x}" + (" = SUCCESS!" if payload[2] == 0x01 else ""))

        # ── TEST B: [0x06]+nonce, then [0x08]+AES(challenge XOR phone_nonce) ──
        print("\n" + "=" * 60)
        print("TEST B: [0x08]+AES(challenge XOR phone_nonce)")
        print("=" * 60)

        phone_nonce2 = os.urandom(16)
        frame = chunked_frame(0x0082, bytes([0x06]) + phone_nonce2)
        while not rx_q.empty(): rx_q.get_nowait()
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        challenge2 = payload[3:19]
        print(f"  Challenge: {challenge2.hex()}")

        combined = bytes([a ^ b for a, b in zip(challenge2, phone_nonce2)])
        encrypted2 = cipher.encrypt(combined)
        while not rx_q.empty(): rx_q.get_nowait()

        frame = chunked_frame(0x0082, bytes([0x08]) + encrypted2)
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        print(f"  Auth response: {payload.hex()}")
        if len(payload) >= 3:
            print(f"  Status: 0x{payload[2]:02x}" + (" = SUCCESS!" if payload[2] == 0x01 else ""))

        # ── TEST C: [0x06]+nonce, then [0x08]+AES(phone_nonce) ──
        print("\n" + "=" * 60)
        print("TEST C: [0x08]+AES(phone_nonce) — encrypt our own nonce")
        print("=" * 60)

        phone_nonce3 = os.urandom(16)
        frame = chunked_frame(0x0082, bytes([0x06]) + phone_nonce3)
        while not rx_q.empty(): rx_q.get_nowait()
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        challenge3 = payload[3:19]

        encrypted3 = cipher.encrypt(phone_nonce3)
        while not rx_q.empty(): rx_q.get_nowait()

        frame = chunked_frame(0x0082, bytes([0x08]) + encrypted3)
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        print(f"  Auth response: {payload.hex()}")
        if len(payload) >= 3:
            print(f"  Status: 0x{payload[2]:02x}" + (" = SUCCESS!" if payload[2] == 0x01 else ""))

        # ── TEST D: [0x06] bare, then [0x08]+AES(challenge) with sub-byte ──
        print("\n" + "=" * 60)
        print("TEST D: [0x06] bare → [0x08, sub]+AES(challenge)")
        print("=" * 60)

        frame = chunked_frame(0x0082, bytes([0x06]))
        while not rx_q.empty(): rx_q.get_nowait()
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_resp(resp)
        challenge4 = payload[3:19]
        print(f"  Challenge: {challenge4.hex()}")

        for sub in [0x00, 0x01, 0x02, 0x05, 0x06]:
            encrypted4 = cipher.encrypt(challenge4)
            while not rx_q.empty(): rx_q.get_nowait()

            frame = chunked_frame(0x0082, bytes([0x08, sub]) + encrypted4)
            await client.write_gatt_char(CHUNKED_W, frame, response=False)

            resp = await asyncio.wait_for(rx_q.get(), timeout=10)
            ep, payload = parse_resp(resp)
            status = payload[2] if len(payload) >= 3 else 0xFF
            print(f"  [0x08, 0x{sub:02x}] -> status 0x{status:02x}" +
                  (" = SUCCESS!" if status == 0x01 else ""))

            # Re-get challenge for next iteration
            frame = chunked_frame(0x0082, bytes([0x06]))
            while not rx_q.empty(): rx_q.get_nowait()
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
            resp = await asyncio.wait_for(rx_q.get(), timeout=10)
            ep, payload = parse_resp(resp)
            challenge4 = payload[3:19]

        # ── TEST E: Does 0x0b actually mean "feature not configured"? ──
        print("\n" + "=" * 60)
        print("TEST E: Try enabling features via health endpoint 0x000A")
        print("=" * 60)

        # Send config commands to enable monitoring features
        enable_cmds = [
            ("Enable SpO2 monitoring", bytes([0x01, 0x01, 0x25])),
            ("Enable stress monitoring", bytes([0x01, 0x01, 0x13])),
            ("Enable sleep tracking", bytes([0x01, 0x01, 0x48])),
            ("Enable HRV monitoring", bytes([0x01, 0x01, 0x49])),
            ("Enable all health", bytes([0x01, 0x01, 0xFF])),
            ("Config SpO2 auto", bytes([0x03, 0x25, 0x01])),
            ("Config stress auto", bytes([0x03, 0x13, 0x01])),
            ("Set monitoring on", bytes([0x04, 0x01])),
        ]

        for label, cmd in enable_cmds:
            while not rx_q.empty(): rx_q.get_nowait()
            frame = chunked_frame(0x000A, cmd)
            print(f"  [{label}] -> {cmd.hex()}")
            try:
                await client.write_gatt_char(CHUNKED_W, frame, response=False)
                try:
                    resp = await asyncio.wait_for(rx_q.get(), timeout=3)
                    ep, payload = parse_resp(resp)
                    print(f"    Response: ep=0x{ep:04x} payload={payload.hex()}")
                except asyncio.TimeoutError:
                    print(f"    (no response)")
            except Exception as e:
                print(f"    Error: {e}")
                break

        # ── TEST F: Retry fetch after config ──
        print("\n" + "=" * 60)
        print("TEST F: Retry fetch after config attempts")
        print("=" * 60)
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await asyncio.sleep(0.3)

        for tc, name in [(0x01, "Activity"), (0x25, "SpO2"), (0x13, "Stress")]:
            while not ctrl_q.empty(): ctrl_q.get_nowait()
            cmd = bytes([0x01, tc, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
            await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
            try:
                r = await asyncio.wait_for(ctrl_q.get(), timeout=5)
                status = r[2] if len(r) >= 3 else 0xFF
                print(f"  {name} (0x{tc:02x}): status 0x{status:02x}")
            except asyncio.TimeoutError:
                print(f"  {name}: timeout")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
