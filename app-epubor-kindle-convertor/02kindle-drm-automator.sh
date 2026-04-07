#!/bin/bash

# Epubor Kindle DRM Automation Script
# Automates launch order and provides guided steps for Kindle DRM removal on Mac

set -e

# ── Configuration ────────────────────────────────────────────────────────────
EMULATOR_NAME="Pixel_6_Pro_API_30"  # Adjust based on your AVD name
KINDLE_APK_URL="https://download.epubor.com/kindle.apk"
EPUBOR_MAC_URL="https://s3.amazonaws.com/download.epubor.com.bk/kindle_converter-M.zip"  # Apple Silicon
EPUBOR_INTEL_URL="https://download.epubor.com/kindle_converter.zip"
DOWNLOAD_DIR="$HOME/Downloads/epubor-kindle"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Flags (may be overridden by argv) ───────────────────────────────────────
KEEP_DOWNLOADS=false   # set true via --keep-downloads

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Argument parsing ─────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --keep-downloads   Do not delete downloaded APK/ZIP files on exit."
    echo "  -h, --help         Show this help message."
    exit 0
}

for arg in "$@"; do
    case "$arg" in
        --keep-downloads) KEEP_DOWNLOADS=true ;;
        -h|--help) usage ;;
        *) echo -e "${RED}Unknown option: $arg${NC}"; usage ;;
    esac
done

# ── Cleanup ──────────────────────────────────────────────────────────────────
# Files/dirs created by this script that should be removed on exit (unless --keep-downloads)
CLEANUP_FILES=()

# Guard to prevent double-cleanup when INT fires then EXIT fires
_CLEANUP_DONE=false

cleanup() {
    # Run only once
    if [ "$_CLEANUP_DONE" = true ]; then return; fi
    _CLEANUP_DONE=true

    local reason="${1:-exit}"
    local exit_code="${2:-$?}"

    echo ""
    if [ "$reason" = "interrupted" ]; then
        echo -e "${YELLOW}Script interrupted (Ctrl-C). Cleaning up...${NC}"
    elif [ "$exit_code" -ne 0 ]; then
        echo -e "${YELLOW}Script exited with code $exit_code. Cleaning up...${NC}"
    fi

    if [ "$KEEP_DOWNLOADS" = true ]; then
        echo -e "${GREEN}--keep-downloads set: leaving downloaded files in $DOWNLOAD_DIR${NC}"
    else
        # Remove transient working files; keep converted books
        local to_remove=(
            "$DOWNLOAD_DIR/emulator.log"
            "$DOWNLOAD_DIR/kindle-books"   # pulled raw azw files (already copied to Kindle/Epubor dirs)
        )
        for f in "${to_remove[@]}"; do
            if [ -e "$f" ]; then
                rm -rf "$f"
                echo "  Removed: $f"
            fi
        done
    fi
}

handle_interrupt() {
    cleanup interrupted 130
    # Reset the trap and re-raise SIGINT so the shell reports the correct exit status
    trap - INT
    kill -INT "$$"
}

# Trap Ctrl-C (SIGINT) and normal exit
trap 'handle_interrupt' INT
trap 'cleanup exit $?'  EXIT

# ── Banner ───────────────────────────────────────────────────────────────────
echo -e "${BLUE}=== Epubor Kindle DRM Automation Script ===${NC}"
echo "This script follows the official Android emulator method for removing Kindle DRM."
if [ "$KEEP_DOWNLOADS" = true ]; then
    echo -e "${YELLOW}--keep-downloads: downloaded files will be preserved on exit.${NC}"
fi
echo ""

# Verify Apple Silicon (arm64) — exit early on Intel
check_apple_silicon() {
    local arch
    arch=$(uname -m)
    if [ "$arch" != "arm64" ]; then
        echo -e "${RED}ERROR: This script is designed for Apple Silicon (arm64) Macs.${NC}"
        echo "Detected architecture: $arch"
        echo ""
        echo "If you are on an Intel Mac, use the Intel build of Epubor Kindle Converter:"
        echo "  $EPUBOR_INTEL_URL"
        echo "and remove the architecture check from this script."
        exit 1
    fi
    echo -e "${GREEN}Apple Silicon (arm64) detected. ✓${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    if ! command_exists "open"; then
        echo -e "${RED}Error: 'open' command not found. This script requires macOS.${NC}"
        exit 1
    fi
    
    if ! command_exists "curl"; then
        echo -e "${RED}Error: curl is required but not installed.${NC}"
        exit 1
    fi
    
    # Check for Android Studio
    if [ ! -d "/Applications/Android Studio.app" ]; then
        echo -e "${YELLOW}Warning: Android Studio not found in Applications.${NC}"
        echo "Please install Android Studio following: https://www.epubor.com/how-to-set-up-android-emulator-on-mac.html"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Check for Epubor
    if [ ! -d "/Applications/Epubor Kindle Converter.app" ] && [ ! -d "$HOME/Applications/Epubor Kindle Converter.app" ]; then
        echo -e "${YELLOW}Warning: Epubor Kindle Converter not found.${NC}"
        echo "Please download and install from the links provided."
    fi
    
    echo -e "${GREEN}Prerequisites check completed.${NC}"
}

