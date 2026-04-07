"""Helio Strap BLE protocol — direct GATT fetch and real-time HR.

Confirmed working protocol from device testing:
- Real-time HR: Standard BLE HR Service (0x180D), characteristic 0x2A37
- Historical HR: Fetch type 0x55 via control char 0x0004 / data char 0x0005
  - 5-byte records: [counter_lo, counter_hi, counter_high+0xC8, 0x69, bpm]
- Battery: Standard Battery Service (0x180F), characteristic 0x2A19
- Real-time steps/calories: Sensor stream on 0x0002
  - 11-byte packets: [0x07, seq, 0x10, timestamp_4B, steps_4B_LE]
  - 6-byte packets: [0x10, seq, 0xFF, 0x7F, calories_2B_LE]

Health data (SpO2, stress, HRV, activity, sleep) requires ECDH B-163
authentication on endpoint 0x0082 to unlock. After successful auth,
data is fetched via the same 0x0004/0x0005 protocol with type codes:
  0x01 = Activity, 0x13 = Stress auto, 0x25 = SpO2, 0x48 = Sleep/PAI, 0x49 = HRV
"""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from bleak import BleakClient

from backend.config import (
    HR_MEASUREMENT_CHAR,
    BATTERY_LEVEL_CHAR,
    SOFTWARE_REVISION_CHAR,
)

logger = logging.getLogger(__name__)

# Fetch characteristics (direct GATT, NOT chunked protocol)
FETCH_CTRL_CHAR = "00000004-0000-3512-2118-0009af100700"
FETCH_DATA_CHAR = "00000005-0000-3512-2118-0009af100700"

# Working fetch type code (discovered via brute-force scan)
FETCH_TYPE_HR = 0x55
FETCH_TYPE_SECONDARY = 0x56  # Also has data, format TBD

# Health data fetch types (require ECDH auth to unlock)
FETCH_TYPE_ACTIVITY = 0x01
FETCH_TYPE_STRESS_AUTO = 0x13
FETCH_TYPE_SPO2 = 0x25
FETCH_TYPE_SLEEP = 0x48
FETCH_TYPE_HRV = 0x49

# Fetch commands
CMD_INIT_FETCH = 0x01
CMD_START_TRANSFER = 0x02
CMD_ACK = 0x03
RESPONSE_MARKER = 0x10

# HR record constants
HR_RECORD_SIZE = 5
HR_COUNTER_BASE = 0xC8  # byte2 base value for counter high byte
HR_MARKER_BYTE = 0x69   # byte3 is always 0x69
CHUNK_SIZE = 241         # each BLE notification is 241 bytes (1 seq + 240 data)

# Sensor stream (0x0002) — broadcasts steps + calories every second
SENSOR_DATA_CHAR = "00000002-0000-3512-2118-0009af100700"
STEPS_CHAR = "00000007-0000-3512-2118-0009af100700"

# Sensor control (0x0006) — write commands to enable/disable measurements
SENSOR_CTRL_CHAR = "00000006-0000-3512-2118-0009af100700"


@dataclass
class HRReading:
    timestamp: datetime
    bpm: int


@dataclass
class SleepData:
    date: str
    total_minutes: int
    deep_minutes: int
    light_minutes: int
    rem_minutes: int
    awake_minutes: int
    stages: list[dict] = field(default_factory=list)


@dataclass
class SpO2Reading:
    timestamp: datetime
    value: int


@dataclass
class StressReading:
    timestamp: datetime
    level: int


@dataclass
class HRVReading:
    timestamp: datetime
    rmssd: float
    sdnn: float


@dataclass
class ActivityData:
    date: str
    steps: int
    calories: int
    distance: int


