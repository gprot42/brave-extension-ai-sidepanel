#!/usr/bin/env bash
# extract_auth_key.sh — Extract the Helio Strap auth key via ADB + Zepp API
#
# Usage:
#   ./extract_auth_key.sh
#
# Prerequisites:
#   - Android phone connected via USB or wireless ADB
#   - Modified Zepp app installed (see SETUP.md Step 3, Method A)
#   - The Zepp app has synced with the Helio Strap at least once
#
# What this does:
#   1. Restarts the Zepp app to trigger fresh API calls
#   2. Captures the apptoken from logcat
#   3. Queries the Zepp API for your device list
#   4. Extracts the auth_key from the response
#   5. Optionally saves it to .env and the app settings

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ZEPP_PKG="com.huami.watch.hmwatchmanager"
API_BASE="https://api.amazfit.com"

echo -e "${CYAN}=== Helio Strap Auth Key Extractor ===${NC}"
echo ""

# Check adb
if ! command -v adb &>/dev/null; then
    echo -e "${RED}Error: adb not found. Install Android platform tools:${NC}"
    echo "  brew install android-platform-tools"
    exit 1
fi

# Check device connected
echo -e "${YELLOW}Checking ADB connection...${NC}"
DEVICES=$(adb devices 2>/dev/null | grep -v "^List" | grep -v "^$" | wc -l | tr -d ' ')
if [ "$DEVICES" = "0" ]; then
    echo -e "${RED}No Android device connected via ADB.${NC}"
    echo ""
    echo "To connect via USB:"
    echo "  1. Enable USB debugging on your phone"
    echo "  2. Plug in the USB cable"
    echo ""
    echo "To connect wirelessly:"
    echo "  1. Enable Wireless debugging on your phone"
    echo "  2. adb pair <phone_ip>:<pairing_port>"
    echo "  3. adb connect <phone_ip>:<connect_port>"
    exit 1
fi
echo -e "${GREEN}ADB device connected.${NC}"

# Check Zepp app installed
echo -e "${YELLOW}Checking Zepp app...${NC}"
if ! adb shell pm list packages 2>/dev/null | grep -q "$ZEPP_PKG"; then
    echo -e "${RED}Zepp app not installed on device.${NC}"
    echo "Install the modified Zepp app first (see SETUP.md Step 3)."
    exit 1
fi
echo -e "${GREEN}Zepp app found.${NC}"

# Step 1: Clear logs and restart Zepp
echo ""
echo -e "${YELLOW}Step 1: Restarting Zepp app to capture fresh API token...${NC}"
adb logcat -c 2>/dev/null
adb shell am force-stop "$ZEPP_PKG" 2>/dev/null
sleep 1
adb shell monkey -p "$ZEPP_PKG" -c android.intent.category.LAUNCHER 1 2>/dev/null
echo "Waiting 15 seconds for the app to sync..."
sleep 15

# Step 2: Extract apptoken
echo ""
echo -e "${YELLOW}Step 2: Extracting API token from logcat...${NC}"
LOGCAT=$(adb logcat -d 2>/dev/null)

# Try LogcatInterceptor pattern (modified Zepp)
TOKEN_LINE=$(echo "$LOGCAT" | grep -i "LogcatInterceptor" | grep -i "apptoken" | head -1 || true)

if [ -z "$TOKEN_LINE" ]; then
    # Try alternative patterns
    TOKEN_LINE=$(echo "$LOGCAT" | grep -i "apptoken" | head -1 || true)
fi

if [ -z "$TOKEN_LINE" ]; then
    echo -e "${RED}Could not find apptoken in logcat.${NC}"
    echo ""
    echo "Possible reasons:"
    echo "  - The modified Zepp app is not installed (official app doesn't log tokens)"
    echo "  - The app hasn't made API calls yet — try opening it manually and syncing"
    echo "  - Logs were cleared — try running this script again"
    echo ""
    echo "You can also try manually:"
    echo "  adb logcat -d | grep -i apptoken"
    echo ""
    read -rp "Enter apptoken manually (or press Enter to exit): " MANUAL_TOKEN
    if [ -z "$MANUAL_TOKEN" ]; then
        exit 1
    fi
    APP_TOKEN="$MANUAL_TOKEN"
else
    # Extract the token value (macOS-compatible, no grep -P)
    APP_TOKEN=$(echo "$TOKEN_LINE" | sed -n 's/.*apptoken: *\([^ "]*\).*/\1/p')
    if [ -z "$APP_TOKEN" ]; then
        APP_TOKEN=$(echo "$TOKEN_LINE" | sed -n 's/.*apptoken[: ]*\([A-Za-z0-9_\.\+\/=\-]*\).*/\1/p')
    fi
    if [ -z "$APP_TOKEN" ]; then
        echo -e "${RED}Found apptoken line but couldn't parse the value:${NC}"
        echo "$TOKEN_LINE"
        read -rp "Enter apptoken manually: " APP_TOKEN
        if [ -z "$APP_TOKEN" ]; then
            exit 1
        fi
    fi
fi
echo -e "${GREEN}Got apptoken: ${APP_TOKEN:0:20}...${NC}"

# Step 3: Extract user ID (macOS-compatible)
echo ""
echo -e "${YELLOW}Step 3: Extracting user ID...${NC}"
USER_ID=$(echo "$LOGCAT" | sed -n 's|.*/users/\([0-9]*\)/.*|\1|p' | head -1 || true)

