"""Unit normalization for reviewer regex-tier comparisons.

Only the units that appear in our 10-paper corpus' quantitative claims are
handled. Anything outside this table returns the raw value with its raw unit.
"""
from __future__ import annotations

import re
from typing import Optional

# canonical units: (alias regex, factor to canonical)
_TABLE: dict[str, list[tuple[str, float]]] = {
    "kV/cm": [(r"kV/cm", 1.0), (r"MV/cm", 1000.0), (r"V/cm", 0.001)],
    "J/cm3": [(r"J/cm[³³3]", 1.0), (r"mJ/cm[³³3]", 0.001)],
    "%":     [(r"%", 1.0)],
    "K":     [(r"K\b", 1.0)],
    "C":     [(r"°?C\b", 1.0)],
    "Hz":    [(r"Hz", 1.0), (r"kHz", 1000.0), (r"MHz", 1e6)],
}

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def normalize(s: str) -> Optional[tuple[float, str]]:
    """Parse `value unit` → (canonical_value, canonical_unit).

    Returns None if no recognized unit matches. Bare numbers return ("", "").
    """
    s = s.strip()
    if not s:
        return None
    for canonical, aliases in _TABLE.items():
        for pat, factor in aliases:
            m = re.match(rf"({_NUM})\s*{pat}\s*$", s)
            if m:
                return (float(m.group(1)) * factor, canonical)
    # Bare number → no unit
    m = re.match(rf"^({_NUM})$", s)
    if m:
        return (float(m.group(1)), "")
    return None


def equal(a: str, b: str, rel_tol: float = 0.01) -> bool:
    """Compare two value-with-unit strings after canonicalizing."""
    na, nb = normalize(a), normalize(b)
    if na is None or nb is None:
        return False
    va, ua = na
    vb, ub = nb
    if ua != ub:
        return False
    if va == 0 and vb == 0:
        return True
    return abs(va - vb) / max(abs(va), abs(vb)) <= rel_tol
