"""Decode activity data (type 0x01) from the Helio Strap.

Connects, authenticates (ECDH), fetches activity data, and tries
multiple record-size interpretations to find where the step count lives.
"""
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

    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key:
        print("No auth key"); return
    if not DEVICE_ID:
        print("No device ID"); return

    print(f"Device: {DEVICE_ID}")

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Phase 1: Basic auth
        fut = asyncio.get_event_loop().create_future()
        def on1(s, d):
            if not fut.done(): fut.set_result(bytes(d))
        await client.start_notify(AUTH_CHAR, on1)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.wait_for(fut, timeout=10)
        fut2 = asyncio.get_event_loop().create_future()
        def on2(s, d):
            if not fut2.done(): fut2.set_result(bytes(d))
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, on2)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.wait_for(fut2, timeout=10)
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK")

        # Phase 2: ECDH auth
        zepp = ZeppOsAuth(client, auth_key)
        ecdh_ok = await zepp.authenticate()
        if not ecdh_ok:
            print("ECDH FAILED"); return
        print("ECDH: OK\n")

        # Fetch activity data
        ctrl_resps = []
        data_chunks = []
        def on_ctrl(s, d):
            ctrl_resps.append(bytes(d))
        def on_data(s, d):
            data_chunks.append(bytes(d))

        await client.start_notify(FETCH_CTRL, on_ctrl)
        await client.start_notify(FETCH_DATA, on_data)

        # Fetch since 7 days ago
        since = datetime.datetime.now() - datetime.timedelta(days=7)
        since_bytes = struct.pack("<HBBBBB",
            since.year, since.month, since.day, 0, 0, 0)
        fetch_cmd = bytes([0x01, 0x01]) + since_bytes + bytes([0x00])
        print(f"Fetch cmd: {fetch_cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, fetch_cmd, response=False)
        await asyncio.sleep(3)

        if not ctrl_resps:
            print("No ctrl response"); return

        resp = ctrl_resps[0]
        print(f"Ctrl response: {resp.hex()}")

        if len(resp) < 16 or resp[2] == 0x05:
            print("No data available"); return

        expected_bytes = struct.unpack_from("<I", resp, 3)[0]
        ts_year = struct.unpack_from("<H", resp, 7)[0]
        ts_month = resp[9]
        ts_day = resp[10]
        ts_hour = resp[11]
        ts_min = resp[12]
        ts_sec = resp[13]
        print(f"Expected: {expected_bytes} bytes")
        print(f"Start time: {ts_year}-{ts_month:02d}-{ts_day:02d} {ts_hour:02d}:{ts_min:02d}:{ts_sec:02d}")

        # ACK to start transfer
        ctrl_resps.clear()
        ack = bytes([0x02, 0x01])
        await client.write_gatt_char(FETCH_CTRL, ack, response=False)
        await asyncio.sleep(8)

        combined = b''.join(data_chunks)
        print(f"\nReceived: {len(combined)} bytes in {len(data_chunks)} chunks")

        if not combined:
            print("No data received"); return

        # Strip any sequence bytes from data chunks (each chunk has 1-byte header)
        # The data characteristic sends raw: [seq_byte] + [payload]
        # Build clean payload by stripping first byte of each chunk
        stripped = b''.join(c[1:] for c in data_chunks if len(c) > 1)
        print(f"Stripped (no seq bytes): {len(stripped)} bytes")

        # ACK completion
        if ctrl_resps:
            print(f"Completion ctrl: {ctrl_resps[-1].hex()}")

        # === Analysis ===
        print(f"\n{'='*60}")
        print("RAW DATA ANALYSIS")
        print(f"{'='*60}")

        # Show first 200 bytes hex
        print(f"\nFirst 200 bytes (raw):")
        for i in range(0, min(200, len(combined)), 16):
            chunk = combined[i:i+16]
            hexstr = ' '.join(f'{b:02x}' for b in chunk)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"  {i:04d}: {hexstr:<48s} {ascii_str}")

        print(f"\nFirst 200 bytes (stripped):")
        for i in range(0, min(200, len(stripped)), 16):
            chunk = stripped[i:i+16]
            hexstr = ' '.join(f'{b:02x}' for b in chunk)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"  {i:04d}: {hexstr:<48s} {ascii_str}")

        # Try different record sizes on stripped data
        for data_label, data in [("raw", combined), ("stripped", stripped)]:
            print(f"\n--- Attempting record-size decode on {data_label} ({len(data)}B) ---")

            for rec_size in [4, 6, 8, 10, 12]:
                # Check if record size divides evenly (with possible header)
                for header in [0, 1, 2, 4]:
                    payload = data[header:]
                    if len(payload) % rec_size == 0 and len(payload) > 0:
                        n_records = len(payload) // rec_size
                        # Sum byte at each position across first 50 records as step candidate
                        total_per_pos = [0] * rec_size
                        nonzero_per_pos = [0] * rec_size
                        for r in range(min(n_records, 50)):
                            off = header + r * rec_size
                            for p in range(rec_size):
                                val = data[off + p]
                                total_per_pos[p] += val
                                if val > 0 and val < 200:
                                    nonzero_per_pos[p] += 1

                        # Also check u16 sums at each position
                        step_candidates_u16 = {}
                        for p in range(rec_size - 1):
                            total = 0
                            for r in range(min(n_records, 50)):
                                off = header + r * rec_size
                                val = struct.unpack_from("<H", data, off + p)[0]
                                if val < 1000:
                                    total += val
                            if total > 0:
                                step_candidates_u16[p] = total

                        print(f"\n  rec_size={rec_size}, header={header}: {n_records} records")
                        print(f"    byte sums (pos 0..{rec_size-1}): {total_per_pos}")
                        print(f"    nonzero counts: {nonzero_per_pos}")
                        # Show top 3 u16 step candidates
                        top = sorted(step_candidates_u16.items(), key=lambda x: -x[1])[:3]
                        if top:
                            print(f"    top u16 sums: {top}")

                        # Show first 5 records decoded
                        print(f"    First 5 records:")
                        for r in range(min(5, n_records)):
                            off = header + r * rec_size
                            rec = data[off:off+rec_size]
                            vals = [f"{b:3d}" for b in rec]
                            print(f"      [{r}] " + " ".join(vals) + f"  | hex: {rec.hex()}")

        # Try the Gadgetbridge per-minute format: 8 bytes/sample
        # byte 0: kind, byte 1: intensity, byte 2: steps, byte 3: hr
        print(f"\n{'='*60}")
        print("GADGETBRIDGE PER-MINUTE DECODE (8 bytes/sample)")
        print(f"{'='*60}")

        for data_label, data in [("stripped", stripped)]:
            total_steps = 0
            active_minutes = 0
            for offset_try in range(min(4, len(data))):
                payload = data[offset_try:]
                if len(payload) // 8 < 10:
                    continue
                n = len(payload) // 8
                steps_sum = 0
                for r in range(n):
                    off = r * 8
                    kind = payload[off]
                    intensity = payload[off+1]
                    steps = payload[off+2]
                    hr = payload[off+3]
                    steps_sum += steps

                print(f"\n  offset={offset_try}: {n} samples, total_steps={steps_sum}")
                # Show first 10 + any with steps > 0
                shown = 0
                for r in range(n):
                    off = r * 8
                    kind = payload[off]
                    intensity = payload[off+1]
                    steps = payload[off+2]
                    hr = payload[off+3]
                    extra = payload[off+4:off+8]
                    if shown < 10 or steps > 0:
                        marker = " <-- STEPS" if steps > 0 else ""
                        print(f"    [{r:4d}] kind=0x{kind:02x} intensity={intensity:3d} steps={steps:3d} hr={hr:3d} extra={extra.hex()}{marker}")
                        shown += 1
                if steps_sum > 0:
                    total_steps = steps_sum
                    break

            if total_steps > 0:
                print(f"\n  >>> TOTAL STEPS: {total_steps}")
            else:
                print(f"\n  No steps found with 8-byte per-minute format.")

        # Also try 4 bytes/sample
        print(f"\n{'='*60}")
        print("4 BYTES/SAMPLE DECODE")
        print(f"{'='*60}")
        for data_label, data in [("stripped", stripped)]:
            for offset_try in range(min(4, len(data))):
                payload = data[offset_try:]
                if len(payload) // 4 < 10:
                    continue
                n = len(payload) // 4
                steps_sum = 0
                for r in range(n):
                    off = r * 4
                    steps_sum += payload[off+2]  # Assuming byte 2 = steps

                print(f"  offset={offset_try}: {n} samples, byte[2] sum={steps_sum}")

        print("\nDone.")

asyncio.run(main())
