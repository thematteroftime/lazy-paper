# v1.12 Phase 1 — RAGAS Baseline

> Captured against code at HEAD `<git rev-parse HEAD>` on 2026-05-25.
> Reproduce: `LLM_TEXT_MODEL=deepseek-chat uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s`

## Setup
- Papers: `meng2024_v111_demo`, `ali2025_flash_v111_demo`
- Questions: 20 per paper (`tests/eval/golden_qa/*.yaml`, ground truth verified
  against `runs/<paper>/s03_chapter/chapters/` on 2026-05-25)
- RAGAS metrics: `faithfulness`, `context_recall`, `context_precision`
- Judge LLM: `deepseek-chat` via `LLM_TEXT_BASE_URL=https://api.deepseek.com/v1`
- Embeddings: `text-embedding-v3` via `LLM_VISION_BASE_URL` (DashScope, fallback per
  `llm/models.yaml`)

## Scores

Captured 2026-05-25 via `pytest -m ragas` (3:13 wall-clock for 60 evaluations
across 2 papers); JSON in `tests/eval/_ragas_out/`.

| Paper | faithfulness | context_recall | context_precision |
|---|---|---|---|
| meng2024 | **0.657** | 1.000 | ~1.000 |
| ali2025_flash | **0.440** | 1.000 | ~1.000 |

### Reading the numbers

- **context_recall = 1.0 and context_precision ≈ 1.0** on both papers: our
  hand-picked `expected_chunks` are perfect — the golden-QA test set isn't
  exercising retrieval at all. This is by design (we want a baseline that
  isolates faithfulness drift; retrieval is tested elsewhere).
- **faithfulness 0.657 (meng2024) vs 0.440 (ali2025_flash)**: this is the
  signal we'll watch. ali2025_flash has more unverifiable claims in s08
  output — probably because the PZO thin-film paper has more multi-step
  reasoning chains and quantitative cross-references that don't trace
  back to a single source span verbatim. meng2024's NBT ceramics flow has
  cleaner one-fact-per-claim structure.
- Faithfulness on a 0-1 scale is a *claim-by-claim verifiability* score,
  not a quality score. The Phase 1 features (`--pdffigures2`, entity
  dedup) target different layers — we don't expect faithfulness to jump
  dramatically from either; the bar is +5pp.

## Notes & gotchas

- ragas 0.1.21 is the **last langchain-compatible** release; 0.2+ / 0.4+ have an
  unconditional `from langchain_community.chat_models.vertexai import ChatVertexAI`
  at module load, removed in langchain-community 0.3+. Pin must be `==0.1.21`.
- DeepSeek `deepseek-reasoner` returns reasoning tokens RAGAS may not parse;
  override to `deepseek-chat` for the harness run.
- Python 3.14 removed implicit event-loop creation; the harness sets one
  explicitly before calling `evaluate()` to fix ragas 0.1.21's
  `asyncio.get_event_loop()` usage.
- The `answer` column is the FULL s08 composed prose for the paper, not a
  per-question answer. We're scoring "do the produced chapters faithfully cover
  this paper's facts," not a Q&A flow.

## What this baseline is FOR

- Task 9 (`--pdffigures2` on meng2024) re-runs the same harness; delta attributes
  to caption-anchored figure renumbering.
- Task 12 (`LAZY_PAPER_ENTITY_DEDUP=1` on meng2024 + ali2025_flash) re-runs the
  same harness; delta attributes to KG entity dedup.

### Decision rule (per Phase 1 plan)

- **≥+5pp on faithfulness** for either feature on either paper → recommend
  default-ON in v1.12 ship
- **Regression of >1pp** on any metric → revert that feature, document the failure mode
