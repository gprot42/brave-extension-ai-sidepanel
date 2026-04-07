#!/bin/bash

# 01setupavd.sh
# Creates a compatible Android Virtual Device for use with Epubor Kindle Converter.
#
# Required AVD configuration:
#   Device:       Pixel 6 Pro
#   System Image: API 30 (Android 11) - Google APIs (arm64-v8a)
#   IMPORTANT:    Must use 'Google APIs', NOT 'Google Play'
#
# Why this configuration is required:
#   Epubor Kindle Converter uses Frida to attach to system_server at runtime and
#   extract Kindle DRM keys from memory.  This requires:
#     1. Android API <= 33  — Frida supports API 21-33; API 34+ blocks injection.
#     2. Google APIs image  — allows 'adb root', which Frida needs.
#     3. Google Play images — block adb root on production builds and will NOT work.

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Configuration ─────────────────────────────────────────────────────────────
AVD_NAME="Epubor_API30_GoogleAPIs"
SYSTEM_IMAGE="system-images;android-30;google_apis;arm64-v8a"
DEVICE_PROFILE="pixel_6_pro"
SDCARD_SIZE="512M"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          Epubor AVD Setup — API 30, Google APIs                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  This script creates the Android Virtual Device required by"
echo "  Epubor Kindle Converter to extract Kindle DRM keys."
echo ""
echo -e "${YELLOW}  AVD name    : $AVD_NAME${NC}"
echo -e "${YELLOW}  System image: $SYSTEM_IMAGE${NC}"
echo -e "${YELLOW}  Device      : $DEVICE_PROFILE${NC}"
echo ""

# ── Helpers ───────────────────────────────────────────────────────────────────
command_exists() { command -v "$1" >/dev/null 2>&1; }

find_tool() {
    local name="$1"
    if command_exists "$name"; then command -v "$name"; return 0; fi
    local sdk_roots=("$HOME/Library/Android/sdk" "$HOME/Android/Sdk")
    for sdk in "${sdk_roots[@]}"; do
        for sub in "cmdline-tools/latest/bin" "tools/bin"; do
            [ -x "$sdk/$sub/$name" ] && echo "$sdk/$sub/$name" && return 0
        done
    done
    return 1
}

# ── Verify Apple Silicon ──────────────────────────────────────────────────────
arch=$(uname -m)
if [ "$arch" != "arm64" ]; then
    echo -e "${RED}ERROR: This script targets Apple Silicon (arm64). Detected: $arch${NC}"
    exit 1
fi
echo -e "${GREEN}Apple Silicon (arm64) confirmed.${NC}"

# ── Locate tools ─────────────────────────────────────────────────────────────
avdmgr=$(find_tool avdmanager 2>/dev/null || true)
sdkmgr=$(find_tool sdkmanager  2>/dev/null || true)

if [ -z "$avdmgr" ] || [ -z "$sdkmgr" ]; then
    echo -e "${RED}ERROR: avdmanager / sdkmanager not found.${NC}"
    echo ""
    echo "Install Android Studio and ensure the Command-line Tools are present:"
    echo "  Android Studio → Preferences → Android SDK → SDK Tools"
    echo "  Check 'Android SDK Command-line Tools (latest)'"
    exit 1
fi

echo "  avdmanager : $avdmgr"
echo "  sdkmanager : $sdkmgr"
echo ""

# ── Check / install system image ──────────────────────────────────────────────
echo -e "${YELLOW}Checking system image: $SYSTEM_IMAGE${NC}"
if "$sdkmgr" --list_installed 2>/dev/null | grep -qF "$SYSTEM_IMAGE"; then
    echo -e "${GREEN}System image already installed.${NC}"
else
    echo "  Downloading system image (this may take several minutes)..."
    echo "y" | "$sdkmgr" "$SYSTEM_IMAGE"
    echo -e "${GREEN}System image downloaded.${NC}"
fi
echo ""

# ── Patch AVD config for host keyboard input ─────────────────────────────────
# Without hw.keyboard=yes the emulator captures no host keyboard events,
# making it impossible to type in the Kindle sign-in form.
patch_avd_keyboard() {
    local avd_name="$1"
    local avd_ini="$HOME/.android/avd/${avd_name}.avd/config.ini"
    if [ ! -f "$avd_ini" ]; then
        echo -e "${YELLOW}  AVD config not found at $avd_ini – skipping keyboard patch.${NC}"
        return 0
    fi
    # Set or update hw.keyboard
    if grep -q "^hw\.keyboard[[:space:]]*=" "$avd_ini"; then
        # macOS BSD sed requires [[:space:]] instead of \s
        sed -i.bak 's/^hw\.keyboard[[:space:]]*=.*/hw.keyboard = yes/' "$avd_ini"
    else
        echo "hw.keyboard = yes" >> "$avd_ini"
    fi
    echo -e "${GREEN}  hw.keyboard = yes set in AVD config (host keyboard input enabled).${NC}"
}

# ── Create AVD ────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Checking for existing AVD '$AVD_NAME'...${NC}"
if "$avdmgr" list avd 2>/dev/null | grep -q "Name: $AVD_NAME"; then
    echo -e "${GREEN}AVD '$AVD_NAME' already exists.${NC}"
    patch_avd_keyboard "$AVD_NAME"
    echo ""
    echo "To recreate it from scratch, delete it first:"
    echo "  avdmanager delete avd --name $AVD_NAME"
    echo "(or run this script again)"
else
    echo "  Creating AVD..."
    echo "y" | "$avdmgr" create avd \
        --name    "$AVD_NAME"      \
        --package "$SYSTEM_IMAGE"  \
        --device  "$DEVICE_PROFILE" \
        --sdcard  "$SDCARD_SIZE"   \
        --force

    if "$avdmgr" list avd 2>/dev/null | grep -q "Name: $AVD_NAME"; then
        echo -e "${GREEN}AVD '$AVD_NAME' created successfully.${NC}"
        patch_avd_keyboard "$AVD_NAME"
    else
        echo -e "${RED}AVD creation failed. Review the output above for errors.${NC}"
        exit 1
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Setup complete!                                                 ║${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}║  AVD ready: $AVD_NAME                              ║${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}║  Next step: run the main automation script:                      ║${NC}"
echo -e "${GREEN}║    ./02kindle-drm-automator.sh                                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}NOTE: The AVD uses 'Google APIs' (NOT 'Google Play').${NC}"
echo "  This allows 'adb root', which Epubor's Frida backend requires."
echo "  Google Play images block adb root and will NOT work with Epubor."
