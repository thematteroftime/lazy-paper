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


# Sentinels wrapping inline-math segments through the Unicode pass; DOCX /
# HTML / PDF render them in italic, PPTX drops the markers.
MATH_OPEN = "\x01"
MATH_CLOSE = "\x02"


def normalize_math(text: str, *, mark_inline: bool = False) -> str:
    """Convert LaTeX math expressions in *text* to Unicode.

    When ``mark_inline=True``, inline math delimiters ``\\(...\\)``,
    ``\\[...\\]``, and ``$...$`` are replaced with the MATH_OPEN/MATH_CLOSE
    sentinels so the DOCX/HTML/PDF renderers can render those segments in
    italic — giving formulas visual distinction from surrounding prose
    without touching the LLM prompts.

    The default is ``mark_inline=False`` so PPTX and plain-text callers get
    a clean flat string. DOCX/HTML/PDF go through ``builder.DocumentBuilder``
    which passes ``mark_inline=True`` explicitly.
    """
    if not text:
        return text
    # Strip / convert LaTeX commands before the Unicode pass so the
    # sub/superscript stage doesn't translate command letters into garbled
    # glyphs. Order matters: accents unwrap `\dot{q}` braces before \frac
    # walks brace pairs.
    text = re.sub(r"\\(?:text|mathrm|mathbf|mathit|mathsf|mathcal|operatorname)"
                  r"\{([^{}]+)\}", r"\1", text)
    text = re.sub(r"\\(?:Big|big|bigg|Bigg|left|right)(?![a-zA-Z])", "", text)
    text = re.sub(r"\\[,;:!\\ ]", " ", text)
    for cmd, combining in (("dot", "̇"), ("hat", "̂"),
                           ("bar", "̄"), ("tilde", "̃"),
                           ("vec", "⃗")):
        text = re.sub(rf"\\{cmd}\{{([^{{}}])\}}", rf"\1{combining}", text)
    text = re.sub(r"\\(exp|sin|cos|tan|log|ln|max|min|arg|sup|inf"
                  r"|lim|det|gcd|sinh|cosh|tanh)(?![a-zA-Z])", r"\1", text)
    for latex_pat, unicode_char in _GREEK_LATEX.items():
        text = re.sub(latex_pat + r"(?![a-zA-Z])", unicode_char, text)
    # Sub/superscript translation. If any character in `_{…}` / `^{…}` lacks
    # a Unicode glyph, fall back to ASCII `_content` so the run renders as a
    # coherent token instead of fragmenting (e.g. `_{motion}` would otherwise
    # become `mₒtᵢₒn` → `Rm_ot_ion` after the collapse pass below).
    def _braced_super(m):
        s = m.group(1)
        translated = s.translate(_SUPER_MAP)
        return translated if translated != s and all(c in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾" for c in translated) else f"^{s}"
    def _braced_sub(m):
        s = m.group(1)
        translated = s.translate(_SUB_MAP)
        return f"_{s}" if any(c.isalpha() and c.isascii() for c in translated) else translated
    def _single(map_, prefix):
        def repl(m):
            ch = m.group(1)
            tr = ch.translate(map_)
            return tr if tr != ch else f"{prefix}{ch}"
        return repl
    text = re.sub(r"\^\{([^}]+)\}", _braced_super, text)
    text = re.sub(r"\^([0-9a-zA-Z+\-])", _single(_SUPER_MAP, "^"), text)
    text = re.sub(r"_\{([^}]+)\}", _braced_sub, text)
    text = re.sub(r"_([0-9a-zA-Z+\-])", _single(_SUB_MAP, "_"), text)
    # \frac{a}{b} → (a)/(b). Subscripts are gone, so brace pairs are clean.
    while True:
        new = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
                     r"(\1)/(\2)", text)
        if new == text:
            break
        text = new

    if mark_inline:
        # Wrap math with sentinels for styled-run renderers (\[..\] first so
        # the \(..\) regex doesn't partial-match).
        text = re.sub(
            r"\\\[\s*(.+?)\s*\\\]",
            lambda m: f"{MATH_OPEN}{m.group(1)}{MATH_CLOSE}",
            text, flags=re.DOTALL,
        )
        text = re.sub(
            r"\\\(\s*(.+?)\s*\\\)",
            lambda m: f"{MATH_OPEN}{m.group(1)}{MATH_CLOSE}",
            text, flags=re.DOTALL,
        )
        text = re.sub(
            r"\$([^$\n]+)\$",
            lambda m: f"{MATH_OPEN}{m.group(1)}{MATH_CLOSE}",
            text,
        )
    else:
        # Flat-string callers (PPTX) — strip delimiters entirely.
        text = re.sub(r"\$([^$]+)\$", r"\1", text)
        text = re.sub(r"\\\(\s*", "", text)
        text = re.sub(r"\s*\\\)", "", text)
        text = re.sub(r"\\\[\s*", "", text)
        text = re.sub(r"\s*\\\]", "", text)

    text = text.replace(r"\%", "%").replace(r"\&", "&")
    text = _collapse_unicode_subscripts(text)
    # v1.3.1: rare Unicode dashes/spaces/punctuation that the default PPT body
    # fonts (Crimson Pro / Songti) lack glyphs for — they render as squares.
    # Map back to ASCII equivalents.
    for ch, repl in _EXOTIC_PUNCT_FALLBACK.items():
        text = text.replace(ch, repl)
    return text


