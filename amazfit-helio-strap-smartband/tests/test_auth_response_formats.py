"""Probe all response formats for endpoint 0x0082 challenge-response auth.

The device gives us a 16-byte challenge via cmd 0x06 (status 0x01).
We need to find the correct response format (encryption + command structure).

Tries: AES-ECB, HMAC-SHA256, various command byte + sub-command combos.
"""

import asyncio
import hashlib
import hmac
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


async def get_challenge(client, rx_q):
    """Request a fresh challenge from device."""
    # Drain queue
    while not rx_q.empty():
        rx_q.get_nowait()

    frame = chunked_frame(0x0082, bytes([0x06]))
    await client.write_gatt_char(CHUNKED_W, frame, response=False)
    resp = await asyncio.wait_for(rx_q.get(), timeout=10)
    ep, payload = parse_resp(resp)
    if len(payload) >= 19 and payload[2] == 0x01:
        return payload[3:19]
    return payload[3:] if len(payload) > 3 else None


async def try_response(client, rx_q, response_payload, label):
    """Send a response and check result."""
    challenge = await get_challenge(client, rx_q)
    if challenge is None:
        print(f"  [{label}] Failed to get challenge")
        return None

    # Clear queue
    while not rx_q.empty():
        rx_q.get_nowait()

    frame = chunked_frame(0x0082, response_payload(challenge))
    await client.write_gatt_char(CHUNKED_W, frame, response=False)

    try:
        resp = await asyncio.wait_for(rx_q.get(), timeout=5)
        ep, payload = parse_resp(resp)
        status = payload[2] if len(payload) >= 3 else 0xFF
        status_str = "SUCCESS!" if status == 0x01 else f"0x{status:02x}"
        cmd_echo = payload[1] if len(payload) >= 2 else 0
        print(f"  [{label}] challenge={challenge.hex()[:16]}... -> cmd_echo=0x{cmd_echo:02x} status={status_str}")
        if len(payload) > 3:
            print(f"    extra: {payload[3:].hex()}")
        return status
    except asyncio.TimeoutError:
        print(f"  [{label}] no response")
        return None


async def main():
    if not AUTH_KEY_HEX:
        print("Set AUTH_KEY"); sys.exit(1)
    auth_key = bytes.fromhex(AUTH_KEY_HEX)

    auth_q: asyncio.Queue = asyncio.Queue()
    rx_q: asyncio.Queue = asyncio.Queue()

    def on_auth(_s, d): auth_q.put_nowait(bytes(d))
    def on_rx(_s, d): rx_q.put_nowait(bytes(d))

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Standard auth
        await client.start_notify(AUTH_CHAR, on_auth)
        await asyncio.sleep(0.3)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.wait_for(auth_q.get(), timeout=10)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.wait_for(auth_q.get(), timeout=10)
        await client.stop_notify(AUTH_CHAR)
        print("Auth OK\n")

        await client.start_notify(CHUNKED_R, on_rx)
        await asyncio.sleep(0.3)

        cipher = AES.new(auth_key, AES.MODE_ECB)

        print("=" * 60)
        print("GROUP 1: AES-ECB(challenge, auth_key) — different cmd formats")
        print("=" * 60)

        # [cmd] + AES(challenge)
        for cmd in [0x03, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd: bytes([cmd]) + cipher.encrypt(c),
                f"cmd=0x{cmd:02x} + AES")

        # [cmd, sub] + AES(challenge)
        for cmd, sub in [(0x07, 0x00), (0x07, 0x01), (0x07, 0x05), (0x07, 0x06),
                         (0x06, 0x00), (0x06, 0x01), (0x06, 0x05),
                         (0x05, 0x00), (0x05, 0x01), (0x05, 0x05),
                         (0x08, 0x00), (0x08, 0x01), (0x08, 0x05)]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd, sub=sub: bytes([cmd, sub]) + cipher.encrypt(c),
                f"cmd=0x{cmd:02x},0x{sub:02x} + AES")

        print("\n" + "=" * 60)
        print("GROUP 2: HMAC-SHA256(challenge, auth_key) — different cmd formats")
        print("=" * 60)

        def hmac_sha256(challenge):
            return hmac.new(auth_key, challenge, hashlib.sha256).digest()

        for cmd in [0x03, 0x05, 0x06, 0x07, 0x08]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd: bytes([cmd]) + hmac_sha256(c),
                f"cmd=0x{cmd:02x} + HMAC256")

        for cmd, sub in [(0x07, 0x00), (0x07, 0x05), (0x07, 0x06),
                         (0x06, 0x00), (0x06, 0x05),
                         (0x08, 0x00), (0x08, 0x05)]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd, sub=sub: bytes([cmd, sub]) + hmac_sha256(c),
                f"cmd=0x{cmd:02x},0x{sub:02x} + HMAC256")

        # HMAC-SHA256 truncated to 16 bytes
        for cmd in [0x07, 0x08]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd: bytes([cmd]) + hmac_sha256(c)[:16],
                f"cmd=0x{cmd:02x} + HMAC256[:16]")

        print("\n" + "=" * 60)
        print("GROUP 3: Just encrypted bytes (no command prefix)")
        print("=" * 60)

        await try_response(client, rx_q,
            lambda c: cipher.encrypt(c), "bare AES")
        await try_response(client, rx_q,
            lambda c: hmac_sha256(c), "bare HMAC256")

        print("\n" + "=" * 60)
        print("GROUP 4: AES-ECB with derived keys")
        print("=" * 60)

        # Maybe key is SHA256(auth_key) truncated?
        derived_key = hashlib.sha256(auth_key).digest()[:16]
        cipher2 = AES.new(derived_key, AES.MODE_ECB)

        for cmd in [0x07, 0x08]:
            await try_response(client, rx_q,
                lambda c, cmd=cmd: bytes([cmd]) + cipher2.encrypt(c),
                f"cmd=0x{cmd:02x} + AES(SHA256(key))")

        # Maybe key XOR with something
        xor_key = bytes([b ^ 0x5C for b in auth_key])
        cipher3 = AES.new(xor_key, AES.MODE_ECB)
        await try_response(client, rx_q,
            lambda c: bytes([0x07]) + cipher3.encrypt(c),
            "cmd=0x07 + AES(key^0x5C)")

        print("\n" + "=" * 60)
        print("GROUP 5: Reversed / swapped challenge")
        print("=" * 60)

        await try_response(client, rx_q,
            lambda c: bytes([0x07]) + cipher.encrypt(c[::-1]),
            "cmd=0x07 + AES(reversed)")

        await try_response(client, rx_q,
            lambda c: bytes([0x07]) + cipher.encrypt(bytes(reversed(c))),
            "cmd=0x07 + AES(reversed2)")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
