"""Dump raw 0x0002 sensor stream packets to identify step count format."""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
SENSOR_CHAR = "00000002-0000-3512-2118-0009af100700"
SENSOR_CTRL = "00000006-0000-3512-2118-0009af100700"

packets = []

def on_sensor(sender, data):
    raw = bytes(data)
    packets.append(raw)
    hex_str = raw.hex()
    
    parts = [f"len={len(raw)}", f"raw={hex_str}", f"b0=0x{raw[0]:02x}"]
    
    if len(raw) >= 2:
        parts.append(f"u16@0={struct.unpack_from('<H', raw, 0)[0]}")
    if len(raw) >= 4:
        parts.append(f"u16@2={struct.unpack_from('<H', raw, 2)[0]}")
    if len(raw) >= 6:
        parts.append(f"u16@4={struct.unpack_from('<H', raw, 4)[0]}")
    if len(raw) >= 8:
        parts.append(f"u16@6={struct.unpack_from('<H', raw, 6)[0]}")
    if len(raw) >= 9:
        parts.append(f"u16@7={struct.unpack_from('<H', raw, 7)[0]}")
    if len(raw) >= 10:
        parts.append(f"u16@8={struct.unpack_from('<H', raw, 8)[0]}")
    if len(raw) >= 11:
        parts.append(f"u16@9={struct.unpack_from('<H', raw, 9)[0]}")
    if len(raw) >= 5:
        parts.append(f"u32@1={struct.unpack_from('<I', raw, 1)[0]}")
    
    print(f"  [{len(packets):3d}] {' | '.join(parts)}")


async def main():
    from backend.config import AUTH_KEY_HEX
    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key:
        print("No auth key set")
        return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Auth via notify
        auth_resp = asyncio.get_event_loop().create_future()
        def on_auth(sender, data):
            if not auth_resp.done():
                auth_resp.set_result(bytes(data))
        await client.start_notify(AUTH_CHAR, on_auth)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        resp = await asyncio.wait_for(auth_resp, timeout=10)
        print(f"Auth step 1: {resp.hex()}")
        
        auth_resp2 = asyncio.get_event_loop().create_future()
        def on_auth2(sender, data):
            if not auth_resp2.done():
                auth_resp2.set_result(bytes(data))
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, on_auth2)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        resp2 = await asyncio.wait_for(auth_resp2, timeout=10)
        print(f"Auth step 2: {resp2.hex()}")
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK\n")

        # Subscribe to sensor stream
        await client.start_notify(SENSOR_CHAR, on_sensor)
        print(f"=== Passive listen on 0x0002 for 15s ===")
        await asyncio.sleep(15)
        print(f"  Got {len(packets)} packets passively\n")

        # Send sensor ctrl enable
        cmds = [
            ("0x15,0x01,0x01", bytes([0x15, 0x01, 0x01])),
            ("0x01,0x01,0x19,0x00", bytes([0x01, 0x01, 0x19, 0x00])),
        ]
        for name, cmd in cmds:
            print(f"=== Writing [{name}] to 0x0006, listen 10s ===")
            count_before = len(packets)
            try:
                await client.write_gatt_char(SENSOR_CTRL, cmd, response=False)
            except Exception as e:
                print(f"  Write error: {e}")
            await asyncio.sleep(10)
            print(f"  Got {len(packets) - count_before} new packets\n")

        # Summary
        print(f"\n=== SUMMARY: {len(packets)} total packets ===")
        sizes = {}
        for p in packets:
            key = (len(p), p[0])
            if key not in sizes:
                sizes[key] = {"count": 0, "example": p}
            sizes[key]["count"] += 1
        for (sz, first), info in sorted(sizes.items()):
            print(f"  len={sz} byte[0]=0x{first:02x}: {info['count']} packets")
            ex = info['example']
            print(f"    example: {ex.hex()}")
            # Decode all possible uint16 LE positions
            for i in range(0, len(ex) - 1):
                val = struct.unpack_from("<H", ex, i)[0]
                if 100 < val < 50000:
                    print(f"    u16@{i}={val}")

asyncio.run(main())
