#!/usr/bin/env python3
"""Fetch KaTeX 0.16.9 assets (CSS + JS + woff2 fonts) into the templates vendor
directory so HtmlRenderer can inline them when LAZY_PAPER_INLINE_KATEX=1.

Idempotent: existing files are skipped unless --force is passed.

Usage:
    uv run python scripts/fetch_katex.py
    uv run python scripts/fetch_katex.py --force
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path


KATEX_VERSION = "0.16.9"
BASE_URL = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist"

VENDOR_DIR = (
    Path(__file__).resolve().parent.parent
    / "stages" / "s09_render" / "templates" / "vendor" / "katex"
)


def _fetch(url: str, dest: Path, force: bool = False) -> None:
    if dest.exists() and not force:
        print(f"  [skip] {dest.relative_to(VENDOR_DIR.parent.parent.parent)} (exists)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [pull] {url} → {dest.relative_to(VENDOR_DIR.parent.parent.parent)}")
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if files already exist")
    args = ap.parse_args(argv)

    print(f"Fetching KaTeX {KATEX_VERSION} into {VENDOR_DIR}")
    # Core CSS + JS
    _fetch(f"{BASE_URL}/katex.min.css", VENDOR_DIR / "katex.min.css", args.force)
    _fetch(f"{BASE_URL}/katex.min.js", VENDOR_DIR / "katex.min.js", args.force)

    # woff2 fonts referenced by katex.min.css
    css = (VENDOR_DIR / "katex.min.css").read_text(encoding="utf-8")
    font_refs = sorted(set(re.findall(r"fonts/(KaTeX_[^.)]+\.woff2)", css)))
    fonts_dir = VENDOR_DIR / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    for fname in font_refs:
        _fetch(f"{BASE_URL}/fonts/{fname}", fonts_dir / fname, args.force)

    total_bytes = sum(p.stat().st_size for p in VENDOR_DIR.rglob("*"))
    print(f"Done. Vendor dir size: {total_bytes / 1024:.1f} KB"
          f" ({len(font_refs)} fonts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
