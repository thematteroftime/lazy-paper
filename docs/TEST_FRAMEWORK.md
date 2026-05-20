# Quality Test Framework (v1.7+)

A reproducible evaluation harness for lazy-paper's section-composer
strategies. Replaces the ad-hoc grep-based comparisons used during v1.5
and v1.6 experimentation with explicit, scriptable metrics covering
**generation quality**, **citation correctness**, and **defect resistance**.

## Why this exists

Each strategy iteration (E / G / H / I / J / K / L / KL) needed to be
compared against the others on the same yardstick. Eyeballing chapters
across multiple variants is noisy; the only way to make confident
"ship/don't ship" decisions is a fixed suite of tests with explicit
scoring rules. This is that suite.

## Quick start

```bash
# Score all recent v1.6/v1.7 runs
uv run python scripts/evaluate.py --all-recent

# Score specific runs
uv run python scripts/evaluate.py runs/meng2024_v170_KL runs/yang2025_v160_J

# Programmatic use: stdout is structured JSON, stderr is the markdown table
uv run python scripts/evaluate.py runs/meng2024_v170_KL 2>/tmp/table.md > /tmp/report.json
```

Output shape:
- **stdout**: JSON list of `{run, paper_id, results: [...]}` per directory
- **stderr**: a one-line-per-run Markdown table for quick visual scanning

## Test cases

Test cases live in `scripts/evaluate.py` as `TestCase` instances. Each
binds (paper_id, section, scoring rules). The four shipping cases:

### T1. meng2024 ch01 — competitor benchmark recovery (max 17)

The original headline defect. The paper cites four literature systems
(Jiang/Ma/Zhang/Tang et al.) with specific `W_rec` and `η` values.
Score is 1 point per recovered pattern:

- **Authors** (4): `Jiang|Ma|Zhang|Tang 等?|et al.`
- **Values** (8): `2.94 | 7.5 J | 8.58 | 8.3 J | 91.04 | 90.5 | 94.5 | 80%`
- **Formulas** (4): `Ca²⁺/Nb⁵⁺ | La(Mg | K₀.₁ | 0.8Bi`
- **Language** (1): zh-character ratio ≥ 30% when `--lang zh` is requested

Maximum 17. The v1.3.3 baseline (full-context-stuffing) hits ~12-13.
v1.4.x default hits 0. Each strategy is scored against this.

### T2. yang2025 ch01 — fabrication resistance (max 3)

The paper is about neuromorphic computing, contains zero
energy-storage measurements. Prior strategies hallucinated
`W_rec=8.6 J/cm³ at η=85%` from template priors. Score:

- **Forbidden patterns** (must NOT match): `8.6 J/cm`, `η=85`, `Wrec=`
- **On-topic patterns** (must match): mentions CBPS or synaptic plasticity
- **Language** (1): zh ratio ≥ 30%

Forbidden matches DON'T reduce score directly but raise a `flag` —
treat any flag as failing this test case.

### T3. meng2024 ch10 — synthesis specificity (max 5)

v1.4.x default wrote "synthesis not addressed; presumably solid-state"
even though the paper explicitly states `tape-casting` with grain-size
measurements. Score:

- **Method** (2): `tape-casting | 流延`
- **Grain data** (2): `μm` measurement + pyrochlore mention
- **Min size** (1): chapter ≥ 500 chars

### T4. ali2025_flash ch14 — comparison-section depth (max 5)

v1.4.x produced a 688-byte stub. Score:

- **Quantitative anchors** (4): at least 4 of {`X K`, `X %`, `X °C`, `X kV`}
- **Min size** (1): chapter ≥ 1000 chars

## Citation accuracy (auto-applied for Strategy J runs)

For any run that wrote `s08_section_compose/*.structured.json`, the
harness additionally computes per-section citation reliability:

```json
"citation_accuracy": {
  "total_claims": 9,
  "claims_with_quote": 9,
  "verified_quotes": 7,
  "verified_ratio": 0.78,
  "fabricated_quote_count": 2,
  "fabricated_sample": [{"quote": "...", "cited_chunk_ids": [11]}]
}
```

