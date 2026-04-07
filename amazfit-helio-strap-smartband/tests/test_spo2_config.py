"""Diagnostic: Test SpO2 config IDs with AES encryption.

Tests whether encrypted config SET/GET works after ECDH auth.
Tests multiple candidate config IDs for SPO2_ALL_DAY:
  0x31 (current), 0x5a, 0x04, 0x01

Key change from v1: Uses AES-ECB encryption post-ECDH (Gadgetbridge format).
Also tests CONFIG_TYPE_BOOL = 0x0b (corrected from 0x00).

Usage:
  source backend/.venv/bin/activate && python tests/test_spo2_config.py
"""
import asyncio
import struct
import sys
import os
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleak import BleakClient
from Crypto.Cipher import AES

AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"

ENDPOINT_CONFIG = 0x000A
CMD_SET = 0x05
CMD_REQUEST = 0x03
CMD_RESPONSE = 0x06

CONFIG_GROUP_HEALTH = 0x08
CONFIG_GROUP_HEALTH_VERSION = 0x03
CONFIG_TYPE_BOOL_OLD = 0x00   # what we were using (WRONG)
CONFIG_TYPE_BOOL_NEW = 0x0b   # Gadgetbridge correct value

SPO2_CANDIDATES = {
    0x31: "current guess",
    0x5a: "Gadgetbridge variant 1",
    0x04: "Gadgetbridge variant 2",
    0x01: "Gadgetbridge variant 3",
}

FLAG_FIRST = 0x01
FLAG_LAST = 0x02
FLAG_ENCRYPTED = 0x08

handle_counter = 200
enc_write_seq_nr = 0
session_key = None
rx_queue = None


def on_chunked_rx(_sender, data: bytearray):
    if rx_queue is not None:
        rx_queue.put_nowait(bytes(data))


def next_handle():
    global handle_counter
    handle_counter += 1
    return handle_counter & 0xFF


def make_message_key(handle):
    return bytes([session_key[i] ^ handle for i in range(16)])


def encrypt_payload(payload, handle):
    global enc_write_seq_nr
    seq_bytes = struct.pack('<I', enc_write_seq_nr)
    to_crc = payload + seq_bytes
    crc = zlib.crc32(to_crc) & 0xFFFFFFFF
    crc_bytes = struct.pack('<I', crc)
    plaintext = to_crc + crc_bytes
    pad_len = (16 - (len(plaintext) % 16)) % 16
    plaintext += b'\x00' * pad_len
    msg_key = make_message_key(handle)
    cipher = AES.new(msg_key, AES.MODE_ECB)
    encrypted = cipher.encrypt(plaintext)
    enc_write_seq_nr += 1
    return encrypted


def decrypt_payload(encrypted, handle, orig_len):
    if not session_key or len(encrypted) == 0:
        return encrypted
    pad_len = (16 - (len(encrypted) % 16)) % 16
    if pad_len:
        encrypted += b'\x00' * pad_len
    msg_key = make_message_key(handle)
    cipher = AES.new(msg_key, AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted)
    return decrypted[:orig_len]


def build_frame(endpoint, payload, encrypted=False):
    h = next_handle()
    orig_len = len(payload)

    if encrypted and session_key:
        enc_data = encrypt_payload(payload, h)
        flags = FLAG_FIRST | FLAG_LAST | FLAG_ENCRYPTED
        return bytes([
            0x03, flags, 0x00, h, 0x00,
            orig_len & 0xFF, (orig_len >> 8) & 0xFF,
            0x00, 0x00,
            endpoint & 0xFF, (endpoint >> 8) & 0xFF,
        ]) + enc_data
    else:
        flags = FLAG_FIRST | FLAG_LAST
        return bytes([
            0x03, flags, 0x00, h, 0x00,
            orig_len & 0xFF, (orig_len >> 8) & 0xFF,
            0x00, 0x00,
            endpoint & 0xFF, (endpoint >> 8) & 0xFF,
        ]) + payload


def parse_response(data):
    if len(data) < 11:
        return 0, data
    flags = data[1]
    handle = data[3]
    orig_len = struct.unpack_from('<H', data, 5)[0]
    ep = struct.unpack_from('<H', data, 9)[0]
    raw = data[11:]
    is_enc = (flags & FLAG_ENCRYPTED) != 0
    if is_enc and session_key:
        payload = decrypt_payload(raw, handle, orig_len)
    else:
        payload = raw[:orig_len]
    return ep, payload


async def try_set(client, config_id, type_byte, encrypted=False, value=True):
    while not rx_queue.empty():
        rx_queue.get_nowait()

    payload = bytes([
        CMD_SET,
        CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
        0x00, 0x01,
        config_id,
        type_byte,
        0x01 if value else 0x00,
    ])
    frame = build_frame(ENDPOINT_CONFIG, payload, encrypted=encrypted)
    await client.write_gatt_char(CHUNKED_W, frame, response=False)

    try:
        resp = await asyncio.wait_for(rx_queue.get(), timeout=5.0)
        ep, data = parse_response(resp)
        if len(data) >= 2 and data[0] == CMD_SET:
            status = data[1]
            return status == 0x01, f"status=0x{status:02x} data={data.hex()}"
        if len(data) >= 1 and data[0] == CMD_RESPONSE:
            return True, f"ACK data={data.hex()}"
        return False, f"unexpected data={data.hex()}"
    except asyncio.TimeoutError:
        return False, "TIMEOUT"


