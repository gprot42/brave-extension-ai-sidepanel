"""BLE connection lifecycle manager for the Helio Strap."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Awaitable

from bleak import BleakClient

from backend.config import DEVICE_ID
import backend.config as config
from backend.ble.scanner import find_helio_by_address
from backend.ble.auth import HuamiAuth
from backend.ble.protocol import HelioProtocol
from backend.ble.device_config import ZeppOsConfig

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    AUTHENTICATING = auto()
    CONNECTED = auto()
    ERROR = auto()


class HelioConnection:
    """Manages the full connection lifecycle: discovery → connect → auth → ready."""

    def __init__(self):
        self._client: BleakClient | None = None
        self._protocol: HelioProtocol | None = None
        self._auth: HuamiAuth | None = None
        self._config: ZeppOsConfig | None = None
        self._state = ConnectionState.DISCONNECTED
        self._error_message: str | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._auto_reconnect = True
        self._on_state_change: list[Callable[[ConnectionState], None]] = []

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def protocol(self) -> HelioProtocol | None:
        return self._protocol

    @property
    def error_message(self) -> str | None:
        return self._error_message

    @property
    def config(self) -> ZeppOsConfig | None:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def is_zepp_authenticated(self) -> bool:
        """True if ECDH auth succeeded — health data is accessible."""
        return self._auth is not None and self._auth.is_zepp_authenticated

    def on_state_change(self, callback: Callable[[ConnectionState], None]):
        self._on_state_change.append(callback)

    def _set_state(self, state: ConnectionState, error: str | None = None):
        self._state = state
        if error:
            self._error_message = error
        elif state == ConnectionState.DISCONNECTED:
            self._error_message = None
        for cb in self._on_state_change:
            try:
                cb(state)
            except Exception:
                pass

    def _on_disconnect(self, _client: BleakClient):
        logger.warning("Device disconnected")
        self._set_state(ConnectionState.DISCONNECTED)
        self._protocol = None
        if self._auto_reconnect:
            self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Try to reconnect with exponential backoff."""
        delay = 2.0
        max_delay = 60.0
        while self._auto_reconnect and self._state == ConnectionState.DISCONNECTED:
            logger.info("Reconnecting in %.0fs...", delay)
            await asyncio.sleep(delay)
            try:
                await self.connect()
                return
            except Exception as e:
                logger.warning("Reconnect failed: %s", e)
                delay = min(delay * 2, max_delay)

    async def connect(self, device_id: str | None = None) -> bool:
        """Connect to the Helio Strap. Auth is attempted if AUTH_KEY is set, skipped otherwise."""
        address = device_id or config.DEVICE_ID
        if not address:
            raise ValueError(
                "No device ID configured. Set DEVICE_ID in .env or pass device_id."
            )

        self._set_state(ConnectionState.CONNECTING)
        logger.info("Connecting to %s...", address)

        # Connect directly by address — no scan needed for previously paired devices
        self._client = BleakClient(address, disconnected_callback=self._on_disconnect)
        try:
            await self._client.connect(timeout=15.0)
        except Exception as e:
            msg = str(e)
            if "turned off" in msg.lower():
                err = "Bluetooth is turned off. Enable Bluetooth and try again."
            elif "not found" in msg.lower() or "timeout" in msg.lower():
                err = f"Device {address[:18]}... not found. Make sure it is nearby and not connected to the Zepp app."
            else:
                err = f"Connection failed: {msg}"
            self._set_state(ConnectionState.ERROR, error=err)
            raise ConnectionError(err) from e

        # Authenticate only if an auth key is configured
        auth_key_hex = config.AUTH_KEY_HEX
        if auth_key_hex:
            self._set_state(ConnectionState.AUTHENTICATING)
            auth_key = bytes.fromhex(auth_key_hex)
            self._auth = HuamiAuth(self._client, auth_key)
            success = await self._auth.authenticate()
            if not success:
                logger.warning("Auth failed — the auth key may be incorrect or expired")
                self._error_message = (
                    "Authentication failed. The auth key in .env may be wrong or expired. "
                    "Re-extract it with ./extract_auth_key.sh and update Settings."
                )
        else:
            logger.info("No AUTH_KEY configured, skipping authentication")
            self._error_message = (
                "No auth key configured. Set AUTH_KEY in Settings or .env to unlock health data."
            )

        self._protocol = HelioProtocol(self._client)
        self._config = ZeppOsConfig(self._client)
        self._set_state(ConnectionState.CONNECTED)
        logger.info("Connected successfully")
        return True

    async def disconnect(self):
        """Disconnect from the device."""
        self._auto_reconnect = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._protocol:
            try:
                await self._protocol.stop_realtime_hr()
            except Exception:
                pass
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._protocol = None
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Disconnected")


# Singleton
connection = HelioConnection()
