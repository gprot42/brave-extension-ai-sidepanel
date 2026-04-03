"""Dump raw HR fetch data to debug the decoder."""
import asyncio
import struct
from bleak import BleakClient
from datetime import datetime, timedelta, timezone

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR  = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"

ctrl_responses = []
data_chunks = []

def on_ctrl(s, d): ctrl_responses.append(bytes(d))
def on_data(s, d): data_chunks.append(bytes(d))

async def main():
    auth_key = None
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k.strip() in ("AUTH_KEY_HEX", "AUTH_KEY") and v:
                    auth_key = bytes.fromhex(v)
    if not auth_key:
        print("No auth key"); return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.sleep(0.5)
        print("Auth done")

        # ECDH auth
        import sys; sys.path.insert(0, '.')
        from backend.ble.zepp_auth import ZeppOsAuth
        zepp = ZeppOsAuth(client, auth_key)
        ok = await zepp.authenticate()
        print(f"ECDH auth: {'OK' if ok else 'FAILED'}")

        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        # Fetch HR (type 0x55) - last 1 day only
        since = datetime.now(timezone.utc) - timedelta(days=1)
        cmd = bytes([0x01, 0x55,
                     since.year & 0xFF, (since.year >> 8) & 0xFF,
                     since.month, since.day, since.hour, since.minute,
                     0x00, 0x00])

        ctrl_responses.clear()
        data_chunks.clear()
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        await asyncio.sleep(3)

        if not ctrl_responses:
            print("No ctrl response!"); return

        resp = ctrl_responses[0]
        print(f"\nCtrl: {resp.hex()}")

        if len(resp) >= 7:
            expected = struct.unpack_from("<I", resp, 3)[0]
            print(f"Expected size: {expected}")
        if len(resp) >= 13:
            y = struct.unpack_from("<H", resp, 7)[0]
            m, d, h, mi = resp[9], resp[10], resp[11], resp[12]
            print(f"Start time: {y}-{m:02d}-{d:02d} {h:02d}:{mi:02d}")

        if resp[2] == 0x01:
            ctrl_responses.clear()
            data_chunks.clear()
            await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
            await asyncio.sleep(8)

            raw = b"".join(data_chunks)
            print(f"\nReceived: {len(raw)}B in {len(data_chunks)} chunks")

            # Show first few chunks
            for i, chunk in enumerate(data_chunks[:3]):
                print(f"  Chunk {i} ({len(chunk)}B): {chunk[:32].hex()}{'...' if len(chunk) > 32 else ''}")

            # Strip chunk seq bytes
            payload = bytearray()
            pos = 0
            while pos < len(raw):
                chunk_size = min(241, len(raw) - pos)
                payload.extend(raw[pos + 1:pos + chunk_size])
                pos += chunk_size

            print(f"\nPayload: {len(payload)}B")
            print(f"First 60 bytes: {bytes(payload[:60]).hex()}")

            # Try different record sizes
            for rec_size in [1, 2, 3, 4, 5, 6]:
                print(f"\n--- Record size = {rec_size} ---")
                shown = 0
                for i in range(0, min(len(payload) - rec_size + 1, rec_size * 10), rec_size):
                    rec = payload[i:i+rec_size]
                    vals = ' '.join(f'{b:02x}({b:3d})' for b in rec)
                    print(f"  rec[{i//rec_size:3d}]: {vals}")
                    shown += 1

            # Special: try 1-byte-per-minute format (common for HR on Zepp OS)
            print(f"\n--- 1-byte-per-minute interpretation ---")
            valid = [b for b in payload if 30 <= b <= 220]
            invalid = [b for b in payload if b == 0 or b == 0xFF]
            other = len(payload) - len(valid) - len(invalid)
            print(f"  Valid HR (30-220): {len(valid)}")
            print(f"  Zero/0xFF (no reading): {len(invalid)}")
            print(f"  Other: {other}")
            if valid:
                print(f"  Valid BPM range: {min(valid)} - {max(valid)}")
                print(f"  First 20 valid: {valid[:20]}")
        else:
            print(f"No data (status 0x{resp[2]:02x})")

asyncio.run(main())
