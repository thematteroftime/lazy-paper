# v1.8.2 — Ten-paper corpus validation + security/quality hardening

Run 2026-05-21 via `scripts/evaluate.py`. Covers the v1.8.1 KL composer
on a 10-paper corpus + the v1.8.2 audit fixes (security HIGH/MEDIUM,
flow bugs, normalizer dedup).

## Corpus scoreboard

### Papers with specific TestCases

| Paper | Test | v1.8.x KL | Prior (v1.7 KL) | Status |
|---|---|---|---|---|
| meng2024 | ch01 benchmark recovery (3 runs) | **12 / 17 / 16** (mean 15.0, floor 12) | 13 / 1 / 1 (mean 5, floor 1) | **headline win preserved** |
| meng2024 | ch10 synthesis specificity (3 runs) | 5 / 3 / 2 (mean 3.3) | 2 / 3 / 4 (mean 3) | parity |
| yang2025 | ch01 fabrication resistance | 3/3 ✓ | 3/3 ✓ | no regression |
| fu2020 | ch01 basic | 3/4 ✓ | 3/4 ✓ | no regression |
| chai2026 | ch01 basic | 4/4 ✓ | 4/4 ✓ | no regression |
| ali2025_flash | ch14 comparison depth | 0/5 ⚠ | 4/5 | **outlier — see below** |

### Papers without dedicated TestCases (pipeline-success only)

All 8 completed end-to-end with substantive Chinese-language output:

| Paper | Chapters | Intro chars | Retry-fires |
|---|---|---|---|
| gaur2022 | 15/15 ✓ | 1402 | 2 |
| ge2025 | 15/15 ✓ | 2170 | 2 |
| he2023 | 15/15 ✓ | 1381 | 0 |
| liu2022 | 15/15 ✓ | 1141 | 0 |
| pamula2025 | 15/15 ✓ | 1639 | 3 |
| pan2025 | 15/15 ✓ | 2804 | 2 |
| randall2021 | 15/15 ✓ | 1155 | 0 |
| yao2022 | 15/15 ✓ | 1199 | 0 |

Retry-when-empty (v1.8.1 mechanism) fires on 4 of these 8 papers,
confirming the safety net is active and useful across diverse papers.
The remaining 4 didn't need retries because the LLM hit required
mentions on the first pass.

## ali2025_flash ch14 outlier — analysis

v1.7 KL scored 4/5; v1.8.1 KL scored 0/5. Investigation
(`runs/ali2025_flash_v181_KL/s08_section_compose/14-Comparison_with_Prior_Work.structured.json`):

- The LLM produced only 3 verified claims this run (vs 8 in the v1.7 KL run on the same paper).
- The Section is 683 characters; the test requires `min_chars=1000` and ≥2 quantitative anchors.
- The verifier rejected 11 claims with `best_ratio` of 0.026–0.14 — the LLM's English quotes (e.g., *"Our RAFE-FHC capacitor device boasts the best performance…"*) don't appear in the 15 retrieved chunks; the LLM appears to quote from a portion of the paper that wasn't reached by the retriever for this particular section query.

Root cause: **LLM sampling variance + retrieval miss**, not a regression in
the v1.8.1 verifier. The v1.8.1 verifier is strictly *more permissive*
than v1.7 (added LaTeX normalization + chunk-ID slop fallback). The
v1.7 KL run on the same paper happened to sample 8 claims that survived;
the v1.8.1 run sampled fewer.

Mitigations for a future v1.9:

- **Length-based retry trigger**: fire one extra LLM call when the verified section is < 500 chars OR has < 4 claims (not only on `missing_required`).
- **Wider retrieval for "Comparison" sections**: raise `top_k` from 15 to 25 when the section title matches survey-section keywords.

Both are tracked but **deferred** — adding them now would push v1.8.2
beyond its scope as a hardening release.

## v1.8.2 hardening (separate from corpus run above)

Three audit subagents reviewed `cli.py`, `stages/`, `llm/` for
redundancy, security, and tuning surface. Findings applied:

### Security

- **HIGH — path traversal via `--paper-id`** (`cli.py:234`): now
  always slugifies, even when user-supplied. Prevents `--paper-id
  "../../tmp/x"` writing outside `runs/`.
- **MEDIUM — zip-slip in MinerU OCR** (`stages/s01_ocr/mineru.py`):
  validates each ZipInfo path before extraction; refuses absolute
  paths and `..` segments.
- **LOW — error redaction**: PaddleOCR HTTP errors no longer echo
  `r.text` (could leak upstream gateway headers); s09 render
  failures now persist `type(exc).__name__ + str(exc)[:200]` rather
  than full `repr(exc)`.

### Flow

- **PaddleOCR infinite poll fixed** (`stages/s01_ocr/runner.py`):
  added `PADDLEOCR_TIMEOUT_S` deadline (default 1800s) — previously
  could hang forever on a stuck job.
- **Silent `except Exception: pass` removed** in two places:
  `s08_section_compose/runner.py::_build_retrieval_query` and
  `s09_render/runner.py::PaperContext.__init__`. Both now log the
  exception while still falling back gracefully.

### Maintainability

- **Shared OCR/LaTeX normalizer**: `stages/_common/normalize.py`
  consolidates the `_normalize_for_match` previously duplicated in
  `structured.py` (and partially in `reviewer.py` / `evaluate.py`).
- **Dead code removed**: `coverage_summary()` (zero callers) deleted.
- **Stale docstring**: `kg_extract.py` no longer mentions the
  removed `paper_kg_v2.md`; documents `paper_kg_v3.md` (the v1.7+
  recommended prompt) instead.

### New env-overridable knobs

| Variable | Default | Purpose |
|---|---|---|
| `MINERU_BASE_URL` | `https://mineru.net/api/v4` | self-hosted / proxied MinerU |
| `MINERU_TIMEOUT_S` | `1800` | hard deadline for MinerU poll |
| `MINERU_POLL_S` | `10` | MinerU poll interval |
| `PADDLEOCR_BASE_URL` | `https://paddleocr.aistudio-app.com/...` | self-hosted Paddle |
| `PADDLEOCR_MODEL` | `PaddleOCR-VL-1.5` | pin model version |
| `PADDLEOCR_TIMEOUT_S` | `1800` | hard deadline for Paddle poll |
| `PADDLEOCR_POLL_S` | `5` | Paddle poll interval |

(In addition to the v1.8.1 knobs: `LAZY_PAPER_VERIFIER_THRESHOLD`,
`LAZY_PAPER_RETRY_THRESHOLD`.)

## Test suite

250/250 passing (unchanged from v1.8.1; no test count regression).

## Shipping decision

v1.8.2 ships as a hardening release on top of v1.8.1's quality fix.
KL remains the recommended high-quality default. The ali2025_flash
T4 outlier is documented; the two mitigation candidates are tracked
for v1.9.
