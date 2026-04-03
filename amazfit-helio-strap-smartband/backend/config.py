import os
from dotenv import load_dotenv

load_dotenv()


def _persist_env(key: str, value: str):
    """Write or update a key in the .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)


# Huami auth key (32 hex chars = 16 bytes). Extract via Gadgetbridge / Huami token helper.
# Set in .env file as AUTH_KEY=0123456789abcdef0123456789abcdef
AUTH_KEY_HEX: str = os.getenv("AUTH_KEY", "")


def set_auth_key(key_hex: str):
    """Set the auth key at runtime and persist to .env file."""
    global AUTH_KEY_HEX
    AUTH_KEY_HEX = key_hex
    _persist_env("AUTH_KEY", key_hex)

# Device identifier. On macOS this is a CoreBluetooth UUID, not a MAC address.
# Set in .env as DEVICE_ID=<UUID or MAC>, or scan from the dashboard.
DEVICE_ID: str = os.getenv("DEVICE_ID", "")


def set_device_id(device_id: str):
    """Set the device ID at runtime and persist to .env file."""
    global DEVICE_ID
    DEVICE_ID = device_id
    _persist_env("DEVICE_ID", device_id)


# Huami BLE service/characteristic UUIDs
HUAMI_SERVICE = "0000fee0-0000-1000-8000-00805f9b34fb"
HUAMI_AUTH_SERVICE = "0000fee1-0000-1000-8000-00805f9b34fb"
HUAMI_AUTH_CHAR = "0000fedd-0000-1000-8000-00805f9b34fb"
HUAMI_AUTH_READ = "0000fede-0000-1000-8000-00805f9b34fb"
HUAMI_CHUNKED_CHAR = "00000004-0000-3512-2118-0009af100700"
HUAMI_SENSOR_CONTROL = "00000001-0000-3512-2118-0009af100700"
HUAMI_SENSOR_DATA = "00000002-0000-3512-2118-0009af100700"
HUAMI_ACTIVITY_DATA = "00000005-0000-3512-2118-0009af100700"
HUAMI_FETCH_CONTROL = "00000004-0000-3512-2118-0009af100700"

# Standard BLE services
HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"

# Zepp cloud API credentials (for sleep, stress, SpO2 data)
ZEPP_EMAIL: str = os.getenv("ZEPP_EMAIL", "")
ZEPP_PASSWORD: str = os.getenv("ZEPP_PASSWORD", "")
ZEPP_APPTOKEN: str = os.getenv("ZEPP_APPTOKEN", "")
ZEPP_USERID: str = os.getenv("ZEPP_USERID", "")
ZEPP_REGION: str = os.getenv("ZEPP_REGION", "eu-central-1")

# Sync intervals (seconds)
PERIODIC_SYNC_INTERVAL: int = int(os.getenv("SYNC_INTERVAL", "300"))

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./helio_data.db")

# API
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
