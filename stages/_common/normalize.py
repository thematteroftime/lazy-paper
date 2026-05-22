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
import unicodedata

_LATEX_CMD = re.compile(r"\\[a-zA-Z]+")
_LATEX_DELIM = re.compile(r"[\$\{\}]")
# v1.10 (Auditor 2 cycle 2 BS3): `\%`, `\&`, `\_`, `\^`, `\$` escape — strip
# the leading backslash so the rendered char matches the LLM's quote which
# has no backslash. Mirrors `reviewer.py::_LATEX_NOISE`.
_LATEX_ESCAPE = re.compile(r"\\(?=[%$&_^{}])")
_OCR_DIGIT_SPACE = re.compile(r"(?<=[\d.])\s+(?=[\d.])")
_WHITESPACE = re.compile(r"\s+")
# v1.10 (Auditor 2 cycle 2 BS4 sub): Unicode dashes that NFKD doesn't fold
# back to ASCII `-`. LLM quotes use the ASCII hyphen; OCR uses U+2212
# (minus sign), U+2013 (en-dash), U+2014 (em-dash).
_UNICODE_DASH = re.compile(r"[−–—]")


def normalize_ocr_latex(text: str, *, lowercase: bool = True) -> str:
    """Return `text` with LaTeX commands stripped + OCR digit-spacing folded.

    - `\\mathrm`, `\\frac`, ... → space (preserves arg via separate run when
      callers want the inner text — most match paths don't care)
    - `$ { }` → space
    - `\\%`, `\\&`, `\\_`, ... → strip the leading backslash (LaTeX escape
      sequences whose rendered form has no backslash)
    - Unicode compatibility: `³ ₂ ⁻¹` decompose to ASCII via NFKD so they
      match LLM quotes that use plain digits/letters
    - any whitespace between digits-and-dots is collapsed: `5 . 0 0` → `5.00`
      (applied to fixed-point so 5+ char chains fully fold)
    - all whitespace collapsed to single spaces
    - lowercased by default for case-insensitive substring tests
    """
    # v1.10 (Auditor 2 cycle 2 BS4): NFKD decomposes Unicode super/subscript
    # digits (`³` → `3`, `₂` → `2`) and ligatures so `J/cm³` matches the
    # LLM's `J/cm3`. Does NOT touch Greek letters (α/β/π preserved).
    s = unicodedata.normalize("NFKD", text)
    s = _UNICODE_DASH.sub("-", s)
    s = _LATEX_ESCAPE.sub("", s)
    s = _LATEX_CMD.sub(" ", s)
    s = _LATEX_DELIM.sub(" ", s)
    prev = None
    while prev != s:
        prev, s = s, _OCR_DIGIT_SPACE.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s.lower() if lowercase else s
