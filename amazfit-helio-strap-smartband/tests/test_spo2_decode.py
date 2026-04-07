"""Decode SpO2 raw data from the Helio Strap to find the correct record format."""
import asyncio
import struct
import datetime
from bleak import BleakClient

AUTH_CHAR   = "00000001-0000-3512-2118-0009af100700"
FETCH_CTRL  = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA  = "00000005-0000-3512-2118-0009af100700"


async def main():
    from backend.config import AUTH_KEY_HEX, DEVICE_ID
    from backend.ble.zepp_auth import ZeppOsAuth

    auth_key = bytes.fromhex(AUTH_KEY_HEX)
    print(f"Device: {DEVICE_ID}")

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Auth phase 1
        fut = asyncio.get_event_loop().create_future()
        await client.start_notify(AUTH_CHAR, lambda s, d: fut.set_result(bytes(d)) if not fut.done() else None)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.wait_for(fut, timeout=10)
        fut2 = asyncio.get_event_loop().create_future()
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, lambda s, d: fut2.set_result(bytes(d)) if not fut2.done() else None)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.wait_for(fut2, timeout=10)
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK")

        # ECDH
        zepp = ZeppOsAuth(client, auth_key)
        if not await zepp.authenticate():
            print("ECDH FAILED"); return
        print("ECDH: OK\n")

        # Fetch SpO2
        ctrl_resps = []
        data_chunks = []
        await client.start_notify(FETCH_CTRL, lambda s, d: ctrl_resps.append(bytes(d)))
        await client.start_notify(FETCH_DATA, lambda s, d: data_chunks.append(bytes(d)))

        since = datetime.datetime.now() - datetime.timedelta(days=7)
        cmd = bytes([0x01, 0x25]) + struct.pack("<HBBBBB", since.year, since.month, since.day, 0, 0, 0) + bytes([0x00])
        print(f"Fetch cmd: {cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, cmd, response=False)
        await asyncio.sleep(3)

        if not ctrl_resps:
            print("No response"); return

        resp = ctrl_resps[0]
        print(f"Ctrl: {resp.hex()}")
        if len(resp) >= 3 and resp[2] == 0x05:
            print("No SpO2 data available"); return
        if len(resp) >= 3 and resp[2] == 0x0b:
            print("Locked (ECDH required)"); return

        expected = struct.unpack_from("<I", resp, 3)[0]
        print(f"Expected: {expected} records/bytes")
        ts_year = struct.unpack_from("<H", resp, 7)[0]
        print(f"Start: {ts_year}-{resp[9]:02d}-{resp[10]:02d} {resp[11]:02d}:{resp[12]:02d}")

        # ACK
        ctrl_resps.clear()
        await client.write_gatt_char(FETCH_CTRL, bytes([0x02, 0x01]), response=False)
        await asyncio.sleep(8)

        raw = b''.join(data_chunks)
        stripped = b''.join(c[1:] for c in data_chunks if len(c) > 1)
        print(f"\nReceived: {len(raw)} bytes in {len(data_chunks)} chunks")
        print(f"Stripped: {len(stripped)} bytes")

        # Hex dump first 300 bytes
        print(f"\n{'='*60}")
        print("STRIPPED DATA HEX DUMP (first 300 bytes)")
        print(f"{'='*60}")
        for i in range(0, min(300, len(stripped)), 16):
            chunk = stripped[i:i+16]
            h = ' '.join(f'{b:02x}' for b in chunk)
            a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"  {i:04d}: {h:<48s} {a}")

        # Try different record sizes
        print(f"\n{'='*60}")
        print("RECORD SIZE ANALYSIS")
        print(f"{'='*60}")
        for rec_size in [1, 2, 4, 8, 10, 16, 20, 22, 65]:
            for hdr in [0, 1, 2, 4]:
                p = stripped[hdr:]
                if len(p) >= rec_size and len(p) % rec_size == 0:
                    n = len(p) // rec_size
                    # Count values in SpO2 range (85-100) at each byte position
                    spo2_candidates = []
                    for pos in range(rec_size):
                        count = sum(1 for r in range(min(n, 50)) if 85 <= p[hdr + r*rec_size + pos] <= 100)
                        if count > 5:
                            spo2_candidates.append((pos, count))
                    if spo2_candidates:
                        print(f"\n  rec_size={rec_size}, hdr={hdr}: {n} records")
                        print(f"    SpO2 candidates (byte pos, count in 85-100): {spo2_candidates}")
                        print(f"    First 5 records:")
                        for r in range(min(5, n)):
                            off = hdr + r * rec_size
                            rec = p[off:off+rec_size]
                            print(f"      [{r}] {rec.hex()}")

        # Simple 1-byte decode (original assumption)
        spo2_1byte = [v for v in stripped if 50 <= v <= 100]
        print(f"\n1-byte decode: {len(spo2_1byte)} values in range 50-100")
        if spo2_1byte:
            print(f"  Sample: {spo2_1byte[:20]}")
            print(f"  Min={min(spo2_1byte)} Max={max(spo2_1byte)} Avg={sum(spo2_1byte)//len(spo2_1byte)}")

        print("\nDone.")

asyncio.run(main())
