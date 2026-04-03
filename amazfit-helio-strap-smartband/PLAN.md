# Amazfit Helio Strap: Direct BLE Data Extraction + FastAPI Backend + React Dashboard

## Objective

Build a Python program that connects directly to the Amazfit Helio Strap via BLE (using `bleak`), authenticates using the Huami/Zepp OS protocol (referencing Gadgetbridge's reverse-engineered implementation), extracts all sensor data, stores it in SQLite, and displays it via a FastAPI + React/TypeScript web dashboard with real-time HR streaming and periodic sync for other metrics.

## Architecture

```
Helio Strap (BLE 5.2 / Zepp OS)
        │
        │ GATT
        ▼
Python BLE Client (bleak)
        │
        ├── Huami Auth (AES-128)
        ├── Data Sync Manager
        │       ├── Real-time: HR notifications → WebSocket
        │       └── Periodic: Sleep, SpO2, Stress, HRV, Activity
        ▼
    SQLite DB
        │
        ▼
  FastAPI (REST + WebSocket)
        │
        ▼
  React/TypeScript Dashboard (Vite + Tailwind + Recharts)
```

## Project Structure

```
amazfit-helio-strap-smartband/
├── backend/
│   ├── ble/
│   │   ├── __init__.py
│   │   ├── scanner.py          # BLE device discovery
│   │   ├── auth.py             # Huami auth protocol (AES-128 challenge-response)
│   │   ├── connection.py       # Connection lifecycle manager
│   │   └── protocol.py         # Zepp OS GATT service/characteristic handlers
│   ├── data/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy models for all sensor data
│   │   ├── database.py         # SQLite setup, session management
│   │   └── sync.py             # Periodic sync orchestrator
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app, CORS, lifespan
│   │   ├── routes.py           # REST endpoints
│   │   └── websocket.py        # WebSocket for real-time HR
│   ├── config.py               # Auth key, device MAC, sync intervals
│   ├── requirements.txt
│   └── run.py                  # Entry point
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── RealtimeHR.tsx
│   │   │   ├── SleepChart.tsx
│   │   │   ├── SpO2Chart.tsx
│   │   │   ├── StressChart.tsx
│   │   │   ├── ActivitySummary.tsx
│   │   │   ├── HRVChart.tsx
│   │   │   └── DeviceStatus.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useHealthData.ts
│   │   ├── types.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── PLAN.md
└── README.md
```

## Implementation Steps

### Step 1: BLE Discovery & Authentication

- Scan for Helio Strap by Huami service UUID `0000fee0-0000-1000-8000-00805f9b34fb`
- Implement Huami 3-step auth:
  1. Write `[0x01, 0x00]` + auth key (16 bytes) to Auth characteristic
  2. Wait for `[0x10, 0x01, 0x01]` (key accepted)
  3. Encrypt challenge with AES-128-ECB, write `[0x03, 0x00]` + encrypted response
  4. Wait for `[0x10, 0x03, 0x01]` (auth success)
- Auth key must be extracted once via Zepp app + Huami token helper

### Step 2: GATT Protocol Handlers

- Heart Rate: Standard BLE HR Service `0x180D` char `0x2A37` + Huami continuous mode
- Activity (steps, calories): Huami activity fetch protocol
- Sleep: Activity fetch type `0x07`
- SpO2, Stress, HRV: Huami extended characteristics
- Battery: Standard Battery Service `0x180F`

### Step 3: Data Models & Storage (SQLite)

Tables: HeartRate, Sleep, SpO2, Stress, HRV, Activity, DeviceInfo

### Step 4: Sync Manager

- Real-time: HR characteristic notifications → WebSocket + DB
- Periodic (5 min default): Sleep, SpO2, stress, HRV, activity

### Step 5: FastAPI Backend

- REST: /api/device, /api/hr, /api/sleep, /api/spo2, /api/stress, /api/hrv, /api/activity
- WebSocket: ws://localhost:8000/ws/hr
- Manual sync/connect/disconnect endpoints

### Step 6: React Frontend

- Dashboard with real-time HR chart, sleep stages, SpO2, stress, HRV, activity summary
- Vite + React + TypeScript + Tailwind CSS + Recharts

## Key Dependencies

| Component | Package |
|-----------|---------|
| BLE | `bleak` |
| Crypto | `pycryptodome` |
| Backend | `fastapi`, `uvicorn` |
| ORM | `sqlalchemy`, `aiosqlite` |
| Frontend | `react`, `vite`, `tailwindcss`, `recharts` |

## Constraints & Risks

- Auth key requires one-time pairing via Zepp app + extraction
- macOS BLE uses CoreBluetooth via bleak — device addressed by UUID not MAC
- Some data types (SpO2 sync, body temp) are experimental in Gadgetbridge
- Real-time HR requires enabling Huami continuous monitoring mode
