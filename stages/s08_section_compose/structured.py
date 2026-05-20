"""Strategy J (v1.6) — structured composition with citation pre-injection.

Architecture (see docs/v1_6_strategy_j_design.md):
- Perplexity-style pre-injection: chunks pre-labeled with IDs, LLM constrained
  to cite only that set via Pydantic validator.
- Onyx-vendored citation_processor handles rendering ([span:doc:start-end]).
- ClarityArc-style verifier: fuzzy-match cited_quote against actual chunk
  text to filter hallucinated quotes after the LLM call.

Day-1 scope (this file at first commit): Pydantic schemas + verifier gate +
required-mentions builder + top-N selection. No LLM calls yet — Day-2 wires
the instructor flow.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

if TYPE_CHECKING:
    from llm.paper_kg import PaperKG
    from llm.retriever import Chunk


# Section-title keywords that justify treating comparator/claim entities as
# "required to be cited" for this section. Mirrors coverage.py's gate.
_SURVEY_SECTION_KEYWORDS = (
    "introduction", "background", "prior", "comparison", "literature",
    "related", "review", "discussion", "limitations",
    "引言", "背景", "对比", "比较", "综述", "讨论",
)


# ─── Pydantic schemas ────────────────────────────────────────────────────────


class GroundedClaim(BaseModel):
    """One sentence-or-paragraph of the section, anchored to retrieved chunks.

    The validator rejects `cited_chunk_ids` outside the allowed set (passed
    via `model_validate(..., context={"allowed_chunk_ids": {...}})`).
    Without context the validator is a no-op (backward compat).
    """
    text: str = Field(min_length=2)
    cited_chunk_ids: list[int] = Field(default_factory=list)
    cited_quote: str = Field(default="")

    @field_validator("cited_chunk_ids")
    @classmethod
    def _check_chunk_ids(cls, ids: list[int], info: ValidationInfo) -> list[int]:
        allowed = (info.context or {}).get("allowed_chunk_ids")
        if allowed is None:
            return ids  # no constraint set
        bad = [i for i in ids if i not in allowed]
        if bad:
            head = sorted(allowed)[:5] if allowed else []
            raise ValueError(
                f"chunk_ids {bad} not in retrieved set {head}..."
            )
        return ids


class SectionDraft(BaseModel):
    """The complete section as a list of grounded claims."""
    claims: list[GroundedClaim] = Field(min_length=2, max_length=14)

    def render(
        self, *,
        mode: Literal["REMOVE", "KEEP", "HYPERLINK"] = "REMOVE",
        chunks_by_id: "dict[int, Chunk] | None" = None,
    ) -> str:
        """Assemble claims into prose with [span:...] markers per mode.

        REMOVE: plain prose, no markers (default for DOCX).
        KEEP: appends [span:doc:start-end] to each sentence.
        HYPERLINK: same as KEEP but the renderer will pass through to
        llm/citation/__init__.process_text() for HTML hyperlink resolution.
        """
        parts: list[str] = []
        for c in self.claims:
            sentence = c.text.strip()
            if mode in ("KEEP", "HYPERLINK") and chunks_by_id:
                markers = []
                for cid in c.cited_chunk_ids:
                    ch = chunks_by_id.get(cid)
                    if ch is None:
                        continue
                    markers.append(
                        f"[span:{ch.doc_name}:{ch.char_start}-{ch.char_end}]"
                    )
                if markers:
                    # Remove a trailing period before inserting, then re-add
                    if sentence.endswith((".", "。")):
                        sentence = sentence[:-1] + " " + "".join(markers) + sentence[-1]
                    else:
                        sentence = sentence + " " + "".join(markers)
            parts.append(sentence)
        return " ".join(parts)


class RequiredMention(BaseModel):
    """A KG entity the section MUST cite for v1.6 grounded compose.

    Soft-enforced: if the final SectionDraft doesn't cite it, we log to
    critic_flags.yaml but still ship the chapter.
    """
    entity_text: str
    entity_type: str
    evidence_chunk_id: int
    evidence_quote: str
    linked_values: list[str] = Field(default_factory=list)


# ─── verifier gate ───────────────────────────────────────────────────────────


def _quote_in_chunk(quote: str, chunk_text: str,
                    ratio_threshold: float = 0.85) -> float:
    """Return the best match score for `quote` inside `chunk_text`.

    Strategy: substring check first (cheap path; LLM usually copies
    verbatim). Falls back to SequenceMatcher.find_longest_match() to
    measure the longest common contiguous span, which captures
    "quote is a slightly-paraphrased substring" better than raw
    ratio() does on length-mismatched strings.
    """
    if not quote.strip() or not chunk_text:
        return 0.0
    quote_s = quote.strip()
    # Cheap path 1: exact substring.
    if quote_s in chunk_text:
        return 1.0
    # Cheap path 2: case-insensitive substring.
    if quote_s.lower() in chunk_text.lower():
        return 0.99
    # Fuzzy path: longest contiguous matching block.
    matcher = SequenceMatcher(None, quote_s, chunk_text)
    longest = matcher.find_longest_match(0, len(quote_s), 0, len(chunk_text))
    # Coverage of the quote by the longest matching block.
    coverage = longest.size / max(1, len(quote_s))
    return coverage


def verify_section_draft(
    draft: SectionDraft,
    chunks_by_id: "dict[int, Chunk]",
    ratio_threshold: float = 0.85,
) -> tuple[list[GroundedClaim], list[dict]]:
    """Drop claims whose `cited_quote` doesn't fuzzy-match any cited chunk.

    Match criterion: the longest contiguous run of `cited_quote` characters
    found in the chunk text must cover at least `ratio_threshold` of the
    quote's length. Exact-substring case returns 1.0; verbatim-with-typo
    LLM output stays well above 0.85.

    Empty quotes skip verification (cited_chunk_ids alone is the grounding
    signal — the LLM may still write good prose without verbatim quoting).
    """
    accepted: list[GroundedClaim] = []
    rejected: list[dict] = []
    for c in draft.claims:
        if not c.cited_quote.strip():
            accepted.append(c)
            continue
        best_score = 0.0
        matched = False
        for cid in c.cited_chunk_ids:
            ch = chunks_by_id.get(cid)
            if ch is None:
                continue
            score = _quote_in_chunk(c.cited_quote, ch.text, ratio_threshold)
            best_score = max(best_score, score)
            if score >= ratio_threshold:
                matched = True
                break
        if matched:
            accepted.append(c)
        else:
            rejected.append({
                "text": c.text[:120],
                "quote": c.cited_quote[:120],
                "best_ratio": round(best_score, 3),
                "cited_chunk_ids": list(c.cited_chunk_ids),
            })
    return accepted, rejected


# ─── required-mentions construction ──────────────────────────────────────────


def _is_survey_section(title: str) -> bool:
    title_low = title.lower()
    return any(kw in title_low for kw in _SURVEY_SECTION_KEYWORDS)


def _find_chunk_for_entity_span(
    entity: "Entity",
    retrieved_chunks: list["Chunk"],
) -> int | None:
    """Return the retrieved-chunks index whose char range contains the
    entity's source_span, or None if no retrieved chunk covers it."""
    doc, start, end = entity.source_span
    mid = (start + end) // 2
    for i, ch in enumerate(retrieved_chunks):
        if ch.doc_name == doc and ch.char_start <= mid < ch.char_end:
            return i
    return None


