"""REST API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import Response
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import PERIODIC_SYNC_INTERVAL, set_auth_key
import backend.config as config
from backend.data.database import get_session, async_session
from backend.data import models
from backend.data.sync import (
    run_sync, start_realtime_hr, start_sensor_stream, periodic_sync_loop,
    init_cloud_client, cloud_login, run_cloud_sync,
)
from backend.cloud.huami_client import client as cloud_client
from backend.ble.connection import connection, ConnectionState
from backend.ble.scanner import scan_for_helio

router = APIRouter()
_sync_task: asyncio.Task | None = None


def _utc_iso(dt: datetime) -> str:
    """Format a naive-UTC datetime as ISO 8601 with Z suffix."""
    return dt.isoformat() + "Z"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s)


# ── Device ─────────────────────────────────────────────────

@router.get("/device")
async def get_device(session: AsyncSession = Depends(get_session)):
    info = (await session.execute(select(models.DeviceInfo))).scalar_one_or_none()
    return {
        "state": connection.state.name,
        "battery_level": info.battery_level if info else None,
        "firmware_version": info.firmware_version if info else None,
        "last_sync": info.last_sync.isoformat() if info and info.last_sync else None,
        "has_auth": bool(config.AUTH_KEY_HEX),
        "device_id": config.DEVICE_ID or None,
        "error_message": connection.error_message,
    }


@router.post("/auth-key")
async def set_auth_key_endpoint(key: str = Query(...)):
    key = key.strip()
    if len(key) != 32:
        raise HTTPException(status_code=400, detail="Auth key must be exactly 32 hex characters")
    try:
        bytes.fromhex(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Auth key must be valid hexadecimal")
    set_auth_key(key)
    return {"status": "ok", "has_auth": True}


@router.get("/auth-key")
async def get_auth_key_endpoint():
    if not config.AUTH_KEY_HEX:
        return {"key": None}
    return {"key": config.AUTH_KEY_HEX}


@router.get("/scan")
async def scan_devices():
    devices = await scan_for_helio(timeout=8.0)
    return [{"name": d.name, "address": d.address, "rssi": d.rssi} for d in devices]


@router.get("/device-config/spo2-auto")
async def get_spo2_auto():
    """Get current auto SpO2 setting from device."""
    if not connection.is_connected or not connection.config:
        raise HTTPException(status_code=400, detail="Device not connected")
    if not connection.is_zepp_authenticated:
        raise HTTPException(status_code=400, detail="ECDH auth required")
    val = await connection.config.get_spo2_auto()
    return {"enabled": val}


@router.post("/device-config/spo2-auto")
async def set_spo2_auto(enabled: bool = Query(...)):
    """Enable or disable auto SpO2 measurement on the device."""
    if not connection.is_connected or not connection.config:
        raise HTTPException(status_code=400, detail="Device not connected")
    if not connection.is_zepp_authenticated:
        raise HTTPException(status_code=400, detail="ECDH auth required")
    ok = await connection.config.set_spo2_auto(enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="Device rejected config change")
    return {"status": "ok", "enabled": enabled}


@router.post("/connect")
async def connect_device(device_id: Optional[str] = Query(None)):
    global _sync_task
    try:
        # Cache device ID if provided (from scan result)
        if device_id:
            config.set_device_id(device_id)
        await connection.connect(device_id=device_id)
        await start_realtime_hr()
        await start_sensor_stream()
        # Delay sync so HR stream establishes first (device can't do both)
        async def _delayed_sync():
            await asyncio.sleep(5)
            await run_sync()
        asyncio.create_task(_delayed_sync())
        if _sync_task is None or _sync_task.done():
            _sync_task = asyncio.create_task(
                periodic_sync_loop(interval=PERIODIC_SYNC_INTERVAL)
            )
        return {"status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_device():
    await connection.disconnect()
    return {"status": "disconnected"}


@router.post("/sync")
async def trigger_sync():
    if not connection.is_connected:
        raise HTTPException(status_code=409, detail="Not connected")
    await run_sync()
    return {
        "status": "sync_complete",
        "ecdh_authenticated": connection.is_zepp_authenticated,
        "note": "Device only sends new data once per session. After Reset Data, historical data cannot be re-fetched."
    }


# ── Heart Rate ─────────────────────────────────────────────

@router.get("/hr")
async def get_hr(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(500, le=5000),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.HeartRate).order_by(desc(models.HeartRate.timestamp)).limit(limit)
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if start_dt:
        q = q.where(models.HeartRate.timestamp >= start_dt)
    if end_dt:
        q = q.where(models.HeartRate.timestamp <= end_dt)

    rows = (await session.execute(q)).scalars().all()
    return [{"timestamp": _utc_iso(r.timestamp), "bpm": r.bpm} for r in rows]


@router.get("/hr-stats")
async def get_hr_stats(
    session: AsyncSession = Depends(get_session),
):
    """Return HR stats: average, min, max, and sleep resting heart rate."""
    from sqlalchemy import func
    from datetime import timedelta

    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    # 24h stats
    q = select(
        func.avg(models.HeartRate.bpm),
        func.min(models.HeartRate.bpm),
        func.max(models.HeartRate.bpm),
        func.count(models.HeartRate.bpm),
    ).where(models.HeartRate.timestamp >= day_ago)
    row = (await session.execute(q)).one()
    avg_bpm, min_bpm, max_bpm, count = row

    # Sleep RHR: find most recent sleep session, get HR during deep+light+rem stages
    sleep_rhr = None
    sleep_q = select(models.Sleep).order_by(desc(models.Sleep.date)).limit(1)
    sleep_row = (await session.execute(sleep_q)).scalars().first()
    if sleep_row and sleep_row.stages_json:
        sleep_stages = json.loads(sleep_row.stages_json)
        # Collect all non-awake sleep periods
        sleep_periods = [
            (s["start"], s["end"])
            for s in sleep_stages
            if s.get("stage") in ("deep", "light", "rem")
        ]
        if sleep_periods:
            # Get HR readings during sleep periods
            sleep_hrs = []
            for start_iso, end_iso in sleep_periods:
                sq = select(models.HeartRate.bpm).where(
                    models.HeartRate.timestamp >= start_iso,
                    models.HeartRate.timestamp <= end_iso,
                )
                rows = (await session.execute(sq)).scalars().all()
                sleep_hrs.extend(rows)
            if sleep_hrs:
                # RHR = lowest 10th percentile average during sleep
                sleep_hrs.sort()
                p10_count = max(len(sleep_hrs) // 10, 1)
                sleep_rhr = round(sum(sleep_hrs[:p10_count]) / p10_count)

    return {
        "avg": round(avg_bpm) if avg_bpm else None,
        "min": min_bpm,
        "max": max_bpm,
        "count": count,
        "sleep_rhr": sleep_rhr,
        "period": "24h",
    }


# ── Sleep ──────────────────────────────────────────────────

@router.get("/sleep")
async def get_sleep(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(30, le=365),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.Sleep).order_by(desc(models.Sleep.date)).limit(limit)
    if start:
        q = q.where(models.Sleep.date >= start)
    if end:
        q = q.where(models.Sleep.date <= end)

    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "date": r.date,
            "total_minutes": r.total_minutes,
            "deep_minutes": r.deep_minutes,
            "light_minutes": r.light_minutes,
            "rem_minutes": r.rem_minutes,
            "awake_minutes": r.awake_minutes,
            "stages": json.loads(r.stages_json) if r.stages_json else [],
        }
        for r in rows
    ]


# ── SpO2 ───────────────────────────────────────────────────

@router.get("/spo2")
async def get_spo2(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(500, le=5000),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.SpO2).order_by(desc(models.SpO2.timestamp)).limit(limit)
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if start_dt:
        q = q.where(models.SpO2.timestamp >= start_dt)
    if end_dt:
        q = q.where(models.SpO2.timestamp <= end_dt)

    rows = (await session.execute(q)).scalars().all()
    return [{"timestamp": _utc_iso(r.timestamp), "value": r.value} for r in rows]


# ── Stress ─────────────────────────────────────────────────

@router.get("/stress")
async def get_stress(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(500, le=5000),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.Stress).order_by(desc(models.Stress.timestamp)).limit(limit)
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if start_dt:
        q = q.where(models.Stress.timestamp >= start_dt)
    if end_dt:
        q = q.where(models.Stress.timestamp <= end_dt)

    rows = (await session.execute(q)).scalars().all()
    return [{"timestamp": _utc_iso(r.timestamp), "level": r.level} for r in rows]


# ── HRV ────────────────────────────────────────────────────

@router.get("/hrv")
async def get_hrv(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(500, le=5000),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.HRV).order_by(desc(models.HRV.timestamp)).limit(limit)
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if start_dt:
        q = q.where(models.HRV.timestamp >= start_dt)
    if end_dt:
        q = q.where(models.HRV.timestamp <= end_dt)

    rows = (await session.execute(q)).scalars().all()
    return [
        {"timestamp": _utc_iso(r.timestamp), "rmssd": r.rmssd, "sdnn": r.sdnn}
        for r in rows
    ]


# ── Activity ───────────────────────────────────────────────

@router.get("/activity")
async def get_activity(
    start: Optional[str] = Query(None, alias="from"),
    end: Optional[str] = Query(None, alias="to"),
    limit: int = Query(30, le=365),
    session: AsyncSession = Depends(get_session),
):
    q = select(models.Activity).order_by(desc(models.Activity.date)).limit(limit)
    if start:
        q = q.where(models.Activity.date >= start)
    if end:
        q = q.where(models.Activity.date <= end)

    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "date": r.date,
            "steps": r.steps,
            "calories": r.calories,
            "distance": r.distance,
        }
        for r in rows
    ]


# ── Cloud API ──────────────────────────────────────────────

@router.get("/cloud-status")
async def cloud_status():
    return {
        "logged_in": cloud_client.is_logged_in,
        "userid": cloud_client.userid or None,
        "region": cloud_client.region,
        "has_credentials": bool(config.ZEPP_EMAIL and config.ZEPP_PASSWORD),
        "login_retrying": _cloud_login_task is not None and not _cloud_login_task.done(),
    }


_cloud_login_task: asyncio.Task | None = None


async def _background_cloud_login(email: str, password: str):
    """Retry cloud login with exponential backoff."""
    delays = [60, 120, 300, 600, 1800, 3600]  # 1m, 2m, 5m, 10m, 30m, 1h
    log = logging.getLogger(__name__)
    for i, delay in enumerate(delays):
        log.info("Cloud login retry %d/%d in %ds...", i + 1, len(delays), delay)
        await asyncio.sleep(delay)
        try:
            await cloud_login(email, password)
            log.info("Background cloud login succeeded!")
            return
        except ValueError as e:
            if "Rate limited" not in str(e):
                log.error("Cloud login failed (not rate-limit): %s", e)
                return
            log.info("Still rate limited, will retry...")
        except Exception as e:
            log.error("Cloud login error: %s", e)
            return
    log.error("Cloud login: all retries exhausted")


@router.post("/cloud-login")
async def cloud_login_endpoint(
    payload: dict = Body(...),
):
    global _cloud_login_task
    email = payload.get("email", "")
    password = payload.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    try:
        apptoken, userid = await cloud_login(email, password)
        return {"status": "ok", "userid": userid}
    except ValueError as e:
        msg = str(e)
        if "Rate limited" in msg:
            # Schedule background retries
            if _cloud_login_task is None or _cloud_login_task.done():
                _cloud_login_task = asyncio.create_task(
                    _background_cloud_login(email, password)
                )
            raise HTTPException(
                status_code=429,
                detail="Rate limited by Huami API. Login will retry automatically in the background — check back in a few minutes.",
            )
        raise HTTPException(status_code=401, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cloud-sync")
async def trigger_cloud_sync(days: int = Query(7, le=30)):
    if not cloud_client.is_logged_in:
        raise HTTPException(status_code=409, detail="Not logged in to Zepp cloud")
    await run_cloud_sync(days=days)
    return {"status": "cloud_sync_complete"}


# ── Export ─────────────────────────────────────────────────

@router.get("/export")
async def export_all_health_data(
    days: int = Query(30, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Export all health data as a single JSON file suitable for LLM analysis."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Heart rate
    hr_rows = (await session.execute(
        select(models.HeartRate)
        .where(models.HeartRate.timestamp >= cutoff)
        .order_by(models.HeartRate.timestamp)
    )).scalars().all()
    hr_data = [{"timestamp": _utc_iso(r.timestamp), "bpm": r.bpm} for r in hr_rows]

    # SpO2
    spo2_rows = (await session.execute(
        select(models.SpO2)
        .where(models.SpO2.timestamp >= cutoff)
        .order_by(models.SpO2.timestamp)
    )).scalars().all()
    spo2_data = [{"timestamp": _utc_iso(r.timestamp), "value": r.value} for r in spo2_rows]

    # Sleep
    sleep_rows = (await session.execute(
        select(models.Sleep)
        .where(models.Sleep.date >= cutoff_str)
        .order_by(models.Sleep.date)
    )).scalars().all()
    sleep_data = [
        {
            "date": r.date,
            "total_minutes": r.total_minutes,
            "deep_minutes": r.deep_minutes,
            "light_minutes": r.light_minutes,
            "rem_minutes": r.rem_minutes,
            "awake_minutes": r.awake_minutes,
            "stages": json.loads(r.stages_json) if r.stages_json else None,
        }
        for r in sleep_rows
    ]

    # Stress
    stress_rows = (await session.execute(
        select(models.Stress)
        .where(models.Stress.timestamp >= cutoff)
        .order_by(models.Stress.timestamp)
    )).scalars().all()
    stress_data = [{"timestamp": _utc_iso(r.timestamp), "level": r.level} for r in stress_rows]

    # HRV
    hrv_rows = (await session.execute(
        select(models.HRV)
        .where(models.HRV.timestamp >= cutoff)
        .order_by(models.HRV.timestamp)
    )).scalars().all()
    hrv_data = [{"timestamp": _utc_iso(r.timestamp), "rmssd": r.rmssd} for r in hrv_rows]

    # Activity
    activity_rows = (await session.execute(
        select(models.Activity)
        .where(models.Activity.date >= cutoff_str)
        .order_by(models.Activity.date)
    )).scalars().all()
    activity_data = [
        {
            "date": r.date,
            "steps": r.steps,
            "calories": r.calories,
            "distance": r.distance,
        }
        for r in activity_rows
    ]

    export = {
        "export_date": datetime.utcnow().isoformat() + "Z",
        "period_days": days,
        "summary": {
            "heart_rate_readings": len(hr_data),
            "spo2_readings": len(spo2_data),
            "sleep_sessions": len(sleep_data),
            "stress_readings": len(stress_data),
            "hrv_readings": len(hrv_data),
            "activity_days": len(activity_data),
        },
        "heart_rate": hr_data,
        "spo2": spo2_data,
        "sleep": sleep_data,
        "stress": stress_data,
        "hrv": hrv_data,
        "activity": activity_data,
    }

    content = json.dumps(export, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=health_export_{days}d.json"
        },
    )


@router.post("/reset-data")
async def reset_all_data():
    """Delete all health data from the database and reset in-memory counters."""
    for attempt in range(3):
        try:
            async with async_session() as session:
                for table in ["heart_rate", "sleep", "spo2", "stress", "hrv", "activity"]:
                    await session.execute(text(f"DELETE FROM {table}"))
                await session.commit()
            # Reset in-memory step/calorie counters
            if connection.protocol:
                connection.protocol.reset_counters()
            # Reclaim disk space
            async with async_session() as session:
                await session.execute(text("VACUUM"))
            logger.info("All health data reset")
            return {"status": "ok", "message": "All health data deleted"}
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1)
                continue
            logger.error("Reset data failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Reset failed (DB may be busy during sync): {e}")
