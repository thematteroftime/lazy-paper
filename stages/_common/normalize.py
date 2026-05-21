"""OCR + LaTeX text normalization for substring/fuzzy match.

Source PDFs OCR into mixed forms — `W_{rec}` may appear as
`$W _ { \\mathrm { rec } }$` with OCR spaces around digits like
`5 . 0 0`. Substring-matching the LLM's verbatim quote against the
raw OCR string loses to whitespace divergence. This helper collapses
both quirks symmetrically on both sides of the match.

Used by:
- stages/s08_section_compose/structured.py — verifier gate
- stages/s08_section_compose/reviewer.py — regex critic value lookup
- scripts/evaluate.py — citation-accuracy scoring
"""
from __future__ import annotations

import re

_LATEX_CMD = re.compile(r"\\[a-zA-Z]+")
_LATEX_DELIM = re.compile(r"[\$\{\}]")
_OCR_DIGIT_SPACE = re.compile(r"(?<=[\d.])\s+(?=[\d.])")
_WHITESPACE = re.compile(r"\s+")


def normalize_ocr_latex(text: str, *, lowercase: bool = True) -> str:
    """Return `text` with LaTeX commands stripped + OCR digit-spacing folded.

    - `\\mathrm`, `\\frac`, ... → space (preserves arg via separate run when
      callers want the inner text — most match paths don't care)
    - `$ { }` → space
    - any whitespace between digits-and-dots is collapsed: `5 . 0 0` → `5.00`
      (applied to fixed-point so 5+ char chains fully fold)
    - all whitespace collapsed to single spaces
    - lowercased by default for case-insensitive substring tests
    """
    s = _LATEX_CMD.sub(" ", text)
    s = _LATEX_DELIM.sub(" ", s)
    prev = None
    while prev != s:
        prev, s = s, _OCR_DIGIT_SPACE.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s.lower() if lowercase else s
