"""Reviewer: two-tier critic for s08 chapter drafts.

Tier 1 (v1.3.4): pure Python regex, free, observe-only.
Tier 2 (v1.4.0): instructor + Pydantic, runs only when tier 1 flags.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from llm.paper_kg import PaperKG
from stages.s08_section_compose._units import equal as units_equal

Problem = Literal[
    "numeric_not_in_source",
    "fig_not_in_yaml",
    "formula_not_in_kg",
    "unit_mismatch",
]


class Flag(BaseModel):
    span: tuple[int, int]
    claim: str
    problem: Problem
    evidence: str | None = None


_NUM_UNIT = re.compile(
    r"(?<![A-Za-z\d])([-+]?\d+(?:\.\d+)?)\s*"
    r"(kV/cm|MV/cm|J/cm[³³3]|mJ/cm[³³3]|%|K\b|°?C\b|kHz|MHz)"
)
_FIG_REF = re.compile(r"\bFig\.\s*\d+[a-z]?\b")
_FORMULA = re.compile(
    r"\b(Vogel[- ]Fulcher|Curie[- ]Weiss|Maxwell[- ]Wagner|Lorentz|Debye)\b"
)


def _source_contains_value(source_docs: dict[str, str], val_unit: str) -> str | None:
    """Search source for a numerically equal value-with-unit. Returns evidence snippet."""
    for doc_name, text in source_docs.items():
        for m in _NUM_UNIT.finditer(text):
            candidate = f"{m.group(1)} {m.group(2)}"
            if units_equal(val_unit, candidate):
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                return f"[{doc_name}] ...{text[start:end]}..."
    return None


def regex_check(
    draft: str,
    source_docs: dict[str, str],
    kg: PaperKG,
    fig_yaml: list[dict],
) -> list[Flag]:
    """Return list of Flag for issues detectable without an LLM."""
    flags: list[Flag] = []

    # Numeric-with-unit assertions must appear (or numerically equal) in source
    for m in _NUM_UNIT.finditer(draft):
        val_unit = f"{m.group(1)} {m.group(2)}"
        evidence = _source_contains_value(source_docs, val_unit)
        if evidence is None:
            flags.append(Flag(
                span=(m.start(), m.end()),
                claim=val_unit,
                problem="numeric_not_in_source",
                evidence=None,
            ))

    # Figure references must be in figures.yaml
    known_figs = {str(f.get("fig_id", "")).strip() for f in fig_yaml}
    for m in _FIG_REF.finditer(draft):
        ref = m.group(0).strip()
        # Accept "Fig. 2" matching "Fig. 2" or "Fig. 2a" → check loosely
        if not any(ref.split()[1].rstrip("abcdefghij") in k for k in known_figs):
            flags.append(Flag(
                span=(m.start(), m.end()),
                claim=ref,
                problem="fig_not_in_yaml",
            ))

    # Named formula must have at least one method/claim entity referencing it
    kg_text_blob = " ".join(e.text.lower() for e in kg.entities)
    for m in _FORMULA.finditer(draft):
        name = m.group(0).lower()
        if name.split()[0] not in kg_text_blob:
            flags.append(Flag(
                span=(m.start(), m.end()),
                claim=m.group(0),
                problem="formula_not_in_kg",
            ))

    # Attach evidence to numeric_not_in_source flags after the fact
    for f in flags:
        if f.problem == "numeric_not_in_source" and f.evidence is None:
            # Provide closest-match evidence if any value with same unit exists
            unit = f.claim.split()[-1]
            for doc_name, text in source_docs.items():
                m = _NUM_UNIT.search(text)
                if m and m.group(2) == unit:
                    f.evidence = f"[{doc_name}] near: {m.group(0)}"
                    break

    return flags
