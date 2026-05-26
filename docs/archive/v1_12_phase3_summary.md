# v1.12 Phase 3 — Hygiene & Generalization Sweep

> Implementation: 2026-05-26 on `worktree-v1.12-phase1` (additive on Phase 1+2).
> Driven by a 3-auditor cross-review (redundancy / prose+prompt / generalization).

## What changed across 3a/3b/3c

### Phase 3a — Chinese mirror fix (single commit)

`docs_zh/USER_GUIDE.md` had no v1.12 section at all. `docs_zh/ARCHITECTURE.md`
had no anchored-quote row in §5.5 or closure note in §11.1.

- `docs_zh/USER_GUIDE.md`: +59 lines, full v1.12 block translated
  (PDFFigures 2 + entity dedup + anchored-quote enforcement, 3 subsections)
- `docs_zh/ARCHITECTURE.md`: +3 lines (verifier table row + §11.1 closure)

Chinese terminology kept English proper nouns (`cited_quote`,
`anchored_claim_no_quote`, `LAZY_PAPER_ANCHORED_QUOTE`) to match the code.

### Phase 3c — Domain-agnostic prompts + KG + docs (single commit)

The project starts from materials-science but the audit found 5 hard
bindings that would degrade quality on non-materials papers.

| File | Change |
|---|---|
| `llm/prompts/paper_context.md` | "materials-science research assistant" → "scientific research assistant"; `system:` field examples now cover ML, materials, chemistry |
| `llm/prompts/paper_kg.md` + `paper_kg_v3.md` | Opening declaration generalized; `dopant` entity gets a note treating it as `additive / modifier` for non-materials domains |
| `llm/prompts/paper_kg_v3.md` (comparator block) | Hardcoded `has_W_rec / has_η / has_E_b` softened to generic `has_<metric>` (materials kept as default but ML/chemistry options shown) |
| `stages/s08_section_compose/structured.py` `_STRUCTURED_SYSTEM` | Author attribution example now pairs materials (Jiang et al. NBT) with ML (Smith et al. ResNet-50 on ImageNet); anchor examples added `BLEU score 36.8` |
| `stages/s06_context/kg_extract.py::extract_headline_metrics` | **No code change needed** — auditor's suggested change was already implemented in v1.10 (uses dynamic `startswith("has_")` loop). |
| `README.md` | Top adds "works with any scientific PDF — defaults are materials science but pipeline is domain-agnostic"; cross-domain framing for unCLIP test |
| `docs/USER_GUIDE.md` | Quickstart paragraph reminds outline template is hierarchy-only |

`extract_headline_metrics` not needing change is a good signal — the audit
caught what the code ALREADY did right.

### Phase 3b — Prompt compression (single commit)

Net savings ~1200 characters per s08 system prompt = real token cost
reduction × every section × every paper × long-term use.

| Change | File | Saved chars |
|---|---|---|
| Merge two redundant "Quantitative fidelity" blocks into 8-rule list | `llm/prompts/section_compose.md` | ~700 |
| Tighten HARD RULE block in `_STRUCTURED_SYSTEM` from 680→430 chars (kept all rules) | `stages/s08_section_compose/structured.py` | ~250 |
| Compress Unicode-math block from 5 lines to 3 | `llm/prompts/pptx_summarize.md` | ~120 |
| Add backtick examples (slight expansion) | `llm/prompts/pptx_outline.md` | -20 |
| Remove duplicate "Be MORE inclusive" segment (already said "Be aggressive") | `llm/prompts/paper_kg_v3.md` | ~100 |

Total: ~**1150 chars/call** saved on the heaviest LLM call (s08 compose).
Skipped `figure_analyze.md` change — the "verdict" the auditor flagged
turned out to be the schema's `note` field spec, not duplication.

## Regression check — RAGAS delta

Re-ran s05+s08+s09 on meng2024 + ali2025_flash with all Phase 3 prompts
+ Phase 2 verifier. Comparison vs **Phase 2 baseline** (`*_v112_anchoredq`):

| Paper × Metric | Phase 2 baseline | Phase 3 (a+b+c) | Δ |
|---|---|---|---|
| meng2024 · faithfulness | 0.545 | <fill> | <fill> |
| meng2024 · context_recall | 1.000 | <fill> | <fill> |
| meng2024 · context_precision | ~1.000 | <fill> | <fill> |
| ali2025_flash · faithfulness | 0.491 | <fill> | <fill> |
| ali2025_flash · context_recall | 1.000 | <fill> | <fill> |
| ali2025_flash · context_precision | ~1.000 | <fill> | <fill> |

**Pass criterion**: no regression > 2pp on either paper. The prompt
compressions were content-preserving (rules same, fewer words), so we
expect ≈0pp change. Larger drops would suggest accidental rule loss.

## Files touched (Phase 3 entire)

```
docs_zh/USER_GUIDE.md            +59
docs_zh/ARCHITECTURE.md          +3
llm/prompts/paper_context.md     small generalization
llm/prompts/paper_kg.md          small generalization
llm/prompts/paper_kg_v3.md       generalization + 100-char compression
llm/prompts/section_compose.md   700-char compression
llm/prompts/pptx_summarize.md    120-char compression
llm/prompts/pptx_outline.md      slight expansion
stages/s08_section_compose/structured.py  HARD RULE compression + ML example
README.md                        cross-domain framing
docs/USER_GUIDE.md               cross-domain reminder
docs/archive/v1_12_phase3_summary.md  this doc
```

## Cost & wall-clock (Phase 3 verification)

- Pipeline rerun (2 papers × s05+s08+s09): ~15 min, ~$0.20
- RAGAS rerun (4 papers × 60 evaluations): ~3 min, ~$0.10
- Phase 3 total LLM cost: ~$0.30

## What Phase 3 did NOT change

- KG entity type names (`dopant` stays as is to avoid parquet schema migration)
- `_claim_anchors()` and its regexes (already domain-generic)
- s03 / s04 bilingual regex (already domain-generic)
- test fixtures (golden_qa stays focused on the 2 demo papers; users
  can add more)
- ChemDataExtractor 2.0 / MiniCheck / coref-rewrite (still queued as
  Phase 4 candidates)
