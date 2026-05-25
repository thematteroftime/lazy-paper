#!/usr/bin/env bash
# Docker wrapper for PDFFigures 2. Host requires only `docker`.
#   Input:  $1 = path to PDF (absolute or relative)
#   Output: prints JSON array to stdout (figures/captions/regions/figType)
#
# The image must be built first:
#   docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .
set -euo pipefail

PDF="${1:?usage: pdffigures2.sh <pdf>}"
PDF_ABS="$(cd "$(dirname "$PDF")" && pwd)/$(basename "$PDF")"
PDF_DIR="$(dirname "$PDF_ABS")"
PDF_NAME="$(basename "$PDF_ABS")"

OUT_DIR="$(mktemp -d -t pf2-XXXXXX)"
trap 'rm -rf "$OUT_DIR"' EXIT

# `-d /out/meta_` writes <prefix><pdfname>.json with figure data; `-q` quiets logs.
# We discard the stdout of `docker run` (verbose info logging) and read the JSON file.
docker run --rm \
    -v "$PDF_DIR:/work:ro" \
    -v "$OUT_DIR:/out" \
    lazy-paper/pdffigures2:0.1.0 \
    "/work/$PDF_NAME" -d /out/meta_ -q >/dev/null 2>&1 || {
    echo "[pdffigures2.sh] docker run failed — check that the image exists" >&2
    echo "[pdffigures2.sh] build with: docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 ." >&2
    exit 1
}

# pdffigures2 names the JSON as <prefix><pdf-stem-without-suffix>.json
cat "$OUT_DIR"/meta_*.json 2>/dev/null || echo "[]"