# Create download directory
setup_directories() {
    mkdir -p "$DOWNLOAD_DIR"
    echo -e "${GREEN}Download directory ready: $DOWNLOAD_DIR${NC}"
}

# Download files
download_files() {
    echo -e "${YELLOW}Downloading required files...${NC}"
    
    # Download Kindle APK
    if [ ! -f "$DOWNLOAD_DIR/kindle.apk" ]; then
        echo "Downloading Kindle APK..."
        curl -L -o "$DOWNLOAD_DIR/kindle.apk" "$KINDLE_APK_URL"
        echo -e "${GREEN}Kindle APK downloaded.${NC}"
    else
        echo -e "${GREEN}Kindle APK already exists.${NC}"
    fi
    
    # Determine architecture and download Epubor
    if [[ $(uname -m) == 'arm64' ]]; then
        EPUBOR_URL="$EPUBOR_MAC_URL"
        ZIP_NAME="kindle_converter-M.zip"
    else
        EPUBOR_URL="$EPUBOR_INTEL_URL"
        ZIP_NAME="kindle_converter.zip"
    fi
    
    if [ ! -f "$DOWNLOAD_DIR/$ZIP_NAME" ]; then
        echo "Downloading Epubor Kindle Converter..."
        curl -L -o "$DOWNLOAD_DIR/$ZIP_NAME" "$EPUBOR_URL"
        echo -e "${GREEN}Epubor installer downloaded.${NC}"
    else
        echo -e "${GREEN}Epubor installer already exists.${NC}"
    fi
    
    echo -e "${BLUE}Files are in: $DOWNLOAD_DIR${NC}"
}

# Locate the Android SDK emulator binary even if not in PATH
find_emulator_bin() {
    # 1. Already in PATH
    if command_exists "emulator"; then
        command -v emulator
        return 0
    fi

    # 2. Standard Android SDK locations on macOS
    local sdk_roots=(
        "$HOME/Library/Android/sdk"
        "$HOME/Android/Sdk"
        "/usr/local/share/android-sdk"
        "/opt/homebrew/share/android-sdk"
    )
    for sdk in "${sdk_roots[@]}"; do
        local bin="$sdk/emulator/emulator"
        if [ -x "$bin" ]; then
            echo "$bin"
            return 0
        fi
    done

    # 3. Ask Android Studio's bundled sdkmanager path
    local as_sdk
    as_sdk=$(defaults read /Applications/Android\ Studio.app/Contents/Info.plist \
             JVMOptions 2>/dev/null | grep -o 'android.sdk.path=[^ ]*' | cut -d= -f2 || true)
    if [ -n "$as_sdk" ] && [ -x "$as_sdk/emulator/emulator" ]; then
        echo "$as_sdk/emulator/emulator"
        return 0
    fi

    return 1
}

# Locate adb binary
find_adb_bin() {
    if command_exists "adb"; then
        command -v adb
        return 0
    fi
    local sdk_roots=(
        "$HOME/Library/Android/sdk"
        "$HOME/Android/Sdk"
        "/usr/local/share/android-sdk"
        "/opt/homebrew/share/android-sdk"
    )
    for sdk in "${sdk_roots[@]}"; do
        local bin="$sdk/platform-tools/adb"
        if [ -x "$bin" ]; then
            echo "$bin"
            return 0
        fi
    done
    return 1
}

