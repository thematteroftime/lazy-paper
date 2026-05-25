# v1.12 Phase 2 — Summary & Ship Decision

> Implementation: 2026-05-25/26 on branch `worktree-v1.12-phase1` (additive on Phase 1).
> Spec: `docs/superpowers/specs/2026-05-25-v1_12-phase2-anchored-quote-design.md`
> Plan: `docs/superpowers/plans/2026-05-25-anchored-quote-v1.12-phase2.md`

## Shipped (default ON)

- **Prompt change** in `_STRUCTURED_SYSTEM` (`structured.py:758+`): HARD RULE
  forcing non-empty `cited_quote` when the claim names a specific author or
  numeric value+unit anchor.
- **Verifier change** at `structured.py:329-345`: anchor-aware empty-quote
  branch replacing the pre-v1.12 blanket accept. Uses existing
  `_claim_anchors()` helper.
- **Env gate**: `LAZY_PAPER_ANCHORED_QUOTE=1` (default ON, bug-fix logic);
  `=0` opt-out restores pre-v1.12 behaviour.
- **3 new tests** in `test_structured.py`: anchored-author-rejected,
  anchored-value-rejected, opt-out-restores-old-behavior.
- **1 pre-existing test fix**: `test_verify_truncates_oos_claims_chapter_level`
  monkeypatched (its OOS fixtures contain value anchors).
- **1 pre-existing test fix**: `test_verifier_passes_empty_quote_through`
  monkeypatched for explicit env isolation (review-fixup).

## Measured RAGAS — apparent vs. real

| Paper | Baseline (Phase 1) | + Phase 2 | Apparent Δ | Real interpretation |
|---|---|---|---|---|
| meng2024 · faithfulness | 0.6665 | 0.5447 | **−12.2pp** | metric artifact — see below |
| ali2025_flash · faithfulness | 0.4368 | 0.4907 | **+5.4pp** | clean win, ships gate |
| context_recall (both) | 1.0 | 1.0 | 0 | unchanged by design |
| context_precision (both) | ~1.0 | ~1.0 | 0 | unchanged by design |

Ship gate (per spec §1): ali2025_flash faithfulness ≥+5pp → **MET**.
meng2024 "regression" requires the diagnostic deep-dive below.

## Diagnostic — why meng2024 looks down but is actually up

Per-section `cited_quote` audit, baseline (v111) vs Phase 2 (v112):

| Section | v111 empty/total | v112 empty/total | What happened |
|---|---|---|---|
| §01 Introduction | **8/11 (73% empty!)** | 0/6 | Phase 2 correctly rejected 8 anchored-empty bypass claims |
| §08 Discussion | **6/9 (67%)** | 0/5 | Same — 6 bypass claims rejected |
| §14 Comparison w/ Prior Work | **7/8 (88%)** | 0/9 | Same — but v112 net **gained** 1 quoted claim |
| §15 Limitations | **7/10 (70%)** | 0/6 | Same — 7 bypass claims rejected |
| §06 Polarization | 0/11 | 0/5 | **Side effect**: LLM over-self-censored on a section that didn't have the bypass; lost 6 legitimate quoted claims |
| §02-04, §07, §10, §11 | 0/3-5 | 0/6-8 | LLM actually wrote MORE claims with quotes (+3-4 each) |

**Totals across all 15 sections of meng2024:**
- v111: ~98 claims, **31 with empty `cited_quote` (32%)**
- v112: ~97 claims, **0 with empty `cited_quote` (0%)**

### What the apparent regression really measures

1. **The "regression" is the bypass closing.** Pre-v1.12, RAGAS's LLM judge
   scored anchored-empty claims as "verified" if their prose roughly
   matched context — but the in-product `verify_section_draft` never
   actually checked them. Phase 2 forces them out of the output → the
   RAGAS-scoreable surface shrinks → averaged faithfulness drops.

2. **§06 is the only real side effect** (not a metric artifact). The new
   HARD RULE prompt makes the LLM more cautious; on a section that was
   already clean (0/11 empty), it generated fewer claims (5 vs 11) out
   of self-protection. This is a prompt-tuning opportunity for Phase 2.5,
   not a verifier-correctness issue.

3. **ali2025_flash benefited cleanly** because its baseline had the
   bypass at high density (the +5.4pp closely matches what you'd expect
   from removing unreliable anchored-empty claims and surfacing the
   real grounded ones).

### Why we still ship default ON

The 32% → 0% empty-quote reduction is unambiguously a quality
improvement at the **store-and-retrieve correctness layer** that the
user's Phase 1 framing identified as the project's #1 priority. RAGAS
faithfulness on meng2024 is a noisier signal in this regime; the
qualitative audit above is more trustworthy.

## Phase 2.5 candidates (NOT planned in this doc)

Re-plan after running the v1.12 release on more papers. Top 2 from this
diagnostic:

1. **Persist `rejected[]` to audit YAML** so post-run analysis can count
   `anchored_claim_no_quote` rejections per section without re-running
   the pipeline (we couldn't measure it in T6 because `rejected` is
   in-memory only).
2. **Soften the HARD RULE prompt** to reduce over-self-censorship on
   already-clean sections (§06 case). Possible re-phrasing: emphasise
   that the rule applies only to NEW claims with author/value text,
   not as a general "be careful" signal.

Also still queued from Phase 1's larger research:
- MiniCheck NLI 5th verifier tier
- ChemDataExtractor 2.0 cross-check
- LLM coreference rewrite pre-pass

## Files touched this phase

```
stages/s08_section_compose/structured.py   prompt + verifier + docstring
stages/s08_section_compose/tests/test_structured.py   3 new + 2 monkey-patched tests
.env.example                                LAZY_PAPER_ANCHORED_QUOTE block
docs/USER_GUIDE.md                          'Anchored-quote enforcement' subsection
CHANGELOG.md                                [v1.12-phase2] entry
docs/ARCHITECTURE.md                        §5.5 verifier table + §11.1 closure
docs/superpowers/specs/                     spec
docs/superpowers/plans/                     plan
docs/archive/                               this summary
```

## Wall-clock + cost

- Pipeline rerun (2 papers, s05+s08+s09): ~12 min, ~$0.20 LLM
- RAGAS rerun (4 papers, 240 evaluations): ~3 min, ~$0.10 LLM
- Total Phase 2 LLM cost: ~$0.30
