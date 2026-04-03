"""BLE scanner for discovering Amazfit Helio Strap devices."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from backend.config import HUAMI_SERVICE

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    name: str
    address: str  # UUID on macOS, MAC on Linux
    rssi: int


async def scan_for_helio(timeout: float = 10.0) -> list[DiscoveredDevice]:
    """Scan for Helio Strap devices advertising the Huami service UUID."""
    devices: list[DiscoveredDevice] = []

    def _callback(device: BLEDevice, adv: AdvertisementData):
        if HUAMI_SERVICE.lower() in [s.lower() for s in (adv.service_uuids or [])]:
            devices.append(
                DiscoveredDevice(
                    name=device.name or "Unknown",
                    address=device.address,
                    rssi=adv.rssi if adv.rssi is not None else -100,
                )
            )

    scanner = BleakScanner(detection_callback=_callback)
    logger.info("Scanning for Helio Strap devices (%ss)...", timeout)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    # Deduplicate by address
    seen: set[str] = set()
    unique: list[DiscoveredDevice] = []
    for d in devices:
        if d.address not in seen:
            seen.add(d.address)
            unique.append(d)
    logger.info("Found %d device(s)", len(unique))
    return unique


async def find_helio_by_address(address: str, timeout: float = 10.0) -> BLEDevice | None:
    """Find a specific device by address/UUID."""
    return await BleakScanner.find_device_by_address(address, timeout=timeout)