class HelioProtocol:
    """High-level protocol handler for Helio Strap data extraction."""

    def __init__(self, client: BleakClient):
        self._client = client
        self._hr_callbacks: list[Callable[[HRReading], Awaitable[None] | None]] = []
        self._activity_callbacks: list[Callable[[int, int], Awaitable[None] | None]] = []
        self._hr_poll_task: asyncio.Task | None = None
        self._hr_reading_count: int = 0
        self._ctrl_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._data_chunks: list[bytes] = []
        self._data_bytes_received: int = 0
        self._fetch_subscribed = False
        self._sensor_subscribed = False
        self._current_steps: int = 0
        self._current_calories: int = 0

    # ── Heart Rate (real-time) ─────────────────────────────

    def on_hr(self, callback: Callable[[HRReading], Awaitable[None] | None]):
        self._hr_callbacks.append(callback)

    def _hr_notification_handler(self, _sender, data: bytearray):
        if len(data) < 2:
            return
        flags = data[0]
        if flags & 0x01:
            bpm = struct.unpack_from("<H", data, 1)[0]
        else:
            bpm = data[1]
        if bpm == 0 or bpm == 128 or bpm < 30 or bpm > 220:
            return
        self._hr_reading_count += 1
        cb_count = len(self._hr_callbacks)
        if self._hr_reading_count <= 3 or self._hr_reading_count % 30 == 0:
            logger.info("HR notification: %d bpm (reading #%d, %d callbacks registered)",
                        bpm, self._hr_reading_count, cb_count)
        reading = HRReading(timestamp=datetime.now(timezone.utc), bpm=bpm)
        loop = asyncio.get_event_loop()
        for cb in self._hr_callbacks:
            try:
                result = cb(reading)
                if asyncio.iscoroutine(result):
                    if loop.is_running():
                        asyncio.ensure_future(result)
                    else:
                        asyncio.create_task(result)
            except Exception as e:
                logger.error("HR callback error: %s", e)

    async def start_realtime_hr(self):
        """Enable real-time HR streaming.
        
        Subscribe to 0x2A37 once, then write [0x15, 0x01, 0x01] to sensor
        control (0x0006) to trigger continuous measurement. The trigger is
        re-sent periodically to keep the stream alive.
        """
        logger.info("Starting real-time HR stream")
        if self._hr_poll_task and not self._hr_poll_task.done():
            return
        try:
            await self._client.start_notify(
                HR_MEASUREMENT_CHAR, self._hr_notification_handler
            )
        except Exception as e:
            logger.warning("HR notify subscribe failed: %s", e)
            return
        self._hr_poll_task = asyncio.create_task(self._hr_keepalive_loop())

    async def _hr_keepalive_loop(self):
        """Periodically write sensor ctrl to keep continuous HR measurement active."""
        cycle = 0
        while True:
            try:
                await self._client.write_gatt_char(
                    SENSOR_CTRL_CHAR,
                    bytes([0x15, 0x01, 0x01]),
                    response=False,
                )
                cycle += 1
                if cycle <= 3 or cycle % 12 == 0 or (cycle == 4 and self._hr_reading_count > 0):
                    logger.info("HR keepalive cycle %d (%d readings so far)", cycle, self._hr_reading_count)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("HR keepalive error: %s", e)
                await asyncio.sleep(10)

    async def enable_hr_measurement(self):
        """Re-enable continuous HR after data fetches complete.
        
        Fully restarts the HR stream: stops keepalive, cycles subscription,
        sends sensor ctrl, and relaunches the keepalive loop.
        """
        try:
            # Stop existing keepalive loop
            if self._hr_poll_task and not self._hr_poll_task.done():
                self._hr_poll_task.cancel()
                try:
                    await self._hr_poll_task
                except asyncio.CancelledError:
                    pass
                self._hr_poll_task = None

            # Cycle the notification subscription (fresh subscribe)
            try:
                await self._client.stop_notify(HR_MEASUREMENT_CHAR)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await self._client.start_notify(
                HR_MEASUREMENT_CHAR, self._hr_notification_handler
            )

            # Send sensor ctrl enable and wait for device to calibrate
            await self._client.write_gatt_char(
                SENSOR_CTRL_CHAR,
                bytes([0x15, 0x01, 0x01]),
                response=False,
            )
            await asyncio.sleep(1)

            # Restart keepalive loop
            self._hr_poll_task = asyncio.create_task(self._hr_keepalive_loop())
            logger.info("HR measurement fully restarted (subscribe + ctrl + keepalive)")
        except Exception as e:
            logger.warning("HR re-enable failed: %s", e)

    async def stop_realtime_hr(self):
        if self._hr_poll_task and not self._hr_poll_task.done():
            self._hr_poll_task.cancel()
            try:
                await self._hr_poll_task
            except asyncio.CancelledError:
                pass
            self._hr_poll_task = None
        try:
            await self._client.write_gatt_char(
                SENSOR_CTRL_CHAR,
                bytes([0x15, 0x01, 0x00]),
                response=False,
            )
        except Exception:
            pass
        try:
            await self._client.stop_notify(HR_MEASUREMENT_CHAR)
        except Exception:
            pass

    # ── Battery ────────────────────────────────────────────

    async def read_battery(self) -> int:
        data = await self._client.read_gatt_char(BATTERY_LEVEL_CHAR)
        return data[0] if data else 0

    async def read_firmware_version(self) -> str | None:
        """Read the Software Revision String (0x2a28) from the device."""
        try:
            data = await self._client.read_gatt_char(SOFTWARE_REVISION_CHAR)
            if data:
                return data.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.warning("Could not read firmware version: %s", e)
        return None

    # ── Sensor Stream (0x0002) — real-time steps & calories ─

    def on_activity(self, callback: Callable[[int, int], Awaitable[None] | None]):
        """Register callback(steps, calories) for real-time activity updates."""
        self._activity_callbacks.append(callback)

    def _sensor_notification_handler(self, _sender, data: bytearray):
        """Parse 0x0002 sensor stream packets.

        11-byte packets: [0x07, seq, 0x10, timestamp_4B, steps_2B_LE, reserved_2B]
          - bytes[7:9] = today's running step count (updates periodically on device)
        6-byte packets:  [0x10, seq, 0xFF, 0x7F, calories_2B_LE]
          - bytes[4:6] = today's running calorie count
        
        Historical daily summaries come from the ECDH activity fetch (type 0x01).
        """
        raw = bytes(data)
        changed = False
        if len(raw) == 11 and raw[0] == 0x07:
            steps = struct.unpack_from("<H", raw, 7)[0]
            if steps != self._current_steps:
                logger.info("Sensor stream: steps changed %d -> %d", self._current_steps, steps)
                if steps > 0:
                    self._current_steps = steps
                    changed = True
        if len(raw) == 6 and raw[0] == 0x10:
            calories = struct.unpack_from("<H", raw, 4)[0]
            if calories != self._current_calories:
                self._current_calories = calories
                changed = True
        if changed:
            self._fire_activity()

    def _fire_activity(self):
        for cb in self._activity_callbacks:
            result = cb(self._current_steps, self._current_calories)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    async def start_sensor_stream(self):
        """Subscribe to 0x0002 for real-time steps/calories."""
        if self._sensor_subscribed:
            return
        try:
            await self._client.start_notify(
                SENSOR_DATA_CHAR, self._sensor_notification_handler
            )
            self._sensor_subscribed = True
            logger.info("Sensor stream active (steps/calories via 0x0002)")
        except Exception as e:
            logger.warning("Sensor stream notify failed: %s", e)

    async def stop_sensor_stream(self):
        if self._sensor_subscribed:
            try:
                await self._client.stop_notify(SENSOR_DATA_CHAR)
            except Exception:
                pass
            self._sensor_subscribed = False

    async def get_steps(self) -> int:
        """Read current step count from device characteristic 0x0007."""
        try:
            data = await self._client.read_gatt_char(STEPS_CHAR)
            if len(data) >= 5:
                # Huami format: byte[0]=type, bytes[1:5]=steps uint32 LE
                steps = int.from_bytes(data[1:5], 'little')
                if steps > 0:
                    self._current_steps = steps
                    return steps
            elif len(data) >= 3:
                # Alternate format: bytes[1:3]=steps uint16 LE
                steps = int.from_bytes(data[1:3], 'little')
                if steps > 0:
                    self._current_steps = steps
                    return steps
        except Exception as e:
            logger.debug("GATT read steps failed: %s", e)
        return self._current_steps

    async def get_calories(self) -> int:
        """Return current calorie count from sensor stream."""
        return self._current_calories

    def reset_counters(self):
        """Reset in-memory step/calorie counters (used by data reset)."""
        self._current_steps = 0
        self._current_calories = 0
        logger.info("Protocol counters reset (steps/calories)")

    # ── Historical Data Fetch (type 0x55) ──────────────────

    def _on_ctrl(self, _sender, data: bytearray):
        self._ctrl_queue.put_nowait(bytes(data))

    def _on_data(self, _sender, data: bytearray):
        # Strip the sequence byte (first byte) from each BLE notification at
        # collection time so decoders receive clean, contiguous payload bytes.
        # Chunks are variable-size (MTU-dependent), so stripping must happen
        # per-notification, not at a fixed CHUNK_SIZE stride.
        if len(data) > 1:
            self._data_chunks.append(bytes(data[1:]))
        self._data_bytes_received += len(data)

    async def _ensure_fetch_subscribed(self):
        """Subscribe to fetch control and data notifications."""
        if not self._fetch_subscribed:
            await self._client.start_notify(FETCH_CTRL_CHAR, self._on_ctrl)
            await self._client.start_notify(FETCH_DATA_CHAR, self._on_data)
            self._fetch_subscribed = True
            await asyncio.sleep(0.3)

    async def _raw_fetch(self, fetch_type: int, since: datetime, ack: bool = True) -> tuple[bytes, datetime | None, int]:
        """Fetch raw data from the device using the direct GATT protocol.

        Returns (raw_data, start_timestamp, expected_size) where start_timestamp
        is parsed from the device's response header.

        If ack=False, the ACK command is not sent after transfer completion.
        This allows re-fetching the same data later (useful for sleep debugging).
        """
        await self._ensure_fetch_subscribed()

        # Clear queues
        while not self._ctrl_queue.empty():
            self._ctrl_queue.get_nowait()
        self._data_chunks.clear()
        self._data_bytes_received = 0

        # Step 1: Init fetch — 10-byte command with date
        cmd = bytes([
            CMD_INIT_FETCH, fetch_type,
            since.year & 0xFF, (since.year >> 8) & 0xFF,
            since.month, since.day,
            since.hour, since.minute,
            0x00, 0x00,  # timezone offset
        ])
        logger.info("Fetch 0x%02x: init since %s, cmd=%s", fetch_type, since, cmd.hex())
        await self._client.write_gatt_char(FETCH_CTRL_CHAR, cmd, response=False)

        # Wait for ctrl response
        try:
            resp = await asyncio.wait_for(self._ctrl_queue.get(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Fetch 0x%02x: no response (timeout)", fetch_type)
            return b"", None, 0

        logger.info("Fetch 0x%02x: ctrl response = %s", fetch_type, resp.hex())

        # Check if data is available
        if len(resp) < 3 or resp[0] != RESPONSE_MARKER or resp[1] != CMD_INIT_FETCH:
            logger.warning("Fetch 0x%02x: unexpected response %s", fetch_type, resp.hex())
            return b"", None, 0

        status = resp[2]
        if status != 0x01:
            logger.info("Fetch 0x%02x: status=0x%02x (no data available)", fetch_type, status)
            return b"", None, 0

        # Parse expected size and start timestamp from header
        start_ts = None
        expected_size = 0
        if len(resp) >= 7:
            expected_size = struct.unpack_from("<I", resp, 3)[0]
            logger.info("Fetch 0x%02x: expecting %d bytes", fetch_type, expected_size)
        if len(resp) >= 13:
            year = struct.unpack_from("<H", resp, 7)[0]
            month, day = resp[9], resp[10]
            hour, minute = resp[11], resp[12]
            try:
                start_ts = datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
                logger.info("Fetch 0x%02x: data starts from %s", fetch_type, start_ts)
            except ValueError:
                pass

        # Step 2: Start data transfer
        logger.info("Fetch 0x%02x: starting transfer...", fetch_type)
        await self._client.write_gatt_char(
            FETCH_CTRL_CHAR, bytes([CMD_START_TRANSFER]), response=False
        )

        # Collect data until stall or completion
        last_count = 0
        stall_counter = 0
        while True:
            await asyncio.sleep(1)
            current = self._data_bytes_received
            if current == last_count:
                stall_counter += 1
                if stall_counter >= 5:
                    break
            else:
                stall_counter = 0
                last_count = current

            # Check for completion notification
            while not self._ctrl_queue.empty():
                msg = self._ctrl_queue.get_nowait()
                logger.debug("Fetch 0x%02x: ctrl during transfer = %s", fetch_type, msg.hex())

        raw = b"".join(self._data_chunks)
        logger.info("Fetch 0x%02x: received %d bytes in %d chunks",
                     fetch_type, len(raw), len(self._data_chunks))

        # Step 3: ACK (optional - skip if ack=False to allow re-fetching)
        if ack:
            try:
                await self._client.write_gatt_char(
                    FETCH_CTRL_CHAR, bytes([CMD_ACK]), response=False
                )
            except Exception:
                pass

        return raw, start_ts, expected_size

    def _decode_hr_data(self, raw: bytes, start_ts: datetime | None) -> list[HRReading]:
        """Decode type 0x55 raw data into HR readings.

        Raw format: 241-byte chunks. First byte = chunk sequence number.
        Remaining 240 bytes = 48 records of 5 bytes each:
          [counter_lo, counter_hi, counter_high + 0xC8, 0x69, bpm]

        Full counter = (byte2 - 0xC8) * 65536 + (byte1 << 8 | byte0)
        Timestamp = start_time + (full_counter - first_counter) seconds
        """
        if not raw:
            return []

        # Sequence bytes are already stripped at collection time (_on_data).
        payload = raw

        # Parse 5-byte records
        records: list[HRReading] = []
        if len(payload) < HR_RECORD_SIZE:
            return records

        # Get first record's counter as base
        first_counter = struct.unpack_from("<H", payload, 0)[0]
        first_high = payload[2] - HR_COUNTER_BASE if payload[2] >= HR_COUNTER_BASE else 0
        base_counter = first_high * 65536 + first_counter

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=72)

        for i in range(0, len(payload) - HR_RECORD_SIZE + 1, HR_RECORD_SIZE):
            counter16 = struct.unpack_from("<H", payload, i)[0]
            counter_high = payload[i + 2] - HR_COUNTER_BASE if payload[i + 2] >= HR_COUNTER_BASE else 0
            bpm = payload[i + 4]

            if bpm == 0 or bpm > 220 or bpm == 128 or bpm < 30:
                continue

            full_counter = counter_high * 65536 + counter16
            offset_seconds = full_counter - base_counter
            ts = start_ts + timedelta(seconds=offset_seconds)

            # Skip future timestamps (device clock drift) and ancient ones
            now = datetime.now(timezone.utc)
            if ts > now + timedelta(hours=1) or ts < now - timedelta(days=30):
                continue

            records.append(HRReading(timestamp=ts, bpm=bpm))

        logger.info("Decoded %d HR readings from %d bytes", len(records), len(raw))
        return records

    async def fetch_historical_hr(self, since: datetime | None = None) -> list[HRReading]:
        """Fetch historical HR data using type 0x55."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_HR, since)
        return self._decode_hr_data(raw, start_ts)

    # ── Data stripping helper ──────────────────────────────

    def _strip_chunk_seq_bytes(self, raw: bytes) -> bytes:
        """Return raw as-is; sequence bytes are stripped at collection time in _on_data."""
        return raw

    # ── SpO2 (type 0x25) ─────────────────────────────────

    def _decode_spo2_data(self, raw: bytes, start_ts: datetime | None) -> list[SpO2Reading]:
        """Decode type 0x25 raw data into SpO2 readings.

        Format (from Gadgetbridge FetchSpo2NormalOperation):
          1-byte version header (expected 0x02) + N × 65-byte records.
          Each record: [timestamp_4B_LE, spo2_raw_1B, unknown_60B]
          SpO2 decoding: bit 7 set → auto measurement, value = raw - 128
                         bit 7 clear → manual measurement, value = raw
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        SPO2_RECORD_SIZE = 65

        # Temporal bounds: accept readings from up to 90 days ago through 1h in the future
        now = datetime.now(timezone.utc)
        ts_min = now - timedelta(days=90)
        ts_max = now + timedelta(hours=1)

        version = payload[0]
        if version != 0x02:
            logger.warning("SpO2: unexpected version %d (expected 2), trying anyway", version)

        data = payload[1:]
        num_records = len(data) // SPO2_RECORD_SIZE
        if len(data) % SPO2_RECORD_SIZE != 0:
            logger.warning("SpO2: data length %d not divisible by %d (remainder %d)",
                           len(data), SPO2_RECORD_SIZE, len(data) % SPO2_RECORD_SIZE)

        readings = []
        skipped_temporal = 0
        skipped_physio = 0
        for i in range(num_records):
            offset = i * SPO2_RECORD_SIZE
            ts_seconds = struct.unpack_from("<i", data, offset)[0]
            spo2_raw = data[offset + 4]

            # Sign-bit decoding: bit 7 = auto measurement flag
            if spo2_raw & 0x80:
                spo2_value = spo2_raw - 128  # Auto measurement
            else:
                spo2_value = spo2_raw  # Manual measurement

            # Physiological guard: SpO2 below 80% is almost certainly corruption
            # (sustained values this low are incompatible with consciousness)
            if spo2_value < 80 or spo2_value > 100:
                skipped_physio += 1
                continue

            # Convert Unix timestamp
            try:
                ts = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
            except (OSError, ValueError, OverflowError):
                skipped_temporal += 1
                continue

            # Temporal guard: discard readings outside the 90-day observation window
            if ts < ts_min or ts > ts_max:
                logger.debug("SpO2: record %d ts=%s outside window [%s, %s], skipping",
                             i, ts.isoformat(), ts_min.isoformat(), ts_max.isoformat())
                skipped_temporal += 1
                continue

            readings.append(SpO2Reading(timestamp=ts, value=spo2_value))

        if skipped_temporal or skipped_physio:
            logger.warning("SpO2: skipped %d temporal outliers and %d physiological outliers "
                           "from %d total records", skipped_temporal, skipped_physio, num_records)
        logger.info("Decoded %d SpO2 readings from %d records (%d bytes)",
                     len(readings), num_records, len(raw))
        return readings

    async def fetch_spo2(self, since: datetime | None = None) -> list[SpO2Reading]:
        """Fetch SpO2 data using type 0x25 (requires ECDH auth)."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_SPO2, since)
        return self._decode_spo2_data(raw, start_ts)

    # ── Stress (type 0x13) ────────────────────────────────

    def _decode_stress_data(self, raw: bytes, start_ts: datetime | None) -> list[StressReading]:
        """Decode type 0x13 raw data into stress readings.

        Format: 1 byte per minute. 0xFF = no reading, 1-100 = stress level.
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=24)

        now = datetime.now(timezone.utc)
        readings = []
        for i, val in enumerate(payload):
            if val == 0xFF or val == 0:
                continue
            if 1 <= val <= 100:
                ts = start_ts + timedelta(minutes=i)
                if ts > now:
                    break  # Stop at current time — rest is garbage
                readings.append(StressReading(timestamp=ts, level=val))

        logger.info("Decoded %d stress readings from %d bytes", len(readings), len(raw))
        return readings

    async def fetch_stress(self, since: datetime | None = None) -> list[StressReading]:
        """Fetch stress data using type 0x13 (requires ECDH auth)."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_STRESS_AUTO, since)
        return self._decode_stress_data(raw, start_ts)

    # ── HRV (type 0x49) ──────────────────────────────────

    def _decode_hrv_data(self, raw: bytes, start_ts: datetime | None) -> list[HRVReading]:
        """Decode type 0x49 raw data into HRV readings.

        Format: 1 byte per minute. Value represents RMSSD in ms.
        0 = no reading. Non-zero values are valid RMSSD (typically 10-150ms).
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=24)

        now = datetime.now(timezone.utc)
        readings = []
        for i, val in enumerate(payload):
            if val == 0 or val == 0xFF:
                continue
            ts = start_ts + timedelta(minutes=i)
            if ts > now:
                break  # Stop at current time — rest is garbage
            readings.append(HRVReading(timestamp=ts, rmssd=float(val), sdnn=0.0))

        logger.info("Decoded %d HRV readings from %d bytes", len(readings), len(raw))
        return readings

    async def fetch_hrv(self, since: datetime | None = None) -> list[HRVReading]:
        """Fetch HRV data using type 0x49 (requires ECDH auth)."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_HRV, since)
        return self._decode_hrv_data(raw, start_ts)

    # ── Sleep (type 0x48) ─────────────────────────────────

    # Maximum gap (minutes) between consecutive confirmed stages that are still
    # considered the SAME sleep cluster.  During actual sleep the device emits
    # confirmed stages (val=1/2/3) every 15–30 min.  During pre/post-sleep
    # drowsiness it emits them every 60–90 min.  A threshold of 50 min correctly
    # separates the two: sleep stages merge into one large cluster; isolated
    # drowsiness stages form tiny single-entry clusters that are discarded.
    SLEEP_CONFIRMED_CLUSTER_GAP = 120   # must exceed longest gap between consecutive
                                         # confirmed stages within a single sleep period.
                                         # Sleep cycles are ~90 min; confirmed stages appear
                                         # at cycle transitions, so gaps of 50-100 min are
                                         # normal within continuous sleep.  50 was too tight
                                         # and split each cycle into its own cluster, yielding
                                         # only 2h instead of 8h.  120 merges full nights.

    # ── Sleep session blob constants (type 0x48) ─────────────────────────
    # Confirmed by Gadgetbridge HuamiSleepSessionSampleProvider:
    # Each session is a 594-byte fixed-size blob containing header,
    # per-segment stage list, and pre-computed totals.
    SLEEP_SESSION_BLOB_SIZE = 594
    SLEEP_DAY_CUTOFF_HOUR = 12       # sleep before noon → previous calendar day

    # Session blob stage type → internal label.
    # From Gadgetbridge SleepStage.asActivityKind():
    #   4=LIGHT, 5=DEEP, 7=AWAKE, 8=REM
    _SESSION_STAGE_LABEL: dict[int, str] = {
        4: "light",
        5: "deep",
        7: "awake",
        8: "rem",
    }

    @staticmethod
    def _local_utc_offset() -> timedelta:
        """Return the current local UTC offset as a timedelta (DST-aware)."""
        return datetime.now().astimezone().utcoffset() or timedelta(0)

    def _sleep_night_date(self, ts: datetime, local_offset: timedelta) -> str:
        """Return the sleep-night date string for a given timestamp.

        Converts UTC timestamp to local time before applying the noon cutoff.
        Sleep before noon local time is attributed to the previous calendar day.
        e.g. 2am Apr 4 local → '2026-04-03' (the night of Apr 3).
        """
        local_ts = ts + local_offset
        if local_ts.hour < self.SLEEP_DAY_CUTOFF_HOUR:
            return (local_ts - timedelta(days=1)).strftime("%Y-%m-%d")
        return local_ts.strftime("%Y-%m-%d")

    def _decode_sleep_data(self, raw: bytes, start_ts: datetime | None) -> list[SleepData]:
        """Decode type 0x48 raw data — 594-byte session blobs.

        Confirmed by Gadgetbridge HuamiSleepSessionSampleProvider:
        Each session is a fixed 594-byte blob containing:
          - Header: timestamps, sleep start/end minutes, avg HR, score
          - Offset 0x54: number of stage entries (u8)
          - Offset 0x56+: 5-byte stage entries (start_u16, end_u16, type_u8)
          - Offset 0x24A-0x251: pre-computed totals (REM, Light, Deep, Wake u16s)

        Stage type mapping (from Gadgetbridge SleepStage.asActivityKind()):
          4=LIGHT, 5=DEEP, 7=AWAKE, 8=REM
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        local_offset = self._local_utc_offset()
        BLOB = self.SLEEP_SESSION_BLOB_SIZE  # 594

        logger.info("Sleep decode: %d payload bytes, blob_size=%d, local_offset=%s",
                     len(payload), BLOB, local_offset)
        logger.info("Sleep payload first 64 bytes hex: %s", payload[:min(64, len(payload))].hex())

        # Verify payload is a multiple of 594 bytes
        if len(payload) < BLOB or len(payload) % BLOB != 0:
            logger.warning(
                "Sleep: payload %d bytes is NOT a multiple of %d — "
                "cannot parse as session blobs (possible protocol variant)",
                len(payload), BLOB,
            )
            return []

        num_sessions = len(payload) // BLOB
        logger.info("Sleep: parsing %d session blob(s) from %d bytes", num_sessions, len(payload))

        results: list[SleepData] = []

        for s in range(num_sessions):
            blob = payload[s * BLOB : (s + 1) * BLOB]

            # ── Parse header ──────────────────────────────────────────
            ts_session = struct.unpack_from('<I', blob, 0x00)[0]
            ts_midnight = struct.unpack_from('<I', blob, 0x04)[0]
            sleep_start_min = struct.unpack_from('<H', blob, 0x0A)[0]
            sleep_end_min = struct.unpack_from('<H', blob, 0x0C)[0]

            # Validate timestamps (must be reasonable epoch values 2020-2040)
            if ts_session < 1577836800 or ts_session > 2208988800:  # 2020-01-01 to 2040-01-01
                logger.warning("Sleep blob %d: invalid session timestamp %d, skipping", s, ts_session)
                continue
            if ts_midnight < 1577836800 or ts_midnight > 2208988800:
                logger.warning("Sleep blob %d: invalid midnight timestamp %d, skipping", s, ts_midnight)
                continue

            session_dt = datetime.fromtimestamp(ts_session, tz=timezone.utc)
            midnight_dt = datetime.fromtimestamp(ts_midnight, tz=timezone.utc)

            # Optional header fields (may be zero if device doesn't populate)
            avg_hr = blob[0x15] if len(blob) > 0x16 else 0
            score = blob[0x16] if len(blob) > 0x17 else 0

            # ── Parse stage entries ───────────────────────────────────
            num_stages = blob[0x54]
            max_stages = (BLOB - 0x56) // 5  # max that fit in the blob
            if num_stages > max_stages:
                logger.warning("Sleep blob %d: num_stages=%d exceeds max=%d, clamping",
                               s, num_stages, max_stages)
                num_stages = max_stages

            stage_entries: list[dict] = []
            counts: dict[str, int] = {"deep": 0, "light": 0, "rem": 0, "awake": 0}

            for i in range(num_stages):
                off = 0x56 + 5 * i
                if off + 5 > BLOB:
                    break
                seg_start = struct.unpack_from('<H', blob, off)[0]
                seg_end = struct.unpack_from('<H', blob, off + 2)[0]
                seg_type = blob[off + 4]

                label = self._SESSION_STAGE_LABEL.get(seg_type)
                if label is None:
                    logger.debug("Sleep blob %d stage %d: unknown type %d", s, i, seg_type)
                    label = "light"  # safe default

                duration = max(seg_end - seg_start, 0)
                if duration == 0 or duration > 840:  # skip zero or >14h segments
                    continue

                # Convert segment start/end from midnight-relative minutes to absolute UTC
                seg_start_dt = midnight_dt + timedelta(minutes=seg_start)
                seg_end_dt = midnight_dt + timedelta(minutes=seg_end)

                stage_entries.append({
                    "stage": label,
                    "start": seg_start_dt.isoformat(),
                    "end": seg_end_dt.isoformat(),
                    "minutes": duration,
                })
                counts[label] += duration

            # ── Parse pre-computed totals from blob footer ────────────
            # Offsets confirmed by Gadgetbridge:
            #   0x24A = totalRemMinutes, 0x24C = totalLightMinutes,
            #   0x24E = totalDeepMinutes, 0x250 = totalWakeMinutes
            blob_rem = struct.unpack_from('<H', blob, 0x24A)[0]
            blob_light = struct.unpack_from('<H', blob, 0x24C)[0]
            blob_deep = struct.unpack_from('<H', blob, 0x24E)[0]
            blob_wake = struct.unpack_from('<H', blob, 0x250)[0]

            # Prefer blob totals if they're non-zero (device pre-computed),
            # otherwise fall back to summing stage entries.
            if blob_rem + blob_light + blob_deep > 0:
                deep = blob_deep
                light = blob_light
                rem = blob_rem
                awake = blob_wake
                total = deep + light + rem
                source = "blob_totals"
            elif counts["deep"] + counts["light"] + counts["rem"] > 0:
                deep = counts["deep"]
                light = counts["light"]
                rem = counts["rem"]
                awake = counts["awake"]
                total = deep + light + rem
                source = "stage_sum"
            else:
                logger.info("Sleep blob %d: no sleep data (all totals zero), skipping", s)
                continue

            # Sanity check: skip sessions with unrealistic totals
            if total > 14 * 60:
                logger.warning("Sleep blob %d: unrealistic total %d min, skipping", s, total)
                continue
            if total < 10:
                logger.info("Sleep blob %d: trivial total %d min, skipping", s, total)
                continue

            # ── Determine night date ──────────────────────────────────
            night_date = self._sleep_night_date(session_dt, local_offset)

            # ── Log diagnostic info ───────────────────────────────────
            local_session = session_dt + local_offset
            logger.info(
                "Sleep blob %d: session=%s (local %s), midnight=%s, "
                "start_min=%d end_min=%d, %d stages, "
                "totals(%s): D=%d L=%d R=%d A=%d total=%d, "
                "avgHR=%d score=%d -> night=%s",
                s, session_dt.isoformat(), local_session.strftime("%H:%M"),
                midnight_dt.isoformat(),
                sleep_start_min, sleep_end_min, num_stages,
                source, deep, light, rem, awake, total,
                avg_hr, score, night_date,
            )

            result = SleepData(
                date=night_date,
                total_minutes=total,
                deep_minutes=deep,
                light_minutes=light,
                rem_minutes=rem,
                awake_minutes=awake,
                stages=stage_entries,
            )
            results.append(result)

        # Deduplicate by night date (first occurrence wins)
        seen: dict[str, SleepData] = {}
        for r in results:
            if r.date not in seen:
                seen[r.date] = r
            else:
                # Keep the one with more total sleep
                if r.total_minutes > seen[r.date].total_minutes:
                    seen[r.date] = r

        final = sorted(seen.values(), key=lambda x: x.date)
        logger.info("Sleep: decoded %d session(s) from %d blob(s), %d unique night(s)",
                     len(results), num_sessions, len(final))
        return final

    async def fetch_sleep(self, since: datetime | None = None) -> list[SleepData]:
        """Fetch sleep data using type 0x48 (requires ECDH auth).

        The device returns 0x05 if the requested date range was already ACK'd.
        We retry with progressively more recent 'since' dates to catch new nights.
        Accumulates results across all retry attempts, keyed by date.
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        now = datetime.now(timezone.utc)

        # Build candidate "since" dates.  Strategy:
        #   - Start with the requested `since` date (usually the latest sleep in DB).
        #   - Also try EARLIER dates (since-1d, since-2d) in case the device's ACK
        #     pointer was set to a later date and earlier data can be re-fetched.
        #   - Also try RECENT dates (3d, 2d, 1d, today) to catch newly recorded nights.
        # The device returns 0x05 for ranges it has already delivered; each non-empty
        # response gives us data that we accumulate — first occurrence per night wins.
        candidates: list[datetime] = []
        # Earlier fallbacks (catch data that might have been decoded incorrectly before)
        for days_earlier in [2, 1]:
            c = (since - timedelta(days=days_earlier)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            candidates.append(c)
        # The main since date
        candidates.append(since)
        # Recent dates to catch newly recorded nights
        for days_back in [6, 5, 4, 3, 2, 1, 0]:
            c = (now - timedelta(days=days_back)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if c > since:
                candidates.append(c)

        logger.info("Sleep fetch: trying %d candidate since-dates: %s",
                     len(candidates),
                     ", ".join(c.strftime("%Y-%m-%d") for c in candidates))

        # Accumulate results across retries, first occurrence per date wins.
        # For sleep data, we use ack=False on the first fetch to avoid prematurely
        # ACKing data that might decode incorrectly. Once we have valid results,
        # we re-fetch with ack=True to clear the device's buffer.
        all_results: dict[str, SleepData] = {}
        fetch_to_ack: list[tuple[datetime, bytes]] = []  # (since, raw_data) pairs to ACK later
        
        for attempt_since in candidates:
            # First fetch without ACK - allows retry if decode fails
            raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_SLEEP, attempt_since, ack=False)
            if raw:
                logger.info("Sleep fetch attempt since=%s: got %d raw bytes (no ACK yet)",
                             attempt_since.isoformat(), len(raw))
                results = self._decode_sleep_data(raw, start_ts)
                if results:
                    # Check if any result has unrealistic duration (> 14 hours)
                    # If so, don't accept it and don't ACK - let device resend later
                    realistic_results = []
                    for s in results:
                        if s.total_minutes > 14 * 60:  # > 14 hours is suspicious
                            logger.warning(
                                "Sleep %s: unrealistic duration %d min (%dh%02dm) — "
                                "possible decode error, will not ACK this fetch",
                                s.date, s.total_minutes, 
                                s.total_minutes // 60, s.total_minutes % 60
                            )
                        else:
                            realistic_results.append(s)
                    
                    for s in realistic_results:
                        if s.date not in all_results:
                            all_results[s.date] = s
                            fetch_to_ack.append((attempt_since, raw))
                else:
                    # No valid sessions decoded from this raw data - don't ACK
                    logger.info("Sleep fetch since=%s: decoded 0 sessions, not ACKing",
                                 attempt_since.isoformat())
            else:
                logger.info("Sleep fetch attempt since=%s: no data (0x05 or timeout)",
                             attempt_since.isoformat())
            await asyncio.sleep(1.0)  # give device time to reset state between requests

        # If we got valid results, re-fetch with ACK to clear device buffer
        if all_results and fetch_to_ack:
            logger.info("Sleep fetch: re-fetching with ACK to clear device buffer...")
            for since_date, _ in fetch_to_ack:
                # Short timeout - we just need to send the ACK
                await self._raw_fetch(FETCH_TYPE_SLEEP, since_date, ack=True)
                await asyncio.sleep(0.5)

        if all_results:
            logger.info("Sleep fetch: %d unique nights from %d attempts",
                         len(all_results), len(candidates))
            return list(all_results.values())

        logger.info("Sleep: no data from device after %d attempts", len(candidates))
        return []

    # ── Activity (type 0x01) ──────────────────────────────

    # Maximum plausible steps in a single day (world record ~70k; cap at 80k)
    ACTIVITY_MAX_DAILY_STEPS = 80_000

    def _decode_activity_data(self, raw: bytes, start_ts: datetime | None, expected_size: int = 0) -> list[ActivityData]:
        """Decode type 0x01 raw data into daily activity records.

        On Zepp OS devices, type 0x01 returns per-minute activity samples,
        8 bytes each:
          byte 0: kind (activity category)
          byte 1: intensity
          byte 2: steps (steps taken in that minute, 0-255)
          byte 3: heart rate
          bytes 4-7: extra data (SpO2/stress flags, sleep markers)

        We sum the per-minute steps into daily totals.
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=24)

        SAMPLE_SIZE = 8
        n_samples = len(payload) // SAMPLE_SIZE
        if n_samples == 0:
            logger.info("Activity: payload too small (%d bytes, need at least %d)", len(payload), SAMPLE_SIZE)
            return []

        # Use runtime-correct local UTC offset (fixes DST static-flag bug)
        local_utc_offset = datetime.now().astimezone().utcoffset() or timedelta(0)

        # Diagnostic: track byte[2] distribution to catch format bugs
        val_dist = {0: 0, "1-10": 0, "11-100": 0, "101-200": 0, "201-254": 0, 255: 0}
        today_str = (datetime.now(timezone.utc) + local_utc_offset).strftime("%Y-%m-%d")
        daily: dict[str, int] = {}

        for i in range(n_samples):
            off = i * SAMPLE_SIZE
            steps = payload[off + 2]

            # Track distribution for diagnostics
            if steps == 0:
                val_dist[0] += 1
            elif steps <= 10:
                val_dist["1-10"] += 1
            elif steps <= 100:
                val_dist["11-100"] += 1
            elif steps <= 200:
                val_dist["101-200"] += 1
            elif steps <= 254:
                val_dist["201-254"] += 1
            else:  # steps == 255 — likely a sentinel/no-data byte
                val_dist[255] += 1
                continue   # skip 0xFF sentinel values

            ts = start_ts + timedelta(minutes=i)
            local_ts = ts + local_utc_offset
            date_str = local_ts.strftime("%Y-%m-%d")
            if date_str > today_str:
                continue
            daily[date_str] = daily.get(date_str, 0) + steps

        logger.info("Activity: %d samples, start=%s, byte[2] dist: %s",
                    n_samples, start_ts, val_dist)

        results = []
        for date_str, total_steps in sorted(daily.items()):
            if total_steps > self.ACTIVITY_MAX_DAILY_STEPS:
                logger.warning(
                    "Activity: date %s has suspiciously high steps=%d "
                    "(byte[2] dist: %s) — discarding as likely corrupt",
                    date_str, total_steps, val_dist,
                )
                continue  # don't save clearly wrong data
            results.append(ActivityData(
                date=date_str,
                steps=total_steps,
                calories=0,
                distance=0,
            ))

        total = sum(r.steps for r in results)
        logger.info("Activity: decoded %d samples -> %d day(s), %d total steps",
                     n_samples, len(results), total)
        return results

    async def fetch_activity(self, since: datetime | None = None) -> list[ActivityData]:
        """Fetch activity data using type 0x01 (requires ECDH auth).

        Loops with advancing since-dates until the device says no more data.
        Uses a dict keyed by date to deduplicate across iterations (takes max steps).
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        # Keyed by date string — ensures no duplicate dates across iterations
        all_results: dict[str, ActivityData] = {}
        current_since = since
        max_iterations = 14  # safety cap: max 14 days

        for _ in range(max_iterations):
            raw, start_ts, expected_size = await self._raw_fetch(FETCH_TYPE_ACTIVITY, current_since)
            if not raw:
                break  # no more data

            records = self._decode_activity_data(raw, start_ts, expected_size)
            if not records:
                break

            for r in records:
                existing = all_results.get(r.date)
                if existing is None or r.steps > existing.steps:
                    all_results[r.date] = r

            # Advance since to the day AFTER the last record returned
            # (not just start_ts+1day, which could leave gaps or overlaps)
            last_date_str = records[-1].date
            try:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                current_since = last_date + timedelta(days=1)
            except ValueError:
                if start_ts:
                    current_since = start_ts + timedelta(days=1)
                else:
                    break

            await asyncio.sleep(0.5)

        result_list = sorted(all_results.values(), key=lambda x: x.date)
        logger.info("Activity: fetched %d unique day records total", len(result_list))
        return result_list
