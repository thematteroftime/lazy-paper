# Content Optimization Roadmap — v1.4

> Status: **research-validated, awaiting maintainer greenlight**.
>
> v1.3.x closed all observable layout defects. v1.4 attacks three content
> defects surfaced by parallel audits (template-driven hallucination,
> quoted-symbol drift, missed source facts) by rebuilding the generation
> pipeline around **entity grounding + scoped retrieval + self-reflective
> drafting** — not around the wrong category of OSS projects that the
> first draft accidentally referenced.

## What category does paper2md actually live in?

We take **one paper** and produce a **15-section, figure/table/equation-
anchored, bilingual analytical document with ground-truth fidelity to
source**. The three load-bearing categories are:

| Category | What we need from it | Why it matters here |
|---|---|---|
| **C — Entity / KG grounding** | Extract paper-specific entities (materials, units, parameters, figures, claims) into a small KG keyed to source spans | Symbol drift (E_b vs test field) and hallucinated benchmarks both collapse to "the writer didn't have a typed entity to anchor to" |
| **B+F — Multi-section structured orchestration** | Per-section scoped sub-agents that load only what they need | 15 sections × multi-format output × bilingual; a single LLM call per chapter can't carry that |
| **A+E — Citation-grounded scientific writing** | Self-reflective drafting that decides "is this evidence sufficient?" before emitting a claim | Closes the "missed direct source facts" gap (meng2024 "tape-casting") |

This is **not** Q&A (PaperQA2), not Wikipedia (STORM), not paper generation
(Sakana), not prompt compilation (DSPy), not generic SWE agents (MetaGPT/
AutoGen). The first draft of this doc referenced those — drop them.

## The four anchor references for v1.4

### 1. Microsoft GraphRAG  (category C — entity / KG grounding)
- URL: https://github.com/microsoft/graphrag
- Borrow: **entity-extraction → community-summary** pipeline from
  `index/operations/extract_graph` + `community_reports`. Repurpose
  "community summaries" as our **per-section entity briefs** that
  constrain section drafting.
- Risk: indexing is corpus-scale and tuned for many docs; we need a
  stripped-down "single-paper KG" mode (entity+relation extraction
  with section-aware clustering, no full community detection).

### 2. ByteDance DeerFlow  (category B+F — long-horizon multi-agent)
- URL: https://github.com/bytedance/deer-flow
- Borrow: the **lead-agent + dynamic scoped-context sub-agents +
  skill-registry** pattern. Our 15 sections map naturally to scoped
  sub-agents that load only the entities + source spans they need.
- Risk: heavyweight runtime (Docker sandboxes, LangGraph, message
  gateway). Lift the **pattern**, not the runtime. ~150 LOC of plain
  Python orchestration, not a framework adoption.

### 3. OpenScholar (AllenAI)  (category A+E — scientific RAG with self-reflection)
- URL: https://github.com/AkariAsai/OpenScholar
- Borrow: **self-reflective generation + reranker + citation
  attribution** pipeline tuned for scientific text. Particularly the
  "is retrieved evidence sufficient?" gate — repurpose for our
  section-drafter to decide "re-retrieve or commit".
- Risk: literature-corpus oriented (cross-paper retrieval). Reranker
  thresholds need recalibration for **intra-document** retrieval.

### 4. agentic-rag-for-dummies  (category A — reference impl)
- URL: https://github.com/GiovanniPasq/agentic-rag-for-dummies
- Borrow: **parent-child hierarchical chunking + hybrid dense/BM25 +
  multi-agent map-reduce**. Small, readable, swap-in-friendly.
- Risk: it's a tutorial repo — production hardening, broken-text-layer
  PDFs, equation regions are not covered. Treat as a structural
  template, not a dependency.

**Patterns only (no code lift)**: Reflexion + Self-Refine for the per-
section critic loop — these are techniques, not codebases to import.

## The four-step v1.4 architecture

