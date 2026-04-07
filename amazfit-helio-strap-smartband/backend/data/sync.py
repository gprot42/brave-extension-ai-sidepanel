"""Sync orchestrator — manages real-time HR streaming, sensor stream, periodic data fetch,
and Zepp cloud API sync for sleep, stress, and SpO2 data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, func, text, desc

from backend.ble.connection import connection
import backend.config as config
from backend.ble.protocol import HRReading
from backend.cloud.huami_client import client as cloud_client
from backend.cloud.parser import (
    parse_band_data_summary,
    parse_spo2_events,
    parse_stress_events,
)
from backend.data.database import async_session
from backend.data import models

logger = logging.getLogger(__name__)

# Shared list of WebSocket send functions for real-time HR broadcast
hr_subscribers: list = []


_hr_write_count = 0  # Track successful DB writes for logging

async def _on_hr_reading(reading: HRReading):
    """Called for each real-time HR reading: persist + broadcast.
    
    128 bpm (0x80) is a sensor calibration status, not a real reading.
    We skip both broadcast and DB write for calibration values.
    """
    global _hr_write_count
    # Skip calibration status (128 = 0x80) entirely
    if reading.bpm == 128:
        return

    # Broadcast via WebSocket
    payload = json.dumps(
        {"timestamp": reading.timestamp.isoformat(), "bpm": reading.bpm}
    )
    ws_count = len(hr_subscribers)
    dead: list[int] = []
    for i, send_fn in enumerate(hr_subscribers):
        try:
            await send_fn(payload)
        except Exception:
            dead.append(i)
    for i in reversed(dead):
        hr_subscribers.pop(i)

    try:
        async with async_session() as session:
            # Normalize timestamp to naive UTC for SQLite compatibility
            ts_naive = reading.timestamp.replace(tzinfo=None) if reading.timestamp.tzinfo else reading.timestamp
            # Deduplicate: skip if a reading with the same timestamp already exists
            existing = (
                await session.execute(
                    select(models.HeartRate).where(
                        models.HeartRate.timestamp == ts_naive
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(models.HeartRate(timestamp=ts_naive, bpm=reading.bpm))
                await session.commit()
                _hr_write_count += 1
                if _hr_write_count <= 5 or _hr_write_count % 30 == 0:
                    logger.info("HR realtime: wrote %d bpm to DB (ws_subs=%d, total_writes=%d)",
                                reading.bpm, ws_count, _hr_write_count)
    except Exception as e:
        logger.error("HR DB write error: %s", e)


async def _on_activity_update(steps: int, calories: int):
    """Called when steps/calories change from sensor stream or activity fetch.
    
    Uses atomic INSERT OR REPLACE to avoid UNIQUE constraint races.
    Steps=0 means "no step data from this source" and won't overwrite existing steps.
    """
    today = date.today().isoformat()
    async with async_session() as session:
        await session.execute(
            text(
                "INSERT INTO activity (date, steps, calories, distance) "
                "VALUES (:date, :steps, :calories, 0) "
                "ON CONFLICT(date) DO UPDATE SET "
                "steps = CASE WHEN :steps > 0 THEN :steps ELSE activity.steps END, "
                "calories = CASE WHEN :calories > 0 THEN :calories ELSE activity.calories END"
            ),
            {"date": today, "steps": steps, "calories": calories},
        )
        await session.commit()


_hr_callback_proto = None  # Track which protocol object has the HR callback

async def start_realtime_hr():
    """Start streaming HR from device."""
    global _hr_callback_proto, _hr_write_count
    proto = connection.protocol
    if proto is None:
        logger.warning("Cannot start HR stream — not connected")
        return
    if _hr_callback_proto is not proto:
        logger.info("HR stream: registering callback on protocol %s (prev=%s)",
                     id(proto), id(_hr_callback_proto) if _hr_callback_proto else "None")
        proto.on_hr(_on_hr_reading)
        _hr_callback_proto = proto
        _hr_write_count = 0  # Reset counter for new connection
    else:
        logger.info("HR stream: callback already registered on protocol %s", id(proto))
    await proto.start_realtime_hr()


async def _on_sensor_activity(steps: int, calories: int):
    """Called by sensor stream when steps/calories change.
    
    The sensor stream provides the device's own step counter, which is the
    authoritative source for today's steps.
    """
    await _on_activity_update(steps, calories)


_activity_callback_proto = None  # Track which protocol object has the activity callback

async def start_sensor_stream():
    """Start sensor stream for real-time steps/calories."""
    global _activity_callback_proto
    proto = connection.protocol
    if proto is None:
        logger.warning("Cannot start sensor stream — not connected")
        return
    if _activity_callback_proto is not proto:
        proto.on_activity(_on_sensor_activity)
        _activity_callback_proto = proto
    await proto.start_sensor_stream()


async def periodic_sync_loop(interval: int = 300):
    """Periodically fetch battery and historical HR data."""
    while True:
        await asyncio.sleep(interval)
        await run_sync()


async def run_sync():
    """Run a single sync cycle: battery + activity snapshot + historical HR."""
    proto = connection.protocol
    if proto is None:
        logger.warning("Skipping sync — not connected")
        return

    logger.info("Starting sync...")

    # Battery & firmware (always works, no auth needed)
    try:
        battery = await proto.read_battery()
        firmware = await proto.read_firmware_version()
        async with async_session() as session:
            info = (await session.execute(select(models.DeviceInfo))).scalar_one_or_none()
            if info:
                info.battery_level = battery
                if firmware:
                    info.firmware_version = firmware
                info.last_sync = datetime.now(timezone.utc)
            else:
                session.add(
                    models.DeviceInfo(
                        battery_level=battery,
                        firmware_version=firmware,
                        last_sync=datetime.now(timezone.utc),
                    )
                )
            await session.commit()
        logger.info("Battery: %d%%%s", battery, f", Firmware: {firmware}" if firmware else "")
    except Exception as e:
        logger.error("Battery/firmware sync error: %s", e)

    # Persist calories from sensor stream. Steps from the sensor stream are
    # unreliable on this device (stale cached value); real step counts come
    # from the activity fetch (type 0x01) in _sync_health_data().
    try:
        calories = await proto.get_calories()
        if calories > 0:
            await _on_activity_update(0, calories)
            logger.info("Activity: %d cal (sensor stream, steps via fetch)", calories)
    except Exception as e:
        logger.error("Activity sync error: %s", e)

    if not config.AUTH_KEY_HEX:
        logger.info("Sync complete (battery + activity). Set AUTH_KEY in .env for historical HR.")
        return

    # Historical HR (type 0x55) — fetch since last known reading or 7 days ago
    try:
        since = datetime.now(timezone.utc) - timedelta(days=7)

        # Check what we already have to avoid duplicates
        async with async_session() as session:
            latest = (
                await session.execute(
                    select(func.max(models.HeartRate.timestamp))
                )
            ).scalar()
            if latest:
                # Sanity check: ignore future timestamps from corrupt data
                now = datetime.now(timezone.utc)
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                if latest > now:
                    logger.warning("Latest HR timestamp %s is in the future — ignoring, using 7-day window", latest)
                    latest = None
                else:
                    since = latest - timedelta(minutes=5)
                    logger.info("Fetching HR since %s (last known reading)", since)

        readings = await proto.fetch_historical_hr(since=since)
        if readings:
            async with async_session() as session:
                inserted = 0
                existing_ts = set()
                if latest:
                    result = await session.execute(
                        select(models.HeartRate.timestamp).where(
                            models.HeartRate.timestamp >= since
                        )
                    )
                    # Normalize to naive UTC for comparison (SQLite stores naive)
                    existing_ts = {
                        row[0].replace(tzinfo=None) if row[0] and hasattr(row[0], 'tzinfo') and row[0].tzinfo else row[0]
                        for row in result
                    }

                for r in readings:
                    # Strip timezone for DB storage and comparison
                    ts_naive = r.timestamp.replace(tzinfo=None) if r.timestamp.tzinfo else r.timestamp
                    if ts_naive not in existing_ts:
                        session.add(models.HeartRate(timestamp=ts_naive, bpm=r.bpm))
                        existing_ts.add(ts_naive)
                        inserted += 1
                        if inserted % 5000 == 0:
                            await session.commit()

                await session.commit()
                logger.info("Synced %d new HR readings (%d total fetched)", inserted, len(readings))
        else:
            logger.info("Historical HR: no data returned from device")
    except Exception as e:
        logger.error("Historical HR sync error: %s", e, exc_info=True)

    # Health data sync (requires ECDH auth)
    if connection.is_zepp_authenticated:
        await _sync_health_data(proto)
    else:
        logger.warning("Health data sync SKIPPED — ECDH auth not available. Reconnect to device to enable.")

    logger.info("Sync complete — re-enabling HR stream...")

    # Let BLE settle after data fetches, then re-enable HR
    await asyncio.sleep(1)
    try:
        await proto.enable_hr_measurement()
        logger.info("HR stream re-enabled after sync")
    except Exception as e:
        logger.warning("HR re-enable after sync failed: %s", e)


async def _sync_health_data(proto):
    """Fetch SpO2, stress, HRV, sleep, and activity from device (requires ECDH auth)."""
    since = datetime.now(timezone.utc) - timedelta(days=7)

    # SpO2
    try:
        readings = await proto.fetch_spo2(since)
        if readings:
            async with async_session() as session:
                inserted = 0
                for r in readings:
                    exists = (
                        await session.execute(
                            select(models.SpO2).where(models.SpO2.timestamp == r.timestamp)
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.SpO2(timestamp=r.timestamp, value=r.value))
                        inserted += 1
                await session.commit()
                logger.info("BLE SpO2: saved %d new readings", inserted)
    except Exception as e:
        logger.error("BLE SpO2 sync error: %s", e, exc_info=True)

    # Stress
    try:
        readings = await proto.fetch_stress(since)
        if readings:
            async with async_session() as session:
                inserted = 0
                for r in readings:
                    exists = (
                        await session.execute(
                            select(models.Stress).where(models.Stress.timestamp == r.timestamp)
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.Stress(timestamp=r.timestamp, level=r.level))
                        inserted += 1
                await session.commit()
                logger.info("BLE Stress: saved %d new readings", inserted)
    except Exception as e:
        logger.error("BLE Stress sync error: %s", e, exc_info=True)

    # HRV
    try:
        readings = await proto.fetch_hrv(since)
        if readings:
            async with async_session() as session:
                inserted = 0
                for r in readings:
                    exists = (
                        await session.execute(
                            select(models.HRV).where(models.HRV.timestamp == r.timestamp)
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.HRV(timestamp=r.timestamp, rmssd=r.rmssd, sdnn=r.sdnn))
                        inserted += 1
                await session.commit()
                logger.info("BLE HRV: saved %d new readings", inserted)
    except Exception as e:
        logger.error("BLE HRV sync error: %s", e, exc_info=True)

    # Sleep
    try:
        # Use the most recent sleep date to avoid re-fetching already-ACK'd data
        async with async_session() as session:
            latest_sleep = (await session.execute(
                select(models.Sleep.date).order_by(desc(models.Sleep.date)).limit(1)
            )).scalar_one_or_none()
        if latest_sleep:
            # Fetch from the day after the last known sleep record
            sleep_since = datetime.strptime(latest_sleep, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            sleep_since = since
        sessions_data = await proto.fetch_sleep(sleep_since)
        if sessions_data:
            import json
            # Warn if adjacent nights have identical durations
            totals = [(s.date, s.total_minutes) for s in sessions_data]
            for i in range(1, len(totals)):
                if totals[i][1] == totals[i-1][1]:
                    logger.warning("BLE Sleep: nights %s and %s have identical duration %d min",
                                    totals[i-1][0], totals[i][0], totals[i][1])

            async with async_session() as session:
                for s in sessions_data:
                    exists = (
                        await session.execute(
                            select(models.Sleep).where(models.Sleep.date == s.date)
                        )
                    ).scalar_one_or_none()
                    stages_str = json.dumps(s.stages) if s.stages else None
                    if not exists:
                        logger.info("BLE Sleep: INSERT %s — %d min (D=%d L=%d R=%d A=%d)",
                                     s.date, s.total_minutes, s.deep_minutes,
                                     s.light_minutes, s.rem_minutes, s.awake_minutes)
                        session.add(models.Sleep(
                            date=s.date,
                            total_minutes=s.total_minutes,
                            deep_minutes=s.deep_minutes,
                            light_minutes=s.light_minutes,
                            rem_minutes=s.rem_minutes,
                            awake_minutes=s.awake_minutes,
                            stages_json=stages_str,
                        ))
                    else:
                        changed = exists.total_minutes != s.total_minutes
                        logger.info("BLE Sleep: UPDATE %s — %d→%d min%s",
                                     s.date, exists.total_minutes, s.total_minutes,
                                     " (changed)" if changed else " (same)")
                        exists.total_minutes = s.total_minutes
                        exists.deep_minutes = s.deep_minutes
                        exists.light_minutes = s.light_minutes
                        exists.rem_minutes = s.rem_minutes
                        exists.awake_minutes = s.awake_minutes
                        exists.stages_json = stages_str
                await session.commit()
                logger.info("BLE Sleep: saved %d sessions", len(sessions_data))
    except Exception as e:
        logger.error("BLE Sleep sync error: %s", e, exc_info=True)

    # Activity — fetch per-minute samples and aggregate to daily totals.
    # For today's date, the real-time sensor stream may provide a more up-to-date
    # step count, so we use MAX() to keep the higher value.
    try:
        activities = await proto.fetch_activity(since)
        if activities:
            async with async_session() as session:
                for a in activities:
                    # Atomic upsert — avoids SQLAlchemy session-flush race conditions
                    # that can cause duplicate-insert conflicts when the same date
                    # appears more than once in the activities list.
                    await session.execute(
                        text(
                            "INSERT INTO activity (date, steps, calories, distance) "
                            "VALUES (:date, :steps, :calories, 0) "
                            "ON CONFLICT(date) DO UPDATE SET "
                            "steps = MAX(activity.steps, excluded.steps), "
                            "calories = MAX(activity.calories, excluded.calories)"
                        ),
                        {"date": a.date, "steps": a.steps, "calories": a.calories},
                    )
                await session.commit()
                logger.info("BLE Activity: saved/updated %d day records", len(activities))
    except Exception as e:
        logger.error("BLE Activity sync error: %s", e, exc_info=True)


# ── Cloud sync ─────────────────────────────────────────

async def init_cloud_client():
    """Initialize cloud client with saved credentials from .env."""
    if config.ZEPP_APPTOKEN and config.ZEPP_USERID:
        cloud_client.set_credentials(config.ZEPP_APPTOKEN, config.ZEPP_USERID)
        if config.ZEPP_REGION:
            cloud_client.region = config.ZEPP_REGION
        logger.info("Cloud client initialized with saved credentials (userid=%s)", config.ZEPP_USERID)


async def cloud_login(email: str, password: str) -> tuple[str, str]:
    """Login to Zepp cloud and return (apptoken, userid)."""
    if config.ZEPP_REGION:
        cloud_client.region = config.ZEPP_REGION
    apptoken, userid = await cloud_client.login(email, password)
    # Save to config (caller should persist to .env)
    config.ZEPP_APPTOKEN = apptoken
    config.ZEPP_USERID = userid
    return apptoken, userid


async def run_cloud_sync(days: int = 7):
    """Fetch sleep, activity, stress, and SpO2 from Zepp cloud."""
    if not cloud_client.is_logged_in:
        logger.info("Cloud sync skipped — not logged in. Set ZEPP_APPTOKEN/ZEPP_USERID in .env or call /api/cloud-login")
        return

    today = date.today()
    from_date = today - timedelta(days=days)
    logger.info("Cloud sync: fetching %d days (%s to %s)", days, from_date, today)

    # Fetch band_data (sleep + activity)
    try:
        raw = await cloud_client.fetch_sleep_and_activity(from_date, today)
        sleep_records, activity_records = parse_band_data_summary(raw)

        async with async_session() as session:
            # Upsert sleep
            for rec in sleep_records:
                existing = (
                    await session.execute(
                        select(models.Sleep).where(models.Sleep.date == rec["date"])
                    )
                ).scalar_one_or_none()
                if existing:
                    for k, v in rec.items():
                        setattr(existing, k, v)
                else:
                    session.add(models.Sleep(**rec))

            # Upsert activity (merge with BLE data — prefer higher step count)
            for rec in activity_records:
                existing = (
                    await session.execute(
                        select(models.Activity).where(models.Activity.date == rec["date"])
                    )
                ).scalar_one_or_none()
                if existing:
                    if rec["steps"] > existing.steps:
                        existing.steps = rec["steps"]
                        existing.calories = rec["calories"]
                        existing.distance = rec["distance"]
                else:
                    session.add(models.Activity(**rec))

            await session.commit()
            logger.info("Cloud: saved %d sleep + %d activity records", len(sleep_records), len(activity_records))
    except Exception as e:
        logger.error("Cloud band_data sync error: %s", e, exc_info=True)

    # Fetch SpO2 events
    try:
        events = await cloud_client.fetch_spo2(from_date, today)
        spo2_records = parse_spo2_events(events)

        if spo2_records:
            async with async_session() as session:
                inserted = 0
                for rec in spo2_records:
                    exists = (
                        await session.execute(
                            select(models.SpO2).where(models.SpO2.timestamp == rec["timestamp"])
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.SpO2(**rec))
                        inserted += 1
                await session.commit()
                logger.info("Cloud: saved %d new SpO2 records", inserted)
    except Exception as e:
        logger.error("Cloud SpO2 sync error: %s", e, exc_info=True)

    # Fetch stress events
    try:
        events = await cloud_client.fetch_stress(from_date, today)
        stress_records = parse_stress_events(events)

        if stress_records:
            async with async_session() as session:
                inserted = 0
                for rec in stress_records:
                    exists = (
                        await session.execute(
                            select(models.Stress).where(models.Stress.timestamp == rec["timestamp"])
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.Stress(**rec))
                        inserted += 1
                await session.commit()
                logger.info("Cloud: saved %d new stress records", inserted)
    except Exception as e:
        logger.error("Cloud stress sync error: %s", e, exc_info=True)

    logger.info("Cloud sync complete")
