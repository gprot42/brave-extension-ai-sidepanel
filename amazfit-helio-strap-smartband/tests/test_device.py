#!/usr/bin/env python3
"""
Comprehensive device test — connects to the Helio Strap, enumerates all
GATT services/characteristics, tests auth, and attempts each data fetch.

Usage:
  source backend/.venv/bin/activate
  python test_device.py
"""

import asyncio
import os
import struct
import sys
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from bleak import BleakClient

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEVICE_ID = os.getenv("DEVICE_ID", "695AC20C-2379-4C06-6515-7588E51FD026")
AUTH_KEY = os.getenv("AUTH_KEY", "")

# Characteristics
CHUNKED_WRITE = "00000016-0000-3512-2118-0009af100700"
CHUNKED_READ = "00000017-0000-3512-2118-0009af100700"
HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"
AUTH_CHAR = "0000fedd-0000-1000-8000-00805f9b34fb"
AUTH_READ = "0000fede-0000-1000-8000-00805f9b34fb"

# Fetch types
FETCH_TYPES = {
    0x01: "Activity",
    0x05: "Sports Summaries",
    0x12: "Stress (manual)",
    0x13: "Stress (auto)",
    0x25: "SpO2 (normal)",
    0x26: "SpO2 (sleep)",
    0x2E: "Temperature",
    0x3A: "Resting HR",
    0x48: "Sleep Session",
    0x49: "HRV",
}


