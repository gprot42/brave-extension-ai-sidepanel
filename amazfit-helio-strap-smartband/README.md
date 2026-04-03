# Amazfit Helio Strap Data Extraction & Dashboard

Connects directly to the Amazfit Helio Strap via BLE, extracts all sensor data, and displays it in a real-time web dashboard.

## Features

- **Direct BLE connection** — no phone/Zepp app needed after initial auth key extraction
- **Real-time HR streaming** via WebSocket
- **Periodic sync** of sleep, SpO2, stress, HRV, and activity data
- **Web dashboard** with interactive charts (React + Tailwind + Recharts)
- **SQLite storage** for all historical data

## Prerequisites

1. **Auth key** — You must pair the Helio Strap with the Zepp app once, then extract the auth key. See [Gadgetbridge Huami Server Pairing](https://codeberg.org/Freeyourgadget/Gadgetbridge/wiki/Huami-Server-Pairing).

2. **Python 3.11+** and **Node.js 18+**

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your AUTH_KEY and DEVICE_ID
```

## Running

### Development

Terminal 1 — Backend:
```bash
cd backend && source .venv/bin/activate
python -m backend.run
```

Terminal 2 — Frontend:
```bash
cd frontend
npm run dev
```

Open http://localhost:3000

### Scanning for devices

```python
import asyncio
from backend.ble.scanner import scan_for_helio

async def main():
    devices = await scan_for_helio()
    for d in devices:
        print(f"{d.name} — {d.address} (RSSI: {d.rssi})")

asyncio.run(main())
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/device` | Connection status, battery |
| GET | `/api/scan` | Scan for nearby devices |
| POST | `/api/connect` | Connect to device |
| POST | `/api/disconnect` | Disconnect |
| POST | `/api/sync` | Trigger manual sync |
| GET | `/api/hr?from=&to=` | Heart rate history |
| GET | `/api/sleep?from=&to=` | Sleep data |
| GET | `/api/spo2?from=&to=` | SpO2 readings |
| GET | `/api/stress?from=&to=` | Stress levels |
| GET | `/api/hrv?from=&to=` | HRV data |
| GET | `/api/activity?from=&to=` | Steps/calories/distance |
| WS | `/ws/hr` | Real-time HR stream |

## Architecture

```
Helio Strap (BLE 5.2) → bleak → Huami Auth → Protocol Parser → SQLite → FastAPI → React Dashboard
```

## Notes

- The BLE protocol implementation is based on [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge)'s reverse-engineered Zepp OS support
- On macOS, devices are identified by CoreBluetooth UUID (not MAC address)
- Some data types (body temperature, respiratory rate) are experimental and may not work on all firmware versions
