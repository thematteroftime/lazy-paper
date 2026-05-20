# v1.7.0 KL Strategy — Validation Results

Run 2026-05-21 via the v1.7 scriptable harness (`scripts/evaluate.py` +
`docs/TEST_FRAMEWORK.md`). Seven KL runs across five papers; comparison
against three prior J runs on meng2024.

## Scoreboard

### T1 — meng2024 ch01 benchmark recovery (max 17)

| Run | KL score | J score |
|---|---|---|
| run 1 | **13** 🏆 | 8 |
| run 2 | 1 | 6 |
| run 3 | 1 | 5 |
| **Mean** | **5.0** | **6.3** |
| **Stdev** | **6.9** | **1.5** |
| **Range** | **1 – 13** | **5 – 8** |

**KL has higher peak but lower mean + much wider variance.** The
architecture CAN recover 13 of 17 patterns (matching v1.3.3's
unconstrained-context baseline of ≈12), but in 2 of 3 samples the LLM
ignored the pre-injected required-mentions list and wrote a generic
intro with no literature citations. Both N=2 sub-runs of best-of-N
converged on similar generic content, so the merge step had nothing
diversity-additive to combine.

Diagnostic: KG-v3 extraction in run3 was perfect (4 authors + 4
comparators + 4 cited_by_paper relations). The failure is entirely on
the compose side — LLM sampling discretion.

### T2-T6 — single-run scores on other papers

| Test case | Score | Notes |
|---|---|---|
| T2 yang2025 ch01 no_fabrication | 3/3 ✓ | Preserves the v1.4.1 fix |
| T3 meng2024 ch10 synthesis | 2/5 ⚠ run1, 3/5 run2, 4/5 run3 | Inverse correlation with T1 — when KL "goes big" on intro comparators, it neglects synthesis depth |
| T4 ali2025_flash ch14 depth | 4/5 | Same as J |
| T5 fu2020 ch01 basic | 3/4 | On-topic; mentions Ma 等人 source citation organically |
| T6 chai2026 ch01 basic | 4/4 ✓ | Clean |

## Shipping decision

**Do NOT make KL the default.** J remains the better default for v1.7
because:

1. **J's mean is higher** (6.3 vs 5.0 on T1).
2. **J's floor is much higher** (5 vs 1).
3. **Both pass T2-T6 equivalently**.
4. **KL's peak (13) is unreachable reliably**.

KL stays available as opt-in (`LAZY_PAPER_BEST_OF_N=2
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md`) for users willing to roll the
dice for occasional 13/17 outputs, accepting that 2 of 3 attempts
will be near zero.

## v1.8 candidates — addressing KL's floor

The architecture is correct (run1's 13/17 proves it). The floor problem
is purely LLM sampling. Three options ranked by leverage:

1. **Retry-when-empty** (lowest effort, biggest impact): after KL's
   merge, if zero comparators from the required-mentions list are
   cited, re-issue one more LLM call with a stronger "MUST cite"
   instruction. Expected to lift mean from 5.0 toward 9+.

2. **Stronger pre-injection prompt**: the current "you MUST cover each"
   instruction is too gentle. Try adding "Output will be rejected if
   any required entity is absent" + Pydantic-level validation that
   counts required-entity coverage.

3. **Increase best-of-N to 3 with greater temperature spread**: 0.2 /
   0.4 / 0.6 instead of 0.2 / 0.35. Wider sampling should produce
   more diverse drafts to merge. Cost: 1.5× current.

(2) is most principled; (1) is most pragmatic for v1.8.

## Cost notes

- Each KL run on meng2024: ~12 min wall clock (best-of-N=2 doubles
  s08 LLM time; s06 KG-v3 adds ~1 min vs v2).
- Total experimental burn for this validation: 4 runs × ~12 min = ~48
  min wall clock; ~$3-5 of DeepSeek API spend.

## Test harness

Reproducible via:

```bash
LAZY_PAPER_STRUCTURED=1 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
  LAZY_PAPER_BEST_OF_N=2 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id <name>_v170_KL --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html

uv run python scripts/evaluate.py runs/<name>_v170_KL
```
