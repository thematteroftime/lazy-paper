# Content Optimization Roadmap — v1.4

> Status: **research-validated, awaiting implementation greenlight from maintainer**.
> v1.3.x closed all observable layout defects. v1.4 attacks the three content defects
> the parallel audits surfaced (template-driven hallucination, quoted-symbol drift,
> missed source facts) by switching the generation paradigm from "template fill" to
> "retrieve evidence → write → verify".
>
> This document was revised after a deep-research subagent stress-tested an earlier
> draft against the upstream repositories. See "Research findings" below for what
> changed vs. the v1.3.3 draft.

## The three content defects (recap)

| # | Defect | Where seen |
|---|---|---|
| 1 | **Template-driven hallucination** when source doesn't cover topic | yang2025 ch01 fabricated "8.6 J/cm³ at η=85%"; ch03 invented KNN/NBT review |
| 2 | **Quoted-symbol drift** | meng2024 ch01 conflated E_b (348 kV/cm) with test field (340 kV/cm) |
| 3 | **Missed direct source facts** | meng2024 ch10 missed "tape-casting" stated explicitly in source |

Common root: the LLM only sees keyword-matched excerpts, never the full source, and
no mechanism verifies what it generated against source.

## Refined two-stage plan for v1.4

The original draft had four stages; research showed two are right-sized for v1.4
and two should defer.

### Stage 1 — RAG over the paper (CONFIRMED, in-house build)

Replace keyword scoring with embedding retrieval scoped to the current section.

**Build, not depend on PaperQA2.** PaperQA2 is library-grade but its citations are
page-range scoped (not character-offset), it bundles its own answer-loop, and the
total adoption cost outweighs writing a 200-line retriever ourselves.

**Concrete spec**:

```
stages/s06_context/embed.py        # ~80 LOC
  build_index(chapters_dir, fig_notes) -> parquet
    chunks each chapter to 200-400 chars (preserve sentence boundaries)
    embeds via openai-compatible API (default: text-embedding-3-small or bge-m3)
    stores (doc_id, chunk_id, text, char_start, char_end, vec) rows

llm/retriever.py                   # ~120 LOC
  retrieve(index, query, top_k=8) -> list[Chunk]
    cosine-sim over the index parquet
    returns Chunk with char_start/end for stage 2 grounding
```

The char-offset span is critical — Stage 2's symbol-drift check needs to grep the
source for an exact substring. Page-level citations alone don't enable that.

**Figure notes are atomic.** Don't fragment a `deep_observation` (which is one
paragraph of vision-LLM critique). Embed each `fig_notes.yaml` entry as one chunk;
chunk only the cleaned chapter text.

**Prompt change in s08**:
> Use ONLY facts present in the `<evidence>` block below. If a fact you want to
> assert isn't grounded in evidence, write "this paper does not directly address
> X" instead of inventing.

**Cost**: LLM context per s08 call drops from 8K-15K → ~3K tokens (8 chunks × 400
chars + section guidance). Embedding cost ≈ $0.001 per paper.

**Effort**: ~3 days, mostly testing on the 10-paper corpus.

### Stage 2 — Self-Refine critic loop (CONFIRMED, Self-Refine pattern)

After s08 produces a chapter, run a deterministic-then-LLM verification.

**Two-tier verification**:

1. **Python regex tier (cheap, 100% reliable)** — Before the critic LLM sees the
   text, deterministic checks:
   - Every numeric assertion (e.g. `8.6 J/cm³`, `85%`, `348 kV/cm`) → string-match
     against the source (or normalized form). Unit normalization (`kV/cm` ↔
     `kV·cm⁻¹`, `4000 kV/cm` ↔ `4 MV/cm`) handled deterministically.
   - Every `Fig. N` reference → must exist in `s04_figures/figures.yaml`.
   - Every chemical formula (regex for `[A-Z][a-z]?\d+(\.\d+)?`) → must appear in
     source OR `s06_context/context.yaml`.
   - Failures collected as `(span, claim, problem)` tuples.

2. **LLM critic tier (Self-Refine pattern)** — Only if regex tier finds problems:
   - 3-prompt loop (Self-Refine spec): `init → feedback → refine`.
   - Feedback prompt receives the regex-flagged spans + the source excerpts they
     should have matched.
   - One revision round max (research finding: more rounds rarely help).

**License-safe critic checklist** — inspired by Sakana AI Scientist's reviewer
fields (Soundness/Clarity/Grounding/Quote-fidelity), reimplemented from scratch.
Their code is on a RAIL-derivative license, incompatible with our Apache-2.0.

**Effort**: ~3 days. Regex tier first (1 day); LLM tier on top (2 days).

**Cost**: ~+100% LLM calls per section (one critic, one revise). Earlier draft
estimated +30%; research showed that was unrealistic.

## What's deferred

### Stage 3 — Multi-perspective outliner — DEFER to v1.5

Originally proposed three roles (Outliner / Researcher / Synthesizer per section).
Research finding: STORM's three-role pattern is designed for open-domain Wikipedia
where multiple perspectives need surfacing. For a single grounded scientific
paper, Researcher and Synthesizer collapse to one call given retrieved evidence.

**Plan for v1.5**: try a 2-role pattern (Researcher with evidence → Composer).
Reassess after v1.4 audit results.

### Stage 4 — DSPy — DOWNGRADE to v2.0, Signature-only

