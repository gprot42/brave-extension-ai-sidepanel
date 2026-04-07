#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

VERSION="$(head -1 version.md | tr -d '[:space:]')"

if [ -z "$VERSION" ]; then
  echo "ERROR: version.md is empty"
  exit 1
fi

echo "Syncing version ${VERSION} across project..."

# package.json
sed -i '' "s/\"version\": \".*\"/\"version\": \"${VERSION}\"/" package.json

# src-tauri/tauri.conf.json
sed -i '' "s/\"version\": \".*\"/\"version\": \"${VERSION}\"/" src-tauri/tauri.conf.json

# src-tauri/Cargo.toml — only the package version line (line 3)
sed -i '' "3s/version = \".*\"/version = \"${VERSION}\"/" src-tauri/Cargo.toml

echo "Done — all files set to v${VERSION}"
