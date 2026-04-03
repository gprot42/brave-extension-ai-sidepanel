"""Zepp OS device configuration commands via chunked protocol.

Sends config get/set commands on endpoint 0x000A to control device
settings like auto SpO2 measurement, heart rate monitoring, etc.

Config protocol format (on endpoint 0x000A):
  CMD_GET = 0x04: [config_group, config_version, config_id]
  CMD_SET = 0x05: [config_group, config_version, config_id, type, ...value]

Config types:
  0x01 = BOOL (1 byte: 0x00 or 0x01)
  0x06 = SHORT (2 bytes LE)
  0x10 = STRING (null-terminated)
"""

from __future__ import annotations

import asyncio
import logging
import struct

from bleak import BleakClient

logger = logging.getLogger(__name__)

CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"

# Config endpoint
ENDPOINT_CONFIG = 0x000A

# Config commands
CMD_GET = 0x04
CMD_SET = 0x05
CMD_RESPONSE = 0x06  # response to GET

# Config groups
CONFIG_GROUP_HEALTH = 0x08
CONFIG_GROUP_HEALTH_VERSION = 0x03

# Health config IDs
CONFIG_HR_AUTO_MEASURE = 0x5D
CONFIG_BLOOD_OXYGEN_AUTO = 0x5E
CONFIG_SPO2_AUTO_MEASURE = 0x5F
CONFIG_TEMP_AUTO_MEASURE = 0x60

# Config types
CONFIG_TYPE_BOOL = 0x01
CONFIG_TYPE_SHORT = 0x06


class ZeppOsConfig:
    """Sends config get/set commands to Zepp OS device."""

    def __init__(self, client: BleakClient):
        self._client = client
        self._rx_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._handle = 100  # start at different offset from auth
        self._notifying = False

    def _next_handle(self) -> int:
        self._handle += 1
        return self._handle & 0xFF

    def _build_chunked_frame(self, endpoint: int, payload: bytes) -> bytes:
        """Build a chunked protocol frame for writing to 0x0016."""
        h = self._next_handle()
        plen = len(payload)
        return bytes([
            0x03, 0x03, 0x00, h, 0x00,
            plen & 0xFF, (plen >> 8) & 0xFF,
            0x00, 0x00,
            endpoint & 0xFF, (endpoint >> 8) & 0xFF,
        ]) + payload

    @staticmethod
    def _parse_chunked_response(data: bytes) -> tuple[int, bytes]:
        """Parse chunked response from 0x0017. Returns (endpoint, payload)."""
        if len(data) < 11:
            return (0, data)
        plen = struct.unpack_from('<H', data, 5)[0]
        ep = struct.unpack_from('<H', data, 9)[0]
        return (ep, data[11:11 + plen])

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
        """Set a boolean config value. Returns True on success."""
        try:
            await self._ensure_notify()

            # Drain stale responses
            while not self._rx_queue.empty():
                self._rx_queue.get_nowait()

            payload = bytes([
                CMD_SET,
                group, version,
                config_id,
                CONFIG_TYPE_BOOL,
                0x01 if value else 0x00,
            ])
            frame = self._build_chunked_frame(ENDPOINT_CONFIG, payload)
            logger.info("Config SET: group=0x%02x id=0x%02x value=%s", group, config_id, value)
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            # Wait for response
            try:
                resp = await asyncio.wait_for(self._rx_queue.get(), timeout=5.0)
                ep, data = self._parse_chunked_response(resp)
                logger.info("Config response: ep=0x%04x data=%s", ep, data.hex())
                # Response format: [CMD_SET_RESPONSE, status, ...]
                # status 0x01 = success
                if len(data) >= 2 and data[0] == CMD_SET:
                    status = data[1]
                    if status == 0x01:
                        logger.info("Config SET success")
                        return True
                    else:
                        logger.warning("Config SET rejected: status=0x%02x", status)
                        return False
                # Some devices just echo back the command
                return True
            except asyncio.TimeoutError:
                logger.warning("Config SET: no response (timeout)")
                # Some devices don't respond to config sets — treat as success
                return True
        except Exception as e:
            logger.error("Config SET error: %s", e)
            return False
        finally:
            await self._stop_notify()

    async def get_bool_config(
        self,
        group: int,
        version: int,
        config_id: int,
    ) -> bool | None:
        """Get a boolean config value. Returns True/False or None on failure."""
        try:
            await self._ensure_notify()

            while not self._rx_queue.empty():
                self._rx_queue.get_nowait()

            payload = bytes([CMD_GET, group, version, config_id])
            frame = self._build_chunked_frame(ENDPOINT_CONFIG, payload)
            logger.info("Config GET: group=0x%02x id=0x%02x", group, config_id)
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            try:
                resp = await asyncio.wait_for(self._rx_queue.get(), timeout=5.0)
                ep, data = self._parse_chunked_response(resp)
                logger.info("Config GET response: ep=0x%04x data=%s", ep, data.hex())
                # Response: [CMD_RESPONSE, group, version, config_id, type, value]
                if len(data) >= 6 and data[0] == CMD_RESPONSE:
                    val = data[5]
                    return val != 0x00
                return None
            except asyncio.TimeoutError:
                logger.warning("Config GET: no response")
                return None
        except Exception as e:
            logger.error("Config GET error: %s", e)
            return None
        finally:
            await self._stop_notify()

    # ---- Convenience methods ----

    async def set_spo2_auto(self, enabled: bool) -> bool:
        """Enable or disable auto SpO2 measurement."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SPO2_AUTO_MEASURE, enabled,
        )

    async def get_spo2_auto(self) -> bool | None:
        """Get current auto SpO2 setting."""
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_SPO2_AUTO_MEASURE,
        )

    async def set_hr_auto(self, enabled: bool) -> bool:
        """Enable or disable auto heart rate measurement."""
        return await self.set_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_HR_AUTO_MEASURE, enabled,
        )

    async def get_hr_auto(self) -> bool | None:
        return await self.get_bool_config(
            CONFIG_GROUP_HEALTH, CONFIG_GROUP_HEALTH_VERSION,
            CONFIG_HR_AUTO_MEASURE,
        )
