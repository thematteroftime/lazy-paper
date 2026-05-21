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


# Common materials-science terms that match many entities trivially —
# matching on these alone shouldn't count an entity as "covered".
_STOP_TOKENS = {
    "based", "ceramics", "ceramic", "rfe", "afe", "rafe", "pnr", "pnrs",
    "nbt", "ferroelectric", "antiferroelectric", "relaxor", "energy",
    "storage", "ceramic", "doping", "doped", "modified", "performance",
    "system", "material", "materials", "phase", "loop", "loops",
}


def _distinctive_tokens(text: str) -> set[str]:
    """Tokens worth requiring a draft to match. Excludes generic vocabulary
    and prefers chemical-formula-shaped strings (mixed letters+digits or
    5+ char alphanum). For "Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3-based RFE
    ceramics" this returns {"ca2", "nb5", "codoped", "bi0", "na0", "tio3"}
    rather than including generic "based"/"ceramics"/"rfe"."""
    out: set[str] = set()
    for m in re.finditer(r"[A-Za-z0-9.+/_-]{3,}", text):
        tok = m.group(0).lower()
        # filter stop-tokens
        if tok in _STOP_TOKENS:
            continue
        # require either chemical-formula shape (letter+digit mix) or 5+ chars
        has_digit = any(c.isdigit() for c in tok)
        has_letter = any(c.isalpha() for c in tok)
        if (has_digit and has_letter) or len(tok) >= 5:
            out.add(tok)
    # Plus 4+ char CJK runs (longer is more distinctive)
    for m in re.finditer(r"[一-鿿]{4,}", text):
        out.add(m.group(0))
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
    """Return entities whose distinctive text-tokens don't appear in the draft.

    Matching rule: an entity is "covered" iff
      (a) its full text appears verbatim in the draft, OR
      (b) at least one of its DISTINCTIVE tokens appears in the draft.

    Distinctive = a chemical-formula-shaped token (mixed alphanum) or 5+ char
    word, EXCLUDING common stop-words like "RFE", "based", "ceramics" that
    would otherwise produce false covered-positives.
    """
    draft_lower = draft.lower()
    missing: list[Entity] = []
    for e in scope_entities:
        ent_text = e.text.strip()
        if not ent_text:
            continue
        if ent_text.lower() in draft_lower:
            continue
        distinctive = _distinctive_tokens(ent_text)
        if distinctive and any(t in draft_lower for t in distinctive):
            continue
        missing.append(e)
    return missing


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
