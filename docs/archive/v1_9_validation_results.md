# v1.9.0 — Informed-retry validation

15 KL runs across 13 papers (10 new + 3 meng2024 variance runs).
2026-05-22.

## Headline: deterministic recovery on meng2024

| Version | T1 scores (3 runs) | Mean | Stdev | Floor |
|---|---|---|---|---|
| v1.7 KL | 13 / 1 / 1 | 5.0 | 6.9 | 1 |
| v1.8.1 KL | 12 / 17 / 16 | 15.0 | 2.6 | 12 |
| v1.8.3 KL | 5 / 1 / 1 / 1 / 1 (5 runs) | 1.8 | 1.8 | 1 |
| **v1.9 KL** | **9 / 9 / 9** | **9.0** | **0** 🏆 | **9** |

Three independent v1.9 runs scored exactly 9/17 on meng2024 ch01
benchmark recovery. The variance that's plagued this test since v1.7
is **eliminated**.

The remaining gap to v1.8.1's 12+ mean is a separate problem — LLM
self-selectivity on which comparators to write about — and is queued
for v1.9.x via STORM/LitLLM-style per-comparator drafting.

## Why informed-retry works

Previous retry-when-empty (v1.8.x):

```
## CRITICAL — REQUIRED MENTIONS MISSING FROM PRIOR DRAFT
Your previous draft missed most of the required mentions...
[generic instruction to cover all entities]
```

v1.9 informed-retry generates per-entity diagnosis:

```
## CRITICAL — SPECIFIC REQUIRED MENTIONS MISSING
Your previous draft covered 1/5 required entities. The following are
NOT yet covered — your next draft MUST include each:

  - comparator: 'Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3'
      → write a claim containing "Jiang et al." or "Jiang 等人" OR "W_rec=2.94 J/cm³"
      → evidence chunk: [3]
  - comparator: 'La(Mg1/2Zr1/2)O3-modified Bi0.5Na0.5TiO3'
      → write a claim containing "Ma et al." or "Ma 等人" OR "W_rec=7.5 J/cm³"
      ...
```

The deterministic checklist eliminates the LLM's "I'll skip this one"
discretion — it knows exactly which token to include in the next
sample.

## 13-paper corpus — no regressions

| Test | v1.8.3 | v1.9 | Status |
|---|---|---|---|
| meng2024 T1 | 5/17 single | **9/17 ×3** | floor +4, variance eliminated |
| meng2024 T3 | 3/5 | 3, 3, 5 / 5 | within variance |
| yang2025 T2 | 3/3 ✓ | 3/3 ✓ | preserved |
| fu2020 T5 | 3/4 ✓ | 3/4 ✓ | preserved |
| chai2026 T6 | 4/4 ✓ | 4/4 ✓ | preserved |
| ali2025_flash T4 | 4/5 ✓ | 4/5 ✓ | preserved |

## 8 papers without dedicated TestCases — quality + retry behavior

| Paper | intro chars | HTML anchors | retry-when-empty fires |
|---|---|---|---|
| gaur2022 | 1635 | ✓ | 8× |
| ge2025 | 2027 | ✓ | 8× |
| he2023 | 837 | ✓ | 4× |
| liu2022 | 2057 | ✓ | 8× |
| pamula2025 | 1223 | ✓ | 13× |
| pan2025 | 2239 | ✓ | 7× |
| randall2021 | 2189 | ✓ | 2× |
| yao2022 | 1156 | ✓ | 2× |

retry-when-empty firing 2-13× per paper confirms the informed-retry
mechanism is heavily load-bearing across the corpus, not just on the
meng2024 benchmark paper.

## Cost notes

- Per-paper wall-clock: ~12-15 min KL run on meng2024 (informed-retry
  adds 1-3 extra LLM calls per section when triggered).
- Per-paper DeepSeek API cost: ~$0.30-0.60 typical, up to ~$0.90 on
  papers with many comparators.
- Diagnosis adds ~300-500 tokens to the retry prompt — DeepSeek input
  caching makes this nearly free across best-of-N samples.

## v1.9.x candidate — closing the 9→15 gap

Web research surfaced two compounding techniques to push beyond 9/17:

1. **Pydantic validator-as-coverage-gate** (instructor reask pattern,
   half-day work). Add a `model_validator` on `SectionDraft` that
   checks substring presence of each required entity; instructor's
   built-in reask uses the validation error as targeted feedback.

2. **STORM/LitLLM per-comparator drafting** (1-day work). For
   survey sections, draft one micro-paragraph per comparator with a
   single-entity context (the LLM literally cannot skip when there's
   nothing else to write about), then stitch via "preserve every
   author + value verbatim" instruction.

Combined, these target the meng2024 12+ mean recovery while keeping
v1.9's zero-variance floor.

## Reproducible test command

```bash
LAZY_PAPER_STRUCTURED=1 \
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
LAZY_PAPER_BEST_OF_N=2 \
LLM_MAX_TOKENS_CEILING=64000 \
LAZY_PAPER_MIN_SECTION_CHARS=500 \
LAZY_PAPER_MIN_SECTION_CLAIMS=4 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id <name>_v190 --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html

uv run python scripts/evaluate.py runs/<name>_v190
```

Tests: 253/253 pass.
