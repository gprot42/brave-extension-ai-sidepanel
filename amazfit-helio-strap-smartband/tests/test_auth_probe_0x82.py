"""Probe endpoint 0x0082 to discover supported auth types.

The device responded to our ECDH attempt with [10, 04, 28] — status 0x28.
This script probes different auth commands and types to find what works.
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
log = logging.getLogger(__name__)

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY_HEX = os.getenv("AUTH_KEY", "")

AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"

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


async def main():
    if not AUTH_KEY_HEX:
        print("ERROR: Set AUTH_KEY in .env")
        sys.exit(1)

    auth_key = bytes.fromhex(AUTH_KEY_HEX)

    auth_q: asyncio.Queue[bytes] = asyncio.Queue()
    rx_q: asyncio.Queue[bytes] = asyncio.Queue()
    tx_q: asyncio.Queue[bytes] = asyncio.Queue()

    def on_auth(_s, d): auth_q.put_nowait(bytes(d))
    def on_rx(_s, d): rx_q.put_nowait(bytes(d))
    def on_tx(_s, d): tx_q.put_nowait(bytes(d))

    async def drain(q, timeout=0.5):
        results = []
        while True:
            try:
                r = await asyncio.wait_for(q.get(), timeout=timeout)
                results.append(r)
            except asyncio.TimeoutError:
                break
        return results

    async def send_and_recv(endpoint, payload, label="", timeout=5):
        # drain old
        await drain(rx_q, 0.1)
        await drain(tx_q, 0.1)

        frame = chunked_frame(endpoint, payload)
        if label:
            print(f"\n  [{label}] payload={payload.hex()}")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        # Collect responses
        all_resp = []
        for _ in range(5):
            try:
                r = await asyncio.wait_for(rx_q.get(), timeout=timeout)
                print(f"    [0x0017]: {r.hex()} ({len(r)}b)")
                all_resp.append(('rx', r))
            except asyncio.TimeoutError:
                break
        # Also check tx
        while True:
            try:
                r = tx_q.get_nowait()
                print(f"    [0x0016]: {r.hex()} ({len(r)}b)")
                all_resp.append(('tx', r))
            except asyncio.QueueEmpty:
                break
        if not all_resp:
            print(f"    (no response)")
        return all_resp

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Phase 1: standard auth
        await client.start_notify(AUTH_CHAR, on_auth)
        await asyncio.sleep(0.3)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"Auth step 1: {r.hex()}")
        # Parse auth type from response
        auth_type_byte = r[3] if len(r) > 3 else 0
        print(f"  Device auth type byte: 0x{auth_type_byte:02x} ({auth_type_byte})")

        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"Auth step 2: {r.hex()}")
        await client.stop_notify(AUTH_CHAR)
        print("Auth OK\n")

        # Subscribe chunked
        await client.start_notify(CHUNKED_R, on_rx)
        await client.start_notify(CHUNKED_W, on_tx)
        await asyncio.sleep(0.3)

        print("=" * 60)
        print("PROBE 1: Different command bytes on endpoint 0x0082")
        print("=" * 60)

        # Try bare commands
        for cmd_byte in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x10, 0x82]:
            await send_and_recv(0x0082, bytes([cmd_byte]), f"cmd=0x{cmd_byte:02x}", timeout=3)

        print("\n" + "=" * 60)
        print("PROBE 2: Auth command 0x04 with different auth types")
        print("=" * 60)

        # [0x04, auth_type, step, key_type]
        for auth_type in [0x00, 0x01, 0x02, 0x03, 0x04, 0x05]:
            await send_and_recv(0x0082, bytes([0x04, auth_type, 0x00, 0x00]),
                                f"auth_type=0x{auth_type:02x}", timeout=3)

        print("\n" + "=" * 60)
        print("PROBE 3: Auth command 0x04, type 0x05 (from device hint)")
        print("=" * 60)

        # The device said 0x05 in step 1 response — try auth type 5
        for step in [0x00, 0x01, 0x02]:
            for kt in [0x00, 0x01, 0x02]:
                await send_and_recv(0x0082, bytes([0x04, 0x05, step, kt]),
                                    f"type=5 step={step} kt={kt}", timeout=3)

        print("\n" + "=" * 60)
        print("PROBE 4: Try 0x02 command (some devices use this)")
        print("=" * 60)

        await send_and_recv(0x0082, bytes([0x02, 0x00]), "0x02,0x00", timeout=3)
        await send_and_recv(0x0082, bytes([0x02, 0x01]), "0x02,0x01", timeout=3)
        await send_and_recv(0x0082, bytes([0x02, 0x05]), "0x02,0x05", timeout=3)
        await send_and_recv(0x0082, bytes([0x02, 0x00, 0x02]), "0x02,0x00,0x02", timeout=3)

        print("\n" + "=" * 60)
        print("PROBE 5: HMAC-SHA256 auth attempt (type 0x01)")
        print("=" * 60)

        # HMAC auth: [0x04, 0x01, 0x00] + HMAC_key or nonce
        # Send just the init command
        await send_and_recv(0x0082, bytes([0x04, 0x01, 0x00]), "hmac init bare", timeout=3)
        # With key type
        await send_and_recv(0x0082, bytes([0x04, 0x01, 0x00, 0x01]), "hmac init kt=1", timeout=3)
        await send_and_recv(0x0082, bytes([0x04, 0x01, 0x00, 0x02]), "hmac init kt=2", timeout=3)

        print("\n" + "=" * 60)
        print("PROBE 6: Try different endpoints for auth")
        print("=" * 60)

        for ep in [0x0001, 0x0002, 0x0010, 0x0015, 0x001D, 0x0050, 0x0075, 0x00FD]:
            await send_and_recv(ep, bytes([0x04, 0x02, 0x00, 0x02]),
                                f"ep=0x{ep:04x}", timeout=2)

        print("\n" + "=" * 60)
        print("PROBE 7: Query device capabilities on 0x0082")
        print("=" * 60)

        # Various "get info" commands
        await send_and_recv(0x0082, bytes([0x00]), "query 0x00", timeout=3)
        await send_and_recv(0x0082, bytes([0x01, 0x00]), "query 0x01,00", timeout=3)
        await send_and_recv(0x0082, bytes([0x01, 0x01]), "query 0x01,01", timeout=3)
        await send_and_recv(0x0082, bytes([0x01, 0x05]), "query 0x01,05", timeout=3)
        await send_and_recv(0x0082, bytes([0x03, 0x00]), "query 0x03,00", timeout=3)
        await send_and_recv(0x0082, bytes([0x03, 0x02]), "query 0x03,02", timeout=3)

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
