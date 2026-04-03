"""ECDH B-163 auth using custom Gadgetbridge-compatible ECDH implementation.

Uses ecdh_b163.py (exact port of Gadgetbridge's ECDH_B163.java) to ensure
the shared secret matches what the device expects.
"""

import asyncio
import logging
import os
import struct
import sys
from dotenv import load_dotenv
from bleak import BleakClient
from Crypto.Cipher import AES

import ecdh_b163

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


def parse_chunked(data):
    if len(data) < 11:
        return (0, data)
    plen = struct.unpack_from('<H', data, 5)[0]
    ep = struct.unpack_from('<H', data, 9)[0]
    return (ep, data[11:11 + plen])


async def main():
    if not AUTH_KEY_HEX:
        print("Set AUTH_KEY"); sys.exit(1)
    auth_key = bytes.fromhex(AUTH_KEY_HEX)

    auth_q: asyncio.Queue = asyncio.Queue()
    rx_q: asyncio.Queue = asyncio.Queue()
    ctrl_q: asyncio.Queue = asyncio.Queue()
    data_chunks = []
    data_received = 0

    def on_auth(_s, d): auth_q.put_nowait(bytes(d))
    def on_rx(_s, d):
        print(f"  [RX 0x0017]: {bytes(d).hex()} ({len(d)}b)")
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
        print("=== PHASE 1: Standard Auth (0x0001) ===")
        await client.start_notify(AUTH_CHAR, on_auth)
        await asyncio.sleep(0.3)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"  Step 1: {r.hex()}")
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        r = await asyncio.wait_for(auth_q.get(), timeout=10)
        print(f"  Step 2: {r.hex()}")
        try:
            await asyncio.wait_for(auth_q.get(), timeout=3)
        except asyncio.TimeoutError:
            pass
        await client.stop_notify(AUTH_CHAR)
        print("  Phase 1: OK\n")

        # Phase 2: ECDH using custom B-163 implementation
        print("=== PHASE 2: ECDH Auth (endpoint 0x0082) ===")
        await client.start_notify(CHUNKED_R, on_rx)
        await asyncio.sleep(0.3)

        # Generate ECDH keypair using Gadgetbridge-compatible implementation
        priv_key = ecdh_b163.generate_private_key()
        pub_key = ecdh_b163.ecdh_generate_public(priv_key)
        if pub_key is None:
            print("  ERROR: Failed to generate public key")
            return

        print(f"  Private key (24B): {priv_key.hex()}")
        print(f"  Public key (48B):  {pub_key.hex()}")

        # Send CMD_PUB_KEY: [0x04, 0x02, 0x00, 0x02] + 48-byte pubkey
        cmd = bytes([0x04, 0x02, 0x00, 0x02]) + pub_key
        frame = chunked_frame(0x0082, cmd)
        print(f"  Sending CMD_PUB_KEY ({len(cmd)}B payload)...")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=15)
        ep, payload = parse_chunked(resp)
        print(f"  Response: ep=0x{ep:04x} payload={payload.hex()} ({len(payload)}B)")

        # Parse: [0x10, 0x04, status, ...random(16)..., ...device_pubkey(48)...]
        if len(payload) < 67:
            print(f"  ERROR: Response too short ({len(payload)}B, need 67)")
            return

        cmd_echo = payload[0]
        subcmd = payload[1]
        status = payload[2]
        print(f"  CMD echo: 0x{cmd_echo:02x}, subcmd: 0x{subcmd:02x}, status: 0x{status:02x}")

        if status != 0x01:
            print(f"  CMD_PUB_KEY FAILED: status 0x{status:02x}")
            return

        device_random = payload[3:19]
        device_pubkey = payload[19:67]
        print(f"  Device random (16B): {device_random.hex()}")
        print(f"  Device pubkey (48B): {device_pubkey.hex()}")

        # Compute shared secret using our ECDH implementation
        shared = ecdh_b163.ecdh_generate_shared(priv_key, device_pubkey)
        if shared is None:
            print("  ERROR: Shared secret computation failed (point not on curve?)")
            return

        # shared is 48 bytes (X + Y), matching Gadgetbridge's sharedEC
        print(f"  Shared secret (48B): {shared.hex()}")

        # Derive session key: sharedEC[i+8] XOR secretKey[i] for i in 0..15
        # enc_seq_nr = uint32_LE(sharedEC[0:4])
        session_key = bytes([shared[i + 8] ^ auth_key[i] for i in range(16)])
        enc_seq = (shared[0] & 0xFF) | ((shared[1] & 0xFF) << 8) | ((shared[2] & 0xFF) << 16) | ((shared[3] & 0xFF) << 24)
        print(f"  Session key: {session_key.hex()}")
        print(f"  Enc seq nr:  {enc_seq}")

        # CMD_SESSION_KEY: [0x05] + AES_ECB(random, auth_key) + AES_ECB(random, session_key)
        # NOTE: No subcmd byte! Gadgetbridge sends exactly 33 bytes: 1 cmd + 16 enc1 + 16 enc2
        cipher_ak = AES.new(auth_key, AES.MODE_ECB)
        cipher_sk = AES.new(session_key, AES.MODE_ECB)
        enc_rand_ak = cipher_ak.encrypt(device_random)
        enc_rand_sk = cipher_sk.encrypt(device_random)

        confirm = bytes([0x05]) + enc_rand_ak + enc_rand_sk

        while not rx_q.empty():
            rx_q.get_nowait()

        frame = chunked_frame(0x0082, confirm)
        print(f"\n  Sending CMD_SESSION_KEY ({len(confirm)}B)...")
        await client.write_gatt_char(CHUNKED_W, frame, response=False)

        resp = await asyncio.wait_for(rx_q.get(), timeout=10)
        ep, payload = parse_chunked(resp)
        print(f"  Response: {payload.hex()}")

        auth_success = False
        if len(payload) >= 3:
            status = payload[2]
            if status == 0x01:
                print("\n  *** ECDH AUTH SUCCESS! ***\n")
                auth_success = True
            elif status == 0x25:
                print(f"  AUTH FAILED (0x25) — wrong session key")
                print(f"\n  Debug:")
                print(f"    shared = {shared.hex()}")
                print(f"    shared[8:24] = {shared[8:24].hex()}")
                print(f"    auth_key = {auth_key.hex()}")
                print(f"    session_key = {session_key.hex()}")
                print(f"    device_random = {device_random.hex()}")
                print(f"    enc(random, auth_key) = {enc_rand_ak.hex()}")
                print(f"    enc(random, session_key) = {enc_rand_sk.hex()}")
            else:
                print(f"  Status: 0x{status:02x}")

        # Phase 3: Test data fetch
        print("\n=== PHASE 3: Data Fetch Test ===")
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        for tc, name in [(0x01, "Activity"), (0x25, "SpO2"), (0x13, "Stress"),
                         (0x48, "Sleep"), (0x49, "HRV")]:
            while not ctrl_q.empty():
                ctrl_q.get_nowait()
            data_chunks.clear()
            data_received = 0

            cmd = bytes([0x01, tc, 0xEA, 0x07, 0x03, 0x19, 0x00, 0x00, 0x00, 0x00])
            await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
            try:
                r = await asyncio.wait_for(ctrl_q.get(), timeout=10)
                s = r[2] if len(r) >= 3 else 0xFF
                if s == 0x01:
                    sz = struct.unpack_from('<I', r, 3)[0] if len(r) >= 7 else 0
                    print(f"  {name}: DATA AVAILABLE ({sz}B)")
                    if auth_success:
                        await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
                        await asyncio.sleep(8)
                        print(f"    Received {data_received}B in {len(data_chunks)} chunks")
                elif s == 0x0b:
                    print(f"  {name}: 0x0b (locked)")
                else:
                    print(f"  {name}: 0x{s:02x}")
            except asyncio.TimeoutError:
                print(f"  {name}: timeout")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
