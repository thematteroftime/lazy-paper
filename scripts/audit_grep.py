"""OCR-tolerant grep for audit work.

A plain `grep "17.3"` against MinerU OCR output silently misses values that
the OCR encoded with LaTeX-style char spacing (e.g. `$\\sim 1 7 . 3$`). That
is exactly the cycle-12 v1.11.1 audit miss that triggered the v1.11.2
erratum: three baseline values flagged as "fabricated" in `ali2025_flash`
ch13 turned out to be in the source paper, just spaced by the OCR.

Use this script when auditing model output against an OCR'd paper:

    uv run python scripts/audit_grep.py 17.3 runs/<paper>/s02_clean/doc_*.md

It runs every line through `stages._common.normalize.normalize_ocr_latex`
(the same normalizer the s08 verifier uses), then runs the pattern as a
plain substring match against the normalized form. Hits are printed
`file:line` along with the original (un-normalized) text so you can see
exactly what form the source contained.
"""
from __future__ import annotations

import sys
from pathlib import Path

from stages._common.normalize import normalize_ocr_latex


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        print(f"\nusage: {argv[0]} <pattern> <file_or_glob> [<file>...]", file=sys.stderr)
        return 2
    pattern = normalize_ocr_latex(argv[1])
    if not pattern:
        print(f"empty pattern after normalization: {argv[1]!r}", file=sys.stderr)
        return 2

    paths: list[Path] = []
    for arg in argv[2:]:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("doc_*.md")))
        else:
            paths.append(p)

    hits = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError):
            continue
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            if pattern in normalize_ocr_latex(raw_line):
                hits += 1
                trimmed = raw_line.strip()
                if len(trimmed) > 200:
                    trimmed = trimmed[:200] + "…"
                print(f"{path}:{lineno}: {trimmed}")

    if hits == 0:
        print(f"[audit_grep] no matches for normalized pattern {pattern!r} in {len(paths)} file(s)",
              file=sys.stderr)
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
