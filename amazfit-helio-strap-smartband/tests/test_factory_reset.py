"""Try to factory reset the Amazfit Helio Strap to clear its bond table.

Tries multiple approaches since characteristic 0x0003 doesn't exist on this device.
After running this, immediately do the physical reset (remove/insert x10) and
then scan from the Zepp app.
"""
import asyncio
import struct
from bleak import BleakClient

DEVICE = "695AC20C-2379-4C06-6515-7588E51FD026"
AUTH_CHAR       = "00000001-0000-3512-2118-0009af100700"
FIRMWARE_CTRL   = "00001531-0000-3512-2118-0009af100700"
CHUNKED_WRITE   = "00000016-0000-3512-2118-0009af100700"
CHUNKED_READ    = "00000017-0000-3512-2118-0009af100700"


def build_chunked_frame(endpoint: int, payload: bytes, handle: int = 0) -> bytes:
    """Build a chunked protocol frame for 0x0016."""
    plen = len(payload)
    frame = bytearray()
    frame.append(0x03)           # command marker
    frame.append(0x01)           # flags: first+last, unencrypted
    frame.append(0x00)           # reserved
    frame.append(handle & 0xFF)  # write handle
    frame.append(0x00)           # chunk count
    frame += struct.pack("<H", plen)  # payload length
    frame += bytes([0x00, 0x00])      # padding
    frame += struct.pack("<H", endpoint)
    frame += payload
    return bytes(frame)


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
        await asyncio.wait_for(auth_fut, timeout=10)

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

        # Listen on chunked read
        def on_resp(sender, data):
            print(f"  [0x0017]: {bytes(data).hex()}")
        await client.start_notify(CHUNKED_READ, on_resp)

        # Method 1: Factory reset via chunked protocol endpoint 0x000A
        # Gadgetbridge: COMMAND_FACTORY_RESET = {0x06, 0x0b, 0x00, 0x01}
        # Normally written to 0x0003 but that doesn't exist — try via chunked
        print("=== Method 1: Factory reset via chunked endpoint 0x000A ===")
        reset_cmd = bytes([0x06, 0x0b, 0x00, 0x01])
        frame = build_chunked_frame(0x000A, reset_cmd, handle=1)
        try:
            await client.write_gatt_char(CHUNKED_WRITE, frame, response=False)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"  Error: {e}")

        # Method 2: Try various reset-like commands on firmware ctrl
        print("\n=== Method 2: Firmware control commands ===")
        for cmd_name, cmd_bytes in [
            ("reboot (0x05)", bytes([0x05])),
            ("reset (0x06)", bytes([0x06])),
            ("factory (0x09)", bytes([0x09])),
        ]:
            print(f"  Trying {cmd_name}...")
            try:
                await client.write_gatt_char(FIRMWARE_CTRL, cmd_bytes, response=False)
                await asyncio.sleep(1)
                print(f"    Sent OK")
            except Exception as e:
                print(f"    Error: {e}")

        # Method 3: Try clearing bond via chunked endpoint 0x0082 (auth endpoint)
        print("\n=== Method 3: Clear session via auth endpoint 0x0082 ===")
        # Send a "disconnect" or "clear" command
        for sub_cmd in [0x01, 0x06, 0x07, 0x08]:
            clear_payload = bytes([sub_cmd])
            frame = build_chunked_frame(0x0082, clear_payload, handle=2 + sub_cmd)
            try:
                await client.write_gatt_char(CHUNKED_WRITE, frame, response=False)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  cmd 0x{sub_cmd:02x} error: {e}")

        await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("NOW DO THIS IMMEDIATELY:")
    print("=" * 60)
    print("1. Make sure Mac Bluetooth is OFF")
    print("2. Physical reset: remove/insert strap quickly 10 times")
    print("3. After last insert, WAIT for device to show pairing screen")
    print("4. Open Zepp app > Add Device > Scan")
    print("5. If Zepp finds it, pair and check if steps work")


asyncio.run(main())
