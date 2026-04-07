#!/usr/bin/env python3
"""Test script to fetch sleep data directly from the device."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta, timezone
from backend.ble.connection import HelioConnection
from backend.ble.protocol import HelioProtocol
from backend.ble.auth import HuamiAuth
from backend.config import DEVICE_ID, AUTH_KEY_HEX
import backend.config as config

DEVICE = DEVICE_ID
AUTH_KEY = bytes.fromhex(AUTH_KEY_HEX) if AUTH_KEY_HEX else b""

async def main():
    print(f"Device: {DEVICE}")
    print("Connecting...")
    
    conn = HelioConnection()
    connected = await conn.connect()
    if not connected:
        print("Failed to connect")
        return
    
    print("Connected: True")
    
    # Auth
    auth = HuamiAuth(conn._client, AUTH_KEY)
    auth_ok = await auth.authenticate()
    print(f"Auth: {'OK' if auth_ok else 'FAILED'}")
    if not auth_ok:
        await conn.disconnect()
        return
    
    # Create protocol
    proto = HelioProtocol(conn._client)
    
    # Fetch sleep data - try various dates
    print("\n=== Fetching sleep data ===")
    
    # Try fetching from very old date to force fresh data
    test_dates = [
        datetime.now(timezone.utc) - timedelta(days=7),
        datetime.now(timezone.utc) - timedelta(days=14),
        datetime(2026, 4, 1, tzinfo=timezone.utc),  # Before any ACKs
    ]
    
    for since in test_dates:
        print(f"\n--- Trying since: {since.isoformat()} ---")
        try:
            sessions = await proto.fetch_sleep(since)
            print(f"Result: {len(sessions)} session(s)")
            for s in sessions:
                print(f"  {s.date}: {s.total_minutes}min ({s.total_minutes//60}h{s.total_minutes%60:02d}m)")
            if sessions:
                break  # Got data, stop trying
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    await conn.disconnect()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
