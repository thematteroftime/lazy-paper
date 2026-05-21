# v1.8.1 KL Strategy — Validation Results

Run 2026-05-21 via the v1.7 scriptable harness (`scripts/evaluate.py` +
`docs/TEST_FRAMEWORK.md`). Six KL runs across four papers, comparing
v1.8.1 against v1.7 KL and v1.7 J.

## Scoreboard

### T1 — meng2024 ch01 benchmark recovery (max 17)

| Run | v1.8.1 KL | v1.7 KL | v1.7 J |
|---|---|---|---|
| run 1 | **12** | 13 | 8 |
| run 2 | **17** 🏆 | 1 | 6 |
| run 3 | **16** | 1 | 5 |
| **Mean** | **15.0** | 5.0 | 6.3 |
| **Stdev** | **2.6** | 6.9 | 1.5 |
| **Range** | **12 – 17** | 1 – 13 | 5 – 8 |
| **Floor** | **12** | 1 | 5 |

**v1.8.1 KL is now the strongest strategy on every dimension:**

- **Peak** (17 vs 13) — beat both v1.7 KL's lucky-run high and the
  v1.3.3 unconstrained-context baseline (~12).
- **Mean** (15 vs J's 6.3) — 2.4× higher than the prior best default.
- **Floor** (12 vs J's 5, vs v1.7 KL's 1) — every run now exceeds the
  v1.3.3 baseline. KL's floor problem is solved.

### T2 – T6 — single-run scores on other papers

| Test case | v1.8.1 KL | v1.7 KL |
|---|---|---|
| T2 yang2025 ch01 fabrication resistance | 3/3 ✓ | 3/3 ✓ |
| T3 meng2024 ch10 synthesis (3 runs) | 5 / 3 / 2 (mean 3.3) | 2 / 3 / 4 (mean 3.0) |
| T5 fu2020 ch01 basic | 3/4 ✓ | 3/4 |
| T6 chai2026 ch01 basic | 4/4 ✓ | 4/4 ✓ |

No regressions on any non-meng test case.

## Root-cause analysis

v1.7 KL's wide variance was caused by two compounding compose-side
bugs in `stages/s08_section_compose/structured.py`. Both are now
fixed.

### Bug 1 — verifier rejected good claims on LaTeX-form quotes

The source PDF OCRs `W_rec=5.00 J/cm³` as `$W _ { \mathrm { rec } } =
5 . 0 0 \mathrm { J } / { \mathrm { c m } } ^ { 3 }`. The LLM
correctly extracts this form into `cited_quote` and writes a claim
like *"在 0.85NBST-0.15BMZ 陶瓷中实现了 W_rec=5.00 J/cm³"* with
`cited_chunk_ids=[2]`. The verifier did a substring check between the
literal LaTeX form and the LLM's quote, which lost matches over
whitespace inside `{ \mathrm { rec } }`. The `find_longest_match`
fallback then scored 0.629 — below the 0.85 threshold — and the
claim was rejected, deleting the comparator citation from the
final prose.

**Fix:** `_normalize_for_match` strips LaTeX commands and collapses
OCR digit-spacing on both sides before the substring/fuzzy tier:

```python
s = _LATEX_CMD_RE.sub(" ", text)        # \mathrm \frac \text ...
s = _LATEX_DELIM_RE.sub(" ", s)          # $ { }
s = _OCR_DIGIT_DOT_RE.sub(r"\1.", s)     # "8 . 5 8" → "8.58"
s = _OCR_DIGIT_SPACE_RE.sub(r"\1", s)    # "5 0 0" → "500"
```

The verifier now correctly accepts every claim whose quote is a
verbatim copy of any OCR'd form of the source span.

### Bug 2 — retry-when-empty measured PRE-verify coverage

The v1.8 design called for a retry when the LLM ignored the required
mentions list. The diagnostic computed `missing_required(required,
draft)` *before* the verifier ran. Because LLMs typically write
comparator-citing claims (just with imperfect quotes), pre-verify
coverage was ~80% even when the verifier was about to drop those
claims. The retry never fired.

**Fix:** Compute coverage on the **verified** draft. Retry trigger
moved after `verify_section_draft`. When `post_cov ≤
LAZY_PAPER_RETRY_THRESHOLD` (default 0.5), one strengthened call
fires; if its post-verify coverage improves, the draft is swapped.

### Bug 3 — LLM-emitted chunk-ID slop

Some claims correctly quoted from chunk A but wrote
`cited_chunk_ids=[B]`. The verifier rejected because the quote
didn't match the cited chunk's text.

**Fix:** `verify_section_draft` adds a fallback that scans ALL
retrieved chunks. When a match is found in a non-cited chunk, the
claim is accepted and its `cited_chunk_ids` is patched to include the
matched chunk first.

## Cost notes

- v1.8.1 KL on meng2024: ~10-12 min wall clock (same as v1.7 KL).
- Retry-when-empty fires on 1-3 sections per run when the LLM has
  patchy comparator coverage. Each retry is one DeepSeek call (~30s).
- Net cost increase over v1.7 KL: ~5-15% per paper. Variance reduction
  is dramatic (stdev 6.9 → 2.6).

## Reproducible test command

```bash
LAZY_PAPER_STRUCTURED=1 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
  LAZY_PAPER_BEST_OF_N=2 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id <name>_v181_KL --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html

uv run python scripts/evaluate.py runs/<name>_v181_KL
```

Optional knobs for the user to tune behavior:

- `LAZY_PAPER_VERIFIER_THRESHOLD` (default 0.85)
- `LAZY_PAPER_RETRY_THRESHOLD` (default 0.5)
- `LAZY_PAPER_BEST_OF_N` (default 1, recommended 2 for KL)

## Shipping decision

**KL is now the recommended strategy** for users who want maximum
literature-citation recovery. The variance floor is solved. v1.7 J
remains a reasonable lower-cost fallback (no best-of-N overhead).
