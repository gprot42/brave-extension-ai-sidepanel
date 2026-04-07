"""REST API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
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
    await connection.config.start()
    try:
        val = await connection.config.get_spo2_auto()
    finally:
        await connection.config.stop()
    return {"enabled": val}


@router.post("/device-config/spo2-auto")
async def set_spo2_auto(enabled: bool = Query(...)):
    """Enable or disable auto SpO2 measurement on the device."""
    if not connection.is_connected or not connection.config:
        raise HTTPException(status_code=400, detail="Device not connected")
    if not connection.is_zepp_authenticated:
        raise HTTPException(status_code=400, detail="ECDH auth required")
    await connection.config.start()
    try:
        ok = await connection.config.set_spo2_auto(enabled)
    finally:
        await connection.config.stop()
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
        # Run sync shortly after connect so activity/health data appears immediately
        async def _initial_sync():
            await asyncio.sleep(2)
            await run_sync()
        asyncio.create_task(_initial_sync())
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

    # Get timestamps for min and max readings
    min_ts = None
    max_ts = None
    if min_bpm is not None:
        min_row = (await session.execute(
            select(models.HeartRate.timestamp)
            .where(models.HeartRate.timestamp >= day_ago, models.HeartRate.bpm == min_bpm)
            .order_by(models.HeartRate.timestamp.desc()).limit(1)
        )).scalar_one_or_none()
        if min_row:
            min_ts = _utc_iso(min_row)
    if max_bpm is not None:
        max_row = (await session.execute(
            select(models.HeartRate.timestamp)
            .where(models.HeartRate.timestamp >= day_ago, models.HeartRate.bpm == max_bpm)
            .order_by(models.HeartRate.timestamp.desc()).limit(1)
        )).scalar_one_or_none()
        if max_row:
            max_ts = _utc_iso(max_row)

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
        "min_ts": min_ts,
        "max_ts": max_ts,
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


# ── AI Analysis (MedGemma via Ollama) ────────────────────

@router.get("/ai-models")
async def list_ai_models(
    ollama_url: str = "http://localhost:11434",
    provider: str = "ollama"
):
    """List available models from Ollama or LM Studio."""
    import httpx
    url = ollama_url.rstrip("/")
    
    # LM Studio uses OpenAI-compatible /v1/models endpoint
    if provider == "lmstudio":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models_list = [m.get("id", m.get("name", "unknown")) for m in data.get("data", [])]
                    return {"models": models_list, "status": "ok", "provider": "lmstudio"}
                return {"models": [], "status": "error", "detail": f"LM Studio at {url} returned {resp.status_code}"}
        except httpx.ConnectError:
            return {"models": [], "status": "offline", "detail": f"Cannot connect to LM Studio at {url}"}
        except Exception as e:
            return {"models": [], "status": "error", "detail": str(e)}
    
    # Default: Ollama native API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models_list = [m["name"] for m in data.get("models", [])]
                return {"models": models_list, "status": "ok", "provider": "ollama"}
            logger.warning("ai-models: %s/api/tags returned %d", url, resp.status_code)
            return {"models": [], "status": "error", "detail": f"Ollama at {url} returned {resp.status_code}"}
    except httpx.ConnectError:
        return {"models": [], "status": "offline", "detail": f"Cannot connect to Ollama at {url}"}
    except Exception as e:
        return {"models": [], "status": "error", "detail": str(e)}


@router.post("/ai-analysis")
async def ai_analysis(
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Send health data + user prompt to a local LLM via Ollama or LM Studio for analysis."""
    import httpx

    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    days = body.get("days", 7)
    model = body.get("model", "qwen3.5:35b-a3b")
    ollama_url = body.get("ollama_url", "http://localhost:11434").rstrip("/")
    provider = body.get("provider", "ollama")

    logger.info("AI analysis: provider=%s model=%s, days=%d, url=%s, prompt=%s",
                provider, model, days, ollama_url, prompt[:80])

    # Step 1: Verify backend is reachable
    if provider == "lmstudio":
        health_url = f"{ollama_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(health_url)
                if resp.status_code != 200:
                    raise HTTPException(status_code=503,
                        detail=f"LM Studio at {ollama_url} returned HTTP {resp.status_code}. "
                               f"Check the URL in Settings (default: http://localhost:1234)")
                available = [m.get("id", m.get("name", "")) for m in resp.json().get("data", [])]
                if model not in available and available:
                    logger.warning("AI: model '%s' not in available list: %s", model, available)
        except httpx.ConnectError:
            raise HTTPException(status_code=503,
                detail=f"Cannot connect to LM Studio at {ollama_url}. "
                       f"Start LM Studio and ensure the server is running on port 1234.")
    else:
        # Ollama
        health_url = f"{ollama_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                tag_resp = await client.get(health_url)
                if tag_resp.status_code != 200:
                    logger.error("AI: Ollama health check %s returned %d: %s",
                                 health_url, tag_resp.status_code, tag_resp.text[:200])
                    raise HTTPException(status_code=503,
                        detail=f"Ollama at {ollama_url} returned HTTP {tag_resp.status_code}. "
                               f"Check the Ollama URL in Settings (default: http://localhost:11434)")
                available = [m["name"] for m in tag_resp.json().get("models", [])]
                if model not in available:
                    logger.error("AI: model '%s' not found. Available: %s", model, available)
                    raise HTTPException(status_code=400,
                        detail=f"Model '{model}' not installed. Available: {available}. "
                               f"Run: ollama pull {model}")
        except httpx.ConnectError:
            logger.error("AI: cannot connect to Ollama at %s", ollama_url)
            raise HTTPException(status_code=503,
                detail=f"Cannot connect to Ollama at {ollama_url}. "
                       f"Start it with: ollama serve")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("AI: Ollama health check failed (%s): %s", health_url, e)
            raise HTTPException(status_code=503,
                detail=f"Ollama health check failed at {ollama_url}: {e}")

    # Step 2: Build health data context
    try:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        from sqlalchemy import func
        hr_stats = (await session.execute(
            select(
                func.count(models.HeartRate.bpm),
                func.avg(models.HeartRate.bpm),
                func.min(models.HeartRate.bpm),
                func.max(models.HeartRate.bpm),
            ).where(models.HeartRate.timestamp >= cutoff)
        )).one()

        spo2_rows = (await session.execute(
            select(models.SpO2).where(models.SpO2.timestamp >= cutoff).order_by(models.SpO2.timestamp)
        )).scalars().all()
        # SpO2: aggregate to stats + last 5 readings (individual readings are too verbose for LLM context)
        if spo2_rows:
            spo2_vals = [r.value for r in spo2_rows]
            spo2_data = {
                "count": len(spo2_vals),
                "avg": round(sum(spo2_vals) / len(spo2_vals), 1),
                "min": min(spo2_vals),
                "max": max(spo2_vals),
                "recent": [{"ts": _utc_iso(r.timestamp), "val": r.value} for r in spo2_rows[-5:]],
            }
        else:
            spo2_data = {"count": 0}

        sleep_rows = (await session.execute(
            select(models.Sleep).where(models.Sleep.date >= cutoff_str).order_by(models.Sleep.date)
        )).scalars().all()
        sleep_data = [
            {"date": r.date, "total": r.total_minutes, "deep": r.deep_minutes,
             "light": r.light_minutes, "rem": r.rem_minutes, "awake": r.awake_minutes}
            for r in sleep_rows
        ]

        stress_stats = (await session.execute(
            select(
                func.count(models.Stress.level),
                func.avg(models.Stress.level),
                func.min(models.Stress.level),
                func.max(models.Stress.level),
            ).where(models.Stress.timestamp >= cutoff)
        )).one()
        stress_data = {
            "count": stress_stats[0],
            "avg_level": round(stress_stats[1], 1) if stress_stats[1] else None,
            "min_level": stress_stats[2],
            "max_level": stress_stats[3],
        }

        hrv_stats = (await session.execute(
            select(
                func.count(models.HRV.rmssd),
                func.avg(models.HRV.rmssd),
                func.min(models.HRV.rmssd),
                func.max(models.HRV.rmssd),
            ).where(models.HRV.timestamp >= cutoff)
        )).one()
        hrv_data = {
            "count": hrv_stats[0],
            "avg_rmssd": round(hrv_stats[1], 1) if hrv_stats[1] else None,
            "min_rmssd": hrv_stats[2],
            "max_rmssd": hrv_stats[3],
        }

        activity_rows = (await session.execute(
            select(models.Activity).where(models.Activity.date >= cutoff_str).order_by(models.Activity.date)
        )).scalars().all()
        activity_data = [
            {"date": r.date, "steps": r.steps, "cal": r.calories}
            for r in activity_rows
        ]

        health_context = json.dumps({
            "period": f"Last {days} days",
            "heart_rate": {
                "count": hr_stats[0],
                "avg_bpm": round(hr_stats[1], 1) if hr_stats[1] else None,
                "min_bpm": hr_stats[2],
                "max_bpm": hr_stats[3],
            },
            "spo2": spo2_data,
            "sleep": sleep_data[-14:],      # cap at 14 most recent nights
            "stress": stress_data,
            "hrv": hrv_data,
            "activity": activity_data[-14:],  # cap at 14 most recent days
        }, separators=(',', ':'))  # compact: no whitespace to minimise token count

        logger.info("AI: health context built (%d chars / ~%d tokens, HR=%d, SpO2=%d, Sleep=%d, Stress=%d, HRV=%d, Activity=%d)",
                     len(health_context), len(health_context) // 3,
                     hr_stats[0], len(spo2_rows), len(sleep_data),
                     stress_data["count"], hrv_data["count"], len(activity_data))
    except Exception as e:
        logger.error("AI: failed to build health context: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to query health data: {e}")

    system_prompt = (
        "You are a health data assistant analyzing wearable data from an Amazfit Helio Strap. "
        "Provide concise insights. Always note you are not a doctor and advise consulting a healthcare professional.\n\n"
        f"HEALTH DATA (JSON):\n{health_context}"
    )

    # Step 3: Call LLM API (300s timeout for large/slow models)
    try:
        if provider == "lmstudio":
            # LM Studio uses OpenAI-compatible /v1/chat/completions
            logger.info("AI: sending to LM Studio model=%s, prompt_len=%d, context_len=%d",
                         model, len(prompt), len(system_prompt))
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{ollama_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "max_tokens": 2048,
                    },
                )
                if resp.status_code != 200:
                    error_text = resp.text[:600]
                    logger.error("AI: LM Studio returned %d: %s", resp.status_code, error_text)
                    # 400 with n_keep/n_ctx means context overflow — give a clear message
                    if resp.status_code == 400 and "n_ctx" in error_text:
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                f"Model context window too small for the requested data range. "
                                f"Try reducing the day range (e.g. 7 days instead of {days}), "
                                f"or load the model with a larger context in LM Studio. "
                                f"(LM Studio: {error_text[:200]})"
                            )
                        )
                    raise HTTPException(
                        status_code=502,
                        detail=f"LM Studio returned {resp.status_code}: {error_text}"
                    )
                result = resp.json()
                answer = result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                if not answer.strip():
                    logger.warning("AI: empty response from LM Studio. Raw keys: %s", list(result.keys()))
                    answer = "The model returned an empty response. Try a more specific question."
                logger.info("AI: response received (%d chars)", len(answer))
        else:
            # Ollama native API
            logger.info("AI: sending to Ollama model=%s, prompt_len=%d, context_len=%d",
                         model, len(prompt), len(system_prompt))
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "think": False,
                        "options": {
                            "num_predict": 2048,
                        },
                    },
                )
                if resp.status_code != 200:
                    error_text = resp.text[:500]
                    logger.error("AI: Ollama returned %d: %s", resp.status_code, error_text)
                    raise HTTPException(
                        status_code=502,
                        detail=f"Ollama returned {resp.status_code}: {error_text}"
                    )
                result = resp.json()
                answer = result.get("message", {}).get("content", "") or ""
                # Some reasoning models put output in 'thinking' field instead of 'content'
                if not answer.strip():
                    thinking = result.get("message", {}).get("thinking", "")
                    if thinking:
                        answer = thinking
                        logger.info("AI: model returned thinking output instead of content")
                if not answer.strip():
                    logger.warning("AI: empty response from model. Raw keys: %s",
                                   list(result.get("message", {}).keys()))
                    answer = "The model returned an empty response. This can happen with reasoning models. Try a more specific question."
                eval_duration = result.get("eval_duration", 0)
                logger.info("AI: response received (%d chars, eval=%.1fs)",
                             len(answer), eval_duration / 1e9 if eval_duration else 0)
        
        return {
            "answer": answer,
            "model": model,
            "provider": provider,
            "data_summary": {
                "hr_readings": hr_stats[0],
                "spo2_readings": len(spo2_data),
                "sleep_sessions": len(sleep_data),
                "stress_readings": stress_data.get("count", 0),
                "hrv_readings": hrv_data.get("count", 0),
                "activity_days": len(activity_data),
            },
        }
    except httpx.ConnectError:
        logger.error("AI: connection refused at %s", ollama_url)
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to {provider} at {ollama_url}. "
                   f"{'Start LM Studio and ensure the server is running.' if provider == 'lmstudio' else 'Start it with: ollama serve'}"
        )
    except httpx.TimeoutException:
        logger.error("AI: request timed out after 300s (model=%s)", model)
        raise HTTPException(
            status_code=504,
            detail=f"{provider} request timed out (300s). The model may be loading or too slow for this prompt."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI: unexpected error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI analysis error: {e}")
