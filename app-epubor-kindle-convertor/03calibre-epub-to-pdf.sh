#!/bin/bash

# 03epub-to-pdf.sh
# Converts EPUB files to PDF using Calibre's ebook-convert.
#
# Best tool for epub→pdf on macOS:  Calibre (free, open source)
#   Install:  brew install --cask calibre
#   Docs:     https://manual.calibre-ebook.com/generated/en/ebook-convert.html
#
# Usage:
#   ./03epub-to-pdf.sh [INPUT_DIR] [OUTPUT_DIR]
#
#   INPUT_DIR   Directory containing .epub files (default: ~/Documents/Epubor/My Kindle Books)
#   OUTPUT_DIR  Where to save PDFs               (default: INPUT_DIR/PDF)

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          03calibre-epub-to-pdf — EPUB to PDF via Calibre         ║${NC}"
echo -e "${BLUE}║          Powered by Calibre ebook-convert                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Locate ebook-convert ─────────────────────────────────────────────────────
find_ebook_convert() {
    # Standard PATH
    if command -v ebook-convert >/dev/null 2>&1; then
        command -v ebook-convert; return 0
    fi
    # Calibre macOS app bundle
    local bundle="/Applications/calibre.app/Contents/MacOS/ebook-convert"
    [ -x "$bundle" ] && echo "$bundle" && return 0
    return 1
}

EBOOK_CONVERT=$(find_ebook_convert || true)

if [ -z "$EBOOK_CONVERT" ]; then
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  CALIBRE: NOT INSTALLED                                          ║${NC}"
    echo -e "${RED}║                                                                  ║${NC}"
    echo -e "${RED}║  Calibre is required for EPUB to PDF conversion.                 ║${NC}"
    echo -e "${RED}║                                                                  ║${NC}"
    echo -e "${RED}║  Install with Homebrew:                                          ║${NC}"
    echo -e "${RED}║    brew install --cask calibre                                   ║${NC}"
    echo -e "${RED}║                                                                  ║${NC}"
    echo -e "${RED}║  Or download from: https://calibre-ebook.com/download_osx        ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  CALIBRE: INSTALLED                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo -e "${GREEN}  Path: $EBOOK_CONVERT${NC}"
echo ""

# ── Directories ───────────────────────────────────────────────────────────────
DEFAULT_INPUT="$HOME/Documents/Epubor/My Kindle Books"
INPUT_DIR="${1:-$DEFAULT_INPUT}"
OUTPUT_DIR="${2:-$INPUT_DIR/PDF}"

echo "  Input  : $INPUT_DIR"
echo "  Output : $OUTPUT_DIR"
echo ""

if [ ! -d "$INPUT_DIR" ]; then
    echo -e "${RED}Input directory not found: $INPUT_DIR${NC}"
    echo "Usage: $0 [input-dir] [output-dir]"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# ── Conversion ────────────────────────────────────────────────────────────────
shopt -s nullglob
epub_files=("$INPUT_DIR"/*.epub)

if [ ${#epub_files[@]} -eq 0 ]; then
    echo -e "${YELLOW}No .epub files found in: $INPUT_DIR${NC}"
    echo "Check that Epubor Kindle Converter has converted books to EPUB format."
    exit 0
fi

echo -e "${YELLOW}Found ${#epub_files[@]} EPUB file(s) to convert.${NC}"
echo ""

converted=0
skipped=0
failed=0

for epub_file in "${epub_files[@]}"; do
    raw_base=$(basename "$epub_file" .epub)
    # Strip trailing _1, _2, _3 … numeric suffixes so the same book is not
    # converted multiple times when Epubor produces duplicate copies.
    base=$(echo "$raw_base" | sed 's/_[0-9]\{1,\}$//')
    pdf_file="$OUTPUT_DIR/$base.pdf"

    if [ -f "$pdf_file" ]; then
        echo -e "${GREEN}  [skip] $base.pdf already exists (source: $raw_base.epub)${NC}"
        skipped=$((skipped + 1))
        continue
    fi

    echo -n "  Converting: $base ... "
    if "$EBOOK_CONVERT" "$epub_file" "$pdf_file" \
            --paper-size a4             \
            --margin-top    20          \
            --margin-bottom 20          \
            --margin-left   20          \
            --margin-right  20          \
            --base-font-size 11         \
            --font-size-mapping "8,9,10,12,15,20,30,40" \
            >/dev/null 2>&1; then
        echo -e "${GREEN}done${NC}"
        converted=$((converted + 1))
    else
        echo -e "${RED}FAILED${NC}"
        failed=$((failed + 1))
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Conversion complete!                                            ║${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
printf "${GREEN}║  Converted : %-52s║${NC}\n" "$converted file(s)"
printf "${GREEN}║  Skipped   : %-52s║${NC}\n" "$skipped already existed"
printf "${GREEN}║  Failed    : %-52s║${NC}\n" "$failed file(s)"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}║  Output folder opened in Finder.                                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Output: $OUTPUT_DIR"

open "$OUTPUT_DIR"
