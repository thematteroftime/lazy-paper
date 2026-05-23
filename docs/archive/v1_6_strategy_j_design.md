# v1.6 Design — Strategy J: Pre-injection + Structured Citation Emission

> **Status**: design draft, awaiting user approval before implementation.
> Based on the SOTA research from the 3 v1.5 subagent reports and the
> empirical finding that v1.5 Strategy E (post-hoc critic + revision) caps
> at ~4.5/16 mean recovery due to LLM sampling noise on "add content"
> operations. Strategy J replaces post-hoc revision with **architectural
> grounding** — citations are constrained at the schema level, not asked
> for in prose.

## The architectural inheritance

| Component | Source | What we take |
|---|---|---|
| **Pre-injection** | Perplexity AI | Don't ask the LLM to discover citations — give it a numbered chunk list before generation, then constrain output to reference only those IDs. The LLM cannot hallucinate a citation that wasn't in its context. |
| **Structured output + Pydantic validator** | instructor + DeepSeek `Mode.MD_JSON` | The LLM cannot deviate from the schema. A `cited_chunk_ids` field with a custom validator that rejects IDs not in the allowed set kills hallucinated citations at parse time. |
| **Citation rendering** | Onyx `citation_processor.py` (vendored at `llm/citation/stream_processor.py`) | Three modes (HYPERLINK/KEEP/REMOVE) for rendering the markers in the final docx/html. Already in tree from v1.4.0. |
| **Verifier gate** | ClarityArc 2025 production architecture | After the LLM emits a `cited_quote`, fuzzy-match it (`SequenceMatcher.ratio() > 0.90`) against the actual chunk text. Drop or re-prompt on failure. Lifts reported reliability from ~70–80% to 88–92%. |
| **Quote-then-claim** | Chain-of-Verification / ACL 2024 | Force the LLM to emit a verbatim source quote before its synthesis claim — verifiable, not paraphrasable away. |

## What stays from v1.4/1.5

- **PaperDB layer** (s06 KG + s08 retriever).
- **KG-v2 prompt** (paper_kg_v2.md) for comparator extraction; this becomes the default.
- **Default retriever** (Strategy C: title + guidance + KG-scoped entities, top-15, 25K context).
- **Coverage critic** (Strategy A) — but its role changes from "flag missing entities post-hoc" to "select which entities to pre-inject as required-mention list".
- **Onyx citation processor** — render-side only.

## What changes

The s08 `_legacy_compose` function is replaced by a new `_structured_compose`
when Strategy J is enabled (initially env-gated `LAZY_PAPER_STRUCTURED=1`;
ship as default after the validation passes).

### Per-section pipeline (v1.6)