```
                      ┌─────────────────────────────────────┐
                      │   Source paper (post s01–s07)       │
                      └──────────────┬──────────────────────┘
                                     ▼
                ┌────────────────────────────────────┐
   step 1       │  PaperKG: entity + relation +      │  ← Microsoft GraphRAG
  (build once)  │  source-span index                 │     (stripped to single-doc mode)
                └──────────────┬─────────────────────┘
                                     ▼
                ┌────────────────────────────────────┐
   step 2       │  RetrievalLayer: hybrid dense/BM25 │  ← agentic-rag-for-dummies
   (per query)  │  + parent/child chunks, scoped to  │     (LangGraph nodes lifted as
                │  current section guidance          │      plain Python state-machine)
                └──────────────┬─────────────────────┘
                                     ▼
                ┌────────────────────────────────────┐
   step 3       │  SectionAgent (per chapter):       │  ← DeerFlow lead/sub-agent
   (15×)        │   ─ load KG entities for section    │     pattern; OpenScholar's
                │   ─ retrieve evidence chunks        │     self-reflection gate
                │   ─ self-reflect: "evidence enough?"│
                │     • no → re-retrieve              │
                │     • yes → draft + cite spans      │
                └──────────────┬─────────────────────┘
                                     ▼
                ┌────────────────────────────────────┐
   step 4       │  Critic loop (Self-Refine pattern):│  ← Reflexion / Self-Refine
   (per chapter)│   ─ regex tier (numerics/Fig.N/    │     (technique reference, not lib)
                │     chem formulas → grep source)   │
                │   ─ LLM tier (only if regex flags) │
                │   ─ revise once max                │
                └──────────────┬─────────────────────┘
                                     ▼
                          chapter .md → s09 renderer
```

### Step 1 — PaperKG builder  `stages/s06_context/kg_extract.py`

After s06 produces the existing `context.yaml`, a new pass extracts
entities + relations from the cleaned chapter texts + figure notes:

- **Entity types** (closed schema): material, dopant, parameter, value,
  unit, figure, table, claim, method, comparator
- Each entity row: `{id, type, surface_form, normalized, source_span:[doc_id, char_start, char_end]}`
- Each relation: `(entity_a, predicate, entity_b, source_span)`
- Output: `runs/<paper>/s06_context/paper_kg.parquet`

GraphRAG's `extract_graph` is the structural reference; their full LLM-
driven extraction pipeline is overkill for one paper — reuse the schema
and prompts, run once per paper (not per chunk batch).

**Effort**: ~2 days. Adds 1 LLM call per paper (~3K tokens out).

### Step 2 — Hierarchical retrieval  `llm/retriever.py`

Replace s08's keyword-matched excerpts with proper retrieval.

- **Indexing** (build once per paper): chunk cleaned chapters into
  parent/child pairs (parent = section paragraph, ~600 chars; child =
  sentence, ~150 chars). Embed children via OpenAI-compatible
  `text-embedding-3-small` (or `bge-m3` self-hosted). Also build a
  BM25 sparse index over child chunks.
- **Query** (per section): hybrid dense + BM25 → top-K children → return
  their parents (the standard parent-child retrieval pattern in
  agentic-rag-for-dummies). Score-fuse with KG-entity match (boost
  chunks containing entities that the section guidance mentions).

**Effort**: ~2 days. Cuts s08 prompt token cost by ~60%.

### Step 3 — Section sub-agents  `stages/s08_section_compose/agent.py`

Replace the current single-LLM-call s08 with a sub-agent per section:

1. Load the KG entities relevant to the section title + guidance.
2. Retrieve top-8 evidence chunks scoped to those entities.
3. Self-reflect (OpenScholar pattern): a small LLM probe answers "is
   this evidence sufficient to write the section?" Yes → draft.
   No → broaden retrieval / loosen entity filter / re-retrieve.
4. Draft the section with the prompt locked to: "Only assert facts
   present in `<evidence>` or `<kg_entities>`. Cite each numeric claim
   with `[span:doc_X:start–end]`. If you don't have evidence for what
   the guidance asks, say so."

DeerFlow's contribution: the lead-agent (cli.py) spawns 15 of these
section sub-agents with scoped context — each sees only its slice of
the KG + retrieved chunks. No section knows the others' state. This
prevents one section's hallucination from poisoning the next.

**Effort**: ~3 days.

### Step 4 — Two-tier critic  `stages/s08_section_compose/critic.py`

After a section drafts, verify before downstream stages see it:

1. **Python regex tier (deterministic, free, 100% reliable)**:
   - Every numeric assertion → string-match against source (after
     unit normalization: `kV/cm` ↔ `kV·cm⁻¹` ↔ `MV/cm × 1000`).
   - Every `Fig. N` / `Table N` → must exist in `figures.yaml` /
     `tables.yaml`.
   - Every chemical formula (regex) → must appear in source or `kg`.
   - Failures: `[(span, claim, problem)]` list.

2. **LLM tier (only if regex flags problems)**: feed the LLM the
   draft + the regex flags + the source excerpts that should have
   matched. Single revision pass max.

Self-Refine pattern from Madaan et al. (init → critique → refine,
stateless prompts). Reflexion pattern as backup if 1 round insufficient.

**Effort**: ~2 days. Regex tier first (1 day) — already valuable on its
own. LLM tier on top (1 day).

## What about LangGraph?

