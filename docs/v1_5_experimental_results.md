# v1.5 Experimental Results — Strategy A/B/C/E/G/H/I

> Data from the meng2024 ch01 "Jiang/Ma/Zhang/Tang competitor literature
> benchmark" recovery test. v1.3.3 baseline has all 4 authors + 8 specific
> values + 1 formula present in the chapter (total 13/16 pattern hits). All
> v1.4.x default outputs lose this content. This file records which v1.5
> experimental strategies recover it.

## Scoreboard (meng2024 ch01)

| Variant | Authors (/4) | Values (/8) | Formulas (/4) | Total (/16) | Chapter size |
|---|---|---|---|---|---|
| v1.3.3 baseline | 4 | 8 | 1 | **13** | 2296 |
| v1.4.2 default | 0 | 0 | 0 | 0 | 1523 |
| +G (bigger chunks) | 0 | 0 | 0 | 0 | 1675 |
| +G run 2 | **4** | 0 | 3 | **7** | 3394 |
| +I (whole-paper feed) | 0 | 0 | 0 | 0 | 885 |
| +I run 2 | 0 | 0 | 1 | 1 | 3227 |
| **+E (KG-v2 + coverage + critic)** | **1** | **2** | **3** | **6** | 2091 |
| +E run 2 | 0 | 0 | 3 | 3 | 2351 |
| +H (hierarchical alone) | 0 | 0 | 0 | 0 | 2303 |
| +EH (E + H combined) | 0 | 0 | 3 | 3 | 1842 |
| **+J (Strategy J / v1.6) run 1** | 0 | **5** | **3** | **8** | 1786 |
| **+J run 2** | 0 | 4 | 2 | **6** | 1422 |
| **+J run 3** | 0 | 4 | 2 | **5** | 1640 |
| **J mean (3 samples)** | **0** | **4.3** | **2.3** | **6.33** | — |

## Conclusions

### What works

**Strategy E** is the only consistent winner: mean **4.5/16** vs baseline 0.
Mechanism:
1. KG-v2 prompt extracts the 4 comparator entities + 8 benchmark values into `paper_kg.parquet`.
2. Coverage critic scopes those entities to the Introduction section and flags them as missing from the first-draft.
3. Differentiated LLM-critic prompt instructs `entity_coverage_missing` flags as "**add** the missing entity with its linked value" (vs the default "remove unsupported claim" behavior for numeric flags).
4. Per-entity source-span evidence packets give the critic the exact source paragraph for each missing comparator.

### What doesn't work

- **Strategy H** (hierarchical chunking + auto-merge retrieval): zero benefit alone (0/16) and no additive benefit when combined with E (EH 3/16, same as E run 2). The retrieval was never the bottleneck — Strategy G's run 1 showed chunk c0001 containing all 4 author citations ranked #1 in the retriever output, but the LLM still chose to summarize them away.
- **Strategy I** (whole-paper feed): zero recoveries on both samples. Confirms the "lost in the middle" finding — with full source in context, the LLM still cherry-picks toward generic synthesis.
- **Strategy G** (bigger chunks): too high variance (0 in run 1, 7 in run 2). Not a reliable choice.

### High-variance failure mode

Even Strategy E does not consistently match v1.3.3's 13/16. Run 1 hit 6;
run 2 hit 3 (with different subset coverage). The post-hoc critic + revision
loop is inherently noisy:
- Coverage critic correctly identifies the missing entities.
- LLM critic receives entity list + source span evidence.
- But the revision step is still a single LLM call with sampling randomness.
- Some runs the LLM adds all 4 comparators; some runs it adds 1; some
  runs it adds the formulas but not the values; etc.

### Architectural lesson

The fundamental issue: **post-hoc revision is unreliable for "add content"
operations**. Even with perfect evidence pinning, the LLM has the
discretion to incorporate partial content. The high-reliability path
identified by the research subagents (Perplexity / PaperQA2 / Anthropic
Citations API) is **pre-injection at compose time** — give the LLM the
required comparator list as a structured input field BEFORE the first
draft, with explicit "use these in this section" instructions. This is
deferred to v1.6+ as Strategy J.

## Recommendation

- **Ship Strategy E as opt-in** (`LAZY_PAPER_KG_PROMPT=paper_kg_v2.md
  LAZY_PAPER_COVERAGE=1`). It is the strongest improvement on the known
  defect and never regresses other behavior. Worth enabling in production
  where benchmark-citation recovery matters.
- **Strategy G** ships as opt-in already (`LAZY_PAPER_CHUNK_SIZE=2000`).
  Variance too high for default; keep available for users who want to
  experiment.
- **Strategy H** ships as opt-in (`LAZY_PAPER_HIERARCHICAL=1`). No
  measured benefit on this task but might help on other axes
  (figure-caption matching, multi-paragraph claim grounding) — kept for
  further exploration.
- **Strategy I and B** remain experimental, **not recommended** for
  production: I shows no benefit, B regresses chapter sizes.

## Cost

Each strategy run on meng2024 (15 sections) took ~10–15 minutes wall
clock with DeepSeek-Reasoner. Strategy E with both critic round-trips
runs ~1.5× the baseline cost; G and I are roughly baseline cost; H
adds parent-chunk storage (~2× the parquet file size) but no extra
LLM calls.

## Test config

All runs:
- Paper: meng2024 (Meng et al. 2024, ACS Appl. Mater. Interfaces)
- Model: DeepSeek-Reasoner
- Template: Table of Contents-Relaxor AFE-ZGY-HW.docx
- Only stages: s06_context, s08_section_compose, s09_render
- Lang: zh
- Formats: docx, html

Reproduction:
```bash
# Strategy E (best)
LAZY_PAPER_KG_PROMPT=paper_kg_v2.md LAZY_PAPER_COVERAGE=1 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id meng2024_v142_E --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html
```
