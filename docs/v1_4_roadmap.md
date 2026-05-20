# v1.4 Roadmap — Content Fidelity + Process Quality

> Status: **planning**. Compiled from two parallel read-only audits during the v1.3.x cycle: (a) content-fidelity audit against source papers; (b) generation-pipeline architecture audit. v1.3.x focused on layout / display correctness; v1.4 focuses on content correctness and process.

## Content fidelity — top 3 systemic issues

(from per-chapter cross-check against `runs/<paper>/s02_clean/doc_*.md` source OCR)

### 1. Template-driven hallucination when source doesn't cover the topic

**Symptom**: yang2025 (a neuromorphic CBPS paper) had chapters fabricate:
- ch01: "Wrec up to 8.6 J/cm³ at η=85%" — source has zero energy-storage numbers
- ch03: full review of "KNN-based, NBT-based, AN-based" — source mentions none of these
- ch05: Vogel-Fulcher fit and δ_g formulae — source contains no dielectric spectroscopy

**Why it happens**: the template's `{paper.system}` + `key_terms` prompts pull in literature relevant to the *template's domain* (relaxor-AFE energy storage) when the source paper is from an adjacent but different domain.

**Fix proposal**: per-paper "topic-relevance gate" in s08. Before composing a section, score the source's relevance to the template guidance. If below threshold, the section should emit "This paper does not directly address X" rather than hallucinate. yang2025 ch12/ch13/ch07 already do this correctly — the trigger just needs to fire more consistently.

### 2. Quoted-symbol context drift

**Symptom**:
- meng2024 ch01: "0.85NBST-0.15BMZ achieves the highest E_b (340 kV/cm)" — source distinguishes `test field = 340 kV/cm` from `E_b = 348 kV/cm`; the chapter conflates them.
- ali2025 ch13: writes "4 MV/cm" while source consistently uses "4000 kV/cm".

**Fix proposal**: at s07/s08 prompt level, emphasize: "When quoting a symbol like E_b, η, W_rec, copy the value with its exact label as it appears in source — never substitute a nearby value or change units."

### 3. Missed direct facts in source

**Symptom**: meng2024 ch10 (Synthesis) claims "this paper doesn't address synthesis" then guesses "presumably conventional solid-state reaction" — but source `doc_12.md` line 22 says "prepared by a tape-casting method". The chapter composer missed an explicit one-line fact.

**Fix proposal**: full-text grep mandate for high-signal keywords (synthesis methods, common units, key benchmarks) BEFORE concluding "not addressed". Could be a lightweight pre-LLM hint: scan source for {tape-casting, solid-state, sol-gel, PLD, …}.

## Pipeline architecture — top 3 improvements

(from `Explore` agent reading stages/ + prompts/)

### 1. Per-section cache granularity in s08

**Current**: s08 uses stage-level `done.yaml`. If one section's LLM output is bad, must `--force` whole stage (15 LLM calls).

**Fix**: per-section JSON cache + input hash (mirror s09's PptxSummarizer pattern). Then `--rerun-section 3` becomes possible without losing the other 14.

**Effort**: ~2-3 days; refactors `mark_done` semantics for s08.

**Leverage**: HIGH. Reduces iteration latency by ~80% when tweaking one section.

### 2. T3 quant validator moves earlier (s08, not s09 only)

**Current**: quant-content validator only runs in s09 `PptxSummarizer`. If s08 emitted weak text, s09 retries the summarizer (3×) and ultimately soft-accepts — but the chapter body in DOCX/PDF is already weak.

**Fix**: same regex check inside s08 retry loop. Triggers a retry within s08 (1 LLM call) instead of cascading failure to s09.

**Effort**: ~1-2 days.

**Leverage**: HIGH. Catches weak content where it's cheapest to fix.

### 3. S07→S08 claim-consistency check

**Current**: s07 produces `deep_observation` (600-900 chars) → s08 truncates to 400 chars without verifying that the truncation preserves critical claims (numbers / negations / panel labels).

**Fix**: smart truncation that preserves quantitative anchors and negation markers; lightweight regex sweep before writing `fig_observations_brief`.

**Effort**: ~2-3 days.

**Leverage**: MEDIUM. Prevents ~5-10% of downstream composition errors.

### Rejected (lower leverage)

- Domain-detection branching of prompts (yang vs ali) — adds prompt maintenance burden; current domain-agnostic prompt is effective.
- Re-querying s07 vision LLM from s08 — expensive; smart-truncate is the cheaper fix.

## v1.4.0 release plan

If all 6 items above are tackled: ~2 weeks effort.
Recommended priority ordering (highest leverage first):

1. **Per-section cache** (#1 pipeline) — unlocks fast iteration for everything else
2. **T3 in s08** (#2 pipeline) — catches weak content cheap
3. **Topic-relevance gate** (#1 fidelity) — eliminates the worst hallucinations
4. **Symbol-context drift** (#2 fidelity) — prompt-level fix; cheap
5. **Source-fact grep mandate** (#3 fidelity) — pre-LLM hint
6. **Claim consistency at s07→s08** (#3 pipeline)

Items 1-3 alone should reduce content-quality incidents by ~50%; full 6 would close most observed failure modes.
