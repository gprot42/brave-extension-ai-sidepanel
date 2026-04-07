# Epubor Kindle Converter Automation Script

This project provides an automation script to streamline the process of removing Kindle DRM on macOS using the Android emulator method with Epubor Kindle Converter v1.0.1.148, as described in the official guide.

## Overview

The script automates:
- Apple Silicon (arm64) verification
- Prerequisite checks (Android Studio, Epubor installation)
- **Automatic creation of a compatible Android Virtual Device (API 30, Google APIs)**
- Downloading necessary files (Kindle APK, Epubor installer)
- Launching applications in the correct order
- Installing the Kindle APK onto the emulator via `adb`
- Launching the Kindle app automatically after install
- Setting up `adb` port forwarding so Epubor's Frida backend can reach the emulator
- Syncing downloaded book files from the emulator to Kindle for Mac's content directory
- Interactive guidance for sign-in and book download steps
- Ctrl-C handling with automatic cleanup of temporary files

---

## ⚠️ Critical Android Emulator Requirement

Epubor Kindle Converter uses [Frida](https://frida.re/) internally to extract DRM keys by attaching to Android's `system_server` process at runtime.  
This **only works with a specific Android emulator configuration**:

| Requirement | Value | Why |
|---|---|---|
| **Android API level** | **30 (Android 11)** | Frida supports API 21–33; API 34+ blocks injection |
| **System image type** | **Google APIs** (NOT Google Play) | Google Play images are locked — `adb root` is blocked |
| **Architecture** | **arm64-v8a** | Required on Apple Silicon Macs |
| **Device profile** | Pixel 6 Pro (recommended) | Any device works, but Pixel 6 Pro is well-tested |

### ❌ Images that do NOT work

| Image | Problem |
|---|---|
| `google_apis_playstore` (any API) | `adb root` blocked; Frida cannot attach |
| `google_apis` at API 34+ | Android 14+ blocks ptrace injection |
| `default` (AOSP) | May lack required Google frameworks |

### ✅ Correct system image package name

```
system-images;android-30;google_apis;arm64-v8a
```

The script will **automatically download this image and create the AVD** (`Epubor_API30_GoogleAPIs`) if it does not already exist.

---

## Requirements

- **macOS on Apple Silicon (arm64)** — Intel Macs are not supported by this script
- **Android Studio** installed (provides `avdmanager`, `sdkmanager`, `emulator`, `adb`)
- **Epubor Kindle Converter** installed and registered (in `/Applications/`)
- Internet connection (for initial downloads)

## Project Structure

| File | Purpose |
|---|---|
| [`01setupavd.sh`](01setupavd.sh) | Creates the required Android AVD (run once before the main script) |
| [`02kindle-drm-automator.sh`](02kindle-drm-automator.sh) | Full DRM automation (boot emulator → install Kindle → sync books) |
| [`README.md`](README.md) | This document |

## Installation

```bash
# 1. Clone/download this repository
git clone <repo-url>
cd app-epubor-kindle-convertor

# 2. Make scripts executable
chmod +x 01setupavd.sh 02kindle-drm-automator.sh

# 3. Create the compatible AVD (once)
./01setupavd.sh

# 4. Run the main automation
./02kindle-drm-automator.sh
```

## Usage

```
Usage: ./02kindle-drm-automator.sh [OPTIONS]

Options:
  --keep-downloads   Do not delete downloaded APK/ZIP files on exit.
  -h, --help         Show this help message.
```

The script guides you through each step interactively.

---

## Step-by-Step Flow

| Step | What the script does |
|---|---|
| 0 | Verifies Apple Silicon; checks for Android Studio / Epubor |
| 1 | Creates/verifies the `Epubor_API30_GoogleAPIs` AVD (auto-downloads system image) |
| 2 | Downloads `kindle.apk` and Epubor installer if not already present |
| 3 | Boots the emulator; waits for `sys.boot_completed=1` |
| 4 | Checks API level and runs `adb root`; sets up `tcp:27042` port forward for Frida |
| 5 | Installs Kindle APK via `adb install`; launches Kindle app |
| 6 | Launches Epubor Kindle Converter; waits for Frida server to start on emulator |
| 7 | Prompts user to sign in to Kindle |
| 8 | Prompts user to download books in the Kindle emulator app |
| 9 | Pulls book files from emulator; copies to `~/Library/Application Support/Kindle/My Kindle Content` |
| 10 | Prompts user to click Refresh in Epubor |
| 11 | Guides user through conversion |

---

## Automatable vs Manual Steps

**Automated:**
- Apple Silicon check
- AVD creation and system image download
- File downloads (APK, Epubor installer)
- Emulator launch and boot wait
- API level and `adb root` compatibility check
- `adb` port forwarding (port 27042 for Frida)
- Kindle APK install via `adb install`
- Kindle app launch in emulator
- Epubor launch
- Frida port-forward retry after Epubor pushes its server
- Book sync from emulator to Mac
- Temp file cleanup on exit / Ctrl-C

**Manual (Guided):**
- Signing into Amazon account in Kindle (emulator)
- Tapping book covers to download them
- Clicking Refresh in Epubor
- Dragging books to convert panel and clicking Convert

---

## Cleanup

On exit (normal or Ctrl-C) the script removes:
- `~/Downloads/epubor-kindle/emulator.log`
- `~/Downloads/epubor-kindle/kindle-books/` (raw pulled book files — already copied to Kindle for Mac)

Use `--keep-downloads` to skip cleanup.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Books don't appear in Epubor after Refresh | Ensure the AVD uses `google_apis` (not `google_apis_playstore`) at API 30; `adb root` must succeed |
| `adb root` says "not allowed on production builds" | Delete the AVD; re-create with `system-images;android-30;google_apis;arm64-v8a` |
| Emulator exits immediately | Check `~/Downloads/epubor-kindle/emulator.log` for errors |
| Kindle APK install fails | Re-run the script; the APK will be re-downloaded |
| DRM key not found in Epubor | Epubor must be running **before** books are downloaded; delete and re-download the book |

Reference: [Epubor official guide](https://www.epubor.com/how-to-set-up-android-emulator-on-mac.html)