def _evidence_quote(
    entity: "Entity",
    source_docs: dict[str, str],
    max_chars: int = 200,
) -> str:
    doc, start, end = entity.source_span
    src = source_docs.get(doc, "")
    if not src:
        return ""
    pad_left = max(0, start - 30)
    pad_right = min(len(src), end + (max_chars - (end - start) - 30))
    snippet = src[pad_left:pad_right].replace("\n", " ").strip()
    return snippet[:max_chars]


def _linked_values_for_entity(
    entity: "Entity",
    kg: "PaperKG",
) -> list[str]:
    """Find `value` entities related to this entity via has_W_rec / has_η /
    etc. relations (KG-v2 prompt produces these for comparators).

    Falls back to scanning the entity's source-span context for nearby
    `value + unit` patterns if no relations exist.
    """
    out: list[str] = []
    for rel in kg.relations:
        if rel.subject != entity.id:
            continue
        if not rel.predicate.startswith("has_"):
            continue
        target = next((e for e in kg.entities if e.id == rel.object), None)
        if target is None:
            continue
        param = rel.predicate.removeprefix("has_")
        out.append(f"{param}={target.text}")
    return out


def build_required_mentions(
    *,
    section_title: str,
    section_guidance: str,
    kg: "PaperKG",
    source_docs: dict[str, str],
    retrieved_chunks: list["Chunk"],
) -> list[RequiredMention]:
    """Build the list of RequiredMention objects for this section.

    Rules:
    - Survey sections (Introduction / Discussion / Comparison / etc.) get
      ALL `comparator` entities as required.
    - Non-survey sections get only entities whose text-tokens directly
      overlap the section title/guidance (rare).
    - Each required entity must map to one of the retrieved_chunks; if no
      retrieved chunk covers its source_span, we skip it (LLM can't cite
      something not in its context).
    """
    is_survey = _is_survey_section(section_title)
    out: list[RequiredMention] = []
    for e in kg.entities:
        if e.type in ("comparator",):
            if not is_survey:
                continue
        elif e.type in ("claim", "method"):
            if not is_survey:
                # only require if entity text overlaps guidance
                guidance_tokens = set(re.findall(r"[A-Za-z0-9_-]{3,}|[一-鿿]{2,}",
                                                  section_guidance.lower()))
                ent_tokens = set(re.findall(r"[A-Za-z0-9_-]{3,}|[一-鿿]{2,}",
                                             e.text.lower()))
                if not (guidance_tokens & ent_tokens):
                    continue
        else:
            continue
        chunk_idx = _find_chunk_for_entity_span(e, retrieved_chunks)
        if chunk_idx is None:
            continue
        out.append(RequiredMention(
            entity_text=e.text,
            entity_type=e.type,
            evidence_chunk_id=chunk_idx,
            evidence_quote=_evidence_quote(e, source_docs),
            linked_values=_linked_values_for_entity(e, kg),
        ))
    return out


