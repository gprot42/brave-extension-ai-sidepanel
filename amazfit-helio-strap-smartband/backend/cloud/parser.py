"""Parse Huami cloud API responses into database model objects.

band_data.json returns date-keyed entries with base64-encoded JSON summaries.
Events endpoint returns arrays of event objects with JSON `extra` fields.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def parse_band_data_summary(raw: dict) -> tuple[list[dict], list[dict]]:
    """Parse band_data.json (query_type=summary) into sleep + activity records.

    Returns (sleep_records, activity_records).

    Each entry in raw is keyed by date string, with a "summary" field
    containing a base64-encoded JSON string.
    """
    sleep_records: list[dict] = []
    activity_records: list[dict] = []

    data = raw.get("data", raw)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return sleep_records, activity_records

    # Handle both list-of-dicts and dict-of-dicts formats
    entries = data if isinstance(data, list) else data.values() if isinstance(data, dict) else []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        date_str = entry.get("date_time", entry.get("dateTime", ""))
        summary_raw = entry.get("summary", "")

        if not summary_raw or not date_str:
            continue

        # Decode base64 summary
        try:
            if isinstance(summary_raw, str):
                summary = json.loads(base64.b64decode(summary_raw).decode("utf-8"))
            elif isinstance(summary_raw, dict):
                summary = summary_raw
            else:
                continue
        except Exception as e:
            logger.debug("Failed to decode summary for %s: %s", date_str, e)
            # Try as plain JSON string
            try:
                summary = json.loads(summary_raw)
            except Exception:
                continue

        # Parse sleep
        slp = summary.get("slp", {})
        if slp and isinstance(slp, dict):
            deep = slp.get("dp", 0)
            light = slp.get("lt", 0)
            rem = slp.get("rem", 0)
            awake = slp.get("wk", 0)
            total = deep + light + rem + awake

            if total > 0:
                # Parse sleep stages
                stages = []
                for stage in slp.get("stage", []):
                    mode = stage.get("mode", 0)
                    mode_name = {4: "light", 5: "deep", 7: "awake", 8: "rem"}.get(mode, "unknown")
                    stages.append({
                        "start": stage.get("start", 0),
                        "end": stage.get("end", 0),
                        "mode": mode_name,
                    })

                sleep_records.append({
                    "date": date_str[:10],
                    "total_minutes": total,
                    "deep_minutes": deep,
                    "light_minutes": light,
                    "rem_minutes": rem,
                    "awake_minutes": awake,
                    "stages_json": json.dumps(stages) if stages else None,
                })

        # Parse activity (steps)
        stp = summary.get("stp", {})
        if stp and isinstance(stp, dict):
            steps = stp.get("ttl", 0)
            distance = stp.get("dis", 0)
            calories = stp.get("cal", 0)

            if steps > 0:
                activity_records.append({
                    "date": date_str[:10],
                    "steps": steps,
                    "calories": calories,
                    "distance": distance,
                })

    logger.info("Parsed %d sleep + %d activity records from cloud",
                len(sleep_records), len(activity_records))
    return sleep_records, activity_records


def parse_spo2_events(events: list[dict]) -> list[dict]:
    """Parse SpO2 events into {timestamp, value} records."""
    records: list[dict] = []

    for event in events:
        ts_ms = event.get("timestamp", 0)
        extra_str = event.get("extra", "{}")

        try:
            extra = json.loads(extra_str) if isinstance(extra_str, str) else extra_str
        except (json.JSONDecodeError, ValueError):
            continue

        spo2_val = extra.get("spo2", 0)
        if spo2_val and ts_ms:
            records.append({
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "value": int(spo2_val),
            })

    logger.info("Parsed %d SpO2 records from cloud", len(records))
    return records


def parse_stress_events(events: list[dict]) -> list[dict]:
    """Parse stress events into {timestamp, level} records."""
    records: list[dict] = []

    for event in events:
        ts_ms = event.get("timestamp", 0)
        extra_str = event.get("extra", "{}")

        try:
            extra = json.loads(extra_str) if isinstance(extra_str, str) else extra_str
        except (json.JSONDecodeError, ValueError):
            continue

        stress_level = extra.get("stress_level", extra.get("score", 0))
        if stress_level and ts_ms:
            records.append({
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "level": int(float(stress_level)),
            })

    logger.info("Parsed %d stress records from cloud", len(records))
    return records