if [ -z "$USER_ID" ]; then
    # Try to get it from the API — multiple endpoint patterns
    echo "User ID not found in logcat, trying API..."
    for endpoint in "users/-/profile" "users/self/profile" "user/profile"; do
        USER_RESP=$(curl -sf -H "apptoken: $APP_TOKEN" -H "appname: com.huami.midong" \
            "$API_BASE/$endpoint" 2>/dev/null || true)
        if [ -n "$USER_RESP" ]; then
            USER_ID=$(echo "$USER_RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    uid = d.get('userid') or d.get('user_id') or d.get('id') or ''
    if uid: print(uid)
except: pass
" 2>/dev/null || true)
            if [ -n "$USER_ID" ]; then break; fi
        fi
    done
fi

# Try extracting from any URL in logcat containing a numeric user path
if [ -z "$USER_ID" ]; then
    USER_ID=$(echo "$LOGCAT" | grep -o '/users/[0-9]*' | sed 's|/users/||' | head -1 || true)
fi

if [ -z "$USER_ID" ]; then
    echo -e "${YELLOW}Could not auto-detect user ID.${NC}"
    read -rp "Enter your Zepp user ID: " USER_ID
    if [ -z "$USER_ID" ]; then
        exit 1
    fi
fi
echo -e "${GREEN}User ID: $USER_ID${NC}"

# Step 4: Fetch devices and extract auth key
echo ""
echo -e "${YELLOW}Step 4: Fetching device list from Zepp API...${NC}"
DEVICES_JSON=$(curl -sf \
    -H "apptoken: $APP_TOKEN" \
    -H "appname: com.huami.midong" \
    "$API_BASE/users/$USER_ID/devices" 2>/dev/null || true)

if [ -z "$DEVICES_JSON" ]; then
    echo -e "${RED}API request failed. The token may be expired.${NC}"
    echo "Try restarting the Zepp app and running this script again."
    exit 1
fi

# Parse auth_key from response
AUTH_KEY=$(echo "$DEVICES_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('items', data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get('items', [items])
    if not isinstance(items, list):
        items = [items]
    for item in items:
        info = item.get('additionalInfo', '{}')
        if isinstance(info, str):
            info = json.loads(info)
        key = info.get('auth_key', '')
        if key:
            print(key)
            sys.exit(0)
    # Fallback: search all string values
    def find_key(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'auth_key' and isinstance(v, str) and len(v) == 32:
                    print(v)
                    sys.exit(0)
                find_key(v)
        elif isinstance(obj, list):
            for x in obj:
                find_key(x)
        elif isinstance(obj, str):
            try:
                find_key(json.loads(obj))
            except:
                pass
    find_key(data)
except Exception as e:
    print(f'PARSE_ERROR: {e}', file=sys.stderr)
" 2>/dev/null || true)

if [ -z "$AUTH_KEY" ]; then
    echo -e "${RED}Could not find auth_key in API response.${NC}"
    echo ""
    echo "Raw API response:"
    echo "$DEVICES_JSON" | python3 -m json.tool 2>/dev/null || echo "$DEVICES_JSON"
    echo ""
    echo "Look for 'auth_key' in the output above and enter it below."
    read -rp "Enter auth_key (32 hex chars): " AUTH_KEY
    if [ -z "$AUTH_KEY" ]; then
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}==============================${NC}"
echo -e "${GREEN}Auth Key: $AUTH_KEY${NC}"
echo -e "${GREEN}==============================${NC}"
echo ""

# Step 5: Save to .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

read -rp "Save to .env? [Y/n] " SAVE_ENV
SAVE_ENV=${SAVE_ENV:-Y}
if [[ "$SAVE_ENV" =~ ^[Yy] ]]; then
    if [ -f "$ENV_FILE" ]; then
        # Update existing AUTH_KEY or append
        if grep -q "^AUTH_KEY=" "$ENV_FILE"; then
            sed -i.bak "s/^AUTH_KEY=.*/AUTH_KEY=$AUTH_KEY/" "$ENV_FILE"
            rm -f "$ENV_FILE.bak"
        else
            echo "AUTH_KEY=$AUTH_KEY" >> "$ENV_FILE"
        fi
    else
        echo "AUTH_KEY=$AUTH_KEY" > "$ENV_FILE"
    fi
    echo -e "${GREEN}Saved to $ENV_FILE${NC}"
fi

# Step 6: Push to running backend
read -rp "Push to running backend (localhost:8000)? [Y/n] " PUSH_API
PUSH_API=${PUSH_API:-Y}
if [[ "$PUSH_API" =~ ^[Yy] ]]; then
    RESP=$(curl -sf -X POST "http://localhost:8000/api/auth-key?key=$AUTH_KEY" 2>/dev/null || true)
    if echo "$RESP" | grep -q '"ok"'; then
        echo -e "${GREEN}Auth key pushed to backend. Reconnect to apply.${NC}"
    else
        echo -e "${YELLOW}Backend not reachable or returned error. Start the app with ./start.sh and enter the key in Settings.${NC}"
    fi
fi

echo ""
echo -e "${CYAN}Done. Restart the app and reconnect to use the new auth key.${NC}"