# Wait until the emulator has fully booted (sys.boot_completed=1)
wait_for_emulator_boot() {
    local adb_bin="$1"
    local max_wait=240   # seconds
    local interval=5
    local elapsed=0

    echo -e "${YELLOW}Waiting for emulator to finish booting (up to ${max_wait}s)...${NC}"

    while [ "$elapsed" -lt "$max_wait" ]; do
        # grep -c returns exit 1 when count is 0; guard with || echo 0
        local devices
        devices=$("$adb_bin" devices 2>/dev/null | grep -c "emulator-" || echo 0)
        if [ "$devices" -gt 0 ]; then
            local serial
            serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
            local boot_prop
            boot_prop=$("$adb_bin" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n ' || true)
            if [ "$boot_prop" = "1" ]; then
                echo -e "${GREEN}Emulator ($serial) is fully booted.${NC}"
                # Export serial for use by install_kindle_apk
                EMULATOR_SERIAL="$serial"
                return 0
            fi
            echo "  ...device visible but still booting (${elapsed}s elapsed)"
        else
            echo "  ...waiting for emulator to appear in adb (${elapsed}s elapsed)"
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    echo -e "${RED}Emulator did not boot within ${max_wait}s.${NC}"
    echo "Please check Android Studio manually, then press Enter to continue..."
    read -r
}

# Global serial set by wait_for_emulator_boot
EMULATOR_SERIAL=""

# Locate avdmanager and sdkmanager binaries
find_avdmanager() {
    if command_exists avdmanager; then command -v avdmanager; return 0; fi
    local sdk_roots=("$HOME/Library/Android/sdk" "$HOME/Android/Sdk")
    for sdk in "${sdk_roots[@]}"; do
        for sub in "cmdline-tools/latest/bin" "tools/bin"; do
            [ -x "$sdk/$sub/avdmanager" ] && echo "$sdk/$sub/avdmanager" && return 0
        done
    done
    return 1
}

find_sdkmanager() {
    if command_exists sdkmanager; then command -v sdkmanager; return 0; fi
    local sdk_roots=("$HOME/Library/Android/sdk" "$HOME/Android/Sdk")
    for sdk in "${sdk_roots[@]}"; do
        for sub in "cmdline-tools/latest/bin" "tools/bin"; do
            [ -x "$sdk/$sub/sdkmanager" ] && echo "$sdk/$sub/sdkmanager" && return 0
        done
    done
    return 1
}

# Create the required AVD (API 30, Google APIs, arm64) automatically.
# This is the only configuration confirmed to work with Epubor's Frida-based DRM extraction:
#   - API 30 (Android 11)     – Frida supports API 21–33
#   - google_apis image       – supports adb root (unlike google_apis_playstore)
#   - arm64-v8a               – required on Apple Silicon
COMPATIBLE_AVD_NAME="Epubor_API30_GoogleAPIs"
COMPATIBLE_SYSTEM_IMAGE="system-images;android-30;google_apis;arm64-v8a"

create_compatible_avd() {
    local avdmgr
    avdmgr=$(find_avdmanager || true)
    local sdkmgr
    sdkmgr=$(find_sdkmanager || true)

    if [ -z "$avdmgr" ] || [ -z "$sdkmgr" ]; then
        echo -e "${YELLOW}avdmanager/sdkmanager not found – cannot auto-create AVD.${NC}"
        echo "Open Android Studio → Device Manager → Create Virtual Device"
        echo "and choose: Pixel 6 Pro | API 30 | Google APIs | arm64"
        return 1
    fi

    # Check if compatible AVD already exists
    if "$avdmgr" list avd 2>/dev/null | grep -q "Name: $COMPATIBLE_AVD_NAME"; then
        echo -e "${GREEN}Compatible AVD '$COMPATIBLE_AVD_NAME' already exists.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Creating compatible AVD '$COMPATIBLE_AVD_NAME'...${NC}"
    echo "  System image: $COMPATIBLE_SYSTEM_IMAGE"

    # Install system image if not present
    local installed
    installed=$("$sdkmgr" --list_installed 2>/dev/null | grep -c "$COMPATIBLE_SYSTEM_IMAGE" || echo 0)
    if [ "$installed" -eq 0 ]; then
        echo "  Downloading system image (this may take a few minutes)..."
        echo "y" | "$sdkmgr" "$COMPATIBLE_SYSTEM_IMAGE" 2>/dev/null
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to download system image. Check your internet connection and Android SDK setup.${NC}"
            return 1
        fi
        echo -e "${GREEN}System image downloaded.${NC}"
    else
        echo -e "${GREEN}System image already installed.${NC}"
    fi

    # Create the AVD
    echo "y" | "$avdmgr" create avd \
        --name "$COMPATIBLE_AVD_NAME" \
        --package "$COMPATIBLE_SYSTEM_IMAGE" \
        --device "pixel_6_pro" \
        --sdcard "512M" \
        --force \
        2>/dev/null

    if "$avdmgr" list avd 2>/dev/null | grep -q "Name: $COMPATIBLE_AVD_NAME"; then
        echo -e "${GREEN}AVD '$COMPATIBLE_AVD_NAME' created successfully.${NC}"
        # Override the configured emulator name so launch_emulator uses this AVD
        EMULATOR_NAME="$COMPATIBLE_AVD_NAME"
        return 0
    else
        echo -e "${RED}AVD creation failed. Please create it manually in Android Studio:${NC}"
        echo "  Pixel 6 Pro | API 30 | Google APIs | arm64"
        return 1
    fi
}

# Validate the running emulator is compatible with Epubor's Frida-based DRM extraction.
# Requires API <= 33, a debuggable/Google-APIs image, and root access via adb.
check_emulator_compatibility() {
    local adb_bin
    adb_bin=$(find_adb_bin || true)
    if [ -z "$adb_bin" ]; then return 0; fi

    local serial="${EMULATOR_SERIAL:-}"
    if [ -z "$serial" ]; then
        serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
    fi
    if [ -z "$serial" ]; then return 0; fi

    echo -e "${YELLOW}Checking emulator compatibility with Epubor...${NC}"

    # Check API level
    local api
    api=$("$adb_bin" -s "$serial" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r')
    echo "  Android API level: $api"
    if [ -n "$api" ] && [ "$api" -gt 33 ] 2>/dev/null; then
        echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  WARNING: Incompatible Android API level detected!               ║${NC}"
        echo -e "${RED}║                                                                  ║${NC}"
        printf "${RED}║  Detected: API %-2s  |  Supported: API 21-33 (Android 5-13)        ║${NC}\n" "$api"
        echo -e "${RED}║                                                                  ║${NC}"
        echo -e "${RED}║  Epubor uses Frida, which cannot attach to system_server on      ║${NC}"
        echo -e "${RED}║  Android 14+ (API 34+).                                          ║${NC}"
        echo -e "${RED}║                                                                  ║${NC}"
        echo -e "${RED}║  Fix: In AVD Manager, create a new device with:                  ║${NC}"
        echo -e "${RED}║    Device:       Pixel 6 Pro                                     ║${NC}"
        echo -e "${RED}║    System Image: API 30 (Android 11) - Google APIs               ║${NC}"
        echo -e "${RED}║    IMPORTANT:    'Google APIs' not 'Google Play'                 ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo "Press Enter to continue anyway, or Ctrl-C to abort and create a compatible AVD first..."
        read -r
    fi

    # Check build type (user vs userdebug/eng)
    local build_type
    build_type=$("$adb_bin" -s "$serial" shell getprop ro.build.type 2>/dev/null | tr -d '\r')
    echo "  Build type: $build_type"
    if [ "$build_type" = "user" ]; then
        echo -e "${YELLOW}  Build type is 'user' (Google Play image). Attempting adb root...${NC}"
    fi

    # Attempt adb root (required for Frida to attach to system_server)
    local root_output
    root_output=$("$adb_bin" -s "$serial" root 2>&1 | tr -d '\r')
    echo "  adb root: $root_output"
    if echo "$root_output" | grep -qi "cannot\|not allowed\|production builds"; then
        echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ERROR: adb root failed on the running emulator.                 ║${NC}"
        echo -e "${RED}║                                                                  ║${NC}"
        echo -e "${RED}║  The active emulator may be a Google Play image that blocks      ║${NC}"
        echo -e "${RED}║  adb root. Epubor requires root to extract DRM keys.             ║${NC}"
        echo -e "${RED}║                                                                  ║${NC}"
        echo -e "${RED}║  If you already ran 01setupavd.sh, make sure the emulator        ║${NC}"
        echo -e "${RED}║  named '$COMPATIBLE_AVD_NAME' is the one                      ║${NC}"
        echo -e "${RED}║  that was started (check AVD manager for any others).            ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo "Press Enter to continue anyway (books may not appear in Epubor), or Ctrl-C to abort..."
        read -r
    else
        # Wait for adb to reconnect after rooting
        sleep 3
        "$adb_bin" -s "$serial" wait-for-device 2>/dev/null || true
        echo -e "${GREEN}  adb root succeeded – Frida can attach to system_server.${NC}"
        # Re-establish port forward after root reconnect
        "$adb_bin" -s "$serial" forward "tcp:27042" "tcp:27042" >/dev/null 2>&1 || true
    fi
}

# Launch emulator
launch_emulator() {
    echo -e "${YELLOW}Launching Android Emulator...${NC}"

    local emulator_bin
    local adb_bin

    emulator_bin=$(find_emulator_bin || true)
    adb_bin=$(find_adb_bin || true)

    if [ -n "$emulator_bin" ]; then
        # Discover available AVDs if EMULATOR_NAME is not already running
        local avd_to_launch="$EMULATOR_NAME"

        # Check if an emulator is already running
        if [ -n "$adb_bin" ]; then
            local running
            running=$("$adb_bin" devices 2>/dev/null | grep -c "emulator-" || echo 0)
            if [ "$running" -gt 0 ]; then
                local running_serial
                running_serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
                local running_api
                running_api=$("$adb_bin" -s "$running_serial" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r')
                if [ -n "$running_api" ] && [ "$running_api" -le 33 ] 2>/dev/null; then
                    echo -e "${GREEN}Compatible emulator already running ($running_serial, API $running_api) – skipping launch.${NC}"
                    EMULATOR_SERIAL="$running_serial"
                    wait_for_emulator_boot "$adb_bin"
                    return 0
                else
                    echo -e "${YELLOW}Running emulator ($running_serial, API ${running_api:-unknown}) is incompatible (need API <= 33).${NC}"
                    echo -e "${YELLOW}Stopping it and booting '$EMULATOR_NAME' instead...${NC}"
                    "$adb_bin" -s "$running_serial" emu kill 2>/dev/null || true
                    sleep 3
                fi
            fi
        fi

        # Pick the best AVD: prefer configured EMULATOR_NAME, fallback to first available
        local avd_list
        avd_list=$("$emulator_bin" -list-avds 2>/dev/null || true)
        if [ -z "$avd_list" ]; then
            echo -e "${RED}No AVDs found. Please create a virtual device in Android Studio first.${NC}"
            open -a "Android Studio"
            echo "Create an AVD in Android Studio, then press Enter to continue..."
            read -r
            avd_list=$("$emulator_bin" -list-avds 2>/dev/null || true)
        fi

        if echo "$avd_list" | grep -qF "$EMULATOR_NAME"; then
            avd_to_launch="$EMULATOR_NAME"
        else
            # Use the first available AVD
            avd_to_launch=$(echo "$avd_list" | head -1)
            if [ -z "$avd_to_launch" ]; then
                echo -e "${RED}Still no AVDs available. Opening Android Studio...${NC}"
                open -a "Android Studio"
                echo "Please start an emulator manually, then press Enter to continue..."
                read -r
                if [ -n "$adb_bin" ]; then
                    wait_for_emulator_boot "$adb_bin"
                fi
                return 0
            fi
            echo -e "${YELLOW}AVD '$EMULATOR_NAME' not found. Using '$avd_to_launch' instead.${NC}"
        fi

        local emu_log="$DOWNLOAD_DIR/emulator.log"
        echo "Starting AVD '$avd_to_launch' in background (log: $emu_log)..."
        "$emulator_bin" -avd "$avd_to_launch" -no-snapshot-save \
            >"$emu_log" 2>&1 &
        local emu_pid=$!
        echo -e "${GREEN}Emulator process started (PID $emu_pid).${NC}"
        # Give the emulator process a moment to fail fast if something is wrong
        sleep 3
        if ! kill -0 "$emu_pid" 2>/dev/null; then
            echo -e "${RED}Emulator process exited immediately. Check $emu_log for details.${NC}"
            cat "$emu_log" || true
            echo "Press Enter to continue anyway (or Ctrl-C to abort)..."
            read -r
        fi

        if [ -n "$adb_bin" ]; then
            wait_for_emulator_boot "$adb_bin"
        else
            echo -e "${YELLOW}adb not found – cannot auto-detect boot status.${NC}"
            echo "Wait for the emulator to finish booting, then press Enter to continue..."
            read -r
        fi
    else
        # Fallback: open Android Studio and ask the user to start an emulator
        echo -e "${YELLOW}Android SDK emulator binary not found. Opening Android Studio...${NC}"
        if [ -d "/Applications/Android Studio.app" ]; then
            open -a "Android Studio"
            echo -e "${GREEN}Android Studio launched.${NC}"
        else
            echo -e "${RED}Android Studio not found in /Applications.${NC}"
            echo "Please install Android Studio: https://developer.android.com/studio"
        fi

        if [ -n "$adb_bin" ]; then
            wait_for_emulator_boot "$adb_bin"
        else
            echo "Please start an emulator from Android Studio, then press Enter to continue..."
            read -r
        fi
    fi
}

# Install Kindle APK automatically via adb
install_kindle_apk() {
    local apk="$DOWNLOAD_DIR/kindle.apk"
    local adb_bin
    adb_bin=$(find_adb_bin || true)

    echo -e "${YELLOW}Installing Kindle APK onto emulator...${NC}"

    if [ ! -f "$apk" ]; then
        echo -e "${RED}Kindle APK not found at $apk – please re-run the script to download it.${NC}"
        return 1
    fi

    if [ -z "$adb_bin" ]; then
        echo -e "${YELLOW}adb not found – cannot auto-install APK.${NC}"
        echo "Drag and drop $apk onto the emulator window to install manually."
        read -p "Press Enter once the Kindle app is installed..." -r
        return 0
    fi

    # Get serial of first running emulator (prefer the one detected during boot)
    local serial="${EMULATOR_SERIAL:-}"
    if [ -z "$serial" ]; then
        serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
    fi

    if [ -z "$serial" ]; then
        echo -e "${RED}No running emulator detected by adb. Cannot install APK automatically.${NC}"
        echo "Drag and drop $apk onto the emulator window, then press Enter..."
        read -r
        return 0
    fi

    # Check if Kindle is already installed
    local pkg_check
    pkg_check=$("$adb_bin" -s "$serial" shell pm list packages 2>/dev/null | grep "com.amazon.kindle" || echo "")
    if [ -n "$pkg_check" ]; then
        echo -e "${GREEN}Kindle app is already installed on $serial.${NC}"
        return 0
    fi

    echo "Running: adb -s $serial install -r \"$apk\""
    if "$adb_bin" -s "$serial" install -r "$apk"; then
        echo -e "${GREEN}Kindle APK installed successfully on $serial.${NC}"
    else
        echo -e "${RED}adb install failed. Trying manual method...${NC}"
        echo "Drag and drop $apk onto the emulator window, then press Enter..."
        read -r
    fi

    # Launch Kindle app in the emulator automatically
    echo -e "${YELLOW}Launching Kindle app in emulator...${NC}"
    local launch_result
    launch_result=$("$adb_bin" -s "$serial" shell am start \
        -n "com.amazon.kindle/com.amazon.kindle.OfflineActivity" \
        2>&1 || true)
    # Fallback to generic package launch if the activity name changed
    if echo "$launch_result" | grep -qi "error\|exception\|does not exist"; then
        "$adb_bin" -s "$serial" shell monkey \
            -p com.amazon.kindle -c android.intent.category.LAUNCHER 1 \
            >/dev/null 2>&1 || true
    fi
    echo -e "${GREEN}Kindle app launched in emulator.${NC}"
}

# Launch Epubor first (critical — must be running before books are downloaded)
launch_epubor() {
    echo -e "${YELLOW}Launching Epubor Kindle Converter (must be running before book downloads)...${NC}"

    # Find and launch Epubor
    if [ -d "/Applications/Epubor Kindle Converter.app" ]; then
        open -a "Epubor Kindle Converter"
    elif [ -d "$HOME/Applications/Epubor Kindle Converter.app" ]; then
        open -a "$HOME/Applications/Epubor Kindle Converter.app"
    else
        echo -e "${RED}Epubor Kindle Converter not found.${NC}"
        echo "Opening download location: $DOWNLOAD_DIR"
        open "$DOWNLOAD_DIR"
        read -p "Install Epubor Kindle Converter, then press Enter to continue..." -r
        open -a "Epubor Kindle Converter"
    fi

    echo -e "${GREEN}Epubor Kindle Converter is now running.${NC}"
    echo "IMPORTANT: Keep Epubor running during all book downloads in the emulator."
    # Give Epubor time to start and connect to the emulator via adb
    sleep 5
}

# Set up adb port forwarding so Epubor's Mac util can reach its server on the emulator.
# Epubor's server listens on 127.0.0.1:27042 inside the emulator; without a forward
# the Mac side cannot connect and the KindleContent library stays empty.
setup_epubor_port_forward() {
    local adb_bin
    adb_bin=$(find_adb_bin || true)
    if [ -z "$adb_bin" ]; then
        echo -e "${YELLOW}adb not found – skipping port forward setup.${NC}"
        return 0
    fi

    local serial="${EMULATOR_SERIAL:-}"
    if [ -z "$serial" ]; then
        serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
    fi
    if [ -z "$serial" ]; then
        echo -e "${YELLOW}No emulator detected – skipping port forward.${NC}"
        return 0
    fi

    # Epubor server port
    local port=27042
    echo -e "${YELLOW}Setting up adb port forward for Epubor (tcp:$port)...${NC}"
    if "$adb_bin" -s "$serial" forward "tcp:$port" "tcp:$port" 2>/dev/null; then
        echo -e "${GREEN}Port forward established: localhost:$port → emulator:$port${NC}"
    else
        echo -e "${YELLOW}Port forward may have failed (Epubor server may not be running yet). Will retry after Epubor launches.${NC}"
    fi
}

# Retry port forward (called after Epubor has had time to push its server to the emulator)
retry_epubor_port_forward() {
    local adb_bin
    adb_bin=$(find_adb_bin || true)
    if [ -z "$adb_bin" ]; then return 0; fi

    local serial="${EMULATOR_SERIAL:-}"
    if [ -z "$serial" ]; then
        serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
    fi
    if [ -z "$serial" ]; then return 0; fi

    local port=27042
    local max_wait=30
    local interval=3
    local elapsed=0

    echo -e "${YELLOW}Waiting for Epubor server to start on emulator (port $port)...${NC}"
    while [ "$elapsed" -lt "$max_wait" ]; do
        # Check if server is listening inside the emulator
        if "$adb_bin" -s "$serial" shell "netstat -tlnp 2>/dev/null | grep :$port" 2>/dev/null | grep -q "LISTEN"; then
            "$adb_bin" -s "$serial" forward "tcp:$port" "tcp:$port" >/dev/null 2>&1 || true
            echo -e "${GREEN}Epubor server detected and port $port forwarded.${NC}"
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo -e "${YELLOW}Epubor server did not start within ${max_wait}s. Proceeding anyway.${NC}"
}

# Poll the emulator for downloaded Kindle book files and pull them locally
# so Epubor can detect them via its local scan path.
sync_kindle_books() {
    local adb_bin
    adb_bin=$(find_adb_bin || true)

    if [ -z "$adb_bin" ]; then
        echo -e "${YELLOW}adb not found – skipping automatic book sync.${NC}"
        return 0
    fi

    local serial="${EMULATOR_SERIAL:-}"
    if [ -z "$serial" ]; then
        serial=$("$adb_bin" devices 2>/dev/null | grep "emulator-" | awk '{print $1}' | head -1)
    fi
    if [ -z "$serial" ]; then
        echo -e "${YELLOW}No emulator detected by adb – cannot sync books.${NC}"
        return 0
    fi

    # Ensure Epubor port forward is still active (may have been lost after adb restart)
    setup_epubor_port_forward

    # Kindle stores downloaded books here on Android
    local kindle_storage="/sdcard/Android/data/com.amazon.kindle/files"
    local local_books_dir="$DOWNLOAD_DIR/kindle-books"
    mkdir -p "$local_books_dir"

    echo -e "${YELLOW}Checking Kindle download directory on emulator ($serial)...${NC}"
    echo "  Path: $kindle_storage"

    # List files in the Kindle storage directory
    local file_list
    file_list=$("$adb_bin" -s "$serial" shell ls "$kindle_storage" 2>/dev/null || echo "")

    if [ -z "$file_list" ]; then
        echo -e "${YELLOW}No files found in Kindle storage yet.${NC}"
        echo "Make sure you have tapped on a book cover in the Kindle app to download it."
        echo "Books must show a ✓ checkmark (or 'Downloaded' status) before they appear here."
        return 0
    fi

    echo -e "${GREEN}Found files in Kindle storage:${NC}"
    echo "$file_list"
    echo ""

    # Pull all .azw* and .kfx files to the local directory
    echo "Pulling book files to: $local_books_dir"
    "$adb_bin" -s "$serial" pull "$kindle_storage/." "$local_books_dir/" 2>/dev/null || true

    local pulled
    pulled=$(find "$local_books_dir" -name "*.azw*" -o -name "*.kfx" 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${GREEN}Pulled $pulled book file(s) to $local_books_dir${NC}"

    if [ "$pulled" -gt 0 ]; then
        # Epubor Kindle Converter on Mac scans these paths (in priority order):
        #   1. ~/Library/Application Support/Kindle/My Kindle Content  (Kindle for Mac – non-sandboxed)
        #   2. ~/Library/Containers/com.amazon.Kindle/Data/Library/Application Support/Kindle/My Kindle Content  (sandboxed)
        local kindle_mac_dirs=(
            "$HOME/Library/Application Support/Kindle/My Kindle Content"
            "$HOME/Library/Containers/com.amazon.Kindle/Data/Library/Application Support/Kindle/My Kindle Content"
        )
        local copied=false
        for kindle_mac_dir in "${kindle_mac_dirs[@]}"; do
            if [ -d "$kindle_mac_dir" ]; then
                # Copy the complete directory structure from the emulator pull.
                # The Android Kindle app stores books in ASIN-named subdirectories that
                # also contain .ticr DRM vouchers and .ast license files — Epubor needs
                # these alongside the .kfx/.azw book files.
                echo "Syncing book directory tree to: $kindle_mac_dir"
                # rsync preserves subdirectory structure; fall back to cp -r if unavailable
                if command_exists rsync; then
                    rsync -a --ignore-existing "$local_books_dir/" "$kindle_mac_dir/" 2>/dev/null || true
                else
                    cp -Rn "$local_books_dir/." "$kindle_mac_dir/" 2>/dev/null || true
                fi
                echo ""
                echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
                echo -e "${GREEN}║  Books synced to Kindle for Mac content directory.               ║${NC}"
                echo -e "${GREEN}║                                                                  ║${NC}"
                echo -e "${GREEN}║  Now click Refresh (↻) in Epubor Kindle Converter.              ║${NC}"
                echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
                echo -e "${GREEN}  Path: ${YELLOW}$kindle_mac_dir${NC}"
                echo ""
                copied=true
                break
            fi
        done

        if [ "$copied" = false ]; then
            echo ""
            echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗${NC}"
            echo -e "${YELLOW}║  ⚠️   Kindle for Mac content directory not found.            ║${NC}"
            echo -e "${YELLOW}║  Drag the folder below into Epubor's left panel manually:   ║${NC}"
            echo -e "${YELLOW}║                                                              ║${NC}"
            printf "${YELLOW}║  %-62s║${NC}\n" "$local_books_dir"
            echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════╝${NC}"
            echo ""
            open "$local_books_dir"
        fi
    fi
}

# Optional: convert EPUB output files to PDF using Calibre's ebook-convert.
# Calibre is the gold-standard free tool for epub→pdf on macOS.
# Install: brew install --cask calibre
convert_epub_to_pdf() {
    # Locate ebook-convert (Calibre CLI)
    local ebook_convert
    if command_exists ebook-convert; then
        ebook_convert=$(command -v ebook-convert)
    elif [ -x "/Applications/calibre.app/Contents/MacOS/ebook-convert" ]; then
        ebook_convert="/Applications/calibre.app/Contents/MacOS/ebook-convert"
    else
        echo -e "${YELLOW}Calibre not found – skipping automatic EPUB→PDF conversion.${NC}"
        echo "  Best method to convert EPUB to PDF:  Install Calibre and run:"
        echo "    brew install --cask calibre"
        echo "    ebook-convert book.epub book.pdf"
        echo ""
        echo -e "${GREEN}Conversion complete! Find your books in Epubor's output folder.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Calibre found at: $ebook_convert${NC}"
    echo ""

    # Ask user where Epubor saved the converted EPUB files
    local default_epub_dir="$HOME/Documents/Epubor/My Kindle Books"
    echo "Where are the EPUB files from Epubor?"
    echo "  Default: $default_epub_dir"
    read -p "Press Enter to use default or type a path: " epub_dir
    epub_dir="${epub_dir:-$default_epub_dir}"

    if [ ! -d "$epub_dir" ]; then
        echo -e "${YELLOW}Directory not found: $epub_dir${NC}"
        echo "Skipping automatic PDF conversion."
        return 0
    fi

    local pdf_dir="$epub_dir/PDF"
    mkdir -p "$pdf_dir"

    local count=0
    while IFS= read -r -d '' epub_file; do
        local base
        base=$(basename "$epub_file" .epub)
        local pdf_file="$pdf_dir/$base.pdf"
        if [ -f "$pdf_file" ]; then
            echo -e "${GREEN}  Already exists: $base.pdf${NC}"
            continue
        fi
        echo "  Converting: $base.epub → $base.pdf"
        "$ebook_convert" "$epub_file" "$pdf_file" \
            --paper-size a4 \
            --margin-top 20 --margin-bottom 20 \
            --margin-left 20 --margin-right 20 \
            2>/dev/null && echo -e "${GREEN}    Done.${NC}" || echo -e "${RED}    Failed.${NC}"
        count=$((count + 1))
    done < <(find "$epub_dir" -maxdepth 1 -name "*.epub" -print0)

    if [ "$count" -eq 0 ]; then
        echo "No EPUB files found in: $epub_dir"
        echo "  (Books may be in a sub-folder; run ebook-convert manually if needed)"
    else
        echo ""
        echo -e "${GREEN}PDF files saved to: $pdf_dir${NC}"
        open "$pdf_dir"
    fi
}

# Main guided process
main() {
    check_apple_silicon
    check_prerequisites
    setup_directories
    download_files

    # ── Step 0: Ensure a compatible AVD exists ───────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 0: Verify / Create Compatible Android Emulator AVD ===${NC}"
    create_compatible_avd || true   # non-fatal; user may have a compatible AVD already

    # ── Step 1: Boot emulator ────────────────────────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 1: Launch Android Emulator ===${NC}"
    launch_emulator
    check_emulator_compatibility
    setup_epubor_port_forward

    # ── Step 2: Install & open Kindle ───────────────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 2: Install Kindle APK ===${NC}"
    install_kindle_apk

    # ── Step 3: Start Epubor BEFORE any book downloads ──────────────────────
    # CRITICAL: Epubor must be running to capture DRM keys during download.
    echo ""
    echo -e "${BLUE}=== Step 3: Launch Epubor Kindle Converter ===${NC}"
    launch_epubor
    # Epubor pushes its server to the emulator after launch; wait for it then forward port
    retry_epubor_port_forward

    # ── Step 4: Sign in to Kindle ────────────────────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 4: Sign in to Kindle (emulator) ===${NC}"
    echo -e "${YELLOW}In the Kindle app now open in the emulator:${NC}"
    echo "  1. Sign in with your Amazon account."
    echo "  2. Do NOT tap any book covers yet."
    echo ""
    read -p "Signed in to Kindle? Press Enter to continue..." -r

    # ── Step 5: Download books in emulator ──────────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 5: Download Books in Emulator ===${NC}"
    echo -e "${YELLOW}In the Kindle app (emulator):${NC}"
    echo "  1. Go to your Library."
    echo "  2. Tap each book cover and WAIT for it to fully download"
    echo "     (progress bar disappears and a ✓ appears on the cover)."
    echo "  3. Check the 'Downloaded' tab to confirm."
    echo ""
    echo -e "${RED}Do NOT close Epubor while downloading.${NC}"
    echo ""
    read -p "Books fully downloaded? Press Enter to continue..." -r

    # ── Step 6: Sync books from emulator & refresh Epubor ───────────────────
    echo ""
    echo -e "${BLUE}=== Step 6: Sync Book Files from Emulator ===${NC}"
    sync_kindle_books

    echo ""
    echo -e "${YELLOW}Now click the Refresh (↻) button in Epubor Kindle Converter.${NC}"
    echo "Your downloaded books should appear in the left panel."
    echo ""
    read -p "Books visible in Epubor? Press Enter to continue..." -r

    # ── Step 7: Convert in Epubor ────────────────────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 7: Convert Books in Epubor ===${NC}"
    echo "In Epubor Kindle Converter:"
    echo "  1. Drag books from the left panel to the right panel."
    echo "  2. Choose output format (EPUB recommended for best quality)."
    echo "  3. Click Convert."
    echo ""
    read -p "Books converted in Epubor? Press Enter to continue..." -r

    # ── Step 8: Optional EPUB → PDF via Calibre ──────────────────────────────
    echo ""
    echo -e "${BLUE}=== Step 8: Optional EPUB to PDF Conversion ===${NC}"
    convert_epub_to_pdf
}

# Run main function
main "$@"