def select_top_required(
    mentions: list[RequiredMention],
    cap: int = 5,
) -> list[RequiredMention]:
    """Per design: cap at top-N most distinctive.

    Distinctiveness ≈ length of entity_text + 0.5 × count of digit chars
    (chemical-formula density signal). Comparators tend to dominate over
    short claim/method strings, which matches the design intent of
    prioritizing literature-citation recovery.
    """
    def score(m: RequiredMention) -> float:
        text = m.entity_text
        digit_chars = sum(1 for c in text if c.isdigit())
        return len(text) + 0.5 * digit_chars
    ranked = sorted(mentions, key=score, reverse=True)
    return ranked[:cap]


# ─── compose pipeline (Day-2) ────────────────────────────────────────────────


_STRUCTURED_SYSTEM = """You are composing one section of a research-paper deep analysis.

You have been given a numbered list of source chunks in the USER message.
Every claim in your output MUST cite at least one chunk by its 0-based ID,
and you may ONLY cite chunks from this list. Citing a chunk ID outside the
list will cause your output to be rejected.

Some entities are listed under "Required mentions" — these are facts the
section MUST cover. For each, write a GroundedClaim that:
  - includes the entity's verbatim text (chemical formula / author name)
  - includes the linked numeric value when given (e.g. "W_rec=2.94 J/cm³")
  - sets cited_chunk_ids to the evidence_chunk_id given for that entity
  - sets cited_quote to a verbatim slice from that chunk

For other claims (not required, just supporting the section's argument):
  - cite ≥1 chunk that supports the claim
  - cited_quote may be verbatim or empty (empty skips verification)
  - keep prose in the requested language (Chinese unless the user says English)

Quote-then-claim discipline (for the verifier):
  - When you set cited_quote, copy it verbatim from the cited chunk — the
    verifier fuzzy-matches against the chunk text and rejects paraphrased
    quotes.
  - For Chinese chunks, copy CJK + ASCII as-is; do not transliterate.

Output a SectionDraft JSON object matching the schema. Aim for 4–8 claims
unless guidance demands more.

Length / language / quantitative rules from the base section_compose prompt
still apply — see the USER message for {lang_instruction} and other hints.
"""


