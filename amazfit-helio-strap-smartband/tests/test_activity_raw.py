"""Dump raw activity data bytes to understand the format."""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA = "00000005-0000-3512-2118-0009af100700"

ctrl_responses = []
data_chunks = []

def on_ctrl(s, d):
    ctrl_responses.append(bytes(d))

def on_data(s, d):
    data_chunks.append(bytes(d))

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

        # Standard auth
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
        if not ok:
            return

        # Subscribe to fetch characteristics
        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)
        await asyncio.sleep(0.3)

        from datetime import datetime, timedelta, timezone

        # Fetch activity (type 0x01)
        data_chunks.clear()
        ctrl_responses.clear()

        since = datetime.now(timezone.utc) - timedelta(days=7)
        cmd = bytes([0x01, 0x01,
                     since.year & 0xFF, (since.year >> 8) & 0xFF,
                     since.month, since.day, since.hour, since.minute,
                     0x00, 0x00])

        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        await asyncio.sleep(3)

        if not ctrl_responses:
            print("No ctrl response!"); return

        resp = ctrl_responses[0]
        print(f"\nCtrl response: {resp.hex()} ({len(resp)}B)")

        if len(resp) >= 7:
            expected = struct.unpack_from("<I", resp, 3)[0]
            print(f"Expected size field (bytes[3:7]): {expected}")
            if len(resp) >= 13:
                y = struct.unpack_from("<H", resp, 7)[0]
                m, d, h, mi = resp[9], resp[10], resp[11], resp[12]
                print(f"Start time: {y}-{m:02d}-{d:02d} {h:02d}:{mi:02d}")

        if len(resp) >= 3 and resp[2] == 0x01:
            # Start transfer
            ctrl_responses.clear()
            data_chunks.clear()
            await client.write_gatt_char(FETCH_CTRL, bytes([0x02]), response=False)
            await asyncio.sleep(5)

            raw = b"".join(data_chunks)
            print(f"\nReceived: {len(raw)} bytes in {len(data_chunks)} chunks")

            for i, chunk in enumerate(data_chunks):
                print(f"  Chunk {i} ({len(chunk)}B): {chunk.hex()}")

            if raw:
                payload = raw[1:]  # strip chunk seq byte
                print(f"\nPayload (no seq): {payload.hex()} ({len(payload)}B)")

                print(f"\nByte-by-byte:")
                for j, b in enumerate(payload):
                    print(f"  byte[{j}] = 0x{b:02x} ({b})")

                if len(payload) >= 2:
                    for off in range(0, min(len(payload)-1, 8), 2):
                        v = struct.unpack_from("<H", payload, off)[0]
                        print(f"  uint16_LE[{off}:{off+2}] = {v}")

                if len(payload) >= 4:
                    for off in range(0, min(len(payload)-3, 8), 4):
                        v = struct.unpack_from("<I", payload, off)[0]
                        print(f"  uint32_LE[{off}:{off+4}] = {v}")

                if len(payload) >= 8:
                    s1, s2 = struct.unpack_from('<II', payload, 0)
                    print(f"\n  As [uint32, uint32] = [{s1}, {s2}]")
                    h1, h2, h3, h4 = struct.unpack_from('<HHHH', payload, 0)
                    print(f"  As [u16, u16, u16, u16] = [{h1}, {h2}, {h3}, {h4}]")

            # Check ctrl ack responses
            for r in ctrl_responses:
                print(f"  Ctrl ack: {r.hex()}")
        else:
            print(f"No data (status 0x{resp[2]:02x})")

        print("\nDone.")

asyncio.run(main())