```
┌─────────────────────────────────────────────────────────────────┐
│ s08 per-section pipeline (Strategy J)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Build retrieval query (Strategy C) — title + guidance       │
│     + KG-scoped entity texts + keywords                         │
│                                                                 │
│  2. Retriever.retrieve(query, top_k=15) → chunks                │
│                                                                 │
│  3. Coverage-driven required entities                           │
│     - entities_in_scope(title, guidance, kg)                    │
│     - For each scoped entity, locate its source_span chunk      │
│     - Build `required: list[RequiredMention]` — comparators,    │
│       claims, methods that section MUST cite                    │
│                                                                 │
│  4. Pre-inject prompt construction                              │
│     - Build numbered chunk list [1]..[15] with their doc spans  │
│     - List each required mention with (entity_text, chunk_id,   │
│       evidence_quote)                                           │
│     - Issue compose instruction with allowed chunk ID set       │
│                                                                 │
│  5. Single LLM call via instructor + Pydantic SectionDraft      │
│     - Model: deepseek-reasoner (or R1-0528 when available)      │
│     - Mode.MD_JSON (works around R1's reasoning trace)          │
│     - Schema rejects unknown chunk_ids in cited_chunk_ids       │
│                                                                 │
│  6. Verifier gate                                               │
│     - For each GroundedClaim, fuzzy-match cited_quote against   │
│       its declared chunk_id's actual text                       │
│     - Drop claims with ratio < 0.90 OR retry with the diff      │
│                                                                 │
│  7. Render via Onyx citation_processor                          │
│     - draft.render(mode=REMOVE|KEEP|HYPERLINK)                  │
│     - default REMOVE for docx; HYPERLINK for html               │
│                                                                 │
│  8. critic_flags.yaml audit                                     │
│     - Required mentions NOT cited in any claim                  │
│     - Verifier gate rejections                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Pydantic schema (v1.6 — to be added at `stages/s08_section_compose/structured.py`)

```python
"""Strategy J — structured composition with pre-injection and verifier gate."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, ValidationInfo


class GroundedClaim(BaseModel):
    """One sentence-or-paragraph of the section, anchored to one or more
    retrieved chunks. The LLM may NOT cite a chunk ID not in the context."""
    text: str = Field(min_length=10,
                      description="The Chinese (or English) prose. May "
                                  "contain inline [span:chunk_id] markers "
                                  "where citation_processor wants them, but "
                                  "you are not required to emit them — the "
                                  "rendering layer assembles them from your "
                                  "cited_chunk_ids field.")
    cited_chunk_ids: list[int] = Field(default_factory=list,
                                       description="0-based indices into the "
                                                   "pre-injected chunk list. "
                                                   "Each claim cites ≥1 chunk; "
                                                   "max 4 per claim.")
    cited_quote: str = Field(default="",
                             description="Verbatim text copied from one of "
                                         "the cited chunks. Used by the "
                                         "verifier to confirm grounding.")

    @field_validator("cited_chunk_ids")
    @classmethod
    def validate_chunk_ids(cls, ids: list[int], info: ValidationInfo) -> list[int]:
        allowed = (info.context or {}).get("allowed_chunk_ids", set())
        if allowed:
            bad = [i for i in ids if i not in allowed]
            if bad:
                raise ValueError(f"chunk_ids {bad} not in retrieved set "
                                 f"{sorted(allowed)[:5]}...")
        return ids


class SectionDraft(BaseModel):
    """The complete section. List of grounded claims; render() assembles
    them into prose with citation markers in the requested mode."""
    claims: list[GroundedClaim] = Field(min_length=3, max_length=12)

    def render(self, mode: Literal["REMOVE", "KEEP", "HYPERLINK"],
               chunks_by_id: dict[int, "Chunk"]) -> str:
        from llm.citation import process_text, CitationMode
        out_parts: list[str] = []
        for c in self.claims:
            sentence = c.text.strip()
            if mode != "REMOVE":
                # Inject markers using the chunks_by_id to format
                for cid in c.cited_chunk_ids:
                    ch = chunks_by_id[cid]
                    marker = f"[span:{ch.doc_name}:{ch.char_start}-{ch.char_end}]"
                    sentence = sentence.rstrip(".") + f" {marker}."
            out_parts.append(sentence)
        text = " ".join(out_parts)
        sources = [{"document_id": ch.doc_name,
                    "link": str(ch.doc_name)} for ch in chunks_by_id.values()]
        return process_text(text, mode=getattr(CitationMode, mode), sources=sources)


class RequiredMention(BaseModel):
    """A KG entity the section MUST cite. Built from entities_in_scope() +
    coverage check on guidance keywords."""
    entity_text: str           # e.g. "Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3-based RFE ceramics"
    entity_type: str           # comparator | claim | method
    evidence_chunk_id: int     # which retrieved chunk contains the source
    evidence_quote: str        # 50-100 char excerpt from that chunk
    linked_values: list[str]   # e.g. ["W_rec=2.94 J/cm³", "η=91.04%"]
```

### Compose-time system prompt

The compose prompt explicitly enumerates the allowed chunk IDs and required
mentions BEFORE the section guidance. Key innovations vs v1.4.2:

```
SYSTEM:
You are composing one section of a research-paper deep analysis.

You have been given a numbered list of source chunks below. Every claim
in your output MUST cite at least one chunk by its ID, and you may ONLY
cite chunks from this list — if you reference content from outside, the
output will be rejected.

Some claims are REQUIRED — they are listed under "Required mentions"
below. You MUST include a claim that covers each required entity, with
the entity's verbatim text and any linked numeric value from its
evidence_quote.

Output a SectionDraft JSON object — see the Pydantic schema.

Quote-then-claim discipline (highest reliability):
- For each numeric claim, set `cited_quote` to the exact source text
  that contains the number, copied verbatim from the chunk.
- The verifier will fuzzy-match this against the chunk; mismatches are
  rejected.

USER:
## Section to write
- Title: {title}
- Guidance: {guidance}
- Language: {lang_instruction}

## Available chunks (cite ONLY these IDs)
[0] (chapter_001_INTRODUCTION.md chars 2573-3247)
    "As reported by Jiang et al., a moderate W_rec of 2.94 J/cm³ and
    a high η of 91.04% were achieved in Ca2+/Nb5+-codoped..."
[1] (chapter_001_INTRODUCTION.md chars 3247-3548)
    "Ma et al. realized a large W_rec of 7.5 J/cm³ with a high η of
    90.5% by introducing La(Mg1/2Zr1/2)O3..."
...

## Required mentions (you MUST cite each of these)
- comparator: "Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3-based RFE ceramics"
  evidence_chunk_id: 0
  evidence_quote: "Jiang et al., a moderate W_rec of 2.94 J/cm³..."
  linked_values: ["W_rec=2.94 J/cm³", "η=91.04%"]
- comparator: "La(Mg1/2Zr1/2)O3-modified NBT-based RFE ceramics"
  evidence_chunk_id: 1
  ...

## Already established in prior sections (do not restate verbatim)
{prior_findings}

Write the SectionDraft now.
```

### The verifier gate

```python
from difflib import SequenceMatcher

def verify_section_draft(draft: SectionDraft,
                        chunks_by_id: dict[int, Chunk],
                        ratio_threshold: float = 0.85) -> list[GroundedClaim]:
    """Drop claims whose cited_quote doesn't fuzzy-match its source chunk."""
    accepted: list[GroundedClaim] = []
    rejected_log: list[dict] = []
    for c in draft.claims:
        if not c.cited_quote.strip():
            accepted.append(c)  # no quote = no grounding to verify
            continue
        # try each cited chunk; accept if any one matches
        any_match = False
        best_ratio = 0.0
        for cid in c.cited_chunk_ids:
            ch = chunks_by_id.get(cid)
            if not ch:
                continue
            ratio = SequenceMatcher(None, c.cited_quote.strip(),
                                    ch.text).quick_ratio()
            # quick_ratio is upper-bound; do real ratio only if quick > threshold
            if ratio > ratio_threshold:
                real_ratio = SequenceMatcher(None, c.cited_quote.strip(),
                                              ch.text).ratio()
                best_ratio = max(best_ratio, real_ratio)
                if real_ratio > ratio_threshold:
                    any_match = True
                    break
        if any_match:
            accepted.append(c)
        else:
            rejected_log.append({"text": c.text[:80],
                                "quote": c.cited_quote[:80],
                                "best_ratio": best_ratio})
    return accepted, rejected_log
