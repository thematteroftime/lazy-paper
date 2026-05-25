# v1.12 Phase 2 — Anchored-Quote Enforcement Design Spec

> **One-line:** Close the "empty `cited_quote` bypass" in s08 verifier and
> tighten the compose prompt to demand verbatim source text whenever a
> claim names a specific author or numeric value.
>
> **Why now:** Phase 1 baseline shows `context_recall ≈ context_precision ≈ 1.0`
> but `faithfulness 0.44–0.66`. Retrieval is fine; the gap is in the
> generation→verification path. The empty-quote bypass at
> `stages/s08_section_compose/structured.py:329-331` is the documented root
> cause (architecture doc §11.1, deferred to v1.12).

---

## 1. Goal

Lift RAGAS faithfulness on `tests/eval/golden_qa/*.yaml` by closing the
empty-`cited_quote` verifier bypass. Two-layer fix:

- **Prompt layer**: explicit HARD RULE in `llm/prompts/section_compose.md`
  forcing the LLM to fill `cited_quote` whenever its claim text contains
  an author attribution or a numeric+unit value.
- **Verifier layer**: change the empty-quote branch in `verify_section_draft`
  from blanket-accept to anchor-aware reject. Existing `_claim_anchors()`
  helper is reused.

**Ship gate**: `ali2025_flash` RAGAS faithfulness ≥ +5pp over Phase 1 baseline.

**Default behaviour**: ON (this is a bug fix, not a new feature). Backward
compatibility via `LAZY_PAPER_ANCHORED_QUOTE=0` opt-out.

---

## 2. Background — what Phase 1 closed, what it did NOT

Phase 1 hardened the **extraction** layers (s04 figures, s06 KG) by adding
two opt-in tools. It did not touch s08 compose/verify. The RAGAS baseline
captured at end of Phase 1:

| Paper | faithfulness | context_recall | context_precision |
|---|---|---|---|
| meng2024 | 0.657 | 1.000 | ~1.000 |
| ali2025_flash | 0.440 | 1.000 | ~1.000 |

`context_*` perfect → retrieval is not the bottleneck. `faithfulness 0.44`
on ali2025_flash means 56% of claims in the rendered output cannot be
verified against any retrieved chunk. The architecture-level reason: the
verifier never inspects them, because the LLM emits empty `cited_quote`
and the current `verify_section_draft` short-circuits.

---

## 3. The empty-quote bypass — exact location

`stages/s08_section_compose/structured.py:329-331`:

```python
if not c.cited_quote.strip():
    accepted.append(c)
    continue
```

Every other branch in `verify_section_draft` does substantive checks
(quote-match, anchor advisory, figure_id whitelist, OOS overflow). This
branch alone is a blanket pass. The LLM can — and does — exploit it by
omitting `cited_quote` for hard-to-source claims.

---

## 4. Design

### 4.1 Prompt change (`llm/prompts/section_compose.md`)

Add to the SYSTEM prompt body, in the same block as the existing
"chunk-only citation rule":

```
HARD RULE on cited_quote (v1.12 phase 2):
- If your claim text NAMES a specific author ("Jiang et al.",
  "Ma 2022") OR contains a specific numeric value with unit
  ("2.94 J/cm³", "91.04%", "340 kV/cm"), you MUST fill cited_quote
  with the verbatim source text containing that anchor.
- Empty cited_quote is RESERVED for synthesis claims that integrate
  multiple chunks without a single source span.
- A claim with an author attribution or specific value but no
  cited_quote will be rejected by the verifier and lost from the
  rendered output.
```

Rationale: the rule is positive (says what to do), explicit (gives
examples), and warns about the consequence (rejection). Self-reinforcing.

### 4.2 Verifier change (`stages/s08_section_compose/structured.py`)

Replace lines 329-331:

```python
# OLD (pre-Phase 2):
if not c.cited_quote.strip():
    accepted.append(c)
    continue

# NEW (Phase 2):
if not c.cited_quote.strip():
    anchors = _claim_anchors(c.text)
    if anchors and os.environ.get("LAZY_PAPER_ANCHORED_QUOTE", "1") != "0":
        rejected.append({
            "text": c.text[:120],
            "reason": "anchored_claim_no_quote",
            "anchors": anchors,
        })
        continue
    accepted.append(c)  # true synthesis claim
    continue
```

Reuses existing `_claim_anchors()` (`structured.py:280`) which already
extracts author + value+unit anchors. Env gate `LAZY_PAPER_ANCHORED_QUOTE=0`
restores old behaviour for users who need it.