async def try_get(client, config_id, encrypted=False):
    while not rx_queue.empty():
        rx_queue.get_nowait()

    payload = bytes([CMD_REQUEST, 0x01, CONFIG_GROUP_HEALTH, 0x01, config_id])
    frame = build_frame(ENDPOINT_CONFIG, payload, encrypted=encrypted)
    await client.write_gatt_char(CHUNKED_W, frame, response=False)

    try:
        resp = await asyncio.wait_for(rx_queue.get(), timeout=5.0)
        ep, data = parse_response(resp)
        if len(data) >= 6 and data[0] == CMD_RESPONSE:
            val = data[5]
            return val != 0x00, f"val=0x{val:02x} data={data.hex()}"
        if len(data) >= 2:
            return data[-1] != 0x00, f"short data={data.hex()}"
        return None, f"unexpected data={data.hex()}"
    except asyncio.TimeoutError:
        return None, "TIMEOUT"


async def phase1_auth(client, auth_key):
    fut = asyncio.get_event_loop().create_future()
    await client.start_notify(AUTH_CHAR, lambda s, d: fut.set_result(bytes(d)) if not fut.done() else None)
    await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
    resp = await asyncio.wait_for(fut, timeout=10)
    print(f"  Auth step 1: {resp.hex()}")
    fut2 = asyncio.get_event_loop().create_future()
    await client.stop_notify(AUTH_CHAR)
    await client.start_notify(AUTH_CHAR, lambda s, d: fut2.set_result(bytes(d)) if not fut2.done() else None)
    await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
    resp2 = await asyncio.wait_for(fut2, timeout=10)
    print(f"  Auth step 2: {resp2.hex()}")
    await client.stop_notify(AUTH_CHAR)
    return True


async def main():
    global rx_queue, session_key, enc_write_seq_nr

    from backend.config import AUTH_KEY_HEX, DEVICE_ID
    from backend.ble.zepp_auth import ZeppOsAuth

    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key or not DEVICE_ID:
        print("Missing auth key or device ID in .env")
        return

    rx_queue = asyncio.Queue()
    print(f"Device: {DEVICE_ID}")
    print(f"Testing {len(SPO2_CANDIDATES)} config IDs x 2 type bytes x encrypted/unencrypted\n")

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Phase 1
        print("\n=== Phase 1: Standard Auth ===")
        await phase1_auth(client, auth_key)
        print("  OK\n")

        # ECDH
        print("=== Phase 2: ECDH Auth ===")
        zepp = ZeppOsAuth(client, auth_key)
        ecdh_ok = await zepp.authenticate()
        if not ecdh_ok:
            print("  ECDH FAILED — cannot test encrypted config")
            return
        session_key = zepp.session_key
        enc_write_seq_nr = zepp.enc_seq_nr
        print(f"  ECDH OK, session_key={session_key.hex()[:16]}..., seq_nr={enc_write_seq_nr}\n")

        # Subscribe
        await client.start_notify(CHUNKED_R, on_chunked_rx)
        await asyncio.sleep(0.3)

        # ========================================
        # TEST 1: Encrypted + new type byte (0x0b)
        # ========================================
        print("=" * 60)
        print("TEST 1: ENCRYPTED + CONFIG_TYPE_BOOL=0x0b (Gadgetbridge)")
        print("=" * 60)
        for cid, desc in SPO2_CANDIDATES.items():
            print(f"\n  ID 0x{cid:02x} ({desc}):")
            ok, msg = await try_set(client, cid, CONFIG_TYPE_BOOL_NEW, encrypted=True)
            print(f"    SET: {'OK' if ok else 'FAIL'} — {msg}")
            val, msg = await try_get(client, cid, encrypted=True)
            print(f"    GET: val={val} — {msg}")

        # ========================================
        # TEST 2: Encrypted + old type byte (0x00)
        # ========================================
        print(f"\n{'=' * 60}")
        print("TEST 2: ENCRYPTED + CONFIG_TYPE_BOOL=0x00 (our old value)")
        print("=" * 60)
        for cid, desc in SPO2_CANDIDATES.items():
            print(f"\n  ID 0x{cid:02x} ({desc}):")
            ok, msg = await try_set(client, cid, CONFIG_TYPE_BOOL_OLD, encrypted=True)
            print(f"    SET: {'OK' if ok else 'FAIL'} — {msg}")

        # ========================================
        # TEST 3: Unencrypted + new type byte (should fail)
        # ========================================
        print(f"\n{'=' * 60}")
        print("TEST 3: UNENCRYPTED + CONFIG_TYPE_BOOL=0x0b (control test)")
        print("=" * 60)
        for cid, desc in SPO2_CANDIDATES.items():
            print(f"\n  ID 0x{cid:02x} ({desc}):")
            ok, msg = await try_set(client, cid, CONFIG_TYPE_BOOL_NEW, encrypted=False)
            print(f"    SET: {'OK' if ok else 'FAIL'} — {msg}")

        await client.stop_notify(CHUNKED_R)

        # Summary
        print(f"\n{'=' * 60}")
        print("INTERPRETATION")
        print("=" * 60)
        print("TEST 1 OK → encrypted + 0x0b is correct (use this)")
        print("TEST 2 OK → encrypted needed, type byte doesn't matter")
        print("TEST 3 OK → encryption not needed (unexpected)")
        print("All TIMEOUT → frame format or endpoint wrong")

    print("\nDone.")


asyncio.run(main())
