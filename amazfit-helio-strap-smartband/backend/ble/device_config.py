"""Zepp OS device configuration commands via chunked protocol.

Sends config get/set commands on endpoint 0x000A to control device
settings like SpO2 all-day monitoring, heart rate auto, etc.

Config protocol format (on endpoint 0x000A), from Gadgetbridge ZeppOsConfigService:
  CMD_SET = 0x05: [group, version, 0x00, arg_count, config_id, type, ...value]
  CMD_GET = 0x04 (alias CMD_REQUEST = 0x03): [0x01, group, arg_count, config_id, ...]
  CMD_RESPONSE = 0x06: [group, version, config_id, type, value]

Config types (Gadgetbridge ZeppOsConfigService.ConfigType):
  0x0b = BOOL (1 byte: 0x00 or 0x01)
  0x06 = SHORT (2 bytes LE)
  0x10 = STRING (null-terminated)

Post-ECDH encryption (Gadgetbridge Huami2021ChunkedEncoder):
  All chunked frames after ECDH auth must be AES-encrypted.
  Message key = session_key[i] ^ handle (per-frame).
  Encrypted payload = AES-ECB(data + seq_nr(4B LE) + crc32(4B) + zero_pad_to_16).
  Flag byte 0x0b = first(0x01) | last(0x02) | encrypted(0x08).
"""

from __future__ import annotations

import asyncio
import logging
import struct
import zlib

from bleak import BleakClient
from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"

# Config endpoint
ENDPOINT_CONFIG = 0x000A

# Config commands
CMD_REQUEST = 0x03   # request with constraints
CMD_GET = 0x04
CMD_SET = 0x05
CMD_RESPONSE = 0x06  # response to GET

# Config groups
CONFIG_GROUP_HEALTH = 0x08
CONFIG_GROUP_HEALTH_VERSION = 0x03

# Health config IDs (from Gadgetbridge ZeppOsConfigService)
CONFIG_SPO2_ALL_DAY = 0x04            # SPO2_ALL_DAY_MONITORING (bool) — confirmed via encrypted GET readback
CONFIG_SPO2_LOW_ALERT = 0x32          # SPO2_LOW_ALERT threshold (byte)
CONFIG_SLEEP_BREATHING = 0x12         # SLEEP_BREATHING_QUALITY_MONITORING (bool)
CONFIG_HR_ALL_DAY = 0x17              # HR_ALL_DAY_MONITORING (bool)
CONFIG_HR_HIGH_ALERT = 0x18           # HR_HIGH_ALERT threshold (byte)
CONFIG_HR_LOW_ALERT = 0x19            # HR_LOW_ALERT threshold (byte)
CONFIG_STRESS_ALL_DAY = 0x39          # STRESS_ALL_DAY_MONITORING (bool)

# Config types (Gadgetbridge ZeppOsConfigService.ConfigType)
CONFIG_TYPE_BOOL = 0x0b
CONFIG_TYPE_BYTE = 0x01
CONFIG_TYPE_SHORT = 0x06
CONFIG_TYPE_STRING = 0x10

# Chunked frame flags
FLAG_FIRST = 0x01
FLAG_LAST = 0x02
FLAG_NEEDS_ACK = 0x04
FLAG_ENCRYPTED = 0x08


