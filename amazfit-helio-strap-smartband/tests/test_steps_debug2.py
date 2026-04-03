"""Test: ECDH auth + activity fetch to see raw data and expected_size."""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"
CHUNKED_W  = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R  = "00000017-0000-3512-2118-0009af100700"
SENSOR     = "00000002-0000-3512-2118-0009af100700"

ctrl_q = asyncio.Queue()
data_chunks = []

def on_ctrl(s, d): ctrl_q.put_nowait(bytes(d))
def on_data(s, d): data_chunks.append(bytes(d))

async def main():
    auth_key = None
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k in ("AUTH_KEY_HEX", "AUTH_KEY") and v:
                    auth_key = bytes.fromhex(v)
    if not auth_key:
        print("No auth key"); return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Standard auth
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.sleep(0.5)
        print("Auth done")

        # ECDH auth
        from cryptography.hazmat.primitives.asymmetric.ec import (
            ECDH, EllipticCurvePrivateKey, SECT163R2, generate_private_key,
        )
        from Crypto.Cipher import AES
        
        privkey = generate_private_key(SECT163R2())
        pubkey = privkey.public_key()
        nums = pubkey.public_numbers()
        x_bytes = nums.x.to_bytes(24, 'little')
        y_bytes = nums.y.to_bytes(24, 'little')
        our_pubkey = x_bytes + y_bytes

        chunked_responses = asyncio.Queue()
        def on_chunked(s, d): chunked_responses.put_nowait(bytes(d))
        
        await client.start_notify(CHUNKED_R, on_chunked)
        await asyncio.sleep(0.3)

        # Send ECDH pubkey
        payload = bytes([0x04, 0x02, 0x00, 0x02]) + our_pubkey
        seq = 0x01
        frame_payload = payload
        plen = len(frame_payload)
        frame = bytes([0x03, 0x03, seq, 0x00, plen & 0xFF, (plen >> 8) & 0xFF,
                        0x00, 0x00, 0x82, 0x00]) + frame_payload
        await client.write_gatt_char(CHUNKED_W, frame, response=False)
        
        try:
            resp = await asyncio.wait_for(chunked_responses.get(), 5)
            print(f"ECDH response ({len(resp)}B): {resp.hex()}")
            
            # Parse response
            if len(resp) > 14:
                ep_payload = resp[10:]
                if len(ep_payload) >= 67 and ep_payload[0] == 0x10 and ep_payload[1] == 0x04:
                    dev_random = ep_payload[3:19]
                    dev_pubkey_raw = ep_payload[19:67]
                    
                    dev_x = int.from_bytes(dev_pubkey_raw[0:24], 'little')
                    dev_y = int.from_bytes(dev_pubkey_raw[24:48], 'little')
                    
                    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers
                    dev_pub = EllipticCurvePublicNumbers(dev_x, dev_y, SECT163R2()).public_key()
                    shared = privkey.exchange(ECDH(), dev_pub)
                    
                    shared_x = shared[:24] if len(shared) >= 24 else shared
                    shared_x_le = int.from_bytes(shared_x, 'big').to_bytes(len(shared_x), 'little')
                    
                    # Session key derivation
                    session_key = bytes(shared_x_le[8+i] ^ auth_key[i] for i in range(16))
                    enc_seq = struct.unpack_from("<I", shared_x_le, 0)[0]
                    
                    enc_random_auth = AES.new(auth_key, AES.MODE_ECB).encrypt(dev_random)
                    enc_random_sess = AES.new(session_key, AES.MODE_ECB).encrypt(dev_random)
                    
                    cmd_sess = bytes([0x05, 0x02]) + enc_random_auth + enc_random_sess
                    seq += 1
                    plen2 = len(cmd_sess)
                    frame2 = bytes([0x03, 0x03, seq, 0x00, plen2 & 0xFF, (plen2 >> 8) & 0xFF,
                                    0x00, 0x00, 0x82, 0x00]) + cmd_sess
                    await client.write_gatt_char(CHUNKED_W, frame2, response=False)
                    
                    resp2 = await asyncio.wait_for(chunked_responses.get(), 5)
                    auth_payload = resp2[10:]
                    print(f"ECDH auth result: {auth_payload.hex()}")
                    
                    if auth_payload == bytes([0x10, 0x05, 0x01]):
                        print("*** ECDH AUTH SUCCESS ***")
                    else:
                        print(f"ECDH auth failed: {auth_payload.hex()}")
                        return
        except asyncio.TimeoutError:
            print("ECDH timeout - skipping")
            return

        # Now fetch activity with ECDH auth
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        # Fetch type 0x01 (activity)
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(days=7)
        cmd = bytes([0x01, 0x01,
                     since.year & 0xFF, (since.year >> 8) & 0xFF,
                     since.month, since.day, since.hour, since.minute,
                     0x00, 0x00])
        
        data_chunks.clear()
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        resp = await asyncio.wait_for(ctrl_q.get(), 10)
        print(f"\nActivity ctrl response ({len(resp)}B): {resp.hex()}")
        
        if len(resp) >= 7:
            expected_size = struct.unpack_from("<I", resp, 3)[0]
            print(f"Expected data size: {expected_size} bytes")
        
        if resp[2] == 0x01:
            # Start transfer
            await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
            await asyncio.sleep(3)
            
            raw = b"".join(data_chunks)
            print(f"Received {len(raw)} raw bytes in {len(data_chunks)} chunks")
            if raw:
                print(f"Raw hex: {raw.hex()}")
                # Strip first byte (chunk seq)
                payload = raw[1:] if len(raw) > 1 else raw
                print(f"Payload after strip: {payload.hex()} ({len(payload)} bytes)")
                
                if expected_size > 0 and len(payload) > expected_size:
                    print(f"Truncating to expected_size={expected_size}")
                    payload = payload[:expected_size]
                    print(f"Truncated payload: {payload.hex()}")
                
                # Try various interpretations
                if len(payload) >= 4:
                    print("\nAs 4-byte activity records:")
                    for i in range(0, len(payload) - 3, 4):
                        kind, intensity, steps, hr = payload[i], payload[i+1], payload[i+2], payload[i+3]
                        print(f"  Record {i//4}: kind={kind} intensity={intensity} steps={steps} hr={hr}")
                
                if len(payload) >= 2:
                    print(f"\nAs uint16 LE: {struct.unpack_from('<H', payload, 0)[0]}")
                if len(payload) >= 4:
                    print(f"As uint32 LE: {struct.unpack_from('<I', payload, 0)[0]}")
                if len(payload) >= 1:
                    print(f"As single byte: {payload[0]}")
        else:
            print(f"No activity data (status 0x{resp[2]:02x})")

        # Also check sensor stream bytes interpretation
        print("\n--- Sensor stream 11-byte packet analysis ---")
        sensor_pkts = []
        def on_sens(s, d):
            raw = bytes(d)
            if len(raw) == 11 and raw[0] == 0x07:
                sensor_pkts.append(raw)
        
        await client.start_notify(SENSOR, on_sens)
        await asyncio.sleep(5)
        await client.stop_notify(SENSOR)
        
        if sensor_pkts:
            pkt = sensor_pkts[-1]
            print(f"Sample packet: {pkt.hex()}")
            print(f"  bytes[3:7] uint32 LE (timestamp?): {struct.unpack_from('<I', pkt, 3)[0]}")
            print(f"  bytes[7:9] uint16 LE: {struct.unpack_from('<H', pkt, 7)[0]}")
            print(f"  bytes[9:11] uint16 LE: {struct.unpack_from('<H', pkt, 9)[0]}")
            print(f"  bytes[7:11] uint32 LE: {struct.unpack_from('<I', pkt, 7)[0]}")
            print(f"  byte[7]: {pkt[7]}")
            print(f"  byte[8]: {pkt[8]}")
            print(f"  byte[9]: {pkt[9]}")
            print(f"  byte[10]: {pkt[10]}")

asyncio.run(main())
