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
    r"(kV/cm|MV/cm|J/cm[³³3]|mJ/cm[³³3]|%|K(?![A-Za-z/])|°?C(?![A-Za-z/])|kHz|MHz)"
)
_FIG_REF = re.compile(r"\bFig\.\s*\d+[a-z]?\b")
_FORMULA = re.compile(
    r"\b(Vogel[- ]Fulcher|Curie[- ]Weiss|Maxwell[- ]Wagner|Lorentz|Debye)\b"
)

# OCR backends sometimes emit numbers with single spaces between digits
# ("0 . 0 3 6 %") and LaTeX-style escapes preserved from the PDF math layer
# ("$0.036 \\%$"). We collapse both before the regex search so the source
# match isn't lost to those artifacts. Applied iteratively so chains like
# "0 . 0 3 6" fully fold even after the first pass leaves "0. 036".
_OCR_DIGIT_SPACE = re.compile(r"(?<=[\d.])\s+(?=[\d.])")
_LATEX_NOISE = re.compile(r"\\(?=[%$&_^{}])")


def _normalize_source(text: str) -> str:
    prev = None
    cur = text
    while prev != cur:
        prev, cur = cur, _OCR_DIGIT_SPACE.sub("", cur)
    return _LATEX_NOISE.sub("", cur)


def _source_contains_value(source_docs: dict[str, str], val_unit: str) -> str | None:
    """Search source for a numerically equal value-with-unit. Returns evidence snippet."""
    for doc_name, text in source_docs.items():
        normalized = _normalize_source(text)
        for m in _NUM_UNIT.finditer(normalized):
            candidate = f"{m.group(1)} {m.group(2)}"
            if units_equal(val_unit, candidate):
                start = max(0, m.start() - 40)
                end = min(len(normalized), m.end() + 40)
                return f"[{doc_name}] ...{normalized[start:end]}..."
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
    _NUM_TAIL = re.compile(r"(\d+)[a-z]?\b")
    for m in _FIG_REF.finditer(draft):
        ref = m.group(0).strip()
        # Extract the numeric portion robustly — "Fig. 2", "Fig.2", "Fig.2a"
        # all map to "2"; missing numbers skip the check.
        num_match = _NUM_TAIL.search(ref)
        if not num_match:
            continue
        num = num_match.group(1)
        if not any(num in k for k in known_figs):
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


# ─── LLM tier (v1.4.0) ───────────────────────────────────────────────────────

from pydantic import Field
import instructor
from instructor import Mode

from llm.client import LLM, max_tokens


class CritiqueRevision(BaseModel):
    revised_draft: str
    quote_fidelity: int = Field(ge=1, le=4)
    grounding: int = Field(ge=1, le=4)
    synthesis_depth: int = Field(ge=1, le=4)
    notes: str = ""


_REVIEW_SYSTEM = """You are a strict factual reviewer for a single research paper.

You will receive a draft section, a list of issues flagged by a regex critic,
and the source evidence. Produce a revised draft that fixes each flagged issue
by replacing the wrong value/reference with one that the evidence supports,
or by removing the unsupported claim. Do NOT add new claims not in the evidence.

Score quote_fidelity (1-4), grounding (1-4), synthesis_depth (1-4):
- 4 = excellent, 1 = fails on this dimension.
"""


def _llm_review_call(draft: str, flags_text: str, evidence: str) -> CritiqueRevision:
    llm = LLM(role="text")
    client = instructor.from_openai(llm._client, mode=Mode.JSON)
    return client.chat.completions.create(
        model=llm.model,
        response_model=CritiqueRevision,
        messages=[
            {"role": "system", "content": _REVIEW_SYSTEM},
            {"role": "user", "content":
                f"DRAFT:\n{draft}\n\nFLAGS:\n{flags_text}\n\nEVIDENCE:\n{evidence}"},
        ],
        max_tokens=max_tokens(8000),
        temperature=0.1,
        max_retries=2,
    )


def llm_review(draft: str, flags: list[Flag], evidence: str) -> CritiqueRevision:
    """Run the LLM tier given regex flags + supporting evidence."""
    if not flags:
        return CritiqueRevision(
            revised_draft=draft, quote_fidelity=4, grounding=4,
            synthesis_depth=3, notes="no flags",
        )
    flags_text = "\n".join(
        f"- {f.problem}: {f.claim}" + (f" (evidence: {f.evidence})" if f.evidence else "")
        for f in flags
    )
    return _llm_review_call(draft, flags_text, evidence)