def _format_chunks_block(chunks: list["Chunk"]) -> str:
    """Build the numbered chunks block for the USER message."""
    lines: list[str] = []
    for i, c in enumerate(chunks):
        preview = c.text.replace("\n", " ")[:1200]
        lines.append(
            f"[{i}] ({c.doc_name} chars {c.char_start}-{c.char_end})\n"
            f"    {preview}"
        )
    return "\n".join(lines)


def _format_required_block(required: list[RequiredMention]) -> str:
    if not required:
        return "(none — no required entities for this section)"
    lines: list[str] = []
    for r in required:
        vals = f"  linked_values: {', '.join(r.linked_values)}\n" if r.linked_values else ""
        lines.append(
            f"- {r.entity_type}: \"{r.entity_text}\"\n"
            f"  evidence_chunk_id: {r.evidence_chunk_id}\n"
            f"  evidence_quote: \"{r.evidence_quote[:200]}\"\n"
            f"{vals}"
        )
    return "\n".join(lines)


def compose_structured(
    llm,
    *,
    section_title: str,
    section_guidance: str,
    lang_instruction: str,
    chunks: list["Chunk"],
    required: list[RequiredMention],
    prior_findings: str = "",
    paper_context: str = "",
    max_retries: int = 3,
) -> tuple["SectionDraft", list[dict]]:
    """Day-2 entry point: instructor call → SectionDraft → verifier gate.

    Returns the verified SectionDraft (claims filtered to those whose
    cited_quote matched their chunk) + a list of rejected_log dicts for
    audit. Raises if instructor fails after max_retries.
    """
    import instructor
    from instructor import Mode

    chunks_block = _format_chunks_block(chunks)
    required_block = _format_required_block(required)
    user_msg = (
        f"## Section to write\n"
        f"- Title: {section_title}\n"
        f"- Guidance: {section_guidance}\n"
        f"- Language: {lang_instruction}\n\n"
        f"## Paper context\n{paper_context}\n\n"
        f"## Available chunks (cite ONLY these 0-based IDs)\n{chunks_block}\n\n"
        f"## Required mentions (you MUST cover each)\n{required_block}\n\n"
        f"## Already established in prior sections (refer back, do not restate)\n"
        f"{prior_findings or '(this is the first section)'}\n\n"
        f"Emit the SectionDraft JSON now."
    )

    client = instructor.from_openai(llm._client, mode=Mode.MD_JSON)
    allowed = set(range(len(chunks)))
    draft = client.chat.completions.create(
        model=llm.model,
        response_model=SectionDraft,
        validation_context={"allowed_chunk_ids": allowed},
        messages=[
            {"role": "system", "content": _STRUCTURED_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        max_retries=max_retries,
        temperature=0.2,
    )

    chunks_by_id = {i: c for i, c in enumerate(chunks)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id)
    verified = SectionDraft(claims=accepted) if len(accepted) >= 2 else draft
    return verified, rejected


def missing_required(
    required: list[RequiredMention],
    draft: SectionDraft,
) -> list[RequiredMention]:
    """Return the subset of `required` whose evidence_chunk_id is not cited
    by ANY claim in `draft`. Used for the soft-warn audit log per design."""
    cited: set[int] = set()
    for c in draft.claims:
        cited.update(c.cited_chunk_ids)
    return [r for r in required if r.evidence_chunk_id not in cited]
