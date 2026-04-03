"""Probe chunked endpoint 0x000A (Health Service) for realtime step data."""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR  = "00000001-0000-3512-2118-0009af100700"
CHUNKED_W  = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R  = "00000017-0000-3512-2118-0009af100700"
SENSOR     = "00000002-0000-3512-2118-0009af100700"

responses = []

def on_chunked(s, d):
    responses.append(bytes(d))
    print(f"  [RX {len(d)}B]: {bytes(d).hex()}")

handle_counter = 0

def make_chunked_frame(endpoint, payload):
    global handle_counter
    handle_counter += 1
    h = handle_counter
    plen = len(payload)
    # Frame: 03 03 handle 00 plen_lo plen_hi 00 00 ep_lo ep_hi payload
    frame = bytes([0x03, 0x03, h & 0xFF, 0x00,
                   plen & 0xFF, (plen >> 8) & 0xFF,
                   0x00, 0x00,
                   endpoint & 0xFF, (endpoint >> 8) & 0xFF]) + payload
    return frame

async def send_recv(client, endpoint, payload, label, wait=2.0):
    responses.clear()
    frame = make_chunked_frame(endpoint, payload)
    print(f"\n  [{label}] -> ep=0x{endpoint:04x} payload={payload.hex()}")
    await client.write_gatt_char(CHUNKED_W, frame, response=False)
    await asyncio.sleep(wait)
    result = list(responses)
    for r in result:
        if len(r) > 10:
            ep_payload = r[10:]
            print(f"    Endpoint payload: {ep_payload.hex()} ({len(ep_payload)}B)")
            if len(ep_payload) >= 2:
                print(f"    Byte-by-byte: {' '.join(f'{b:02x}({b})' for b in ep_payload)}")
            if len(ep_payload) >= 4:
                for off in range(0, min(len(ep_payload)-3, 20), 4):
                    v = struct.unpack_from("<I", ep_payload, off)
                    print(f"    uint32_LE[{off}:{off+4}] = {v[0]}")
            if len(ep_payload) >= 2:
                for off in range(0, min(len(ep_payload)-1, 20), 2):
                    v = struct.unpack_from("<H", ep_payload, off)
                    print(f"    uint16_LE[{off}:{off+2}] = {v[0]}")
    return result

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

        # Auth
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

        await client.start_notify(CHUNKED_R, on_chunked)
        await asyncio.sleep(0.3)

        print("=" * 60)
        print("PROBE: Endpoint 0x000A (Health/Activity Service)")
        print("=" * 60)

        # Try various GET sub-commands on 0x000A
        # Gadgetbridge uses cmd byte patterns like: [cmd, sub, ...]
        cmds = [
            (bytes([0x01]), "GET bare"),
            (bytes([0x01, 0x00]), "GET sub=0x00"),
            (bytes([0x01, 0x01]), "GET sub=0x01 (steps?)"),
            (bytes([0x01, 0x02]), "GET sub=0x02"),
            (bytes([0x01, 0x03]), "GET sub=0x03"),
            (bytes([0x01, 0x04]), "GET sub=0x04"),
            (bytes([0x01, 0x05]), "GET sub=0x05"),
            (bytes([0x01, 0x10]), "GET sub=0x10"),
            (bytes([0x01, 0x12]), "GET sub=0x12 (stress)"),
            (bytes([0x01, 0x13]), "GET sub=0x13 (auto stress)"),
            (bytes([0x01, 0x25]), "GET sub=0x25 (spo2)"),
            (bytes([0x01, 0x48]), "GET sub=0x48 (sleep)"),
            (bytes([0x01, 0x49]), "GET sub=0x49 (hrv)"),
            (bytes([0x02]), "SET bare"),
            (bytes([0x02, 0x01]), "SET sub=0x01"),
            (bytes([0x00]), "CMD 0x00"),
            (bytes([0x03]), "CMD 0x03"),
            (bytes([0x04]), "CMD START"),
            (bytes([0x04, 0x01]), "START sub=0x01"),
        ]

        for payload, label in cmds:
            await send_recv(client, 0x000A, payload, label, wait=1.5)

        print("\n" + "=" * 60)
        print("PROBE: Endpoint 0x001D (Heart Rate Service)")
        print("=" * 60)

        hr_cmds = [
            (bytes([0x01]), "GET bare"),
            (bytes([0x01, 0x00]), "GET sub=0x00"),
            (bytes([0x01, 0x01]), "GET sub=0x01"),
            (bytes([0x04, 0x01]), "START sub=0x01"),
        ]
        for payload, label in hr_cmds:
            await send_recv(client, 0x001D, payload, label, wait=1.5)

        print("\n" + "=" * 60)
        print("PROBE: Endpoint 0x0001 (Config)")
        print("=" * 60)

        cfg_cmds = [
            (bytes([0x01]), "GET bare"),
            (bytes([0x01, 0x01]), "GET sub=0x01"),
            (bytes([0x01, 0x02]), "GET sub=0x02"),
            (bytes([0x01, 0x03]), "GET sub=0x03"),
        ]
        for payload, label in cfg_cmds:
            await send_recv(client, 0x0001, payload, label, wait=1.5)

        # Also read sensor stream for 3 sec to compare
        print("\n" + "=" * 60)
        print("SENSOR STREAM (3 sec)")
        print("=" * 60)
        sensor_pkts = []
        def on_sens(s, d):
            raw = bytes(d)
            if len(raw) == 11 and raw[0] == 0x07:
                steps = struct.unpack_from("<H", raw, 7)[0]
                sensor_pkts.append(steps)

        await client.start_notify(SENSOR, on_sens)
        await asyncio.sleep(3)
        await client.stop_notify(SENSOR)
        if sensor_pkts:
            print(f"  Sensor stream bytes[7:9] values: {set(sensor_pkts)}")

        print("\nDone.")

asyncio.run(main())
