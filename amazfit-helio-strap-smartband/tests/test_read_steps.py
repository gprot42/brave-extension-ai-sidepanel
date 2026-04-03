#!/usr/bin/env python3
"""Quick test: read all characteristics that might contain step data."""
import asyncio
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"

# Try various characteristic IDs that might hold step data
CHARS_TO_TRY = {
    "0x0007 (steps?)": "00000007-0000-3512-2118-0009af100700",
    "0x0003 (config?)": "00000003-0000-3512-2118-0009af100700",
    "0x0006 (sensor ctrl)": "00000006-0000-3512-2118-0009af100700",
    "0x0008": "00000008-0000-3512-2118-0009af100700",
    "0x0009": "00000009-0000-3512-2118-0009af100700",
    "0x000A": "0000000a-0000-3512-2118-0009af100700",
    "0x000B": "0000000b-0000-3512-2118-0009af100700",
    "0x000C": "0000000c-0000-3512-2118-0009af100700",
    "0x000D": "0000000d-0000-3512-2118-0009af100700",
    "0x000E": "0000000e-0000-3512-2118-0009af100700",
    "0x000F": "0000000f-0000-3512-2118-0009af100700",
    "0x0010": "00000010-0000-3512-2118-0009af100700",
}

async def main():
    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Auth first
        auth_key = None
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ("AUTH_KEY_HEX", "AUTH_KEY") and v:
                        auth_key = bytes.fromhex(v)
        
        if auth_key is None:
            print("ERROR: No auth key found in .env")
            return
        
        print(f"Auth key: found ({len(auth_key)} bytes)")
        
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.sleep(0.5)
        print("Auth done\n")

        # List all services and characteristics
        print("=" * 60)
        print("ALL SERVICES AND CHARACTERISTICS")
        print("=" * 60)
        for service in client.services:
            print(f"\nService: {service.uuid} ({service.description})")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char: {char.uuid} [{props}]")
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        print(f"    Value ({len(val)}B): {val.hex()}")
                        if len(val) >= 2:
                            print(f"    uint16 LE: {int.from_bytes(val[:2], 'little')}")
                        if len(val) >= 4:
                            print(f"    uint32 LE: {int.from_bytes(val[:4], 'little')}")
                        if len(val) >= 5:
                            print(f"    bytes[1:5] uint32 LE: {int.from_bytes(val[1:5], 'little')}")
                    except Exception as e:
                        print(f"    Read error: {e}")
        
        print("\n" + "=" * 60)
        print("TARGETED READS")
        print("=" * 60)
        for name, uuid in CHARS_TO_TRY.items():
            try:
                val = await client.read_gatt_char(uuid)
                print(f"\n  {name}: {val.hex()} ({len(val)}B)")
                if len(val) >= 2:
                    print(f"    uint16 LE: {int.from_bytes(val[:2], 'little')}")
                if len(val) >= 4:
                    print(f"    uint32 LE [0:4]: {int.from_bytes(val[:4], 'little')}")
                if len(val) >= 5:
                    print(f"    uint32 LE [1:5]: {int.from_bytes(val[1:5], 'little')}")
            except Exception as e:
                print(f"\n  {name}: ERROR - {e}")

asyncio.run(main())
