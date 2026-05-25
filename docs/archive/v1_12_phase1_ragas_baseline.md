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

> Filled by Task 5 after RAGAS run completes.

| Paper | faithfulness | context_recall | context_precision |
|---|---|---|---|
| meng2024 | <TBD-fill-from-tests/eval/_ragas_out/meng2024_v111_demo.json> | <TBD> | <TBD> |
| ali2025_flash | <TBD-fill-from-tests/eval/_ragas_out/ali2025_flash_v111_demo.json> | <TBD> | <TBD> |

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
