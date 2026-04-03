"""Test SpO2 auto-enable config command on the Helio Strap."""
import asyncio
from bleak import BleakClient

AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"


async def main():
    from backend.config import AUTH_KEY_HEX, DEVICE_ID
    from backend.ble.zepp_auth import ZeppOsAuth
    from backend.ble.device_config import ZeppOsConfig

    auth_key = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else None
    if not auth_key or not DEVICE_ID:
        print("Missing auth key or device ID"); return

    print(f"Device: {DEVICE_ID}")

    async with BleakClient(DEVICE_ID) as client:
        print(f"Connected: {client.is_connected}")

        # Phase 1: Basic auth
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

        # Phase 2: ECDH auth
        zepp = ZeppOsAuth(client, auth_key)
        if not await zepp.authenticate():
            print("ECDH FAILED"); return
        print("ECDH: OK\n")

        # Test config
        cfg = ZeppOsConfig(client)

        # GET current SpO2 auto setting
        print("=== GET SpO2 Auto ===")
        val = await cfg.get_spo2_auto()
        print(f"  Current value: {val}")

        # SET SpO2 auto = True
        print("\n=== SET SpO2 Auto = True ===")
        ok = await cfg.set_spo2_auto(True)
        print(f"  Result: {'OK' if ok else 'FAILED'}")

        # GET again to verify
        print("\n=== GET SpO2 Auto (verify) ===")
        val2 = await cfg.get_spo2_auto()
        print(f"  Current value: {val2}")

        # Also test HR auto
        print("\n=== GET HR Auto ===")
        hr_val = await cfg.get_hr_auto()
        print(f"  Current value: {hr_val}")

        print("\nDone.")

asyncio.run(main())