# Recognises ``**bold**`` and ``\x01math\x02`` segments for DOCX/HTML run
# splitting. Nested markers fall through — the LLM keeps them disjoint.
_RUN_RE = re.compile(
    r"(?P<bold>\*\*(.+?)\*\*)"
    r"|(?P<math>" + MATH_OPEN + r"(.+?)" + MATH_CLOSE + r")",
    re.DOTALL,
)


def iter_html_runs(raw_text: str):
    """Yield ``(kind, payload)`` tuples for HTML rendering of raw LLM output.

    Unlike :func:`iter_runs` (which works on the normalize_math output),
    this consumes the **original** LLM text and preserves LaTeX source so
    the HTML renderer can pass it to KaTeX via ``data-tex``.

    Yields ``(kind, payload)`` where kind ∈ ``{"plain", "bold", "math_inline",
    "math_display"}``. For math kinds the payload is the raw LaTeX source
    (no delimiters). For ``plain`` and ``bold`` it's the text segment.

    Recognized:
        ``**bold**``                       → ("bold", "bold")
        ``\\[display\\]`` or ``$$..$$``   → ("math_display", "tex")
        ``\\(inline\\)`` or ``$..$``       → ("math_inline", "tex")
    """
    if not raw_text:
        return
    pat = re.compile(
        r"(?P<bold>\*\*(.+?)\*\*)"
        r"|(?P<dmath>\\\[\s*(.+?)\s*\\\]|\$\$\s*(.+?)\s*\$\$)"
        r"|(?P<imath>\\\(\s*(.+?)\s*\\\)|\$([^$\n]+?)\$)",
        re.DOTALL,
    )
    pos = 0
    for m in pat.finditer(raw_text):
        if m.start() > pos:
            yield ("plain", raw_text[pos:m.start()])
        if m.group("bold") is not None:
            yield ("bold", m.group(2))
        elif m.group("dmath") is not None:
            yield ("math_display", m.group(4) or m.group(5))
        else:  # imath
            yield ("math_inline", m.group(7) or m.group(8))
        pos = m.end()
    if pos < len(raw_text):
        yield ("plain", raw_text[pos:])


def iter_runs(text: str):
    """Yield ``(segment, style)`` tuples for paragraph text.

    Style is ``"plain"``, ``"bold"``, or ``"italic"``. Renderers that don't
    support multiple runs can fall back to ``strip_math_markers(text)`` and
    a regex strip of ``**`` markers.

    As a safety net, any stray MATH sentinels in returned segments are
    stripped — they should never appear (a balanced pair is consumed by the
    regex), but a malformed input must not leak control chars into XML
    output (python-docx) or HTML.
    """
    if not text:
        return

    def _clean(s: str) -> str:
        return s.replace(MATH_OPEN, "").replace(MATH_CLOSE, "")

    pos = 0
    for m in _RUN_RE.finditer(text):
        if m.start() > pos:
            yield (_clean(text[pos:m.start()]), "plain")
        if m.group("bold") is not None:
            yield (_clean(m.group(2)), "bold")
        else:
            yield (_clean(m.group(4)), "italic")
        pos = m.end()
    if pos < len(text):
        yield (_clean(text[pos:]), "plain")


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