Originally proposed DSPy as a compilation layer with automatic prompt optimization
(BootstrapFewShot). Research finding: BootstrapFewShot needs ≥20 labeled
(input, gold) pairs + a metric function. We have 10 papers, no gold annotations,
no quality metric.

**Plan for v2.0**: adopt `dspy.Signature` + `dspy.Predict` as a typed prompt scaffold
(replaces string templates with declared fields). **Skip the optimizer.** This is
a maintenance win, not a quality win.

### LangGraph — NOT ADOPTING

Considered: would LangGraph's state-machine + node-graph orchestration help?

**Research finding**: no.

LangGraph's selling points (checkpointing, durable execution, human-in-the-loop,
streaming, agent branching) map to problems we don't have. Our pipeline is a
deterministic 9-stage DAG with explicit `for stage in STAGE_ORDER` iteration —
no agent ambiguity, no branching cycles, no need for cross-process resume.

The simpler-equivalent already-in-repo approach:
- A `StageContext` dataclass passed between stages (state dict)
- A `@retry(max_attempts=2)` decorator on s08 LLM calls (or just `while attempts`)
- Per-section critic→revise loop written as plain Python `while problems and rounds < 1`

Total: ~30 LOC of orchestration vs. taking on a LangChain-adjacent framework
footprint that conflicts with our LiteLLM/openai-SDK minimalism.

If LangGraph becomes useful later (e.g., we add human-in-the-loop review or
multi-paper batch coordination), we'll revisit.

## Risk register (for the v1.4 implementer)

| Stage | Risk | Mitigation |
|---|---|---|
| 1 | Embedding service rate-limit on big papers | Batch embed in 64-chunk groups; retry on 429; cache by content-hash |
| 1 | Chunk boundary cuts a numeric value mid-formula | Preserve sentence boundaries; minimum chunk 100 chars |
| 1 | Figure notes get fragmented | Keep `fig_notes.yaml` entries atomic — one chunk per figure |
| 2 | Critic loop runs away in cost | Hard cap: 1 revision round per chapter, 3 retries per stage total |
| 2 | Regex tier produces false positives (every number is flagged) | Whitelist tokens that match `{paper.system}` / units / chemical formulas already in source |
| 2 | Symbol-drift verification needs unit normalization | Build a small `_units.py` helper: `kV/cm ↔ kV·cm⁻¹ ↔ MV/cm × 1000` etc. |

## DO NOT DO list

1. **Don't depend on PaperQA2 as a library** — its agent loop is a separate
   product; we only need retrieval. 200-line in-house build is the right call.
2. **Don't lift AI-Scientist's `perform_review.py` verbatim** — RAIL-derivative
   license incompatible with Apache-2.0. Reimplement the checklist fields.
3. **Don't run DSPy BootstrapFewShot on the 6-paper corpus** — undertrained;
   you'll overfit to whatever artifacts those 10 papers happen to share. Need
   ≥20 labeled examples and a metric function first.
4. **Don't add LangGraph for "future flexibility"** — adds a framework we don't
   need and conflicts with our minimal LLM-client stack. Revisit only if we add
   a true agent / human-in-loop use case.

## Sequence + costs

| Milestone | Stages included | Duration | LLM cost vs v1.3.3 |
|---|---|---|---|
| **v1.4.0** | Stage 1 (RAG) + Stage 2 (critic) | ~6 days | ~2× per section (retrieval saves token in s08 prompt; critic adds 1 LLM call) |
| **v1.5.0** | Stage 3 (2-role outliner) | ~3-5 days | ~3× total |
| **v2.0.0** | Stage 4 (DSPy Signatures) | ~5 days, distributed | neutral |

## Greenlight

**YES, with changes.**

Stages 1 and 2 are confirmed by upstream evidence; stages 3 and 4 should not block
v1.4. LangGraph is rejected for our deterministic pipeline. Cost budget revised
upward (the original +30% estimate for the critic was unrealistic — plan for
+100%). The build-in-house bias is intentional: paper2md's value is in being a
focused, audit-friendly pipeline. Adding heavy framework dependencies works
against that.

## Adjacent OSS to consider as light-touch tools (no integration commitment)

- **LiteLLM** — already a transitive dep through Sakana / STORM. Could replace
  our hand-rolled `llm/client.py` if we ever support more than 2 providers.
  Right now overkill.
- **Instructor + Pydantic** — replace ad-hoc `_normalize_chapter_summary` with
  Pydantic models for typed LLM outputs. ~half a day, real win in robustness.
  Could land in v1.4 if budget allows.
- **Anthropic Citations API** — first-class grounded outputs (if we add Anthropic
  as a provider). Eliminates Stage 1's need for an in-house retriever for that
  provider. Defer; we don't currently support Anthropic.

## Open questions for maintainer

1. **Embedding model choice** — `text-embedding-3-small` (OpenAI-compatible, costs
   pennies per paper) vs. `bge-m3` (self-hosted via Ollama, free but adds infra).
   Default to OpenAI-compatible; allow opt-out via env var.
2. **Cost ceiling for critic loop** — currently a 15-chapter paper at +100%
   means ~30 LLM calls instead of 15. Acceptable for production-quality output,
   or do we gate the critic behind `--strict-mode`?
3. **Multi-language stress test** — RAG over Chinese source docs needs CJK-aware
   chunking (split on `。` not `.`). Need to validate before claiming "works
   for ZH papers".

Maintainer to greenlight before implementation begins.