### 4.3 Why two layers (not just one)

- **Prompt only**: LLM may still cheat — prompt instructions are not hard
  constraints.
- **Verifier only**: catches the cheat but the LLM keeps emitting bad
  claims that get rejected, wasting tokens and risking the section
  goes empty.

Together: prompt steers the LLM toward right behaviour; verifier punishes
remaining failures with a visible signal (`anchored_claim_no_quote` shows
in the rejected audit trail and the next retry-when-empty pass).

### 4.4 Risks + mitigations

| Risk | Mitigation |
|---|---|
| All claims rejected → empty section | Existing `retry-when-empty` (structured.py:1090+) auto-retries with strengthened prompt; the new prompt rule will be visible in that retry too |
| Synthesis claims wrongly rejected | `_claim_anchors()` requires specific author/value patterns; descriptive prose without anchors passes through (existing behaviour preserved) |
| Backward compat broken | `LAZY_PAPER_ANCHORED_QUOTE=0` opt-out; existing tests that rely on empty-quote acceptance get a one-line env override during the test |
| Faithfulness flat or down | Ship gate is ≥+5pp on ali2025_flash; if not met, revert with Phase 2 lessons recorded for Phase 2.5 |

---

## 5. Out of scope

Explicitly NOT included in Phase 2:

- **Reference-list orthogonal check** (cited author must appear in
  `paper.references`). Architecture doc §11.1 mentioned this as the
  "v1.12 deferred" target. Skipped because we don't yet extract
  references into a structured field; that's its own feature.
- **MiniCheck NLI 5th tier**. Deferred to Phase 3 unless Phase 2
  result is below ship gate.
- **`_claim_anchors()` expansion** to cover additional anchor classes
  (chemical formulas, paper-specific abbreviations). Current regex
  covers author + value+unit; expansion is a separate concern.
- **Legacy + agent compose paths**. The fix applies through
  `verify_section_draft` which only Strategy KL calls. Legacy / agent
  paths are pre-existing fallback code paths; user opt-in to those is
  rare; not worth the additional verification surface.

---

## 6. Files touched

| File | Change |
|---|---|
| `llm/prompts/section_compose.md` | Add HARD RULE block (10-15 lines, system prompt section) |
| `stages/s08_section_compose/structured.py:329-331` | Replace blanket-accept with anchor-aware branch (10 lines) |
| `stages/s08_section_compose/tests/test_structured.py` | Add/update tests for the new branch (3-4 tests) |
| `.env.example` | One-line documenting `LAZY_PAPER_ANCHORED_QUOTE` (default 1) |
| `CHANGELOG.md` | v1.12-phase2 entry |
| `docs/ARCHITECTURE.md` | §5.5 verifier table updated; §11.1 deferred item moved to "shipped" |
| `docs/archive/v1_12_phase2_summary.md` | New report with RAGAS delta |

Net diff estimate: **30-50 LOC code + ~80 LOC tests + docs**.

---

## 7. Verification plan

1. **Unit**: 3-4 new `test_structured.py` cases covering:
   - Empty quote + author anchor → REJECTED
   - Empty quote + value anchor → REJECTED
   - Empty quote + no anchors → ACCEPTED (synthesis)
   - Non-empty quote with anchor mismatch → existing advisory (unchanged)
2. **Regression**: full `pytest -q` must pass. Existing tests that expected
   empty-quote claims to be accepted get `monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")`.
3. **Quantitative**: `pytest -m ragas tests/eval/` against meng2024 +
   ali2025_flash. Ship gate: ali2025_flash faithfulness ≥+5pp.
4. **Audit**: a 1-paper full pipeline run with logs showing
   `anchored_claim_no_quote` rejections — count must be reasonable
   (e.g., <30% of all claims).

---

## 8. Rollout plan

- Land in `worktree-v1.12-phase1` (same branch as Phase 1, additive)
- Phase 1 + Phase 2 ship together as v1.12 from this branch
- Default ON immediately; `LAZY_PAPER_ANCHORED_QUOTE=0` opt-out documented
  in `.env.example` and `docs/USER_GUIDE.md`
- If Phase 2 ship gate not met (faithfulness flat on ali2025_flash):
  feature stays in the branch with the failed data recorded, decision
  to merge or revert escalated to the maintainer

---

## 9. Open questions

None at this point — design is signed off by the user (default ON
selected; scope locked to prompt + verifier only).