```

## File layout

```
stages/s08_section_compose/
    structured.py             NEW ~150 LOC
      - GroundedClaim, SectionDraft, RequiredMention Pydantic
      - compose_structured() — instructor call + verifier gate
      - build_required_mentions() — coverage-driven required list
    runner.py                 MODIFY
      - env-gated branch: if LAZY_PAPER_STRUCTURED=1, use compose_structured
      - _legacy_compose stays as fallback for missing PaperDB
    tests/test_structured.py  NEW ~60 LOC
      - Pydantic validator rejects unknown chunk IDs
      - Verifier gate accepts fuzzy match ≥ 0.90
      - Verifier gate rejects below threshold
      - Build_required_mentions includes scoped comparators
```

Touch count: 1 new file, 1 minor edit to runner, 1 new test file.
LOC budget: ~250 total. No new pip deps (instructor + Pydantic + difflib already in tree).

## Test plan

Same meng2024 ch01 benchmark recovery harness from
`docs/v1_5_experimental_results.md`. Targets:

| Metric | v1.3.3 | v1.5 E (best) | **v1.6 J target** |
|---|---|---|---|
| author recovery /4 | 4 | 1 (range 0–4) | **≥3 across 3 runs** |
| value recovery /8 | 8 | 2 (range 0–2) | **≥5 across 3 runs** |
| formula recovery /4 | 1 | 3 (range 0–3) | **≥3 across 3 runs** |
| total /16 (mean) | 13 | 4.5 | **≥10** |
| variance | n/a | high (3 vs 6) | **≤2 across 3 runs** |

If 3 sequential runs each hit ≥10/16 and stdev ≤2, ship J as default.
If 2/3 hit ≥10 but variance still high, ship as opt-in. If <2/3 hit ≥10,
the schema/prompt needs another iteration.

Secondary metrics:
- Citation marker density (should be ≥85% of bullets in any section with
  retrieved evidence) — currently 0% even in Strategy E
- Verifier rejection rate (target ≤10% — too high means LLM is paraphrasing
  cited_quote)
- LLM call cost per section (target ≤1.3× baseline; if higher, structured
  output overhead is too costly)

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Pydantic validator failure rate high (instructor max_retries=2 not enough) | medium | Cap retries at 3; on final failure, fall back to `_legacy_compose` with Strategy E enabled. Soft-degrade per-section, not per-paper. |
| `cited_quote` fuzzy match too strict (rejects real-but-paraphrased grounding) | low–medium | Default threshold 0.85 (was 0.90 in research); tune if rejection rate >15% |
| Required mentions for non-survey sections cause LLM to force-insert literature where it doesn't belong | low | `entities_in_scope` already gates comparators to Introduction/Discussion/Comparison; non-survey sections get no required mentions, plain compose |
| Structured output regresses prose flow (LLM optimizes for schema completion, not narrative) | medium | Compare chapter prose quality vs v1.4.2 baseline — if measurably worse, add a "polish" 2nd LLM pass that takes the validated claims + writes flowing prose |
| Cost up due to retries + verifier re-prompts | low | DeepSeek input caching makes the 25K-token chunk-list block effectively free across retries |

## What this defers / does NOT do

- Whole-paper coherence pass (Strategy F) — still v1.7+
- Switch to DeepSeek-R1-0528 — orthogonal; can do whenever
- RAPTOR / HippoRAG 2 — research-grade, not needed if J works
- Strategy I (whole-paper) — confirmed not useful; left as opt-in only

## Implementation sequence (when approved)

1. Day 1 — schema + verifier (test-driven, no LLM calls):
   - `GroundedClaim`, `SectionDraft`, `RequiredMention` Pydantic
   - `verify_section_draft` with synthetic fixture
   - validator-rejects-unknown-chunk-id test
   - 5 unit tests, no API calls

2. Day 2 — compose pipeline + integration:
   - `compose_structured(...)` instructor wrapper
   - `build_required_mentions(...)` from KG + coverage
   - prompt template (the v1.6 system + user above)
   - wire into runner.py env-gated

3. Day 3 — live testing on meng2024:
   - 3 sequential runs with `LAZY_PAPER_STRUCTURED=1`
   - record metrics from "Test plan" table
   - compare to v1.5 Strategy E baseline (already in `docs/v1_5_experimental_results.md`)
   - if pass: ship as v1.6.0, env-gated default-on for sections with required-mentions
   - if fail: iterate on schema/prompt; re-test

Expected wall clock: 2–3 days of focused work + a few hours of live test wall clock.

## Open questions for user

1. **Citation format**: keep `[span:doc:start-end]` (current Onyx-compatible) or switch to numeric `[1][2]` (Perplexity/Onyx-native)?
2. **REMOVE-by-default vs KEEP-by-default**: should DOCX render with citations visible by default for v1.6? Or stay hidden behind `--debug-citations`?
3. **Required-mention strictness**: hard fail the LLM call if a required entity isn't cited, or soft-warn? (My recommendation: soft-warn → audit log; hard fail only blocks shipping under-grounded chapters.)
4. **Cap on `required` count per section**: should we limit to e.g. top 5 most-distinctive comparators? Too many might overload the prompt.

After your answers I'll proceed with day-1 implementation.
