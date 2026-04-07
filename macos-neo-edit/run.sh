#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="$(head -1 version.md | tr -d '[:space:]')"
echo "Neo Edit v${VERSION} — starting dev server..."

bun run dev
