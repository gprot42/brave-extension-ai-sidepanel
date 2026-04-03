"""Sync orchestrator — manages real-time HR streaming, sensor stream, periodic data fetch,
and Zepp cloud API sync for sleep, stress, and SpO2 data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, func, text

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


async def _on_hr_reading(reading: HRReading):
    """Called for each real-time HR reading: persist + broadcast."""
    try:
        async with async_session() as session:
            session.add(models.HeartRate(timestamp=reading.timestamp, bpm=reading.bpm))
            await session.commit()
    except Exception as e:
        logger.error("HR DB write error: %s", e)
        return

    payload = json.dumps(
        {"timestamp": reading.timestamp.isoformat(), "bpm": reading.bpm}
    )
    dead: list[int] = []
    for i, send_fn in enumerate(hr_subscribers):
        try:
            await send_fn(payload)
        except Exception:
            dead.append(i)
    for i in reversed(dead):
        hr_subscribers.pop(i)


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


_hr_callback_registered = False

async def start_realtime_hr():
    """Start streaming HR from device."""
    global _hr_callback_registered
    proto = connection.protocol
    if proto is None:
        logger.warning("Cannot start HR stream — not connected")
        return
    if not _hr_callback_registered:
        proto.on_hr(_on_hr_reading)
        _hr_callback_registered = True
    await proto.start_realtime_hr()


async def _on_sensor_activity(steps: int, calories: int):
    """Called by sensor stream when steps/calories change.
    
    Only persists calories — sensor stream step count is stale on this
    device. Real step data comes from the activity fetch (type 0x01).
    """
    await _on_activity_update(0, calories)


_activity_callback_registered = False

async def start_sensor_stream():
    """Start sensor stream for real-time steps/calories."""
    global _activity_callback_registered
    proto = connection.protocol
    if proto is None:
        logger.warning("Cannot start sensor stream — not connected")
        return
    if not _activity_callback_registered:
        proto.on_activity(_on_sensor_activity)
        _activity_callback_registered = True
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

    # Battery (always works, no auth needed)
    try:
        battery = await proto.read_battery()
        async with async_session() as session:
            info = (await session.execute(select(models.DeviceInfo))).scalar_one_or_none()
            if info:
                info.battery_level = battery
                info.last_sync = datetime.now(timezone.utc)
            else:
                session.add(
                    models.DeviceInfo(
                        battery_level=battery,
                        last_sync=datetime.now(timezone.utc),
                    )
                )
            await session.commit()
        logger.info("Battery: %d%%", battery)
    except Exception as e:
        logger.error("Battery sync error: %s", e)

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
                    existing_ts = {row[0] for row in result}

                for r in readings:
                    if r.timestamp not in existing_ts:
                        session.add(models.HeartRate(timestamp=r.timestamp, bpm=r.bpm))
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

    logger.info("Sync complete")

    # Let BLE settle after data fetches, then re-enable HR
    await asyncio.sleep(1)
    try:
        await proto.enable_hr_measurement()
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
        sessions_data = await proto.fetch_sleep(since)
        if sessions_data:
            import json
            async with async_session() as session:
                for s in sessions_data:
                    exists = (
                        await session.execute(
                            select(models.Sleep).where(models.Sleep.date == s.date)
                        )
                    ).scalar_one_or_none()
                    stages_str = json.dumps(s.stages) if s.stages else None
                    if not exists:
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

    # Activity
    try:
        activities = await proto.fetch_activity(since)
        if activities:
            async with async_session() as session:
                for a in activities:
                    exists = (
                        await session.execute(
                            select(models.Activity).where(models.Activity.date == a.date)
                        )
                    ).scalar_one_or_none()
                    if not exists:
                        session.add(models.Activity(
                            date=a.date, steps=a.steps,
                            calories=a.calories, distance=a.distance
                        ))
                    else:
                        exists.steps = max(a.steps, exists.steps)
                        if a.calories > 0:
                            exists.calories = a.calories
                        if a.distance > 0:
                            exists.distance = a.distance
                await session.commit()
                logger.info("BLE Activity: saved %d day records", len(activities))
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