**Verification rule**: each `GroundedClaim.cited_quote` must appear as
either an exact substring of its declared chunk OR achieve ≥ 0.85
longest-contiguous-match coverage (mirrors `structured.py:
verify_section_draft`). Source text is normalized for OCR digit-spacing
and LaTeX escapes before comparison — `2.94 J/cm³` matches
`$2 . 9 4 \mathrm{J/cm}^{3}$`.

A `verified_ratio` below 0.7 indicates the LLM is paraphrasing rather
than copying — diagnostic but doesn't directly affect the test-case
score.

## Strategy scorecards (v1.6 / v1.7 results)

### meng2024 ch01 (T1)

| Strategy | Score / 17 | Notes |
|---|---|---|
| v1.3.3 baseline (full-context) | ~12 | Ground truth — no retrieval at all |
| v1.4.2 default | 0 | No comparators recovered |
| v1.5 E (post-hoc critic) | 6 (mean 4.5) | Critic adds them when KG has them |
| v1.6 J (pre-injection) | 9 | Schema-constrained citations |
| v1.7 K (best-of-N=2, v2 KG) | 1 | LLM avoids bare formulas without authors |
| v1.7 L (KG-v3 author entities) | 9 | Authors lift attribution |
| **v1.7 KL (KG-v3 + best-of-N=2)** | **13** 🏆 | Combined effect closes the gap |

### Other test cases

| Strategy | yang2025 (T2) | meng2024 ch10 (T3) | ali2025_flash (T4) |
|---|---|---|---|
| J | 3/3 ✓ | 4/5 | 4/5 |
| KL | (test pending) | 2/5 ⚠ | (test pending) |

⚠ on KL T3 indicates a regression in non-benchmark chapters — KL's
focus on comparator citation in survey sections is achieved at the cost
of less-detailed prose in synthesis/characterization sections. This is
a known trade-off; if you're optimizing for ch01 benchmark recovery,
KL is best; if you're optimizing for chapter-level depth uniformity, J
is more balanced.

## Adding a new test case

```python
# In scripts/evaluate.py — append to TESTS list

TestCase(
    name="paper_id:short_label",
    paper_id="paper_id",        # base paper, no version suffix
    section="01-Introduction",  # exact section file prefix
    required={
        "category": [r"regex1", r"regex2"],
    },
    forbidden=[r"do-not-write-this"],
    min_chars=500,
    lang_zh_min_ratio=0.30,
),
```

The harness automatically detects which paper a run dir refers to by
trimming `_v\d+_*` suffixes. Each TestCase only scores runs whose
detected paper matches its `paper_id`.

## Reproducibility

- DeepSeek-Reasoner sampling is non-deterministic (we use temperature
  0.2 by default, 0.2/0.35 alternation for best-of-N runs).
- Single-run scores have ±2 point variance on T1. Always sample 2-3
  runs before declaring a strategy "better than baseline".
- Best-of-N (Strategy K) reduces variance by design — its merged drafts
  are more stable across re-runs because it union-merges from multiple
  samples in a single dispatch.

## Limits + intentional gaps

This harness is **regex-pattern + structural**. It does NOT measure:

- Semantic correctness beyond the named patterns
- Cross-chapter coherence (would need a separate cross-section scorer)
- Reader-perceived prose quality (subjective)
- Whether the chapter's narrative arc is logical

For those axes, periodic human review of 1-2 papers per release is
still required. The harness is a regression-prevention floor, not a
quality ceiling.

## Recommended workflow for shipping a new strategy

1. Implement the strategy env-gated (don't change default behavior)
2. Run on meng2024 (T1+T3) to confirm no regression on baseline
3. Run on yang2025 (T2) to confirm no new hallucination
4. Run on ali2025_flash (T4) to confirm survey-section depth
5. `uv run python scripts/evaluate.py --all-recent` and compare
6. If T1 lifts AND T2/T3/T4 stay green: ship as opt-in env var
7. If T1 lifts AND T2/T3/T4 also stay green across 3 sequential runs
   per strategy on each paper: promote to default

This is the discipline that produced v1.4.2 (Strategy C as default
from a 4-way comparison) and v1.6.0 (Strategy J as opt-in from variance
analysis). v1.7 work should follow the same loop.