class ZeppOsConfig:
    """Sends config get/set commands to Zepp OS device with AES encryption."""

    def __init__(
        self,
        client: BleakClient,
        session_key: bytes | None = None,
        enc_seq_nr: int = 0,
    ):
        self._client = client
        self._rx_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._handle = 100  # start at different offset from auth
        self._notifying = False
        self._session_key = session_key
        self._enc_write_seq_nr = enc_seq_nr

    def _next_handle(self) -> int:
        self._handle += 1
        return self._handle & 0xFF

    def _make_message_key(self, handle: int) -> bytes:
        """Derive per-frame message key: session_key[i] ^ handle."""
        return bytes([self._session_key[i] ^ handle for i in range(16)])

    def _encrypt_payload(self, payload: bytes, handle: int) -> bytes:
        """Encrypt payload for chunked frame (Gadgetbridge Huami2021ChunkedEncoder).

        Format: [data + seq_nr(4B LE) + crc32(4B) + zero_pad_to_16]
        Encrypted with AES-ECB/NoPadding using message key.
        """
        # Append 4-byte LE sequence number
        seq_bytes = struct.pack('<I', self._enc_write_seq_nr)
        to_crc = payload + seq_bytes

        # Append 4-byte CRC32
        crc = zlib.crc32(to_crc) & 0xFFFFFFFF
        crc_bytes = struct.pack('<I', crc)
        plaintext = to_crc + crc_bytes

        # Pad to 16-byte boundary
        pad_len = (16 - (len(plaintext) % 16)) % 16
        plaintext += b'\x00' * pad_len

        # Encrypt with AES-ECB
        msg_key = self._make_message_key(handle)
        cipher = AES.new(msg_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(plaintext)

        self._enc_write_seq_nr += 1
        return encrypted

    def _decrypt_payload(self, encrypted: bytes, handle: int, orig_len: int) -> bytes:
        """Decrypt payload from chunked response."""
        if not self._session_key or len(encrypted) == 0:
            return encrypted

        # Pad to 16-byte boundary if needed (shouldn't be necessary but safety)
        pad_len = (16 - (len(encrypted) % 16)) % 16
        if pad_len:
            encrypted += b'\x00' * pad_len

        msg_key = self._make_message_key(handle)
        cipher = AES.new(msg_key, AES.MODE_ECB)
        decrypted = cipher.decrypt(encrypted)

        # Extract original payload (first orig_len bytes)
        return decrypted[:orig_len]

    def _build_chunked_frame(self, endpoint: int, payload: bytes) -> bytes:
        """Build a chunked protocol frame for writing to 0x0016.

        If session_key is set, encrypts the payload.
        """
        h = self._next_handle()
        orig_len = len(payload)

        if self._session_key:
            # Encrypted frame
            encrypted = self._encrypt_payload(payload, h)
            flags = FLAG_FIRST | FLAG_LAST | FLAG_ENCRYPTED  # 0x0b
            return bytes([
                0x03, flags, 0x00, h, 0x00,
                orig_len & 0xFF, (orig_len >> 8) & 0xFF,
                0x00, 0x00,
                endpoint & 0xFF, (endpoint >> 8) & 0xFF,
            ]) + encrypted
        else:
            # Unencrypted frame
            flags = FLAG_FIRST | FLAG_LAST  # 0x03
            return bytes([
                0x03, flags, 0x00, h, 0x00,
                orig_len & 0xFF, (orig_len >> 8) & 0xFF,
                0x00, 0x00,
                endpoint & 0xFF, (endpoint >> 8) & 0xFF,
            ]) + payload

    def _parse_chunked_response(self, data: bytes) -> tuple[int, bytes]:
        """Parse chunked response from 0x0017. Returns (endpoint, payload).

        If the response is encrypted (flag bit 0x08), decrypts it.
        """
        if len(data) < 11:
            return (0, data)

        flags = data[1]
        handle = data[3]
        orig_len = struct.unpack_from('<H', data, 5)[0]
        ep = struct.unpack_from('<H', data, 9)[0]
        raw_payload = data[11:]

        is_encrypted = (flags & FLAG_ENCRYPTED) != 0
        if is_encrypted and self._session_key:
            payload = self._decrypt_payload(raw_payload, handle, orig_len)
        else:
            payload = raw_payload[:orig_len]

        return (ep, payload)

    def _on_rx(self, _sender, data: bytearray):
        self._rx_queue.put_nowait(bytes(data))

    async def _ensure_notify(self):
        """Start notifications on 0x0017 if not already started."""
        if not self._notifying:
            await self._client.start_notify(CHUNKED_R, self._on_rx)
            self._notifying = True
            await asyncio.sleep(0.2)

    async def _stop_notify(self):
        if self._notifying:
            try:
                await self._client.stop_notify(CHUNKED_R)
            except Exception:
                pass
            self._notifying = False

    async def set_bool_config(
        self,
        group: int,
        version: int,
        config_id: int,
        value: bool,
    ) -> bool:
        """Set a boolean config value. Returns True on success.

        Wire format (Gadgetbridge):
          [CMD_SET, group, version, 0x00, arg_count=1, config_id, CONFIG_TYPE_BOOL, value]
        """
        try:
            await self._ensure_notify()

            # Drain stale responses
            while not self._rx_queue.empty():
                self._rx_queue.get_nowait()

            payload = bytes([
                CMD_SET,
                group, version,
                0x00,                        # padding / reserved
                0x01,                        # arg_count = 1
                config_id,
                CONFIG_TYPE_BOOL,            # 0x0b
                0x01 if value else 0x00,
            ])
            frame = self._build_chunked_frame(ENDPOINT_CONFIG, payload)
            logger.info("Config SET: group=0x%02x id=0x%02x value=%s payload=%s encrypted=%s",
                        group, config_id, value, payload.hex(), bool(self._session_key))
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            # Wait for response
            try:
                resp = await asyncio.wait_for(self._rx_queue.get(), timeout=5.0)
                ep, data = self._parse_chunked_response(resp)
                logger.info("Config SET response: ep=0x%04x data=%s", ep, data.hex())

                if len(data) >= 2 and data[0] == CMD_SET:
                    status = data[1]
                    if status == 0x01:
                        logger.info("Config SET success (id=0x%02x)", config_id)
                        return True
                    else:
                        logger.warning("Config SET rejected: status=0x%02x (id=0x%02x)", status, config_id)
                        return False
                # ACK response (0x06)
                if len(data) >= 1 and data[0] == CMD_RESPONSE:
                    logger.info("Config SET ACK received (id=0x%02x)", config_id)
                    return True
                logger.info("Config SET: unexpected response data=%s", data.hex())
                return True
            except asyncio.TimeoutError:
                logger.error("Config SET FAILED: no response (timeout) for id=0x%02x", config_id)
                return False
        except Exception as e:
            logger.error("Config SET error: %s", e)
            return False

    async def get_bool_config(
        self,
        group: int,
        version: int,
        config_id: int,
    ) -> bool | None:
        """Get a boolean config value. Returns True/False or None on failure.

        Wire format (Gadgetbridge):
          Request:  [CMD_REQUEST, 0x01, group, arg_count=1, config_id]
          Response: [CMD_RESPONSE, group, version, config_id, CONFIG_TYPE_BOOL, value]
        """
        try:
            await self._ensure_notify()

            while not self._rx_queue.empty():
                self._rx_queue.get_nowait()

            payload = bytes([CMD_REQUEST, 0x01, group, 0x01, config_id])
            frame = self._build_chunked_frame(ENDPOINT_CONFIG, payload)
            logger.info("Config GET: group=0x%02x id=0x%02x encrypted=%s",
                        group, config_id, bool(self._session_key))
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            try:
                resp = await asyncio.wait_for(self._rx_queue.get(), timeout=5.0)
                ep, data = self._parse_chunked_response(resp)
                logger.info("Config GET response: ep=0x%04x data=%s", ep, data.hex())
                # Response: [CMD_RESPONSE, group, version, config_id, type, value]
                if len(data) >= 6 and data[0] == CMD_RESPONSE:
                    val = data[5]
                    return val != 0x00
                # Try alternate shorter format
                if len(data) >= 2:
                    return data[-1] != 0x00
                return None
            except asyncio.TimeoutError:
                logger.error("Config GET FAILED: no response (timeout) for id=0x%02x", config_id)
                return None
        except Exception as e:
            logger.error("Config GET error: %s", e)
            return None

    # ---- Lifecycle methods ----

    async def start(self):
        """Start notifications for config responses. Call once before a batch of config ops."""
        await self._ensure_notify()

    async def stop(self):
        """Stop notifications. Call after a batch of config ops is complete."""
        await self._stop_notify()

    # ---- Convenience methods ----

    async def set_spo2_all_day(self, enabled: bool) -> bool:
        """Enable or disable all-day SpO2 monitoring."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SPO2_ALL_DAY, enabled,
        )

    async def get_spo2_all_day(self) -> bool | None:
        """Get current all-day SpO2 monitoring setting."""
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SPO2_ALL_DAY,
        )

    async def set_sleep_breathing(self, enabled: bool) -> bool:
        """Enable or disable sleep breathing quality / sleep SpO2 monitoring."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SLEEP_BREATHING, enabled,
        )

    async def get_sleep_breathing(self) -> bool | None:
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SLEEP_BREATHING,
        )

    async def set_stress_all_day(self, enabled: bool) -> bool:
        """Enable or disable all-day stress monitoring."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_STRESS_ALL_DAY, enabled,
        )

    async def get_stress_all_day(self) -> bool | None:
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_STRESS_ALL_DAY,
        )

    async def set_hr_all_day(self, enabled: bool) -> bool:
        """Enable or disable all-day heart rate monitoring."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_HR_ALL_DAY, enabled,
        )

    async def get_hr_all_day(self) -> bool | None:
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_HR_ALL_DAY,
        )

    # Legacy aliases for backward compatibility
    async def set_spo2_auto(self, enabled: bool) -> bool:
        return await self.set_spo2_all_day(enabled)

    async def get_spo2_auto(self) -> bool | None:
        return await self.get_spo2_all_day()

    async def set_blood_oxygen_auto(self, enabled: bool) -> bool:
        return await self.set_sleep_breathing(enabled)

    async def get_blood_oxygen_auto(self) -> bool | None:
        return await self.get_sleep_breathing()

    async def set_hr_auto(self, enabled: bool) -> bool:
        return await self.set_hr_all_day(enabled)

    async def get_hr_auto(self) -> bool | None:
        return await self.get_hr_all_day()
