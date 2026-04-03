"""Investigate all possible ways to read the real-time step count from the device.

The sensor stream (0x0002) bytes[7:9] reports 413 which is stale.
The Zepp app reads 44 steps through some other mechanism.
This script tries multiple approaches to find the real step count.
"""
import asyncio
import struct
from bleak import BleakClient

DEVICE = None  # Will be set from config or scan
AUTH_CHAR    = "00000001-0000-3512-2118-0009af100700"
SENSOR_CHAR  = "00000002-0000-3512-2118-0009af100700"
SENSOR_CTRL  = "00000006-0000-3512-2118-0009af100700"
CHUNKED_W    = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R    = "00000017-0000-3512-2118-0009af100700"
FETCH_CTRL   = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA   = "00000005-0000-3512-2118-0009af100700"
TIME_CHAR    = "00002a2b-0000-1000-8000-00805f9b34fb"


def build_chunked(endpoint, payload, handle=0):
    frame = bytearray()
    frame.append(0x03)
    frame.append(0x01)
    frame.append(0x00)
    frame.append(handle & 0xFF)
    frame.append(0x00)
    frame += struct.pack("<H", len(payload))
    frame += bytes([0x00, 0x00])
    frame += struct.pack("<H", endpoint)
    frame += payload
    return bytes(frame)


