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
        if bpm == 0:
            return
        self._hr_reading_count += 1
        if self._hr_reading_count <= 3 or self._hr_reading_count % 30 == 0:
            logger.info("HR notification: %d bpm (reading #%d)", bpm, self._hr_reading_count)
        reading = HRReading(timestamp=datetime.now(timezone.utc), bpm=bpm)
        for cb in self._hr_callbacks:
            try:
                result = cb(reading)
                if asyncio.iscoroutine(result):
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
        
        Cycles the 0x2A37 notification subscription and immediately sends
        the sensor ctrl command — this mirrors the pattern proven in testing.
        """
        try:
            # Cycle the notification subscription (fresh subscribe)
            try:
                await self._client.stop_notify(HR_MEASUREMENT_CHAR)
            except Exception:
                pass
            await asyncio.sleep(0.3)
            await self._client.start_notify(
                HR_MEASUREMENT_CHAR, self._hr_notification_handler
            )
            # Immediately send sensor ctrl enable
            await self._client.write_gatt_char(
                SENSOR_CTRL_CHAR,
                bytes([0x15, 0x01, 0x01]),
                response=False,
            )
            logger.info("HR measurement re-enabled (fresh subscribe + sensor ctrl)")
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
        self._data_chunks.append(bytes(data))
        self._data_bytes_received += len(data)

    async def _ensure_fetch_subscribed(self):
        """Subscribe to fetch control and data notifications."""
        if not self._fetch_subscribed:
            await self._client.start_notify(FETCH_CTRL_CHAR, self._on_ctrl)
            await self._client.start_notify(FETCH_DATA_CHAR, self._on_data)
            self._fetch_subscribed = True
            await asyncio.sleep(0.3)

    async def _raw_fetch(self, fetch_type: int, since: datetime) -> tuple[bytes, datetime | None]:
        """Fetch raw data from the device using the direct GATT protocol.

        Returns (raw_data, start_timestamp) where start_timestamp is parsed
        from the device's response header.
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
            return b"", None

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

        # Step 3: ACK
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

        # Strip chunk sequence bytes (first byte of each 241-byte chunk)
        payload = bytearray()
        pos = 0
        while pos < len(raw):
            chunk_size = min(CHUNK_SIZE, len(raw) - pos)
            # Skip first byte (chunk sequence number)
            payload.extend(raw[pos + 1:pos + chunk_size])
            pos += chunk_size

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

            if bpm == 0 or bpm > 220:
                continue

            full_counter = counter_high * 65536 + counter16
            offset_seconds = full_counter - base_counter
            ts = start_ts + timedelta(seconds=offset_seconds)
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
        """Strip sequence bytes from raw chunks (first byte of each 241-byte chunk)."""
        payload = bytearray()
        pos = 0
        while pos < len(raw):
            chunk_size = min(CHUNK_SIZE, len(raw) - pos)
            payload.extend(raw[pos + 1:pos + chunk_size])
            pos += chunk_size
        return bytes(payload)

    # ── SpO2 (type 0x25) ─────────────────────────────────

    def _decode_spo2_data(self, raw: bytes, start_ts: datetime | None) -> list[SpO2Reading]:
        """Decode type 0x25 raw data into SpO2 readings.

        Format: 1 byte per minute. 0 = no reading, else SpO2 % (typically 80-100).
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=24)

        readings = []
        for i, val in enumerate(payload):
            if val == 0 or val == 0xFF:
                continue
            if 50 <= val <= 100:
                ts = start_ts + timedelta(minutes=i)
                readings.append(SpO2Reading(timestamp=ts, value=val))

        logger.info("Decoded %d SpO2 readings from %d bytes", len(readings), len(raw))
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

        readings = []
        for i, val in enumerate(payload):
            if val == 0xFF or val == 0:
                continue
            if 1 <= val <= 100:
                ts = start_ts + timedelta(minutes=i)
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

        readings = []
        for i, val in enumerate(payload):
            if val == 0 or val == 0xFF:
                continue
            ts = start_ts + timedelta(minutes=i)
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

    def _decode_sleep_data(self, raw: bytes, start_ts: datetime | None) -> list[SleepData]:
        """Decode type 0x48 raw data into sleep sessions.

        The raw data contains per-minute sleep stage values.
        Stage values: 0=awake, 1=light, 2=deep, 3=REM.
        Non-sleep (0xFF or 0) is ignored.
        """
        payload = self._strip_chunk_seq_bytes(raw)
        if not payload:
            return []

        if start_ts is None:
            start_ts = datetime.now(timezone.utc) - timedelta(hours=24)

        # Count minutes per sleep stage
        deep = light = rem = awake = 0
        stages = []
        current_stage = None
        stage_start = None

        for i, val in enumerate(payload):
            if val == 0xFF or val > 10:
                stage = None
            elif val == 0:
                stage = "awake"
            elif val == 1:
                stage = "light"
            elif val == 2:
                stage = "deep"
            elif val == 3:
                stage = "rem"
            else:
                stage = "light"

            if stage != current_stage:
                if current_stage and stage_start is not None:
                    stages.append({
                        "stage": current_stage,
                        "start": (start_ts + timedelta(minutes=stage_start)).isoformat(),
                        "end": (start_ts + timedelta(minutes=i)).isoformat(),
                        "minutes": i - stage_start,
                    })
                current_stage = stage
                stage_start = i

            if stage == "deep":
                deep += 1
            elif stage == "light":
                light += 1
            elif stage == "rem":
                rem += 1
            elif stage == "awake":
                awake += 1

        # Close last stage
        if current_stage and stage_start is not None:
            stages.append({
                "stage": current_stage,
                "start": (start_ts + timedelta(minutes=stage_start)).isoformat(),
                "end": (start_ts + timedelta(minutes=len(payload))).isoformat(),
                "minutes": len(payload) - stage_start,
            })

        total = deep + light + rem
        if total == 0:
            logger.info("Sleep: no valid sleep stages found in %d bytes", len(raw))
            return []

        date_str = start_ts.strftime("%Y-%m-%d")
        result = SleepData(
            date=date_str,
            total_minutes=total,
            deep_minutes=deep,
            light_minutes=light,
            rem_minutes=rem,
            awake_minutes=awake,
            stages=stages,
        )
        logger.info("Decoded sleep: %d min total (D=%d L=%d R=%d A=%d)",
                     total, deep, light, rem, awake)
        return [result]

    async def fetch_sleep(self, since: datetime | None = None) -> list[SleepData]:
        """Fetch sleep data using type 0x48 (requires ECDH auth)."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)
        raw, start_ts, _ = await self._raw_fetch(FETCH_TYPE_SLEEP, since)
        return self._decode_sleep_data(raw, start_ts)

    # ── Activity (type 0x01) ──────────────────────────────

    def _decode_activity_data(self, raw: bytes, start_ts: datetime | None, expected_size: int = 0) -> list[ActivityData]:
        """Decode type 0x01 raw data into daily activity records.

        On Zepp OS devices, type 0x01 returns per-minute activity samples,
        8 bytes each:
          byte 0: kind (activity category)
          byte 1: intensity
          byte 2: steps (steps taken in that minute)
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

        # Aggregate steps per day
        daily: dict[str, int] = {}
        for i in range(n_samples):
            off = i * SAMPLE_SIZE
            steps = payload[off + 2]
            ts = start_ts + timedelta(minutes=i)
            date_str = ts.strftime("%Y-%m-%d")
            daily[date_str] = daily.get(date_str, 0) + steps

        results = []
        for date_str, total_steps in sorted(daily.items()):
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
        
        The device returns one daily summary per fetch. We loop with
        advancing `since` dates until the device says no more data.
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        all_results: list[ActivityData] = []
        current_since = since
        max_iterations = 14  # safety cap: max 14 days

        for _ in range(max_iterations):
            raw, start_ts, expected_size = await self._raw_fetch(FETCH_TYPE_ACTIVITY, current_since)
            if not raw:
                break  # no more data

            records = self._decode_activity_data(raw, start_ts, expected_size)
            if not records:
                break

            all_results.extend(records)

            # Advance since to the day after the returned data
            if start_ts:
                current_since = start_ts + timedelta(days=1)
                current_since = current_since.replace(hour=0, minute=0, second=0)
            else:
                break

            # Small delay between fetches
            await asyncio.sleep(0.5)

        logger.info("Activity: fetched %d daily records total", len(all_results))
        return all_results
