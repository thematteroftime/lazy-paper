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


def normalize_math(text: str) -> str:
    """Normalize LaTeX math expressions in *text* to Unicode.

    Steps:
    1. Greek letters and common operators (\\eta → η, etc.)
    2. Superscripts: ^{...} or ^X → Unicode superscripts where possible
    3. Subscripts: _{...} or _X → Unicode subscripts where possible
    4. Strip outer $...$ delimiters (any remaining)
    5. Misc cleanups (\\%, \\&)
    """
    if not text:
        return text

    # 1) Greek letters + arrows + operators
    for latex_pat, unicode_char in _GREEK_LATEX.items():
        # Only replace when NOT followed by another letter (avoid partial matches)
        text = re.sub(latex_pat + r"(?![a-zA-Z])", unicode_char, text)

    # 2) Superscripts: ^{...}
    def sup_repl(m: re.Match) -> str:
        body = m.group(1)
        try:
            return body.translate(_SUPER_MAP)
        except Exception:
            return body

    text = re.sub(r"\^\{([^}]+)\}", sup_repl, text)
    # Single-char superscripts: ^X
    text = re.sub(
        r"\^([0-9a-zA-Z+\-])",
        lambda m: m.group(1).translate(_SUPER_MAP),
        text,
    )

    # 3) Subscripts: _{...}
    def sub_repl(m: re.Match) -> str:
        body = m.group(1)
        try:
            return body.translate(_SUB_MAP)
        except Exception:
            return body

    text = re.sub(r"_\{([^}]+)\}", sub_repl, text)
    # Single-char subscripts: _X
    text = re.sub(
        r"_([0-9a-zA-Z+\-])",
        lambda m: m.group(1).translate(_SUB_MAP),
        text,
    )

    # 4) Strip outer $...$ delimiters (if any remain after step 1)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)

    # 5) Common cleanups
    text = text.replace(r"\%", "%").replace(r"\&", "&")

    return text
