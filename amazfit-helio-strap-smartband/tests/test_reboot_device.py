"""Reboot the Amazfit Helio Strap via BLE to restore stuck sensors (pedometer etc)."""
import asyncio
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"
FIRMWARE_CTRL = "00001531-0000-3512-2118-0009af100700"
REBOOT_CMD = bytes([0x05])


async def main():
    from backend.config import AUTH_KEY_HEX
    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key:
        print("No auth key configured in .env")
        return

    async with BleakClient(DEVICE) as client:
        print(f"Connected: {client.is_connected}")

        # Authenticate
        auth_fut = asyncio.get_event_loop().create_future()
        def on_auth(sender, data):
            if not auth_fut.done():
                auth_fut.set_result(bytes(data))
        await client.start_notify(AUTH_CHAR, on_auth)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x01, 0x00]) + auth_key, response=True)
        resp = await asyncio.wait_for(auth_fut, timeout=10)
        print(f"Auth step 1: {resp.hex()}")

        auth_fut2 = asyncio.get_event_loop().create_future()
        def on_auth2(sender, data):
            if not auth_fut2.done():
                auth_fut2.set_result(bytes(data))
        await client.stop_notify(AUTH_CHAR)
        await client.start_notify(AUTH_CHAR, on_auth2)
        await client.write_gatt_char(AUTH_CHAR, bytes([0x02, 0x00]), response=True)
        resp2 = await asyncio.wait_for(auth_fut2, timeout=10)
        print(f"Auth step 2: {resp2.hex()}")
        await client.stop_notify(AUTH_CHAR)
        print("Auth: OK\n")

        # Send reboot
        print("Sending REBOOT command (0x05) to firmware control char 0x1531...")
        try:
            await client.write_gatt_char(FIRMWARE_CTRL, REBOOT_CMD, response=True)
            print("Reboot command sent successfully!")
            print("The device should restart now. Wait ~10 seconds for it to reboot.")
        except Exception as e:
            print(f"Reboot command failed: {e}")
            print("Trying without response flag...")
            try:
                await client.write_gatt_char(FIRMWARE_CTRL, REBOOT_CMD, response=False)
                print("Reboot command sent (no-response mode)!")
            except Exception as e2:
                print(f"Also failed: {e2}")

    print("\nDone. If the device rebooted:")
    print("  1. Wait for it to fully restart (~10-15 seconds)")
    print("  2. Open the Zepp app on your phone and let it sync")
    print("  3. Walk around and check if step count updates")
    print("  4. Then reconnect with our dashboard")


asyncio.run(main())
