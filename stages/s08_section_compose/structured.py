"""Strategy J (v1.6) — structured composition with citation pre-injection.

Architecture (see docs/v1_6_strategy_j_design.md):
- Perplexity-style pre-injection: chunks pre-labeled with IDs, LLM constrained
  to cite only that set via Pydantic validator.
- `llm.citation.process_text` renders the `[span:doc:start-end]` markers
  (REMOVE / KEEP / HYPERLINK modes; design ported from Onyx, see
  THIRD_PARTY_NOTICES.md).
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

        Also strips literal "(chunk N)" / "[chunk N]" patterns the LLM may
        have leaked into prose (it tends to copy the chunk-ID list directly
        when asked to "cite IDs" — those leaks should never be visible to
        the end reader regardless of citation mode).
        """
        import re as _re
        # Two leak forms observed:
        #   "(chunk 11)" / "（chunk 11，12）" — explicit-word form
        #   "[2,5]" / "[0, 3]" — bare-bracket numeric list (no word)
        _CHUNK_LEAK = _re.compile(
            r"\s*[（(\[]\s*(?:chunk\s*)?\d+(?:\s*[,，]\s*\d+)*\s*[)）\]]"
        )
        parts: list[str] = []
        for c in self.claims:
            sentence = c.text.strip()
            sentence = _CHUNK_LEAK.sub("", sentence)
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

    v1.7: `author_text` is populated when the KG-v3 prompt extracted an
    `author` entity linked to this comparator via `cited_by_paper`. The
    compose prompt then asks the LLM to use the form "<author> et al."
    rather than the bare chemical formula.
    """
    entity_text: str
    entity_type: str
    evidence_chunk_id: int
    evidence_quote: str
    linked_values: list[str] = Field(default_factory=list)
    author_text: str = ""  # v1.7: linked author entity, if any


# ─── verifier gate ───────────────────────────────────────────────────────────


from stages._common.normalize import normalize_ocr_latex as _normalize_for_match  # noqa: E402


def _quote_in_chunk(quote: str, chunk_text: str,
                    ratio_threshold: float = 0.85) -> float:
    """Return the best match score for `quote` inside `chunk_text`.

    Strategy:
    1. exact substring (verbatim copy)
    2. case-insensitive substring
    3. normalized substring (LaTeX commands and OCR digit-spacing
       stripped on both sides)
    4. fuzzy longest-common-substring on normalized text

    The normalization tier catches the common case where the LLM
    correctly quotes the chunk but renders LaTeX-form math like
    `$W _ { \\mathrm { rec } }` slightly differently than the OCR'd
    source (different whitespace inside braces, etc.).
    """
    if not quote.strip() or not chunk_text:
        return 0.0
    quote_s = quote.strip()
    if quote_s in chunk_text:
        return 1.0
    if quote_s.lower() in chunk_text.lower():
        return 0.99
    q_norm = _normalize_for_match(quote_s)
    c_norm = _normalize_for_match(chunk_text)
    if q_norm and q_norm in c_norm:
        return 0.97
    if not q_norm:
        return 0.0
    matcher = SequenceMatcher(None, q_norm, c_norm)
    longest = matcher.find_longest_match(0, len(q_norm), 0, len(c_norm))
    coverage = longest.size / max(1, len(q_norm))
    return coverage


_ANCHOR_AUTHOR_RE = re.compile(r"\b([A-Z][a-z]+)\s+(?:et\s+al\.?|等(?:人|等)?)")
_ANCHOR_VALUE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:J/cm[³3]|MV/cm|kV/cm|μC/cm[²2]|%)"
)


def _claim_anchors(text: str) -> list[str]:
    """Extract specific anchor tokens (author surnames + numeric values) a
    quote needs to contain to count as grounding the claim.

    Returns the literal anchors as strings. Empty list = no specific
    anchor — the claim is descriptive/general and any plausible quote
    in the chunk suffices.
    """
    out: list[str] = []
    for m in _ANCHOR_AUTHOR_RE.finditer(text):
        out.append(m.group(1))
    for m in _ANCHOR_VALUE_RE.finditer(text):
        out.append(m.group(1))
    return out


def verify_section_draft(
    draft: SectionDraft,
    chunks_by_id: "dict[int, Chunk]",
    ratio_threshold: float = 0.85,
) -> tuple[list[GroundedClaim], list[dict]]:
    """Drop claims whose `cited_quote` doesn't fuzzy-match any chunk.

    Match criterion: the longest contiguous run of `cited_quote` characters
    found in the chunk text must cover at least `ratio_threshold` of the
    quote's length. Exact-substring case returns 1.0; verbatim-with-typo
    LLM output stays well above 0.85.

    Empty quotes skip verification (cited_chunk_ids alone is the grounding
    signal — the LLM may still write good prose without verbatim quoting).

    Tries the claim's `cited_chunk_ids` first. If none match, falls back to
    scanning ALL retrieved chunks — LLMs sometimes quote from chunk A but
    write `cited_chunk_ids=[B]` (chunk-ID slop). When the fallback succeeds,
    the claim's cited_chunk_ids are patched to point at the chunk that
    actually contains the quote.

    Anchor check: when the claim text names a specific author (`X et al.`)
    or a specific numeric value (`2.94 J/cm³`, `91.04%`), the cited_quote
    must contain that anchor verbatim. Otherwise the quote is "in the
    chunk" but doesn't *support* the specific fact — the verifier flags
    this as an ungrounded citation even though the quote was real.
    """
    accepted: list[GroundedClaim] = []
    rejected: list[dict] = []
    for c in draft.claims:
        if not c.cited_quote.strip():
            accepted.append(c)
            continue
        best_score = 0.0
        matched_cid: int | None = None
        for cid in c.cited_chunk_ids:
            ch = chunks_by_id.get(cid)
            if ch is None:
                continue
            score = _quote_in_chunk(c.cited_quote, ch.text, ratio_threshold)
            best_score = max(best_score, score)
            if score >= ratio_threshold:
                matched_cid = cid
                break
        if matched_cid is None:
            # Chunk-ID slop fallback: search the whole retrieved set.
            cited_set = set(c.cited_chunk_ids)
            for cid, ch in chunks_by_id.items():
                if cid in cited_set:
                    continue
                score = _quote_in_chunk(c.cited_quote, ch.text, ratio_threshold)
                if score > best_score:
                    best_score = score
                if score >= ratio_threshold:
                    matched_cid = cid
                    break
        # Anchor advisory: when the claim names a specific author/value
        # but the quote doesn't contain that anchor, log it as a soft
        # warning (the claim is accepted as long as the quote
        # substring-matches some chunk). Enforcement-as-rejection was too
        # strict in practice — it killed correctly-written claims when
        # the LLM picked a poorly-aligned quote from the same chunk.
        anchors = _claim_anchors(c.text)
        anchor_advisory: list[str] = []
        if anchors and matched_cid is not None:
            q_norm = _normalize_for_match(c.cited_quote)
            anchor_advisory = [a for a in anchors
                               if _normalize_for_match(a) not in q_norm]
        if matched_cid is not None:
            if matched_cid not in c.cited_chunk_ids:
                c = c.model_copy(update={
                    "cited_chunk_ids": [matched_cid, *c.cited_chunk_ids],
                })
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
    """Return the index of a retrieved chunk that "covers" the entity, or
    None if no chunk is plausible.

    Primary: exact doc+span match (the v1.4 contract — works when the KG
    extractor fills `source_span = (chapter_filename, char_start, char_end)`).

    Fallback 1: text-match — when the LLM filled a generic placeholder
    for the doc name (e.g. `doc='paper'`), or the char offsets are
    unreliable, scan retrieved chunks for the entity's text as a
    substring. Strategy KL needs the comparator in the required-mentions
    block; missing the exact span is acceptable as long as a chunk
    plausibly contains the fact.

    Fallback 2: when no chunk text-matches, fall through to the first
    retrieved chunk. The LLM still sees the required entity in the
    prompt's required-mentions block; the cited_chunk_id we pass is best-
    effort. Verifier + retry-when-empty handle the rest.
    """
    doc, start, end = entity.source_span
    mid = (start + end) // 2
    # Primary: exact doc + span match.
    for i, ch in enumerate(retrieved_chunks):
        if ch.doc_name == doc and ch.char_start <= mid < ch.char_end:
            return i
    # Fallback 1: text-substring match.
    text = (entity.text or "").strip().lower()
    if text and len(text) >= 4:
        for i, ch in enumerate(retrieved_chunks):
            if text in ch.text.lower():
                return i
    # Fallback 2: first retrieved chunk (best-effort). Logged because
    # this masks KG-extraction-quality regressions — when the LLM fills
    # a placeholder doc name AND text-substring also misses, the entity
    # silently routes to chunk 0 and the user has no signal.
    if retrieved_chunks:
        safe_text = (entity.text or "")[:60]  # audit α#1: defend against None
        print(f"[s08] _find_chunk_for_entity_span: fallback-2 (chunk 0) "
              f"for entity={safe_text!r} doc={doc!r}", flush=True)
        return 0
    return None


def _evidence_quote(
    entity: "Entity",
    source_docs: dict[str, str],
    max_chars: int = 200,
) -> str:
    doc, start, end = entity.source_span
    src = source_docs.get(doc, "")
    if not src:
        # Fallback: KG LLM filled a placeholder doc name (e.g. 'paper').
        # Look for the entity's text inside any known source doc and
        # return a window around the first match. Note: this snippet's
        # span no longer matches `entity.source_span` (audit α#6) —
        # callers that re-validate doc-name later may mismatch.
        needle = (entity.text or "").strip()
        if not needle or len(needle) < 4:
            return ""
        for src_text in source_docs.values():
            idx = src_text.find(needle)
            if idx < 0:
                continue
            pad_left = max(0, idx - 30)
            pad_right = min(len(src_text), pad_left + max_chars)
            return src_text[pad_left:pad_right].replace("\n", " ").strip()[:max_chars]
        return ""
    # Audit α#5 / β#4: the old formula `end + (max_chars - (end - start) - 30)`
    # could go negative for long spans (entity length > max_chars - 30) and
    # produce an empty/garbage snippet via accidental negative-index slicing.
    # The new formula anchors `pad_right` to a fixed `max_chars` window from
    # `pad_left`, which guarantees a stable snippet. NOTE: when the entity
    # itself is longer than `max_chars - 30`, the tail still gets clipped —
    # the snippet is bounded by `max_chars` either way. This is acceptable
    # because the snippet is a hint, not a verbatim transcript.
    pad_left = max(0, start - 30)
    pad_right = min(len(src), pad_left + max_chars)
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


def _author_for_comparator(
    comparator: "Entity",
    kg: "PaperKG",
) -> str:
    """v1.7 / KG-v3: find the `author` entity linked to this comparator
    via `cited_by_paper` (or `cited_by`) relation. Returns the author's
    text (e.g. 'Jiang') or '' if not in the KG.
    """
    for rel in kg.relations:
        if rel.object != comparator.id:
            continue
        if rel.predicate not in ("cited_by_paper", "cited_by", "authored_by"):
            continue
        author = next((e for e in kg.entities
                       if e.id == rel.subject and e.type == "author"), None)
        if author:
            return author.text
    # Also try the reverse direction (comparator as subject)
    for rel in kg.relations:
        if rel.subject != comparator.id:
            continue
        if rel.predicate not in ("authored_by", "first_author", "cited_from"):
            continue
        author = next((e for e in kg.entities
                       if e.id == rel.object and e.type == "author"), None)
        if author:
            return author.text
    return ""


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
        author_text = (_author_for_comparator(e, kg)
                       if e.type == "comparator" else "")
        out.append(RequiredMention(
            entity_text=e.text,
            entity_type=e.type,
            evidence_chunk_id=chunk_idx,
            evidence_quote=_evidence_quote(e, source_docs),
            linked_values=_linked_values_for_entity(e, kg),
            author_text=author_text,
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
  - includes the entity's verbatim text (chemical formula)
  - **when an `author` field is given, introduce the comparator using
    "<Author> et al." form**, e.g. "Jiang et al. reported W_rec=2.94 J/cm³
    in Ca²⁺/Nb⁵⁺-codoped Bi₀.₅Na₀.₅TiO₃". Author attribution is required
    when provided; do not skip it.
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
        author = (f"  author: \"{r.author_text} et al.\"  "
                  f"(use this form when introducing the comparator in prose)\n"
                  if r.author_text else "")
        lines.append(
            f"- {r.entity_type}: \"{r.entity_text}\"\n"
            f"{author}"
            f"  evidence_chunk_id: {r.evidence_chunk_id}\n"
            f"  evidence_quote: \"{r.evidence_quote[:200]}\"\n"
            f"{vals}"
        )
    return "\n".join(lines)


def _single_compose(
    llm, system: str, user_msg: str, chunks: list["Chunk"],
    max_retries: int, temperature: float,
) -> "SectionDraft":
    """One instructor + SectionDraft call. Helper for compose_structured."""
    import instructor
    from instructor import Mode
    client = instructor.from_openai(llm._client, mode=Mode.MD_JSON)
    allowed = set(range(len(chunks)))
    return client.chat.completions.create(
        model=llm.model,
        response_model=SectionDraft,
        validation_context={"allowed_chunk_ids": allowed},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        max_retries=max_retries,
        temperature=temperature,
    )


def _claim_dedup_key(text: str) -> str:
    """Return a paraphrase-resistant dedupe signature for a claim.

    Two claims that name the same author/value pair OR start with the same
    120-char prefix collapse to the same key. The anchor-based half catches
    paraphrases like
        "Jiang et al. 在Ca²⁺/Nb⁵⁺共掺杂…W_rec=2.94 J/cm³"
        "Jiang et al. 在Ca²⁺/Nb⁵⁺-codoped…W_rec=2.94 J/cm³"
    that the previous prefix-only check kept as separate claims.
    """
    anchors = _claim_anchors(text)
    if anchors:
        return "anchors:" + "|".join(sorted(anchors))
    return "prefix:" + text.strip()[:120]


def _merge_drafts(drafts: list["SectionDraft"], max_claims: int = 14) -> "SectionDraft":
    """Strategy K: union-merge multiple drafts via round-robin interleave.

    Take the i-th claim from each draft in turn (1st-from-run1, 1st-from-run2,
    2nd-from-run1, 2nd-from-run2, ...). Dedupe on a paraphrase-resistant
    signature: claims that name the same (author, value) anchors are
    treated as duplicates even when their prose differs substantially.

    Caps at max_claims (SectionDraft's enforced upper bound is 14).
    Falls back to the first draft if dedup leaves < 2 claims.
    """
    if not drafts:
        raise ValueError("no drafts to merge")
    interleaved: list[GroundedClaim] = []
    seen_keys: set[str] = set()
    max_len = max(len(d.claims) for d in drafts)
    for i in range(max_len):
        for d in drafts:
            if i >= len(d.claims):
                continue
            c = d.claims[i]
            key = _claim_dedup_key(c.text)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            interleaved.append(c)
            if len(interleaved) >= max_claims:
                return SectionDraft(claims=interleaved)
    if len(interleaved) < 2:
        return drafts[0]
    return SectionDraft(claims=interleaved)


_FIG_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{3,}|[一-鿿]{2,}")


def _figure_relevance(
    section_title: str,
    section_guidance: str,
    fig_notes: list[dict],
    top_k: int = 4,
) -> list[dict]:
    """Pick the figures most topically relevant to this section.

    Score = Jaccard overlap between (title + guidance) tokens and
    (caption + deep_observation) tokens. Returns the top-k notes as the
    original dicts (so callers can pull out `fig_id`, `caption`, etc.).
    Empty list when no fig_notes — caller passes nothing to the prompt.
    """
    if not fig_notes:
        return []
    section_tokens = set(_FIG_TOKEN_RE.findall(
        (section_title + " " + section_guidance).lower()
    ))
    if not section_tokens:
        return []
    scored: list[tuple[float, dict]] = []
    for note in fig_notes:
        cap = str(note.get("caption", ""))
        obs = str(note.get("deep_observation", ""))
        fig_tokens = set(_FIG_TOKEN_RE.findall((cap + " " + obs).lower()))
        if not fig_tokens:
            continue
        union = section_tokens | fig_tokens
        overlap = len(section_tokens & fig_tokens)
        if overlap == 0:
            continue
        scored.append((overlap / len(union), note))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [n for _, n in scored[:top_k]]


def _format_section_figures_block(notes: list[dict]) -> str:
    if not notes:
        return "(no figures topically relevant to this section)"
    lines: list[str] = []
    for n in notes:
        fid = n.get("fig_id", "?")
        cap = str(n.get("caption", "")).replace("\n", " ")[:140]
        lines.append(f"- {fid}: {cap}")
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
    section_figures: list[dict] | None = None,
    max_retries: int = 3,
) -> tuple["SectionDraft", list[dict]]:
    """instructor call → SectionDraft → verifier gate.

    Strategy K (env `LAZY_PAPER_BEST_OF_N`, default 1): when set to N>1,
    run the LLM N times with slightly different temperature and union-
    merge the resulting drafts. Lifts per-paper benchmark coverage at
    Nx LLM cost; DeepSeek input caching makes the chunk-list overhead
    almost free across the N calls.

    Returns the verified SectionDraft (claims filtered to those whose
    cited_quote matched their chunk) + a list of rejected_log dicts for
    audit. Raises if instructor fails after max_retries.
    """
    import os as _os
    chunks_block = _format_chunks_block(chunks)
    required_block = _format_required_block(required)
    figures_msg = ""
    if section_figures:
        figures_msg = (
            f"## Figures topically relevant to this section\n"
            f"{_format_section_figures_block(section_figures)}\n"
            f"   (Prefer these when you cite a figure; do not reference "
            f"figures whose caption is unrelated to this section's topic "
            f"unless the source chunk explicitly cross-references them.)\n\n"
        )
    user_msg = (
        f"## Section to write\n"
        f"- Title: {section_title}\n"
        f"- Guidance: {section_guidance}\n"
        f"- Language: {lang_instruction}\n\n"
        f"## Paper context\n{paper_context}\n\n"
        f"## Available chunks (cite ONLY these 0-based IDs)\n{chunks_block}\n\n"
        f"## Required mentions (you MUST cover each)\n{required_block}\n\n"
        f"{figures_msg}"
        f"## Already established in prior sections (refer back, do not restate)\n"
        f"{prior_findings or '(this is the first section)'}\n\n"
        f"Emit the SectionDraft JSON now."
    )

    n = max(1, int(_os.environ.get("LAZY_PAPER_BEST_OF_N", "1")))
    if n == 1:
        draft = _single_compose(llm, _STRUCTURED_SYSTEM, user_msg, chunks,
                                max_retries, temperature=0.2)
    else:
        # Strategy K: N independent samples at slightly varied temperatures
        # so the LLM picks different comparators across runs, then merge.
        # Widened spread (was 0.15) to push more diversity into the pool.
        drafts: list[SectionDraft] = []
        for i in range(n):
            temp = 0.2 + 0.2 * i  # 0.2, 0.4, 0.6...
            try:
                drafts.append(_single_compose(
                    llm, _STRUCTURED_SYSTEM, user_msg, chunks,
                    max_retries, temperature=temp,
                ))
            except Exception as exc:
                if not drafts:
                    raise
                # Tolerate later sample failures, but log them — without
                # this print, a rate-limit / context-window error on
                # sample N would silently drop N from the merge with no
                # user signal (audit α#8).
                print(f"[s08] best-of-N sample {i} failed: {exc!r}; "
                      f"continuing with {len(drafts)} draft(s)",
                      flush=True)
                continue
        draft = _merge_drafts(drafts)

    # Verifier threshold is env-overridable for users who want stricter
    # quote-grounding (raise) or looser tolerance for paraphrasing (lower).
    verifier_threshold = float(
        _os.environ.get("LAZY_PAPER_VERIFIER_THRESHOLD", "0.85")
    )
    chunks_by_id = {i: c for i, c in enumerate(chunks)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=verifier_threshold,
    )
    verified = SectionDraft(claims=accepted) if len(accepted) >= 2 else draft

    # v1.8 retry-when-empty: trigger on POST-VERIFY coverage. The verifier
    # can drop comparator-citing claims if their cited_quote fails to
    # match (LaTeX/OCR drift handled by _normalize_for_match, but quote
    # hallucination is still possible). When verified coverage is poor,
    # one strengthened retry usually lifts the floor.
    retry_threshold = float(
        _os.environ.get("LAZY_PAPER_RETRY_THRESHOLD", "0.5")
    )
    if required and len(required) >= 2:
        pre_missing = missing_required(required, draft)
        post_missing = missing_required(required, verified)
        pre_cov = (len(required) - len(pre_missing)) / len(required)
        post_cov = (len(required) - len(post_missing)) / len(required)
        print(
            f"[s08] structured-compose: required={len(required)} "
            f"pre-verify-missing={len(pre_missing)} ({pre_cov:.0%}) "
            f"post-verify-missing={len(post_missing)} ({post_cov:.0%})",
            flush=True,
        )
        if post_cov <= retry_threshold:
            # v1.9: precise per-entity diagnosis. Instead of a generic
            # "you missed required mentions" reminder, list each missing
            # entity with the specific anchor (author surname OR a key
            # value) the LLM must include. This is the
            # informed-retry pattern from OpenScholar / LitLLM — the
            # model can't choose to skip an entity when the diagnosis
            # tells it exactly which token to write.
            missing_diag_lines = []
            for r in post_missing:
                anchor_hints = []
                if r.author_text:
                    anchor_hints.append(
                        f"\"{r.author_text} et al.\" or \"{r.author_text} 等人\""
                    )
                for v in r.linked_values:
                    # linked_values shape: "W_rec=2.94 J/cm³"
                    anchor_hints.append(f"\"{v}\"")
                anchor_str = " OR ".join(anchor_hints) if anchor_hints else \
                    f"the entity text \"{r.entity_text}\""
                missing_diag_lines.append(
                    f"  - **{r.entity_type}**: {r.entity_text[:70]!r}\n"
                    f"      → write a claim containing {anchor_str}\n"
                    f"      → evidence chunk: [{r.evidence_chunk_id}]"
                )
            missing_diag = "\n".join(missing_diag_lines)
            retry_system = _STRUCTURED_SYSTEM + (
                "\n\n## CRITICAL — SPECIFIC REQUIRED MENTIONS MISSING\n"
                f"Your previous draft covered "
                f"{len(required) - len(post_missing)}/{len(required)} "
                f"required entities. The following entities are NOT yet "
                f"covered — your next draft MUST include each, with the "
                f"specific anchor token shown:\n\n"
                f"{missing_diag}\n\n"
                "Rules:\n"
                "  - Write ONE GroundedClaim per missing entity above.\n"
                "  - Each claim's text MUST contain the listed anchor token "
                "verbatim (author surname OR numeric value).\n"
                "  - Copy a slice from the evidence chunk into cited_quote, "
                "verbatim (the verifier substring-matches; LaTeX and OCR "
                "whitespace are auto-normalized).\n"
                "  - Set cited_chunk_ids to the evidence chunk index given.\n"
                "  - PRESERVE existing well-covered claims from the prior "
                "draft; add the missing ones, do not regenerate everything."
            )
            try:
                retry_draft = _single_compose(
                    llm, retry_system, user_msg, chunks,
                    max_retries=max_retries, temperature=0.3,
                )
                retry_accepted, retry_rejected = verify_section_draft(
                    retry_draft, chunks_by_id,
                    ratio_threshold=verifier_threshold,
                )
                retry_verified = (SectionDraft(claims=retry_accepted)
                                  if len(retry_accepted) >= 2
                                  else retry_draft)
                retry_post_missing = missing_required(required, retry_verified)
                if len(retry_post_missing) < len(post_missing):
                    print(
                        f"[s08] retry-when-empty: lifted post-verify "
                        f"coverage from "
                        f"{len(required) - len(post_missing)}/{len(required)} "
                        f"to "
                        f"{len(required) - len(retry_post_missing)}/{len(required)}",
                        flush=True,
                    )
                    # Also rebind `accepted` so the downstream retry-when-short
                    # guard compares against the updated verifier-accepted set
                    # (audit α#13: stale `accepted` reference).
                    verified, rejected = retry_verified, retry_rejected
                    accepted = retry_accepted
            except Exception as exc:
                print(f"[s08] retry-when-empty failed: {exc!r}; keeping "
                      f"original draft", flush=True)

    # v1.9 retry-when-short: an orthogonal trigger to retry-when-empty.
    # When the verified draft is well-covered on required mentions but
    # still too short / too sparse (e.g. ali2025_flash ch14: 0 missing,
    # 3 claims, 683 chars), one more LLM call usually thickens the
    # section without the LLM regenerating duplicate facts (the
    # no-duplicate rule in the system prompt covers that).
    min_chars = int(_os.environ.get("LAZY_PAPER_MIN_SECTION_CHARS", "500"))
    min_claims = int(_os.environ.get("LAZY_PAPER_MIN_SECTION_CLAIMS", "4"))
    verified_text = " ".join(c.text for c in verified.claims)
    if (min_chars > 0
            and (len(verified_text) < min_chars
                 or len(verified.claims) < min_claims)):
        print(
            f"[s08] structured-compose: verified={len(verified.claims)} claims "
            f"/ {len(verified_text)} chars — below "
            f"min_claims={min_claims} or min_chars={min_chars}",
            flush=True,
        )
        retry_system = _STRUCTURED_SYSTEM + (
            "\n\n## CRITICAL — SECTION TOO SHORT\n"
            f"Your previous draft has only {len(verified.claims)} verified "
            f"claims and {len(verified_text)} characters. Produce a more "
            "substantive draft with 5–8 distinct claims, each carrying its "
            "own quantitative anchor where the source supports it.\n\n"
            "**You must still cover every entry in the 'Required mentions' "
            "block above.** Do NOT skip the literature-citation comparators "
            "(`<Author> et al.`) to make room for general prose; instead, "
            "ADD additional substantive claims on top of those required "
            "mentions. The no-duplicate rule still applies."
        )
        try:
            len_retry_draft = _single_compose(
                llm, retry_system, user_msg, chunks,
                max_retries=max_retries, temperature=0.35,
            )
            len_retry_accepted, len_retry_rejected = verify_section_draft(
                len_retry_draft, chunks_by_id,
                ratio_threshold=verifier_threshold,
            )
            len_retry_verified = (SectionDraft(claims=len_retry_accepted)
                                  if len(len_retry_accepted) >= 2
                                  else len_retry_draft)
            len_retry_text = " ".join(c.text for c in len_retry_verified.claims)
            # Only swap if the retry is genuinely better. Three guards:
            #  - longer prose (otherwise length retry was pointless),
            #  - at least as many *verifier-accepted* claims (compare
            #    accepted counts, not post-fallback claim counts — the
            #    fallback returns the raw draft when accepted < 2, so
            #    a retry with 1 grounded + 5 ungrounded claims would
            #    appear "bigger" but be worse),
            #  - required-mention coverage not regressed.
            current_missing = len(missing_required(required, verified))
            new_missing = len(missing_required(required, len_retry_verified))
            # Audit β#3: require at least ONE verifier-accepted claim before
            # swapping. Otherwise `0 >= 0` would silently swap one fully-
            # ungrounded draft for another and log a misleading "lifted N→M".
            if (len(len_retry_text) > len(verified_text)
                    and len(len_retry_accepted) >= len(accepted)
                    and len(len_retry_accepted) >= 1
                    and new_missing <= current_missing):
                print(
                    f"[s08] retry-when-short: lifted "
                    f"{len(verified.claims)}→{len(len_retry_verified.claims)} "
                    f"claims, {len(verified_text)}→{len(len_retry_text)} chars "
                    f"(accepted {len(accepted)}→{len(len_retry_accepted)}, "
                    f"required missing {current_missing}→{new_missing})",
                    flush=True,
                )
                verified, rejected = len_retry_verified, len_retry_rejected
            elif len(len_retry_text) > len(verified_text):
                print(
                    f"[s08] retry-when-short: REJECTED — "
                    f"accepted {len(accepted)}→{len(len_retry_accepted)}, "
                    f"coverage {current_missing}→{new_missing} missing. "
                    f"Keeping original draft.",
                    flush=True,
                )
        except Exception as exc:
            print(f"[s08] retry-when-short failed: {exc!r}; keeping "
                  f"original draft", flush=True)

    return verified, rejected


def missing_required(
    required: list[RequiredMention],
    draft: SectionDraft,
) -> list[RequiredMention]:
    """Return the subset of `required` whose ENTITY TEXT is not actually
    present in the draft's prose.

    Earlier (v1.7) impl checked whether the entity's `evidence_chunk_id`
    was cited by any claim — but a claim can cite a chunk and still write
    generic content that doesn't include the comparator. The content-based
    check (substring + distinctive-token match + author-name match,
    same logic as coverage.py) is the only reliable way to know if the
    LLM ACTUALLY mentioned the required entity.
    """
    from stages.s08_section_compose.coverage import _distinctive_tokens
    full_text = " ".join(c.text for c in draft.claims).lower()
    out: list[RequiredMention] = []
    for r in required:
        ent_lower = r.entity_text.lower()
        if ent_lower in full_text:
            continue
        distinctive = _distinctive_tokens(r.entity_text)
        if distinctive and any(t in full_text for t in distinctive):
            continue
        if r.author_text:
            # Word-boundary check to avoid e.g. "Ma" matching inside "materials"
            import re as _re
            if _re.search(rf"\b{_re.escape(r.author_text)}\b", full_text,
                          flags=_re.IGNORECASE):
                continue
        out.append(r)
    return out
