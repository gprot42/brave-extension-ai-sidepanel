"""Huami BLE authentication — Amazfit Helio Strap.

Two-phase authentication:
  Phase 1 — Standard Huami auth on characteristic 0x0001:
    1. Write [0x01, 0x00] + 16-byte key → notify [0x10, 0x01, 0x01, ...]
    2. Write [0x02, 0x00]               → notify [0x10, 0x02, 0x01]
    3. (If challenge) Write [0x03, 0x00] + AES(challenge) → success

  Phase 2 — Zepp OS ECDH B-163 auth on endpoint 0x0082:
    Required to unlock health data (SpO2, sleep, stress, HRV, activity).
    Uses chunked protocol (0x0016 write / 0x0017 notify).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from bleak import BleakClient
from Crypto.Cipher import AES

from backend.ble.zepp_auth import ZeppOsAuth

logger = logging.getLogger(__name__)

# Auth characteristic: 0x0001 under Huami service 0xFEE0
AUTH_CHAR = "00000001-0000-3512-2118-0009af100700"


class HuamiAuth:
    """Handles full Huami BLE auth: Phase 1 (standard) + Phase 2 (ECDH)."""

    def __init__(self, client: BleakClient, auth_key: bytes):
        if len(auth_key) != 16:
            raise ValueError("Auth key must be exactly 16 bytes")
        self._client = client
        self._key = auth_key
        self._authenticated = False
        self._zepp_authenticated = False
        self._zepp: ZeppOsAuth | None = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._notifying = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def is_zepp_authenticated(self) -> bool:
        return self._zepp_authenticated

    @property
    def session_key(self) -> bytes | None:
        """AES session key from ECDH auth (16 bytes), or None if not authenticated."""
        return self._zepp.session_key if self._zepp else None

    @property
    def enc_seq_nr(self) -> int:
        """Encryption sequence number from ECDH auth."""
        return self._zepp.enc_seq_nr if self._zepp else 0

    def _on_notify(self, _sender, data: bytearray):
        """Handle auth notifications on 0x0001."""
        logger.debug("Auth notify: %s (%d bytes)", data.hex(), len(data))
        self._response_queue.put_nowait(bytes(data))

    async def _wait_response(self, timeout: float = 10.0) -> Optional[bytes]:
        try:
            return await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def _cleanup_notify(self):
        """Stop auth notifications to free up BLE notification slots."""
        if self._notifying:
            try:
                await self._client.stop_notify(AUTH_CHAR)
            except Exception:
                pass
            self._notifying = False

    async def authenticate(self) -> bool:
        """Run the full auth handshake: Phase 1 (standard) + Phase 2 (ECDH).

        Returns True if at least Phase 1 succeeds.
        Phase 2 failure is non-fatal (basic BLE features still work).
        """
        phase1_ok = await self.phase1_auth()
        if not phase1_ok:
            return False
        await self.phase2_auth()
        return True

    async def phase1_auth(self) -> bool:
        """Run Phase 1: Standard Huami auth on 0x0001.

        Returns True if standard auth succeeds. Does NOT run ECDH.
        """
        # Phase 1: Standard Huami auth
        phase1_ok = await self._phase1_standard_auth()
        if not phase1_ok:
            return False
        return True

    async def phase2_auth(self) -> bool:
        """Run Phase 2: Zepp OS ECDH auth on endpoint 0x0082.

        Requires Phase 1 to have succeeded first.
        Returns True if ECDH succeeds, False otherwise (non-fatal).
        """
        if not self._authenticated:
            logger.error("Phase 2: Cannot run ECDH without Phase 1 auth")
            return False

        try:
            logger.info("Starting Phase 2: Zepp OS ECDH authentication...")
            self._zepp = ZeppOsAuth(self._client, self._key)
            if await self._zepp.authenticate():
                self._zepp_authenticated = True
                logger.info("Phase 2: ECDH auth successful — health data unlocked")
                return True
            else:
                logger.warning("Phase 2: ECDH auth failed — health data will be unavailable")
                self._zepp = None
                return False
        except Exception as e:
            logger.warning("Phase 2: ECDH auth error: %s", e)
            self._zepp = None
            return False

    async def _phase1_standard_auth(self) -> bool:
        """Run the standard 3-step auth handshake on characteristic 0x0001."""
        try:
            # Subscribe to notifications on 0x0001
            if not self._notifying:
                await self._client.start_notify(AUTH_CHAR, self._on_notify)
                self._notifying = True
                await asyncio.sleep(0.3)

            # Step 1: Send auth key
            logger.info("Auth step 1: Sending auth key to 0x0001...")
            await self._client.write_gatt_char(
                AUTH_CHAR, bytes([0x01, 0x00]) + self._key, response=True
            )

            resp = await self._wait_response(timeout=10.0)
            if resp is None:
                logger.error("Auth step 1: No response (timeout)")
                return False
            logger.info("Auth step 1: Response = %s", resp.hex())

            if resp[1] != 0x01 or resp[2] != 0x01:
                logger.error("Auth step 1: Key not accepted")
                return False
            logger.info("Auth step 1: Key accepted")

            # Step 2: Request challenge
            logger.info("Auth step 2: Requesting challenge...")
            await self._client.write_gatt_char(
                AUTH_CHAR, bytes([0x02, 0x00]), response=True
            )

            # Collect notifications — challenge may arrive in follow-up packets,
            # or the device may skip the challenge entirely (already bonded)
            challenge = b""
            got_ack = False
            for _ in range(10):  # max 10 notifications
                resp = await self._wait_response(timeout=10.0)
                if resp is None:
                    break
                logger.info("Auth step 2: Notification = %s (%d bytes)", resp.hex(), len(resp))

                if len(resp) >= 3 and resp[0] == 0x10 and resp[1] == 0x02 and resp[2] == 0x01:
                    got_ack = True
                    # Challenge bytes may be appended
                    if len(resp) > 3:
                        challenge += resp[3:]
                elif got_ack:
                    # Follow-up notification with remaining challenge bytes
                    challenge += resp

                if len(challenge) >= 16:
                    break

            # If device sent 10 02 01 with no challenge, it's already authenticated
            # (bonded device, key was sufficient)
            if got_ack and len(challenge) == 0:
                logger.info("Auth step 2: No challenge — device accepted key-only auth (bonded)")
                self._authenticated = True
                await self._cleanup_notify()
                return True

            challenge = challenge[:16]
            if len(challenge) < 16:
                logger.error("Auth step 2: Incomplete challenge (%d bytes): %s", len(challenge), challenge.hex())
                return False
            logger.info("Auth step 2: Got challenge: %s", challenge.hex())

            # Step 3: Encrypt and send response
            cipher = AES.new(self._key, AES.MODE_ECB)
            encrypted = cipher.encrypt(challenge)

            logger.info("Auth step 3: Sending encrypted response...")
            await self._client.write_gatt_char(
                AUTH_CHAR, bytes([0x03, 0x00]) + encrypted, response=True
            )

            resp = await self._wait_response(timeout=10.0)
            if resp is None:
                logger.error("Auth step 3: No response (timeout)")
                return False
            logger.info("Auth step 3: Response = %s", resp.hex())

            if resp[1] == 0x03 and resp[2] == 0x01:
                logger.info("Authentication successful!")
                self._authenticated = True
                await self._cleanup_notify()
                return True
            else:
                logger.error("Auth step 3: Rejected (%s)", resp.hex())
                await self._cleanup_notify()
                return False

        except Exception as e:
            logger.error("Authentication error: %s", e, exc_info=True)
            await self._cleanup_notify()
            return False