async def main():
    global DEVICE
    from backend.config import AUTH_KEY_HEX, DEVICE_ID
    from backend.ble.zepp_auth import ZeppOsAuth
    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key:
        print("No auth key"); return

    DEVICE = DEVICE_ID
    if not DEVICE:
        from bleak import BleakScanner
        print("No cached device ID, scanning...")
        devices = await BleakScanner.discover(timeout=10)
        for d in devices:
            name = d.name or ""
            if "helio" in name.lower() or "amazfit" in name.lower() or "band" in name.lower():
                DEVICE = d.address
                print(f"Found: {d.name} ({d.address})")
                break
        if not DEVICE:
            print("Device not found. Available devices:")
            for d in devices:
                print(f"  {d.name or '(unnamed)'}: {d.address}")
            return
    print(f"Using device: {DEVICE}")

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Phase 1: Basic auth
        auth_fut = asyncio.get_event_loop().create_future()
        def on_a(s, d):
            if not auth_fut.done(): auth_fut.set_result(bytes(d))
        await client.start_notify(AUTH_CHAR, on_a)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.wait_for(auth_fut, timeout=10)
        auth_fut2 = asyncio.get_event_loop().create_future()
        def on_a2(s, d):
            if not auth_fut2.done(): auth_fut2.set_result(bytes(d))
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, on_a2)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.wait_for(auth_fut2, timeout=10)
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK\n")

        # Phase 2: ECDH auth
        print("=== ECDH Auth ===")
        zepp = ZeppOsAuth(client, auth_key)
        ecdh_ok = await zepp.authenticate()
        print(f"ECDH: {'OK' if ecdh_ok else 'FAILED'}\n")

        # Listen on chunked read
        chunked_responses = []
        def on_chunked(s, d):
            raw = bytes(d)
            chunked_responses.append(raw)
            print(f"  [0x0017 {len(raw)}B]: {raw.hex()}")
        await client.start_notify(CHUNKED_R, on_chunked)

        # ── Test A: Read time characteristic (may contain step data) ──
        print("=== A: Time characteristic (0x2A2B) ===")
        try:
            data = await client.read_gatt_char(TIME_CHAR)
            raw = bytes(data)
            print(f"  Raw ({len(raw)}B): {raw.hex()}")
            if len(raw) >= 7:
                y = struct.unpack_from("<H", raw, 0)[0]
                mo, d, h, mi, s = raw[2], raw[3], raw[4], raw[5], raw[6]
                print(f"  Time: {y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}")
            for i in range(0, len(raw)-1):
                v = struct.unpack_from("<H", raw, i)[0]
                if 0 < v < 50000:
                    print(f"  u16@{i}={v}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── Test B: Query chunked endpoints for step/activity data ──
        # Gadgetbridge uses various endpoints for real-time data
        print("\n=== B: Chunked protocol - query endpoints ===")
        handle = 10

        # Endpoint 0x000A - Health/Fitness config/data
        for sub_cmd in [0x00, 0x01, 0x02, 0x03, 0x04, 0x10, 0x20]:
            print(f"\n  Endpoint 0x000A, cmd 0x{sub_cmd:02x}:")
            chunked_responses.clear()
            frame = build_chunked(0x000A, bytes([sub_cmd]), handle)
            handle += 1
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
            await asyncio.sleep(1)

        # Endpoint 0x0001 - System info  
        for sub_cmd in [0x00, 0x01, 0x02, 0x05]:
            print(f"\n  Endpoint 0x0001, cmd 0x{sub_cmd:02x}:")
            chunked_responses.clear()
            frame = build_chunked(0x0001, bytes([sub_cmd]), handle)
            handle += 1
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
            await asyncio.sleep(1)

        # Endpoint 0x0003 - Activity/steps
        for sub_cmd in [0x00, 0x01, 0x02]:
            print(f"\n  Endpoint 0x0003, cmd 0x{sub_cmd:02x}:")
            chunked_responses.clear()
            frame = build_chunked(0x0003, bytes([sub_cmd]), handle)
            handle += 1
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
            await asyncio.sleep(1)

        # Endpoint 0x0008 - Workout/realtime stats
        for sub_cmd in [0x00, 0x01, 0x02]:
            print(f"\n  Endpoint 0x0008, cmd 0x{sub_cmd:02x}:")
            chunked_responses.clear()
            frame = build_chunked(0x0008, bytes([sub_cmd]), handle)
            handle += 1
            await client.write_gatt_char(CHUNKED_W, frame, response=False)
            await asyncio.sleep(1)

        # ── Test C: Sensor stream with different enable commands ──
        print("\n\n=== C: Sensor stream with different ctrl commands ===")
        sensor_pkts = []
        def on_sensor(s, d):
            raw = bytes(d)
            sensor_pkts.append(raw)
            if len(raw) == 11 and raw[0] == 0x07:
                steps = struct.unpack_from("<H", raw, 7)[0]
                cals = struct.unpack_from("<H", raw, 3)[0]
                ts = struct.unpack_from("<I", raw, 3)[0]
                print(f"  [0x0002] type=0x07 ts={ts} u16@7={steps} u16@3={cals} raw={raw.hex()}")
            elif len(raw) == 6 and raw[0] == 0x10:
                cal = struct.unpack_from("<H", raw, 4)[0]
                print(f"  [0x0002] type=0x10 cal={cal} raw={raw.hex()}")
            else:
                print(f"  [0x0002] len={len(raw)} raw={raw.hex()}")

        await client.start_notify(SENSOR_CHAR, on_sensor)
        
        # Try different sensor control commands
        ctrl_cmds = [
            ("step count enable", bytes([0x03, 0x01])),
            ("activity enable", bytes([0x15, 0x01, 0x01])),
            ("request steps", bytes([0x03, 0x00])),
            ("request activity", bytes([0x01, 0x00])),
        ]
        for name, cmd in ctrl_cmds:
            print(f"\n  Ctrl: {name} ({cmd.hex()}):")
            sensor_pkts.clear()
            try:
                await client.write_gatt_char(SENSOR_CTRL, cmd, response=False)
            except Exception as e:
                print(f"    Error: {e}")
            await asyncio.sleep(3)
            print(f"    Got {len(sensor_pkts)} packets")

        # ── Test D: Activity fetch type 0x01 ──
        print("\n\n=== D: Activity fetch (type 0x01) ===")
        fetch_responses = []
        def on_fetch_ctrl(s, d):
            raw = bytes(d)
            fetch_responses.append(raw)
            print(f"  [CTRL]: {raw.hex()} ({len(raw)}B)")

        fetch_data_chunks = []
        def on_fetch_data(s, d):
            raw = bytes(d)
            fetch_data_chunks.append(raw)

        await client.start_notify(FETCH_CTRL, on_fetch_ctrl)
        await client.start_notify(FETCH_DATA, on_fetch_data)

        # Fetch since today 00:00
        import datetime
        now = datetime.datetime.now()
        since_bytes = struct.pack("<HBBBBB",
            now.year, now.month, now.day, 0, 0, 0)
        # type 0x01 = activity
        fetch_cmd = bytes([0x01, 0x01]) + since_bytes + bytes([0x00])
        print(f"  Fetch cmd: {fetch_cmd.hex()}")
        await client.write_gatt_char(FETCH_CTRL, fetch_cmd, response=False)
        await asyncio.sleep(3)

        if fetch_responses:
            resp = fetch_responses[0]
            if len(resp) >= 3 and resp[2] != 0x05:
                # Ack and receive
                ack = bytes([0x02, 0x01])
                await client.write_gatt_char(FETCH_CTRL, ack, response=False)
                await asyncio.sleep(5)
                print(f"  Got {len(fetch_data_chunks)} data chunks, {sum(len(c) for c in fetch_data_chunks)} bytes total")
                if fetch_data_chunks:
                    combined = b''.join(fetch_data_chunks)
                    print(f"  Raw data: {combined[:100].hex()}...")
                    # Try to decode step count from activity data
                    for i in range(0, min(len(combined), 20)):
                        if i + 2 <= len(combined):
                            v = struct.unpack_from("<H", combined, i)[0]
                            if 0 < v < 50000:
                                print(f"    u16@{i}={v}")
                        if i + 4 <= len(combined):
                            v = struct.unpack_from("<I", combined, i)[0]
                            if 0 < v < 100000:
                                print(f"    u32@{i}={v}")
            else:
                print(f"  Status: 0x{resp[2]:02x} (no data)")

        print("\nDone.")

asyncio.run(main())
