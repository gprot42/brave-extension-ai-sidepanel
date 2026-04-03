"""Zepp OS ECDH B-163 authentication on endpoint 0x0082.

Uses the custom ecdh_b163 module (Gadgetbridge-compatible) to perform
ECDH key exchange and derive a session key for data access.

Auth flow:
  1. Generate ECDH keypair (B-163 curve)
  2. Send CMD_PUB_KEY [0x04, 0x02, 0x00, 0x02] + 48B pubkey via chunked protocol
  3. Receive device's random nonce (16B) + device pubkey (48B)
  4. Compute shared secret, derive session key
  5. Send CMD_SESSION_KEY [0x05] + AES(random, auth_key) + AES(random, session_key)
  6. Device responds with status 0x01 = success
"""

from __future__ import annotations

import asyncio
import logging
import struct

from bleak import BleakClient
from Crypto.Cipher import AES

from backend.ble import ecdh_b163

logger = logging.getLogger(__name__)

CHUNKED_W = "00000016-0000-3512-2118-0009af100700"
CHUNKED_R = "00000017-0000-3512-2118-0009af100700"


class ZeppOsAuth:
    """Handles Zepp OS ECDH B-163 authentication."""

    def __init__(self, client: BleakClient, auth_key: bytes):
        if len(auth_key) != 16:
            raise ValueError("Auth key must be 16 bytes")
        self._client = client
        self._auth_key = auth_key
        self._rx_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._handle = 0
        self._authenticated = False

        # Derived state (available after successful auth)
        self.session_key: bytes | None = None
        self.enc_seq_nr: int = 0

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

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

    async def authenticate(self) -> bool:
        """Run the ECDH B-163 auth handshake. Returns True on success."""
        notifying = False
        try:
            await self._client.start_notify(CHUNKED_R, self._on_rx)
            notifying = True
            await asyncio.sleep(0.3)

            # Generate ECDH keypair
            logger.info("ECDH: Generating keypair (B-163)...")
            priv_key = ecdh_b163.generate_private_key()
            pub_key = ecdh_b163.ecdh_generate_public(priv_key)
            if pub_key is None:
                logger.error("ECDH: Failed to generate public key")
                return False

            # Send CMD_PUB_KEY: [0x04, 0x02, 0x00, 0x02] + 48-byte pubkey
            cmd = bytes([0x04, 0x02, 0x00, 0x02]) + pub_key
            frame = self._build_chunked_frame(0x0082, cmd)
            logger.info("ECDH: Sending public key (%dB)...", len(pub_key))
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            # Wait for device response
            resp = await asyncio.wait_for(self._rx_queue.get(), timeout=15.0)
            ep, payload = self._parse_chunked_response(resp)

            if len(payload) < 67:
                logger.error("ECDH: Response too short (%dB, need 67)", len(payload))
                return False

            status = payload[2]
            if status != 0x01:
                logger.error("ECDH: CMD_PUB_KEY rejected (status=0x%02x)", status)
                return False

            device_random = payload[3:19]
            device_pubkey = payload[19:67]
            logger.info("ECDH: Got device random + pubkey")

            # Compute shared secret
            shared = ecdh_b163.ecdh_generate_shared(priv_key, device_pubkey)
            if shared is None:
                logger.error("ECDH: Shared secret computation failed")
                return False

            # Derive session key: shared[i+8] XOR auth_key[i] for i in 0..15
            session_key = bytes([shared[i + 8] ^ self._auth_key[i] for i in range(16)])
            enc_seq = (
                (shared[0] & 0xFF)
                | ((shared[1] & 0xFF) << 8)
                | ((shared[2] & 0xFF) << 16)
                | ((shared[3] & 0xFF) << 24)
            )

            # Send CMD_SESSION_KEY: [0x05] + AES_ECB(random, auth_key) + AES_ECB(random, session_key)
            cipher_ak = AES.new(self._auth_key, AES.MODE_ECB)
            cipher_sk = AES.new(session_key, AES.MODE_ECB)
            confirm = bytes([0x05]) + cipher_ak.encrypt(device_random) + cipher_sk.encrypt(device_random)

            # Drain stale responses
            while not self._rx_queue.empty():
                self._rx_queue.get_nowait()

            frame = self._build_chunked_frame(0x0082, confirm)
            logger.info("ECDH: Sending session key confirmation...")
            await self._client.write_gatt_char(CHUNKED_W, frame, response=False)

            resp = await asyncio.wait_for(self._rx_queue.get(), timeout=10.0)
            ep, payload = self._parse_chunked_response(resp)

            if len(payload) >= 3 and payload[2] == 0x01:
                self.session_key = session_key
                self.enc_seq_nr = enc_seq
                self._authenticated = True
                logger.info("ECDH: Authentication successful!")
                return True
            else:
                status = payload[2] if len(payload) >= 3 else 0xFF
                logger.error("ECDH: Session key rejected (status=0x%02x)", status)
                return False

        except asyncio.TimeoutError:
            logger.error("ECDH: Timeout waiting for device response")
            return False
        except Exception as e:
            logger.error("ECDH: Auth error: %s", e, exc_info=True)
            return False
        finally:
            if notifying:
                try:
                    await self._client.stop_notify(CHUNKED_R)
                except Exception:
                    pass