The first draft rejected LangGraph because v1.3.x was a flat
deterministic pipeline. v1.4 introduces sub-agents (DeerFlow), retrieval
loops (OpenScholar self-reflection), and critic-and-revise cycles —
**this is exactly LangGraph's sweet spot**.

But two specific reasons to still skip the framework dependency:

1. `agentic-rag-for-dummies` ships ~400 lines of plain Python that
   *implements* the LangGraph node-shape semantics for our exact case
   (parent-child + hybrid + map-reduce). We can lift the **shape**, not
   the framework. Net: 0 new dependencies, ~200 LOC ours.
2. DeerFlow uses LangGraph internally but its valuable pattern (lead-
   agent + scoped sub-agents) is 100 LOC of plain Python orchestration.
   The LangGraph parts are runtime infrastructure we don't need.

**Decision**: build a thin `stages/s08_section_compose/graph.py` —
~150 LOC state machine with explicit `nodes: dict[str, callable]` and
`edges: dict[str, str | callable]`, replay/debug via plain JSON state
dump. If LangGraph becomes the right tool by v1.5 (e.g., we add human-
in-the-loop section review), revisit then.

## Risk register

| Step | Risk | Mitigation |
|---|---|---|
| 1 (KG) | Entity extraction is noisy on equations / chemical formulas | Use s07 `fig_notes.yaml` + s06 `context.yaml` as seed entities before LLM extraction; LLM only fills gaps |
| 1 | KG bloat: paper has 200+ entities, hard to use as constraint | Cap to top-50 entities by source-span frequency; keep an "auxiliary" tier for the rest |
| 2 (retrieval) | Embedding service rate-limit on big papers | Batch in 64-chunk groups, retry on 429, cache by content-hash |
| 2 | BM25 + dense fusion weight is paper-dependent | Start with 0.6 dense + 0.4 BM25; expose env var; evaluate on 10-paper corpus |
| 3 (agent) | Self-reflection prompt loops indefinitely | Hard cap: 2 reflection rounds per section, then commit with "evidence insufficient" note |
| 3 | Sub-agents drift apart, cross-section coherence drops | Lead-agent (cli) passes the prior section's takeaway as forward context (already done in v1.3) |
| 4 (critic) | Regex tier false positives on legitimate paraphrase | Whitelist `{paper.system}` / chemical formulas pre-cleared with KG |
| 4 | Critic LLM costs balloon | Only run LLM tier if regex tier flags ≥1 issue; capped at 1 revision |

## Cost envelope

| Pass | LLM calls per paper | vs v1.3.3 |
|---|---|---|
| Step 1 KG extract | +1 | +1 |
| Step 2 embed (one-time) | +0 (embedding API, not LLM) | trivial $ |
| Step 3 self-reflect (15 sections × avg 1.3 retrievals) | ~20 | already in s08 today; net wash |
| Step 4 regex tier | 0 | free |
| Step 4 LLM critic (~50% of sections trigger) | ~8 | +8 |

Net LLM cost: roughly **+50% per paper** for v1.4 vs v1.3.3. The
self-reflection pass is the costliest single addition. Earlier draft
said +100%; with the regex tier doing most of the verification work
deterministically, the real LLM-call delta drops.

## Sequence

| Item | Effort | Validation |
|---|---|---|
| Step 1 PaperKG | 2 days | KG dump for 10 papers; spot-check 5 entities per paper against source |
| Step 2 Retriever | 2 days | top-8 retrieval for 10 papers × 15 sections; manual relevance check on 20 samples |
| Step 4a Regex critic | 1 day | run against current v1.3.3 outputs to find what would have been caught |
| Step 4b LLM critic | 1 day | gated behind regex tier |
| Step 3 Section sub-agents | 3 days | rewrites s08; gated last because it depends on steps 1+2+4 being stable |

Total: **9 days**. Recommend doing steps 1+2+4a first (5 days) as a
"v1.3.4" intermediate release that already meaningfully grounds
generation, then step 4b + step 3 as v1.4.0 proper.

## Greenlight

**v1.4 is greenlit pending maintainer go-ahead.** The four anchor
projects (GraphRAG, DeerFlow, OpenScholar, agentic-rag-for-dummies) are
category-correct for our use case — verified by reading each project's
README + structure. Eight earlier-considered references (PaperQA2,
STORM, Sakana AI-Scientist, DSPy, LongWriter, AutoRAG, AutoGen, MetaGPT)
are dropped: each is in an adjacent-but-wrong category for "single
paper → 15-section grounded analytical document".

Repository remains at `v1.3.3` (commit `f816795`); rollback is a single
`git checkout v1.3.3`. Implementation only begins after maintainer
explicitly approves; this doc + `docs/INTERNAL/HANDOFF.md` are the
handoff artifacts.
