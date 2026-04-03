# Helio Strap Setup Guide

## Prerequisites

- Amazfit Helio Strap, Bluetooth-paired with your Mac via the Zepp app
- Python 3.9+ and Node.js 18+

## How It Works

The Helio Strap connects via BLE. Without an auth key, you get:

| Feature | Without Auth Key | With Auth Key |
|---------|-----------------|---------------|
| Real-time heart rate | Yes | Yes |
| Heart rate log | Yes | Yes |
| Battery level | Yes | Yes |
| Sleep data | No | Yes |
| SpO2 (blood oxygen) | No | Yes |
| Stress levels | No | Yes |
| HRV | No | Yes |
| Activity (steps) | No | Yes |

## Step 1: Install Dependencies

### Backend

```bash
cd /Users/aicoder/src/amazfit-helio-strap-smartband/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd /Users/aicoder/src/amazfit-helio-strap-smartband/frontend
npm install
```

## Step 2: Run the Dashboard

```bash
./start.sh
```

Open http://localhost:3000

Use the **Scan** button in the header to find nearby Helio Straps. Click a device from the results to connect, or use **Connect** to connect to the default device.

## Step 3: Extract the Auth Key (for full data access)

The auth key is a 32-character hex string required for historical data (sleep, SpO2, stress, etc.).

### Automated Script (Recommended)

Run the included extraction script which handles everything:

```bash
./extract_auth_key.sh
```

This will:
1. Restart the Zepp app to trigger fresh API calls
2. Capture the apptoken from Android logcat
3. Query the Zepp API for your device's auth key
4. Optionally save it to `.env` and push it to the running backend

**Requirements:** Android phone with USB debugging + modified Zepp app (see Method A below for setup).

### Method A: Modified Zepp App + ADB Logcat (Manual steps)

This is the most reliable method. A modified version of the Zepp app logs its API requests to Android's logcat, including the authentication token. We use that token to query the Zepp servers for the auth key.

**Requirements:** Android phone with USB debugging enabled, `adb` installed on your Mac.

#### Step 1: Enable USB debugging on your Android phone

1. Go to **Settings > About phone**
2. Tap **Build number** 7 times until it says "You are now a developer!"
3. Go to **Settings > System > Developer options**
4. Enable **USB debugging**
5. To use wireless ADB (optional): enable **Wireless debugging**, tap it, tap **Pair device with pairing code**, then on your Mac:
   ```bash
   adb pair <phone_ip>:<pairing_port>   # enter the 6-digit code
   adb connect <phone_ip>:<connect_port> # use the port from the main Wireless debugging screen
   ```

#### Step 2: Install megatools (for downloading the APK)

```bash
brew install megatools
```

#### Step 3: Download and install the modified Zepp app

The modified Zepp app is hosted on MEGA. Download and install it via ADB:

```bash
# Download the modified Zepp APK (~184 MB)
megadl "https://mega.nz/file/7hIj0JZL#BXFzx9WuWjSpf4e2apCEDYcIdgZsxqa_FQvyudYHukE" --path /tmp/

# Uninstall the official Zepp app first (if installed)
adb uninstall com.huami.watch.hmwatchmanager

# Install the modified version
adb install "/tmp/Zepp 8.11.5 - All in One.apk"
```

> **Note:** The MEGA link is for "Zepp 8.11.5 - All in One" from [magicalunicorn.fr](https://www.magicalunicorn.fr/). If the link is outdated, visit `https://www.magicalunicorn.fr/download/?app=com.huami.watch.hmwatchmanager` to get the current link.

#### Step 4: Log in and sync

1. Open the **Zepp** app on your phone
2. Log in with your account (however you normally do — Google, email, etc.)
3. Let it connect and sync with the Helio Strap

#### Step 5: Capture the auth token from logcat

Once the app has synced, the API token is in the Android system logs:

```bash
# Clear old logs, restart the Zepp app to force fresh API calls
adb logcat -c
adb shell am force-stop com.huami.watch.hmwatchmanager
adb shell monkey -p com.huami.watch.hmwatchmanager -c android.intent.category.LAUNCHER 1

# Wait ~10 seconds for the app to sync, then extract the token and user ID
sleep 10
adb logcat -d | grep "LogcatInterceptor" | grep "apptoken" | head -1
```

You will see a cURL command like:

```
curl -X GET -H "apptoken: XXXXX..." -H "appname: com.huami.midong" "https://api.amazfit.com//users/1234567890/..."
```

Copy the `apptoken` value and the user ID from the URL (`/users/<USER_ID>/`).

#### Step 6: Fetch the auth key

Use the captured token to query the Zepp API for your device's auth key:

```bash
curl -s \
  -H "apptoken: <YOUR_APPTOKEN>" \
  -H "appname: com.huami.midong" \
  "https://api.amazfit.com/users/<YOUR_USER_ID>/devices" | python3 -m json.tool
```

The response JSON contains an `additionalInfo` field with your `auth_key`:

```json
{
    "items": [{
        "macAddress": "F1:10:5A:2C:F1:55",
        "additionalInfo": "{\"auth_key\":\"9dcbda1304394edfe1f3976a0c1a8da3\", ...}"
    }]
}
```

Copy the 32-character `auth_key` value.

#### Step 7: Clean up

Reinstall the official Zepp app if desired:

```bash
adb uninstall com.huami.watch.hmwatchmanager
```

Then reinstall from the Google Play Store.

### Method B: Rooted Android phone (SQLite database)

If your Android phone is rooted, you can read the auth key directly from the Zepp app's database:

1. Open a root shell:
   ```bash
   adb shell su
   ```

2. Copy the database:
   ```bash
   cp /data/data/com.huami.watch.hmwatchmanager/databases/origin_db_* /sdcard/
   adb pull /sdcard/origin_db_*
   ```

3. Open it with SQLite and extract the key:
   ```bash
   sqlite3 origin_db_*
   SELECT AUTHKEY FROM DEVICE;
   ```

4. The result is your 32-character hex auth key.

## Step 4: Configure the Auth Key

Once you have the key, create a `.env` file in the project root:

```
AUTH_KEY=your_32_character_hex_key_here
DEVICE_ID=your_device_uuid_from_bt_scan
```

Restart the backend. The locked panels (Sleep, SpO2, Stress, HRV, Activity) will unlock and start syncing data.

## Configuration

Override defaults via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVICE_ID` | *(from BT scan)* | BLE device UUID (macOS) or MAC (Linux) |
| `AUTH_KEY` | *(empty)* | 32-char hex Huami auth key for full data access |
| `SYNC_INTERVAL` | `300` | Periodic sync interval in seconds |
| `API_PORT` | `8000` | Backend API port |

## Troubleshooting

### "Device not found" / "Could not connect"
- Close the Zepp app on your phone — it holds an exclusive BLE connection
- Make sure the Helio Strap is charged and nearby
- Use the **Scan** button to check if the device is visible
- After closing Zepp, wait 10-15 seconds for the strap to start advertising

### "Bluetooth device is turned off"
- Go to System Settings > Privacy & Security > Bluetooth
- Add Terminal.app (or your IDE) to the allowed list

### No HR data
- The strap must be worn with skin contact for the optical sensor to activate

### Panels show "Requires auth key"
- See Step 3 above to extract and configure the auth key
- Real-time heart rate works without auth; historical data does not
