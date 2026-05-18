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
    text = text.replace(r"\%", "%").replace(r"\&", "&")
    return text
