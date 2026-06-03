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


# Sentinel markers used to preserve "this was inline math" hints across the
# Unicode normalization pass. Control chars are safe — no LLM output we've
# seen contains them, and renderers can detect/strip them deterministically.
# Renderers that support styled runs (DOCX, HTML, PDF) wrap content between
# these as italic. PPTX strips them via _strip_math_markers().
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
    # ── pre-process LaTeX commands so the Unicode passes below see clean text ──
    # Step 1: text-mode commands (\text{en} → en) — unwrap braces so the
    # subscript pass doesn't translate `\text` letters into garbled subscripts.
    text = re.sub(r"\\(?:text|mathrm|mathbf|mathit|mathsf|mathcal|operatorname)"
                  r"\{([^{}]+)\}", r"\1", text)
    # Step 2: size / spacing macros — purely typographical, drop them.
    text = re.sub(r"\\(?:Big|big|bigg|Bigg|left|right)(?![a-zA-Z])", "", text)
    text = re.sub(r"\\[,;:!\\ ]", " ", text)
    # Step 3: accents BEFORE \frac so inner braces (`\dot{q}`) are unwrapped
    # before the \frac{a}{b} matcher walks the brace pairs.
    for cmd, combining in (("dot", "̇"), ("hat", "̂"),
                           ("bar", "̄"), ("tilde", "̃"),
                           ("vec", "⃗")):
        text = re.sub(rf"\\{cmd}\{{([^{{}}])\}}", rf"\1{combining}", text)
    # Step 4: math function names — drop the leading backslash so they render
    # as plain ASCII (already English words).
    text = re.sub(r"\\(exp|sin|cos|tan|log|ln|max|min|arg|sup|inf"
                  r"|lim|det|gcd|sinh|cosh|tanh)(?![a-zA-Z])", r"\1", text)
    # Step 5: Greek + sub/super first so ``\frac{σ_{en,x}|v|}{...}`` has its
    # inner subscript braces translated away, leaving the \frac pass below
    # with clean brace pairs.
    for latex_pat, unicode_char in _GREEK_LATEX.items():
        text = re.sub(latex_pat + r"(?![a-zA-Z])", unicode_char, text)
    # Sub/superscript translation. When the {…} content has even one
    # character that doesn't have a Unicode subscript/superscript glyph,
    # fall back to ASCII ``_content`` / ``^content`` — otherwise a partial
    # conversion fragments later when ``_collapse_unicode_subscripts`` runs
    # over the mixed-glyph run (e.g. ``_{motion}`` → ``mₒtᵢₒn`` → ``Rm_ot_ion``).
    def _braced_super(m):
        s = m.group(1)
        translated = s.translate(_SUPER_MAP)
        return translated if translated != s and all(c in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾" or c == "" for c in translated) else f"^{s}"
    def _braced_sub(m):
        s = m.group(1)
        translated = s.translate(_SUB_MAP)
        # If translation is incomplete (some chars passed through unchanged),
        # use the ASCII form so renderers show a single coherent token.
        if any(c.isalpha() and c.isascii() for c in translated):
            return f"_{s}"
        return translated
    def _single_sub(m):
        ch = m.group(1)
        tr = ch.translate(_SUB_MAP)
        # Only collapse `_x` → subscript when the char actually has a subscript
        # glyph; otherwise keep the underscore to preserve `R_motion` style.
        return tr if tr != ch else f"_{ch}"
    def _single_super(m):
        ch = m.group(1)
        tr = ch.translate(_SUPER_MAP)
        return tr if tr != ch else f"^{ch}"
    text = re.sub(r"\^\{([^}]+)\}", _braced_super, text)
    text = re.sub(r"\^([0-9a-zA-Z+\-])", _single_super, text)
    text = re.sub(r"_\{([^}]+)\}", _braced_sub, text)
    text = re.sub(r"_([0-9a-zA-Z+\-])", _single_sub, text)
    # Step 6: \frac{a}{b} → (a)/(b). Now that inner subscripts are unwrapped,
    # the brace pairs around the numerator and denominator are clean. Repeat
    # until fixed-point so adjacent fractions all convert.
    while True:
        new = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
                     r"(\1)/(\2)", text)
        if new == text:
            break
        text = new

    if mark_inline:
        # Wrap inline / display math with sentinel chars so styled-run
        # renderers can italicize them. We process the longest delimiters
        # first to avoid partial matches.
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


def strip_math_markers(text: str) -> str:
    """Remove the MATH_OPEN/MATH_CLOSE sentinels (for renderers that don't
    support italic runs, or for plain-text logging)."""
    if not text:
        return text
    return text.replace(MATH_OPEN, "").replace(MATH_CLOSE, "")


# Run-aware parsing helper used by DOCX/HTML renderers. Yields
# ``(text, style)`` tuples where style ∈ {"plain", "bold", "italic"}.
#
# Supported markers:
#   ``**bold**``   — markdown bold from LLM output (was rendered literally
#                    before this helper — readers saw ``**foo**``).
#   ``\x01math\x02`` — inline / display math wrapped by normalize_math.
#
# Nested markers are not supported: the first delimiter wins, the inner
# delimiter is left as plain text. The LLM outputs we see in practice keep
# bold and math segments disjoint.
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
