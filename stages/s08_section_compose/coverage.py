"""Strategy A: per-section KG entity coverage check (env-gated by LAZY_PAPER_COVERAGE=1).

Given a section's title + guidance, derive the KG entities "in scope" for this
section, then check whether the composed draft mentions at least N% of them.
Missing entities are surfaced as a new Flag problem type so the LLM critic
can revise the draft to bring them back.

Targets the depth regressions observed in v1.4.x where the LLM dropped
source-grounded data (e.g. meng2024 ch01 lost literature benchmarks, yang2025
ch10 lost Raman peak positions).
"""
from __future__ import annotations

import re
from typing import Iterable

from llm.paper_kg import Entity, PaperKG


# How much of a section's in-scope entity set must appear in the draft.
# 50% is loose enough that quotation paraphrasing doesn't trigger flags,
# tight enough that "dropped half the source facts" gets caught.
_COVERAGE_THRESHOLD = 0.5
# Max entities to flag per section — keeps the LLM critic's prompt bounded.
_MAX_FLAGS_PER_SECTION = 10


def _tokens(text: str) -> set[str]:
    """Cheap tokenizer for keyword matching: 3+ char ASCII or 2+ char CJK."""
    out: set[str] = set()
    for m in re.finditer(r"[A-Za-z0-9_]{3,}|[一-鿿]{2,}", text):
        out.add(m.group(0).lower())
    return out


# Section-title keywords that justify pulling in ALL comparators from the KG.
# These are the sections that survey prior work or compare against literature.
_COMPARATOR_SECTION_KEYWORDS = {
    "introduction", "background", "prior", "comparison", "literature",
    "related", "review", "discussion", "limitations", "conclusion",
    # zh equivalents
    "引言", "背景", "对比", "比较", "综述", "讨论", "结论",
}


def entities_in_scope(section_title: str, section_guidance: str,
                      kg: PaperKG) -> list[Entity]:
    """Heuristic: an entity is "in scope" for this section if any of its text
    tokens overlaps the section title or guidance.

    Three layers of "always in scope":
      - 'material' + 'parameter': paper-level facts most sections reference.
      - 'comparator' + 'claim': pulled in for survey/discussion sections
        (Introduction, Comparison with Prior Work, Discussion, etc.) where
        the LLM needs to enumerate prior literature. Without this, the
        comparator entities (e.g. "Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3" from
        Jiang et al.) would never match section keywords like "Introduction"
        and would silently drop out of coverage checks.
      - 'figure'/'table': always require explicit token overlap.
    """
    section_tokens = _tokens(section_title + " " + section_guidance)
    if not section_tokens:
        return []
    title_lower = section_title.lower()
    pulls_comparators = any(kw in title_lower for kw in _COMPARATOR_SECTION_KEYWORDS)
    in_scope: list[Entity] = []
    for e in kg.entities:
        if e.type in ("material", "parameter"):
            in_scope.append(e)
            continue
        if pulls_comparators and e.type in ("comparator", "claim"):
            in_scope.append(e)
            continue
        ent_tokens = _tokens(e.text)
        if section_tokens & ent_tokens:
            in_scope.append(e)
    return in_scope


def coverage_missing(draft: str, scope_entities: Iterable[Entity]) -> list[Entity]:
    """Return entities whose text does not appear (case-insensitive) in the draft."""
    draft_lower = draft.lower()
    missing: list[Entity] = []
    for e in scope_entities:
        # any non-trivial token of the entity text appearing counts as covered
        ent_text = e.text.strip()
        if not ent_text:
            continue
        # full string match first, then any 3+ char token
        if ent_text.lower() in draft_lower:
            continue
        ent_tokens = [t for t in _tokens(ent_text) if len(t) >= 3]
        if ent_tokens and any(t in draft_lower for t in ent_tokens):
            continue
        missing.append(e)
    return missing


def coverage_summary(scope: list[Entity], missing: list[Entity]) -> dict:
    """One-line summary for done.yaml / critic_flags.yaml."""
    n_scope = len(scope)
    n_missing = len(missing)
    ratio = (n_scope - n_missing) / n_scope if n_scope else 1.0
    return {
        "in_scope": n_scope,
        "covered": n_scope - n_missing,
        "missing": n_missing,
        "ratio": round(ratio, 2),
        "below_threshold": ratio < _COVERAGE_THRESHOLD,
    }


def truncate_for_flag(missing: list[Entity]) -> list[Entity]:
    """Cap the number of missing entities surfaced as flags so the LLM
    critic's prompt stays focused. Prioritize the rare, high-value types
    (comparator, claim, method, dopant) so they don't get evicted by the
    cap when many parameter/material entities are also missing."""
    priority = {"comparator": 0, "claim": 1, "method": 2, "dopant": 3,
                "table": 4, "figure": 5, "material": 6, "parameter": 7,
                "value": 8, "unit": 9}
    ranked = sorted(missing, key=lambda e: priority.get(e.type, 99))
    return ranked[:_MAX_FLAGS_PER_SECTION]
