"""Quick test: connect, auth, read sensor stream for 10 seconds, report step values."""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
SENSOR_CHAR = "00000002-0000-3512-2118-0009af100700"

step_values = []
calorie_values = []

def on_sensor(sender, data):
    raw = bytes(data)
    if len(raw) == 11 and raw[0] == 0x07:
        steps = struct.unpack_from("<H", raw, 7)[0]
        step_values.append(steps)
        if len(step_values) <= 5:
            print(f"  11B packet: {raw.hex()} → steps(bytes[7:9])={steps}")
    elif len(raw) == 6 and raw[0] == 0x10:
        cals = struct.unpack_from("<H", raw, 4)[0]
        calorie_values.append(cals)
        if len(calorie_values) <= 5:
            print(f"   6B packet: {raw.hex()} → calories(bytes[4:6])={cals}")

async def main():
    # Read auth key
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
    
    if not auth_key:
        print("ERROR: No auth key in .env")
        return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")
        
        # Auth
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.sleep(0.5)
        print("Auth done")
        
        # Subscribe to sensor stream
        await client.start_notify(SENSOR_CHAR, on_sensor)
        print(f"\nListening to sensor stream for 10 seconds...")
        await asyncio.sleep(10)
        await client.stop_notify(SENSOR_CHAR)
        
        print(f"\nResults:")
        print(f"  11B packets received: {len(step_values)}")
        print(f"   6B packets received: {len(calorie_values)}")
        
        if step_values:
            unique = set(step_values)
            print(f"  Step values (unique): {sorted(unique)}")
            print(f"  Step value range: {min(step_values)} - {max(step_values)}")
        
        if calorie_values:
            unique = set(calorie_values)
            print(f"  Calorie values (unique): {sorted(unique)}")

if __name__ == "__main__":
    asyncio.run(main())
