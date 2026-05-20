# v1.5 — Quality Test Cases (Setup, Not Yet Implemented)

This file scopes the **known regression scenarios** that v1.5 work should
fix. Each test case names the symptom, the root cause, the strategy
candidates that should address it, and the verification command.

These are **research test cases** — not pytest-runnable yet. They are
written so any future strategy implementation can be measured against the
same yardstick.

---

## Strategy D — Section-type-aware retrieval queries

### Symptom

For meng2024 ch01 (Introduction), the source contains a competitor
literature benchmark section at char positions `2573–4465` of
`runs/meng2024/s03_chapter/chapters/chapter_001_INTRODUCTION.md`:

> "As reported by **Jiang et al.**, a moderate W_rec of **2.94 J/cm³** and a high η of 91.04%…"
> "**Ma et al.** realized a large W_rec of **7.5 J/cm³**…"
> "**Zhang et al.** reported … W_rec of **8.58 J/cm³** and large η of 94.5%"
> "**Tang et al.** in 0.8Bi…SrTiO₃-0.2CaLaTiO₃ … W_rec of **8.3 J/cm³** with η of 80%"

The v1.3.3 baseline correctly cited all four (positions 2573–4465 fell into
the keyword-scored window). All v1.4 variants (default, +A coverage, +B
two-step, +C query-expand) **omit all four benchmarks**.

### Root cause

Verified by reading the actual retrieved chunks (`runs/meng2024_v141_C/
s08_section_compose/retrieval.parquet`): for the ch01 query the retriever's
top-15 covers source ranges `0–2124`, `6059–7233`, `8759–10095`. The
benchmark span (`2573–4465`) is **not** in any retrieved chunk for any
strategy.

The retriever ranks chunks by semantic similarity to the section's
guidance text. Guidance is template-supplied prose like "why important —
motivation, prior work, gap". The benchmark sentences ("Jiang et al."
etc.) are semantically distant from those terms.

### Strategy D proposal

Map each template section type to a **specialized retrieval query
pattern**. Detected by matching section title against a fixed dictionary:

| Section title contains | Specialized query pattern |
|---|---|
| "Introduction" or "Background" | guidance + `"competitor literature W_rec η values reported"` + `"author et al"` |
| "Comparison with Prior Work" | guidance + `"benchmark table comparison ceramic systems"` + `"Ref."` |
| "Synthesis" or "Preparation" | guidance + `"sintering temperature time atmosphere precursor"` + `"method"` |
| "Characterization" | guidance + `"XRD SEM TEM Raman XPS measurement instrument"` |
| "Theoretical Framework" | guidance + `"equation derivation formula model"` |

Implementation: extend `_build_retrieval_query` in `runner.py` with a
section-type heuristic.

### Test case

```bash
# Verify ch01 Introduction benchmark recovery
grep -c "Jiang\|Ma 等\|Zhang 等\|Tang 等" runs/meng2024_v141_D/s08_section_compose/chapters/01-*.md
# Expected: ≥ 3 (recover at least 3 of 4 competitor citations)

# Verify Synthesis chapter captures preparation specifics
grep -c "tape-casting\|sintering\|ball-mill\|calcin" runs/meng2024_v141_D/s08_section_compose/chapters/10-*.md
# Expected: ≥ 2 method terms
```

---

## Strategy E — KG extraction prompt for literature benchmarks

### Symptom

The KG for meng2024 (`runs/meng2024/s06_context/paper_kg.parquet`)
extracted only **2 comparator entities**:
- `NBT-based ceramics`
- `Ca2+- and Nb5+-codoped Bi0.5Na0.5TiO3` (Jiang's material — but as
  text, no W_rec value attached)

It missed Ma's `La(Mg₁/₂Zr₁/₂)O₃` system (W_rec=7.5), Zhang's
`(Bi₀.₅Na₀.₄K₀.₁)…` system (W_rec=8.58), Tang's `0.8Bi…SrTiO₃…` system
(W_rec=8.3).

### Root cause

The current `llm/prompts/paper_kg.md` describes `comparator` as "another
material this paper compares against (e.g., 'BaTiO3')". The LLM
interprets "compares against" narrowly — extracting only adjacent-domain
materials, not the literature-citation pattern that's typical in
introductions.

### Strategy E proposal

Tighten the `comparator` definition in the KG extraction prompt:

> **comparator**: ANY material cited from prior literature for benchmark
> comparison, including those introduced via "X et al. reported …" or
> ", X et al." footnote-style citations. For each comparator, ALSO extract
> the cited `W_rec`, `η`, and `E_b` values as separate `value` entities
> with `has_W_rec` / `has_η` / `has_E_b` relations connecting them.

Verification: Strategy A's coverage critic should then catch the missing
comparators on ch01 / ch14 drafts because they'd be in the KG.

### Test case

```bash
# After E is implemented, the KG should have ≥6 comparator entities for meng2024
uv run python -c "
from llm.paper_kg import PaperKG; from pathlib import Path
kg = PaperKG.from_parquet(Path('runs/meng2024_v141_E/s06_context/paper_kg.parquet'))
comps = kg.query('comparator')
print(f'{len(comps)} comparators:', [c.text for c in comps])
"
# Expected: ≥ 6 comparators (the 2 existing + at least 4 from Jiang/Ma/Zhang/Tang)
```

Combined with Strategy A (env=`LAZY_PAPER_COVERAGE=1`), the LLM critic
should then revise ch01 drafts to include the missing comparators.

---

## Strategy F — Whole-paper coherence pass

### Symptom

Inter-chapter consistency cannot be verified by per-section compose:
- meng2024 ch06 wrote `5.1 J/cm³` and `91%`; meng2024 ch10 (after
  v1.4.1+) correctly writes `5.00 J/cm³` and `90.09%`. Same paper,
  drifted numbers across chapters.
- ali2025_flash ch14 was a stub (688 bytes vs v1.3.3's 1663) because
  the retriever didn't surface the Fig.4 benchmark table for the
  "Comparison" guidance. A whole-paper pass would see the table cited
  in another chapter and pull it forward.

### Strategy F proposal

After all 15 sections are composed, run **one additional LLM pass**
that:
1. Reads all 15 chapter Markdown files + full source `s02_clean/*.md`.
2. Identifies cross-chapter numeric inconsistencies (e.g. `5.00` in ch10
   vs `5.1` in ch06).
3. Identifies sections that under-cite source data the rest of the paper
   uses.
4. Emits a list of suggested edits (or directly edits, with a diff
   audit file).

Cost: 1 large LLM call with ~50K context. Single call per paper, not
per section.

### Test case

```bash
# After F is implemented, all numeric value references should be consistent
# across chapters for the same parameter. Spot-check:
grep -ohE "W_rec ?= ?[0-9.]+" runs/meng2024_v141_F/s08_section_compose/chapters/*.md | sort -u
# Expected: ≤ 2 distinct values for W_rec (the actual sample's, plus
# possibly a competitor benchmark)
```

---

## Running comparison harness (when D/E/F land)

```bash
# Baseline (v1.4.2 default)
uv run python -m cli run --pdf ... --paper-id meng2024_v142_baseline ...

# +D
LAZY_PAPER_SECTION_QUERIES=1 uv run python -m cli run ... --paper-id meng2024_v142_D ...

# +E (requires re-extracting KG with updated prompt; clear s06 first)
rm -rf runs/meng2024_v142_E/s06_context
LAZY_PAPER_KG_V2=1 uv run python -m cli run ... --paper-id meng2024_v142_E ...

# +D+E (combined)
LAZY_PAPER_SECTION_QUERIES=1 LAZY_PAPER_KG_V2=1 LAZY_PAPER_COVERAGE=1 \
  uv run python -m cli run ... --paper-id meng2024_v142_DE ...

# +F (post-process whole-paper pass)
LAZY_PAPER_COHERENCE_PASS=1 uv run python -m cli run ... --paper-id meng2024_v142_F ...
```

Compare via the existing harness:

```bash
# Chapter sizes vs baseline
python3 scripts/compare_chapter_sizes.py meng2024_v142_baseline meng2024_v142_{D,E,DE,F}

# Benchmark recovery
for v in baseline D E DE F; do
  echo "=== $v ==="
  grep -ohE "(Jiang|Ma|Zhang|Tang) 等" runs/meng2024_v142_${v}/s08_section_compose/chapters/01-*.md | sort -u
done
```

Pick the variant with highest benchmark recovery + lowest critic
flagged_sections.

---

## Out of scope for this file

- pytest-runnable assertions for these scenarios (each requires a full
  paper pipeline run, ~10 min; treat as integration acceptance criteria)
- Cost estimates (each variant adds ~$0.5–$2 of API spend; F adds ~$3)
- Backward-compat strategy (these are all env-gated like A/B/C)
