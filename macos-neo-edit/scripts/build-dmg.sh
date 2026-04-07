#!/bin/bash
set -euo pipefail

APP_NAME="Neo Edit"
BUNDLE_ID="com.neoedit.app"
SIGNING_IDENTITY="${SIGNING_IDENTITY:-Developer ID Application}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

VERSION="$(head -1 version.md | tr -d '[:space:]')"
echo "==> Building Neo Edit v${VERSION}..."
bun run build:vite
cargo tauri build 2>&1

APP_PATH="src-tauri/target/release/bundle/macos/Neo Edit.app"

if [ ! -d "$APP_PATH" ]; then
  echo "ERROR: App bundle not found at: $APP_PATH"
  exit 1
fi

echo "==> Signing app..."
codesign --deep --force --verify --verbose \
  --sign "$SIGNING_IDENTITY" \
  --options runtime \
  "$APP_PATH"

echo "==> Verifying signature..."
codesign --verify --verbose "$APP_PATH"

mkdir -p dist

echo "==> Creating DMG..."
hdiutil create -volname "$APP_NAME" \
  -srcfolder "$APP_PATH" \
  -ov -format UDZO \
  "dist/NeoEdit.dmg"

echo "==> Signing DMG..."
codesign --sign "$SIGNING_IDENTITY" "dist/NeoEdit.dmg"

echo ""
echo "==> Done! DMG at dist/NeoEdit.dmg"
echo ""
echo "To notarize, run:"
echo "  xcrun notarytool submit dist/NeoEdit.dmg --apple-id YOUR_ID --team-id YOUR_TEAM --password YOUR_PASSWORD --wait"
