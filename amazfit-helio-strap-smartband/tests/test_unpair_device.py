"""Unpair/unbond the device so it can be discovered by the Zepp app.

This sends a factory reset command to clear the device's bonding table,
allowing it to pair with a new host (the Zepp app on Android).
"""
import asyncio
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FIRMWARE_CTRL = "00001531-0000-3512-2118-0009af100700"
CHUNKED_WRITE = "00000016-0000-3512-2118-0009af100700"
CHUNKED_READ  = "00000017-0000-3512-2118-0009af100700"


async def main():
    from backend.config import AUTH_KEY_HEX
    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key:
        print("No auth key configured")
        return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Auth
        auth_fut = asyncio.get_event_loop().create_future()
        def on_auth(sender, data):
            if not auth_fut.done():
                auth_fut.set_result(bytes(data))
        await client.start_notify(AUTH_CHAR, on_auth)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        resp = await asyncio.wait_for(auth_fut, timeout=10)

        auth_fut2 = asyncio.get_event_loop().create_future()
        def on_auth2(sender, data):
            if not auth_fut2.done():
                auth_fut2.set_result(bytes(data))
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, on_auth2)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        await asyncio.wait_for(auth_fut2, timeout=10)
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK\n")

        # Listen on chunked read char for responses
        responses = []
        def on_chunked(sender, data):
            responses.append(bytes(data))
            print(f"  [0x0017]: {bytes(data).hex()}")
        await client.start_notify(CHUNKED_READ, on_chunked)

        print("=== Step 1: Try factory reset via chunked protocol ===")
        # Gadgetbridge uses endpoint 0x000A for device config
        # Try sending a reset command on various endpoints
        
        # Method A: Direct firmware reset command
        print("  Sending reboot cmd to 0x1531...")
        try:
            await client.write_gatt_char(FIRMWARE_CTRL, bytes([0x05]), response=True)
            print("  Reboot sent OK")
        except Exception as e:
            print(f"  Reboot error: {e}")
            try:
                await client.write_gatt_char(FIRMWARE_CTRL, bytes([0x05]), response=False)
                print("  Reboot sent (no-response)")
            except Exception as e2:
                print(f"  Also failed: {e2}")

        await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. On your Mac: System Settings > Bluetooth")
    print("   Find 'Helio Strap' or similar > Forget This Device")
    print("2. Wait 15 seconds for the device to fully reboot")
    print("3. On your Android phone: Open Zepp app > Add Device")
    print("4. The strap should now be discoverable")
    print()
    print("If Zepp still can't find it:")
    print("  - Turn Bluetooth OFF then ON on your Android phone")
    print("  - In Android Bluetooth settings, check if the strap")
    print("    appears as a previously paired device and remove it")
    print("  - Try the physical reset again (quick remove/insert x10)")
    print("  - Then immediately open Zepp and scan")


asyncio.run(main())