class ChunkedHelper:
    """Minimal chunked protocol helper for testing."""

    def __init__(self, client: BleakClient):
        self.client = client
        self.handle_counter = 0
        self.responses: asyncio.Queue = asyncio.Queue()

    def _on_notify(self, sender, data: bytearray):
        logger.info("  NOTIFY on 0x0017: %s (%d bytes)", data.hex(), len(data))
        if len(data) < 4 or data[0] != 0x03:
            self.responses.put_nowait(("raw", data))
            return

        flags = data[1]
        is_first = bool(flags & 0x01)
        is_last = bool(flags & 0x02)

        if is_first and len(data) >= 10:
            total_len = struct.unpack_from("<I", data, 4)[0]
            endpoint = struct.unpack_from("<H", data, 8)[0]
            payload = bytes(data[10:])
            logger.info(
                "    -> endpoint=0x%04x total=%d payload=%s",
                endpoint, total_len, payload.hex()[:80],
            )
            self.responses.put_nowait(("chunked", endpoint, payload))
        elif is_last:
            self.responses.put_nowait(("continuation", bytes(data[4:])))

    async def start(self):
        await self.client.start_notify(CHUNKED_READ, self._on_notify)

    async def write(self, endpoint: int, payload: bytes, response=False):
        self.handle_counter = (self.handle_counter + 1) & 0xFF
        header = struct.pack("<I", len(payload)) + struct.pack("<H", endpoint)
        packet = bytes([0x03, 0x03, self.handle_counter, 0x00]) + header + payload
        logger.info("  WRITE to 0x0016: %s", packet.hex())
        await self.client.write_gatt_char(CHUNKED_WRITE, packet, response=response)

    async def wait(self, timeout=10.0):
        try:
            return await asyncio.wait_for(self.responses.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


async def authenticate(client: BleakClient, key_hex: str) -> bool:
    """Run auth via characteristic 0x0001 (write + notify)."""
    from Crypto.Cipher import AES

    key = bytes.fromhex(key_hex)
    AUTH_C = "00000001-0000-3512-2118-0009af100700"
    responses = asyncio.Queue()

    def on_notify(sender, data: bytearray):
        logger.info("  AUTH NOTIFY [0x0001]: %s (%d bytes)", data.hex(), len(data))
        responses.put_nowait(bytes(data))

    await client.start_notify(AUTH_C, on_notify)
    await asyncio.sleep(0.3)

    async def wait_resp(timeout=10.0):
        try:
            return await asyncio.wait_for(responses.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    # Step 1: Send key
    logger.info("Auth Step 1: Sending key to 0x0001...")
    await client.write_gatt_char(AUTH_C, bytes([0x01, 0x00]) + key, response=True)

    resp = await wait_resp()
    if resp is None:
        logger.error("  -> No response (timeout)")
        return False
    logger.info("  -> Response: %s", resp.hex())
    if resp[1] != 0x01 or resp[2] != 0x01:
        logger.error("  -> Key not accepted")
        return False
    logger.info("  -> Key accepted!")

    # Step 2: Request challenge
    logger.info("Auth Step 2: Requesting challenge...")
    await client.write_gatt_char(AUTH_C, bytes([0x02, 0x00]), response=True)

    # Collect notifications — challenge may arrive in follow-up packets
    challenge = b""
    got_ack = False
    for _ in range(10):
        resp = await wait_resp(timeout=10.0)
        if resp is None:
            break
        logger.info("  -> Notification: %s (%d bytes)", resp.hex(), len(resp))
        if len(resp) >= 3 and resp[0] == 0x10 and resp[1] == 0x02 and resp[2] == 0x01:
            got_ack = True
            if len(resp) > 3:
                challenge += resp[3:]
        elif got_ack:
            challenge += resp
        if len(challenge) >= 16:
            break

    # If no challenge, device accepted key-only auth (bonded)
    if got_ack and len(challenge) == 0:
        logger.info("  -> No challenge — device accepted key-only auth (bonded)")
        return True

    challenge = challenge[:16]
    if len(challenge) < 16:
        logger.error("  -> Incomplete challenge (%d bytes): %s", len(challenge), challenge.hex())
        return False
    logger.info("  -> Challenge: %s", challenge.hex())

    # Step 3: Send encrypted response
    logger.info("Auth Step 3: Sending encrypted response...")
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(challenge)
    await client.write_gatt_char(AUTH_C, bytes([0x03, 0x00]) + encrypted, response=True)

    resp = await wait_resp()
    if resp is None:
        logger.error("  -> No response (timeout)")
        return False
    logger.info("  -> Response: %s", resp.hex())
    if resp[1] == 0x03 and resp[2] == 0x01:
        logger.info("  -> AUTHENTICATED!")
        return True
    else:
        logger.error("  -> Auth rejected")
        return False


async def main():
    print("=" * 60)
    print("Helio Strap — Comprehensive Device Test")
    print("=" * 60)
    print(f"Device: {DEVICE_ID}")
    print(f"Auth key: {'SET (%d chars)' % len(AUTH_KEY) if AUTH_KEY else 'NOT SET'}")
    print()

    client = BleakClient(DEVICE_ID)
    try:
        print("[1/6] Connecting...")
        await client.connect(timeout=15.0)
        print(f"  Connected: {client.is_connected}")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Make sure the Helio Strap is nearby and NOT connected to the Zepp app.")
        return

    # Enumerate all services
    print("\n[2/6] GATT Service Discovery")
    print("-" * 50)
    for service in client.services:
        print(f"  Service: {service.uuid} ({service.description or 'unknown'})")
        for char in service.characteristics:
            props = ", ".join(char.properties)
            print(f"    Char: {char.uuid} [{props}]")

    # Battery
    print("\n[3/6] Battery")
    try:
        data = await client.read_gatt_char(BATTERY_CHAR)
        print(f"  Battery: {data[0]}%")
    except Exception as e:
        print(f"  Error: {e}")

    # Auth
    print("\n[4/6] Authentication")
    auth_ok = False
    if AUTH_KEY:
        try:
            auth_ok = await authenticate(client, AUTH_KEY)
            print(f"  Result: {'SUCCESS' if auth_ok else 'FAILED'}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  Skipped (no AUTH_KEY)")

    # Real-time HR
    print("\n[5/6] Real-time Heart Rate (10 seconds)")
    hr_readings = []

    def hr_handler(sender, data: bytearray):
        if len(data) >= 2:
            bpm = data[1]
            if bpm > 0:
                hr_readings.append(bpm)
                print(f"  HR: {bpm} bpm")

    try:
        await client.start_notify(HR_CHAR, hr_handler)
        print("  Subscribed to HR notifications, waiting 10s...")
        await asyncio.sleep(10)
        await client.stop_notify(HR_CHAR)
        print(f"  Received {len(hr_readings)} readings")
    except Exception as e:
        print(f"  Error: {e}")

    # Chunked data fetch
    print("\n[6/6] Data Fetch Tests")
    print("-" * 50)

    if not auth_ok:
        print("  Skipping data fetch (auth not successful)")
        print("  Historical data requires a valid auth key.")
    else:
        chunked = ChunkedHelper(client)
        await chunked.start()
        await asyncio.sleep(0.5)

        since_ts = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())

        for fetch_type, name in FETCH_TYPES.items():
            print(f"\n  Testing: {name} (0x{fetch_type:02x})")
            # Send start-date
            payload = bytes([0x01, fetch_type]) + struct.pack("<I", since_ts)
            try:
                await chunked.write(0x004B, payload)
                resp = await chunked.wait(timeout=10)
                if resp is None:
                    print(f"    -> No response (timeout)")
                else:
                    print(f"    -> Response: {resp}")
                    # Try fetch
                    await chunked.write(0x004B, bytes([0x02]))
                    data_chunks = []
                    while True:
                        chunk = await chunked.wait(timeout=5)
                        if chunk is None:
                            break
                        data_chunks.append(chunk)
                    print(f"    -> {len(data_chunks)} data chunks received")
                    # ACK
                    await chunked.write(0x004B, bytes([0x03]))
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"    -> Error: {e}")

    print("\n" + "=" * 60)
    print("Test complete")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
