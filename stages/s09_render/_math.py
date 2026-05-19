"""Math/LaTeX normalization utility for PPT text content.

Converts LaTeX math expressions to Unicode equivalents so that
PPT text boxes display properly without LaTeX renderer.
"""
from __future__ import annotations

import re

_GREEK_LATEX: dict[str, str] = {
    r"\\alpha":    "α", r"\\beta":     "β", r"\\gamma":    "γ", r"\\delta":    "δ",
    r"\\epsilon":  "ε", r"\\varepsilon":"ε", r"\\zeta":     "ζ", r"\\eta":      "η",
    r"\\theta":    "θ", r"\\iota":     "ι", r"\\kappa":    "κ", r"\\lambda":   "λ",
    r"\\mu":       "μ", r"\\nu":       "ν", r"\\xi":       "ξ", r"\\pi":       "π",
    r"\\rho":      "ρ", r"\\sigma":    "σ", r"\\tau":      "τ", r"\\phi":      "φ",
    r"\\chi":      "χ", r"\\psi":      "ψ", r"\\omega":    "ω",
    r"\\Alpha":    "Α", r"\\Beta":     "Β", r"\\Gamma":    "Γ", r"\\Delta":    "Δ",
    r"\\Epsilon":  "Ε", r"\\Eta":      "Η", r"\\Theta":    "Θ", r"\\Lambda":   "Λ",
    r"\\Mu":       "Μ", r"\\Pi":       "Π", r"\\Sigma":    "Σ", r"\\Phi":      "Φ",
    r"\\Psi":      "Ψ", r"\\Omega":    "Ω",
    r"\\sum":      "Σ", r"\\int":      "∫", r"\\partial":  "∂", r"\\infty":    "∞",
    r"\\to":       "→", r"\\rightarrow":"→", r"\\leftarrow":"←", r"\\leftrightarrow":"↔",
    r"\\le":       "≤", r"\\leq":      "≤", r"\\ge":       "≥", r"\\geq":      "≥",
    r"\\neq":      "≠", r"\\approx":   "≈", r"\\sim":      "∼",
    r"\\pm":       "±", r"\\times":    "×", r"\\cdot":     "·", r"\\div":      "÷",
}

# Superscript Unicode map (digits + common symbols)
_SUPER_MAP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")

# Subscript Unicode map (digits + common letters)
_SUB_MAP = str.maketrans("0123456789+-=()aeiouvxh", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒᵤᵥₓₕ")

# Reverse Unicode-subscript → ASCII map.
# Covers U+2080-U+209C (digits/operators/Latin) and the modifier-letter
# subscripts in U+1D62-U+1D6A. PPT viewers commonly lack glyphs for the rare
# Latin subscripts when the body font is CJK; we fall back to plain ASCII so
# `aₚₕₒₜ` reads as `a_phot` instead of `aphot` (glyph dropped) or □□□□.
_UNICODE_SUB_TO_ASCII: dict[str, str] = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j",
    "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o",
    "ₚ": "p", "ᵣ": "r", "ₛ": "s", "ₜ": "t", "ᵤ": "u",
    "ᵥ": "v", "ₓ": "x",
}
_UNICODE_SUB_CHARS = "".join(_UNICODE_SUB_TO_ASCII.keys())
_UNICODE_SUB_RUN_RE = re.compile(f"([{_UNICODE_SUB_CHARS}]+)")


def _collapse_unicode_subscripts(text: str) -> str:
    """Collapse runs of Unicode subscript chars to a single `_<plain>` token.

    Rationale: when the LLM emits multi-letter subscripts as Unicode
    (`aₚₕₒₜ`), PPT viewers often lack glyphs in the active CJK body font and
    drop them silently. Rendering as `a_phot` is uglier but font-portable.
    Single-digit subscripts adjacent to digits (e.g. `H₂O`) are common and
    well-supported, so we only collapse runs that contain at least one
    Latin-letter subscript — pure digit runs (`H₂O`, `T_m`) keep their
    Unicode form.
    """
    def repl(m: "re.Match[str]") -> str:
        run = m.group(1)
        if not any(c.isalpha() for c in (_UNICODE_SUB_TO_ASCII[c] for c in run)):
            return run  # pure digits/ops — leave Unicode in place
        ascii_run = "".join(_UNICODE_SUB_TO_ASCII[c] for c in run)
        return f"_{ascii_run}"

    return _UNICODE_SUB_RUN_RE.sub(repl, text)


def normalize_math(text: str) -> str:
    """Convert LaTeX math expressions in *text* to Unicode for PPT rendering."""
    if not text:
        return text
    for latex_pat, unicode_char in _GREEK_LATEX.items():
        text = re.sub(latex_pat + r"(?![a-zA-Z])", unicode_char, text)
    text = re.sub(r"\^\{([^}]+)\}", lambda m: m.group(1).translate(_SUPER_MAP), text)
    text = re.sub(r"\^([0-9a-zA-Z+\-])", lambda m: m.group(1).translate(_SUPER_MAP), text)
    text = re.sub(r"_\{([^}]+)\}", lambda m: m.group(1).translate(_SUB_MAP), text)
    text = re.sub(r"_([0-9a-zA-Z+\-])", lambda m: m.group(1).translate(_SUB_MAP), text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    # Strip LaTeX inline/display math delimiters
    text = re.sub(r"\\\(\s*", "", text)   # \(
    text = re.sub(r"\s*\\\)", "", text)   # \)
    text = re.sub(r"\\\[\s*", "", text)   # \[
    text = re.sub(r"\s*\\\]", "", text)   # \]
    text = text.replace(r"\%", "%").replace(r"\&", "&")
    text = _collapse_unicode_subscripts(text)
    # v1.3.1: rare Unicode dashes/spaces/punctuation that the default PPT body
    # fonts (Crimson Pro / Songti) lack glyphs for — they render as squares.
    # Map back to ASCII equivalents.
    for ch, repl in _EXOTIC_PUNCT_FALLBACK.items():
        text = text.replace(ch, repl)
    return text


# v1.3.1: small map of exotic Unicode punctuation that has no glyph in the
# default PPT fonts. Conservatively short — only map the cases we've seen
# in production output.
_EXOTIC_PUNCT_FALLBACK: dict[str, str] = {
    "‑": "-",   # non-breaking hyphen → ASCII hyphen
    "‐": "-",   # hyphen → ASCII hyphen
    " ": " ",   # narrow no-break space → regular space
    " ": " ",   # no-break space → regular space (cosmetic)
    " ": " ",   # thin space → regular space
    " ": " ",   # figure space → regular space
    "​": "",    # zero-width space → drop
}
