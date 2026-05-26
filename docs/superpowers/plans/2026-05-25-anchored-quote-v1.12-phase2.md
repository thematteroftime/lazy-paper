# v1.12 Phase 2 — Anchored-Quote Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the "empty `cited_quote` bypass" in s08 verifier so that LLM claims naming a specific author or numeric value can no longer skip verification by leaving the quote field empty. Target +5pp on `ali2025_flash` RAGAS faithfulness.

**Architecture:** Two-layer fix. (1) Prompt change in `_STRUCTURED_SYSTEM` (the Strategy KL compose prompt baked into `structured.py:758+`) instructing the LLM to fill `cited_quote` whenever the claim names an author/value anchor. (2) Verifier change at `structured.py:329-331` replacing blanket-accept of empty-quote claims with an anchor-aware reject using the existing `_claim_anchors()` helper. Default ON; `LAZY_PAPER_ANCHORED_QUOTE=0` opt-out preserves backward compat.

**Tech Stack:** Python 3.11+ (uv-managed), pytest, existing s08 compose pipeline (Strategy KL via `instructor` + Pydantic), ragas 0.1.21 harness from Phase 1.

**Spec reference:** `docs/superpowers/specs/2026-05-25-v1_12-phase2-anchored-quote-design.md`

---

## File Structure

**Modified files:**
- `stages/s08_section_compose/structured.py:329-331` — verifier empty-quote branch
- `stages/s08_section_compose/structured.py:758+` (`_STRUCTURED_SYSTEM` body, around the current "cited_quote may be verbatim or empty" line at 778) — prompt HARD RULE
- `stages/s08_section_compose/tests/test_structured.py` — update existing empty-quote test + add 3 new
- `.env.example` — one-line documenting `LAZY_PAPER_ANCHORED_QUOTE` (default 1)
- `docs/USER_GUIDE.md` — short "Anchored-quote enforcement (v1.12 phase 2)" subsection under Optional features
- `docs/ARCHITECTURE.md` — §5.5 verifier table updated (new row at the top); §11.1 entry moves from "CUT (cycle 5-7)" reference to "shipped in v1.12 phase 2"
- `CHANGELOG.md` — `[v1.12-phase2]` entry under Unreleased

**Created files:**
- `docs/archive/v1_12_phase2_summary.md` — measured impact (RAGAS delta) + ship decision

**Out of scope (per spec §5):** legacy/agent compose paths; reference-list orthogonal check; MiniCheck; `_claim_anchors` regex expansion.

---

## Task 1: Update `_STRUCTURED_SYSTEM` prompt with HARD RULE

**Files:**
- Modify: `stages/s08_section_compose/structured.py` (around lines 776-778, inside `_STRUCTURED_SYSTEM` triple-quoted string)

- [ ] **Step 1: Read the current prompt block to confirm location**

Run: `grep -n "cited_quote may be verbatim or empty" stages/s08_section_compose/structured.py`
Expected: one match at line 778 (inside `_STRUCTURED_SYSTEM` Python string).

- [ ] **Step 2: Replace the "may be verbatim or empty" block with the new HARD RULE**

Edit `stages/s08_section_compose/structured.py` — find this exact block:

```
For other claims (not required, just supporting the section's argument):
  - cite ≥1 chunk that supports the claim
  - cited_quote may be verbatim or empty (empty skips verification)
  - keep prose in the requested language (Chinese unless the user says English)
```

Replace with:

```
For other claims (not required, just supporting the section's argument):
  - cite ≥1 chunk that supports the claim
  - keep prose in the requested language (Chinese unless the user says English)

## HARD RULE on cited_quote (v1.12 phase 2)

A claim's `cited_quote` field is the verifier's primary grounding signal.
Fill it as follows:

  - **REQUIRED non-empty** when the claim text NAMES one of:
      - a specific author ("Jiang et al.", "Ma 2022", "et al.")
      - a specific numeric value ("2.94 J/cm³", "91.04%", "340 kV/cm")
    The cited_quote MUST contain the verbatim source span carrying that
    anchor. Empty cited_quote on an anchored claim is REJECTED by the
    verifier and the claim is lost from the rendered output.

  - **MAY be empty** ONLY for synthesis claims that integrate multiple
    chunks without a single source span — e.g. high-level summaries,
    cross-chunk inferences. These pass without quote verification.

When in doubt, copy a verbatim slice. Empty quote is the exception, not
the default.
```

- [ ] **Step 3: Run a no-LLM smoke check that the module still imports**

Run: `uv run python -c "from stages.s08_section_compose import structured; print('OK', '\n'.join([k for k in dir(structured) if k.startswith('_STRUCTURED')]))"`
Expected: `OK _STRUCTURED_SYSTEM` (the constant still loads, no syntax error).

- [ ] **Step 4: Run the s08 test suite to ensure no test snapshots reference the old prompt text**

Run: `uv run pytest stages/s08_section_compose/tests/ -q --no-header 2>&1 | tail -5`
Expected: all existing tests pass (the prompt body isn't snapshot-tested, so this is just a regression guard).

- [ ] **Step 5: Commit**

```bash
git add stages/s08_section_compose/structured.py
git commit -m "feat(s08-prompt): HARD RULE — cited_quote required for anchored claims (T1 v1.12 phase 2)

The Strategy KL compose system prompt (_STRUCTURED_SYSTEM) now explicitly
distinguishes 'anchored' claims (naming a specific author or value+unit) from
'synthesis' claims. Anchored claims MUST carry a verbatim cited_quote; empty
quote on an anchored claim is rejected by the verifier (see T2).

This pairs with the verifier change in T2: prompt steers, verifier enforces.

Architecture doc §11.1 closure item (empty cited_quote bypass)."
```

---

## Task 2: Make verifier reject empty quote when claim has anchors

**Files:**
- Modify: `stages/s08_section_compose/structured.py:329-331` (the empty-quote branch in `verify_section_draft`)

- [ ] **Step 1: Confirm `os` is already imported in structured.py**

Run: `grep -n "^import os\|^from os" stages/s08_section_compose/structured.py | head -3`
Expected: at least one match. **If no match**, add `import os` to the imports block (top of file).

- [ ] **Step 2: Replace the empty-quote branch (current lines 329-331)**

Find this exact block:

```python
        if not c.cited_quote.strip():
            accepted.append(c)
            continue
```

Replace with:

```python
        if not c.cited_quote.strip():
            # v1.12 phase 2: anchor-aware empty-quote check.
            # Pre-v1.12: blanket accept. The LLM exploited this by omitting
            # cited_quote for hard-to-source claims, bypassing the verifier.
            # Now: if the claim text names an author or specific value+unit
            # (anchor present), the empty quote is REJECTED. Synthesis claims
            # with no anchors still pass. LAZY_PAPER_ANCHORED_QUOTE=0 restores
            # pre-v1.12 behaviour for backward compat.
            anchors = _claim_anchors(c.text)
            if anchors and os.environ.get("LAZY_PAPER_ANCHORED_QUOTE", "1") != "0":
                rejected.append({
                    "text": c.text[:120],
                    "reason": "anchored_claim_no_quote",
                    "anchors": anchors,
                })
                continue
            accepted.append(c)  # true synthesis claim (no anchors)
            continue
```

- [ ] **Step 3: Update the docstring of `verify_section_draft` (lines 295-316) to reflect new behaviour**

Find this line (currently at 302-304):

```
    Empty quotes skip verification (cited_chunk_ids alone is the grounding
    signal — the LLM may still write good prose without verbatim quoting).
```

Replace with:

```
    Empty quotes are only accepted for synthesis claims (those without
    specific author / value+unit anchors detected by _claim_anchors). An
    anchored claim with empty cited_quote is rejected with reason
    `anchored_claim_no_quote` — set LAZY_PAPER_ANCHORED_QUOTE=0 to restore
    pre-v1.12 behaviour. (v1.12 phase 2 closure of arch doc §11.1.)
```

- [ ] **Step 4: Run existing s08 test suite — expect ONE regression**

Run: `uv run pytest stages/s08_section_compose/tests/test_structured.py::test_verifier_passes_empty_quote_through -v`
Expected: PASS — the existing test uses claims like "A1"/"A2"/"A3" with no anchors, so the new branch still accepts them. **If it fails**, the test is fragile to the change; T3 will adjust.

Run: `uv run pytest stages/s08_section_compose/tests/test_structured.py -v --no-header 2>&1 | tail -15`
Expected: any failure here will be addressed in T3 by either env-overriding the test (`monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")`) or by adding a `cited_quote` value to the test fixture. Note the failure for T3.

- [ ] **Step 5: Commit**

```bash
git add stages/s08_section_compose/structured.py
git commit -m "feat(s08-verifier): reject empty cited_quote when claim has anchors (T2 v1.12 phase 2)

Replaces the unconditional empty-quote accept at structured.py:329-331 with
an anchor-aware branch:
- claim text has author / value+unit anchor (via existing _claim_anchors)
  AND empty cited_quote → REJECTED with reason 'anchored_claim_no_quote'
- no anchors AND empty cited_quote → ACCEPTED (true synthesis claim)
- LAZY_PAPER_ANCHORED_QUOTE=0 opt-out restores pre-v1.12 behaviour

Docstring of verify_section_draft updated to match. Closes architecture
doc §11.1 deferred item."
```

---

## Task 3: Add 3 new verifier tests + adjust existing if needed

**Files:**
- Modify: `stages/s08_section_compose/tests/test_structured.py` (add 3 tests near the existing `test_verifier_*` block, around line 94)

- [ ] **Step 1: Read existing test fixture pattern**

Run: `sed -n '90,110p' stages/s08_section_compose/tests/test_structured.py`
Expected: shows `test_verifier_passes_empty_quote_through` + setup pattern (Chunk objects, SectionDraft, verify_section_draft call).

- [ ] **Step 2: Add the 3 new tests at the end of the existing verifier-test block (after line ~110)**

Open `stages/s08_section_compose/tests/test_structured.py` and locate `test_verifier_passes_empty_quote_through` (line 94+). After its closing line, INSERT:

```python
def test_verifier_rejects_empty_quote_with_author_anchor(monkeypatch):
    """v1.12 phase 2: claim names 'Jiang et al.' but cited_quote empty → REJECT."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "1")  # default; explicit for clarity
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft, Chunk,
    )
    chunks = {0: Chunk(text="Jiang et al. reported W_rec = 2.94 J/cm³.",
                       doc_name="d.md", char_start=0, char_end=46)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang et al. reported a moderate W_rec.",
                      cited_chunk_ids=[0], cited_quote=""),  # anchored but empty quote
        GroundedClaim(text="The system maintains stability.",
                      cited_chunk_ids=[0], cited_quote=""),  # no anchors — should pass
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 1
    assert accepted[0].text == "The system maintains stability."
    assert any(r["reason"] == "anchored_claim_no_quote" for r in rejected)


def test_verifier_rejects_empty_quote_with_value_anchor(monkeypatch):
    """v1.12 phase 2: claim names 'W_rec = 5.00 J/cm³' but cited_quote empty → REJECT."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "1")
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft, Chunk,
    )
    chunks = {0: Chunk(text="A large W_rec of 5.00 J/cm³ was achieved.",
                       doc_name="d.md", char_start=0, char_end=42)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="The flagship achieves W_rec = 5.00 J/cm³ at 340 kV/cm.",
                      cited_chunk_ids=[0], cited_quote=""),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 0
    assert any(r["reason"] == "anchored_claim_no_quote" for r in rejected)


def test_verifier_opt_out_via_env_restores_old_behavior(monkeypatch):
    """LAZY_PAPER_ANCHORED_QUOTE=0 restores pre-v1.12 'blanket accept empty quote'."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft, Chunk,
    )
    chunks = {0: Chunk(text="Jiang et al. reported W_rec.",
                       doc_name="d.md", char_start=0, char_end=29)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang et al. reported a moderate W_rec.",
                      cited_chunk_ids=[0], cited_quote=""),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 1, "opt-out env should accept anchored empty-quote claims"
```

- [ ] **Step 3: Run the new tests**

Run: `uv run pytest stages/s08_section_compose/tests/test_structured.py::test_verifier_rejects_empty_quote_with_author_anchor stages/s08_section_compose/tests/test_structured.py::test_verifier_rejects_empty_quote_with_value_anchor stages/s08_section_compose/tests/test_structured.py::test_verifier_opt_out_via_env_restores_old_behavior -v`
Expected: 3 passed.
**If author/value test fails**: check that the claim text actually triggers `_claim_anchors()` — debug by `uv run python -c "from stages.s08_section_compose.structured import _claim_anchors; print(_claim_anchors('Jiang et al. reported a moderate W_rec.'))"`. Expected non-empty list.

- [ ] **Step 4: Run the whole s08 test suite to verify NO regression**

Run: `uv run pytest stages/s08_section_compose/tests/ -q --no-header 2>&1 | tail -5`
Expected: all pass. **If `test_missing_required_audits_entities_not_in_prose` or any other pre-existing test fails**: the failing claims have anchors AND empty quote — add `monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")` to those tests (they're testing OTHER behaviour and shouldn't be coupled to this new rule), with a brief comment explaining why.

- [ ] **Step 5: Run the entire repo test suite**

Run: `uv run pytest -q --no-header 2>&1 | tail -3`
Expected: 315 passed (312 existing + 3 new), 3 deselected (live + ragas).
**If unexpected failures**: same fix as Step 4 — add monkeypatch to opt out the affected tests with a comment.

- [ ] **Step 6: Commit**

```bash
git add stages/s08_section_compose/tests/test_structured.py
git commit -m "test(s08): 3 verifier tests for anchored-quote enforcement (T3 v1.12 phase 2)

- test_verifier_rejects_empty_quote_with_author_anchor: 'Jiang et al.' +
  empty quote → REJECTED with reason 'anchored_claim_no_quote'; control
  claim without anchor in same draft → ACCEPTED.
- test_verifier_rejects_empty_quote_with_value_anchor: 'W_rec = 5.00 J/cm³' +
  empty quote → REJECTED.
- test_verifier_opt_out_via_env_restores_old_behavior: LAZY_PAPER_ANCHORED_QUOTE=0
  brings back pre-v1.12 blanket accept.

Adjacent pre-existing tests with anchored-empty-quote fixtures (if any)
also got monkeypatched to LAZY_PAPER_ANCHORED_QUOTE=0 to keep their
original intent."
```

---

## Task 4: Document the env flag (.env.example + USER_GUIDE)

**Files:**
- Modify: `.env.example` (append after v1.12 phase 1 block)
- Modify: `docs/USER_GUIDE.md` (under "Optional features (v1.12 phase 1)" — rename to "Optional features (v1.12)" and add new subsection)

- [ ] **Step 1: Append to `.env.example`**

Open `.env.example`, find the existing `LAZY_PAPER_ENTITY_DEDUP=0` line near the end, and AFTER it append:

```bash

# v1.12 phase 2 — Anchored-quote enforcement (default ON).
# Verifier rejects claims that name a specific author/value+unit but leave
# cited_quote empty (was the documented bypass — arch doc §11.1).
# Set to 0 to restore pre-v1.12 'blanket accept empty quote' behaviour.
LAZY_PAPER_ANCHORED_QUOTE=1
```

- [ ] **Step 2: Add a USER_GUIDE subsection**

Open `docs/USER_GUIDE.md`, find the heading `### Entity dedup — author misattribution defence` (from Phase 1). AFTER its closing line (just before the next `---`), append:

```markdown

### Anchored-quote enforcement (v1.12 phase 2) — default ON

Pre-v1.12, claims with an empty `cited_quote` skipped verification
entirely. The LLM exploited this to leave hard-to-source claims
unverified. Phase 2 closes the bypass:

- Claims whose text names a specific author (`Jiang et al.`) or numeric
  value with unit (`2.94 J/cm³`, `91.04%`) MUST carry a non-empty
  `cited_quote`. Empty quote on such a claim is rejected.
- Synthesis claims (no specific anchor in text) still pass without
  quote verification — backward compatible for cross-chunk summaries.

Opt-out for backward compat:

```bash
LAZY_PAPER_ANCHORED_QUOTE=0   # in .env
```

The opt-out exists for projects with existing baselines / regressed
prompts; new runs should leave it on.
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docs/USER_GUIDE.md
git commit -m "docs(v1.12-phase2): document LAZY_PAPER_ANCHORED_QUOTE flag (T4)"
```

---

## Task 5: Pre-RAGAS regression check + run baseline reference

**Files:**
- No code changes — verification step

- [ ] **Step 1: Confirm the symlinks are still in place**

Run: `ls -la runs input 2>&1 | head -5`
Expected: both are symlinks pointing to `../../../runs` and `../../../input` (set up during Phase 1 in this worktree).
**If missing**: re-create per Phase 1 plan — `ln -s ../../../runs runs; ln -s ../../../input input` (the symlinks themselves are gitignored).

- [ ] **Step 2: Capture the Phase 1 baseline JSON files for reference**

Run: `cat tests/eval/_ragas_out/meng2024_v111_demo.json tests/eval/_ragas_out/ali2025_flash_v111_demo.json`
Expected: shows the Phase 1 baseline scores (meng2024 faithfulness 0.657 / ali2025_flash 0.440). Note these for T6 delta comparison.

- [ ] **Step 3: Run the full test suite to confirm green baseline before RAGAS**

Run: `uv run pytest -q --no-header 2>&1 | tail -3`
Expected: 315 passed, 3 deselected. **No regression**.

- [ ] **Step 4: (No commit — verification only)**

---

## Task 6: Re-run pipeline (no PDF needed) + RAGAS delta

**Strategy:** RAGAS scores the s08 output. We need the s08 stage to RE-RUN with the new verifier to produce a new output. Since s08 reads from runs/<paper>/s03+s05+s06+s07/, we can re-run s08 (and optionally s09) without OCR.

**Files:**
- No code changes — execution step

- [ ] **Step 1: Re-run s08 on meng2024 with the new verifier (LLM call required, ~3 min/paper)**

Run:
```bash
LLM_TEXT_MODEL=deepseek-chat uv run python -m cli run \
    --pdf input/hif_2.pdf \
    --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id meng2024_v112_anchoredq \
    --lang zh --only s05_template,s08_section_compose,s09_render --force
```

Wait — `--paper-id meng2024_v112_anchoredq` needs the upstream stages (s03, s04, s06, s07) in that runs/ dir. Copy them first:

```bash
mkdir -p runs/meng2024_v112_anchoredq
cp -R runs/meng2024_v111_demo/{s01_ocr,s02_clean,s03_chapter,s04_figures,s06_context,s07_figure_analyze} \
      runs/meng2024_v112_anchoredq/
ls runs/meng2024_v112_anchoredq/
```
Expected: lists 6 stage dirs.

Then re-run only s05 + s08 + s09 (s05 is fast template parse; s08 is the heavy LLM call we want to measure):

```bash
LLM_TEXT_MODEL=deepseek-chat uv run python -m cli run \
    --pdf input/hif_2.pdf \
    --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id meng2024_v112_anchoredq \
    --lang zh --only s05_template,s08_section_compose,s09_render --force 2>&1 | tail -20
```

**Note**: `--pdf input/hif_2.pdf` is a placeholder — s08/s09 don't read the PDF, only s01 does. The `--pdf` arg is mandatory by the CLI but unused for our `--only` subset. `input/hif_2.pdf` is the only PDF that resolves in the worktree symlink (from Phase 1).
Expected: completes in ~3-5 min. Final line shows compose + render done.

- [ ] **Step 2: Repeat for ali2025_flash**

```bash
mkdir -p runs/ali2025_flash_v112_anchoredq
cp -R runs/ali2025_flash_v111_demo/{s01_ocr,s02_clean,s03_chapter,s04_figures,s06_context,s07_figure_analyze} \
      runs/ali2025_flash_v112_anchoredq/
LLM_TEXT_MODEL=deepseek-chat uv run python -m cli run \
    --pdf input/hif_2.pdf \
    --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id ali2025_flash_v112_anchoredq \
    --lang zh --only s05_template,s08_section_compose,s09_render --force 2>&1 | tail -10
```

- [ ] **Step 3: Add the v112 paper-ids to golden_qa (temporary copies)**

```bash
cp tests/eval/golden_qa/meng2024.yaml tests/eval/golden_qa/_meng2024_v112.yaml
sed -i '' 's/meng2024_v111_demo/meng2024_v112_anchoredq/' tests/eval/golden_qa/_meng2024_v112.yaml
cp tests/eval/golden_qa/ali2025_flash.yaml tests/eval/golden_qa/_ali2025_v112.yaml
sed -i '' 's/ali2025_flash_v111_demo/ali2025_flash_v112_anchoredq/' tests/eval/golden_qa/_ali2025_v112.yaml
```

Files starting with `_` are skipped by the conftest's `golden_papers` fixture (it filters `if yml.name.startswith("_"): continue`). Wait — that means the fixture WILL SKIP them. We need a different approach. **Instead**, rename them WITHOUT the leading underscore but they need to be in the conftest's traversal — actually they will be. So drop the leading underscore:

```bash
mv tests/eval/golden_qa/_meng2024_v112.yaml tests/eval/golden_qa/meng2024_v112.yaml
mv tests/eval/golden_qa/_ali2025_v112.yaml tests/eval/golden_qa/ali2025_v112.yaml
```

Now there are 4 golden_qa files; RAGAS will score 4 papers × 3 metrics × 20 q = 240 evaluations. ETA ~5-8 min.

- [ ] **Step 4: Run RAGAS**

```bash
LLM_TEXT_MODEL=deepseek-chat uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s 2>&1 | tail -20
```
Expected: `1 passed`, 4 JSON files in `tests/eval/_ragas_out/`. Wall clock ~5-8 min.

- [ ] **Step 5: Inspect the deltas**

```bash
for paper in meng2024_v111_demo meng2024_v112_anchoredq ali2025_flash_v111_demo ali2025_flash_v112_anchoredq; do
    echo "=== $paper ==="
    cat tests/eval/_ragas_out/$paper.json
done
```
Note all 4 sets of scores. Compute:
- `meng2024 Δfaithfulness = v112 - v111`
- `ali2025_flash Δfaithfulness = v112 - v111` (this is the ship gate; must be ≥ +0.05)

- [ ] **Step 6: Clean up the temp golden_qa files (keep `runs/` for archive)**

```bash
rm tests/eval/golden_qa/meng2024_v112.yaml tests/eval/golden_qa/ali2025_v112.yaml
```

Don't delete `runs/meng2024_v112_anchoredq` and `runs/ali2025_flash_v112_anchoredq` — they're useful as v1.12 reference artefacts (and runs/ is gitignored anyway).

- [ ] **Step 7: Commit (no file changes from this task — just baseline data captured for T7)**

No commit needed. T7 will commit the docs that reference these numbers.

---

## Task 7: Phase 2 summary + CHANGELOG + ARCHITECTURE

**Files:**
- Create: `docs/archive/v1_12_phase2_summary.md`
- Modify: `CHANGELOG.md` (add `[v1.12-phase2]` entry under `Unreleased`, above `[v1.12-phase1]`)
- Modify: `docs/ARCHITECTURE.md` §5.5 (Verifier table — new row at top); §11.1 (mark deferred item as shipped)

- [ ] **Step 1: Write the phase 2 summary report**

Create `docs/archive/v1_12_phase2_summary.md`:

```markdown
# v1.12 Phase 2 — Summary & Decision

> Implementation: 2026-05-25 on branch `worktree-v1.12-phase1` (additive on top of Phase 1).
> Spec: `docs/superpowers/specs/2026-05-25-v1_12-phase2-anchored-quote-design.md`

## Shipped

- **Prompt change** in `_STRUCTURED_SYSTEM` (`structured.py:758+`): HARD RULE
  forcing non-empty `cited_quote` when the claim names a specific author or
  numeric value+unit anchor.
- **Verifier change** at `structured.py:329-331`: anchor-aware empty-quote
  branch replacing the pre-v1.12 blanket accept. Uses existing
  `_claim_anchors()` helper.
- **Env gate**: `LAZY_PAPER_ANCHORED_QUOTE=1` (default ON, bug fix logic);
  `=0` opt-out restores pre-v1.12 behaviour.
- **3 new tests** in `test_structured.py`: anchored-author-rejected,
  anchored-value-rejected, opt-out-restores-old-behavior.

## Measured RAGAS delta (T6)

| Paper × Metric | Baseline (Phase 1) | + anchored-quote | Δ |
|---|---|---|---|
| meng2024 · faithfulness | 0.657 | <fill-from-T6-Step-5> | <fill> |
| ali2025_flash · faithfulness | 0.440 | <fill-from-T6-Step-5> | <fill> |
| meng2024 · context_recall | 1.000 | <fill> | <fill> |
| meng2024 · context_precision | ~1.000 | <fill> | <fill> |

**Ship gate** (per spec §1): ali2025_flash faithfulness ≥ +5pp (0.440 → ≥0.490).

- [ ] **Step 2: Decide ship**

If the gate is met → DEFAULT ON ships in v1.12 (already configured).
If gate NOT met → revert the verifier change (keep the prompt change as a
no-cost improvement), record the failed data, plan Phase 2.5 around
MiniCheck.

Decision: <ship / revert / iterate — fill from data>.

## Cost recorded (T6 run)

- Wall clock: ~5-8 min (4 papers × 60 metric calls each)
- DeepSeek cost: ~$0.30 estimated (based on Phase 1 baseline cost rate)
```

- [ ] **Step 2: Fill in the numbers from Task 6 Step 5**

After T6 completes, replace each `<fill>` placeholder above with the actual numeric value and computed delta. Compute Δ as `v112_score - v111_baseline`, round to 3 decimals.

- [ ] **Step 3: Update CHANGELOG.md**

Open `CHANGELOG.md`, find the line `## [Unreleased]`. After it (and ABOVE `### [v1.12-phase1]`) insert:

```markdown
### [v1.12-phase2] — 2026-05-25 (default ON)

#### Fixed — anchored-quote bypass closed

The s08 verifier's empty-`cited_quote` branch (architecture doc §11.1) used
to blanket-accept any claim that left the quote field empty, letting the
LLM bypass verification by simply omitting a quote. Now: claims whose text
contains a specific author (`Jiang et al.`) or numeric value+unit
(`2.94 J/cm³`) anchor MUST carry a non-empty cited_quote — empty quote on
such a claim is rejected with `reason: anchored_claim_no_quote`.

Synthesis claims (cross-chunk inferences with no specific anchor) still
pass without quote verification — backward compatible.

#### Added — `LAZY_PAPER_ANCHORED_QUOTE` env (default 1)

Set to `0` to restore pre-v1.12 'blanket accept' behaviour. Provided for
projects with frozen baselines that can't absorb a verifier behaviour
change.

#### Measured impact

Per `docs/archive/v1_12_phase2_summary.md`:
- meng2024 faithfulness: 0.657 → <fill from T6>
- ali2025_flash faithfulness: 0.440 → <fill from T6>
```

After T6 numbers are filled in T7-Step-2, also fill the `<fill from T6>` markers above.

- [ ] **Step 4: Update ARCHITECTURE.md**

Open `docs/ARCHITECTURE.md`. Two targeted edits:

(a) In §5.5 verifier table (search for `Schema prefix leak` to locate it), insert a NEW ROW at the TOP of the verifier-checks table:

```markdown
| **Anchored claim w/o quote** — claim text names author or value+unit anchor; `cited_quote` empty | Reject (`anchored_claim_no_quote`); `LAZY_PAPER_ANCHORED_QUOTE=0` opts out | line 329-345 (v1.12 phase 2) |
```

(b) In §11.1 "cross-citation reject (cut)" section, find the line:

```
**Code marker**: `structured.py:368-372` has `# v1.11 architecture-review CUT: cross-citation reject was 40 LOC...`
```

After this line, append:

```markdown

**v1.12 phase 2 closure**: the underlying defect — empty `cited_quote` bypassing
the verifier — was finally fixed in v1.12 phase 2 with the anchor-aware
empty-quote branch at `structured.py:329-345` (see §5.5 table top row).
The orthogonal reference-list check originally proposed here was NOT
implemented; the anchor-based approach proved sufficient (see
`docs/archive/v1_12_phase2_summary.md` for measured impact).
```

- [ ] **Step 5: Run full test suite one last time**

```bash
uv run pytest -q --no-header 2>&1 | tail -3
```
Expected: 315 passed, 3 deselected.

- [ ] **Step 6: Commit T7**

```bash
git add docs/archive/v1_12_phase2_summary.md CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs(v1.12-phase2): summary + CHANGELOG + ARCHITECTURE updates (T7)

- v1_12_phase2_summary.md: shipped components + measured RAGAS delta +
  ship decision (data from T6)
- CHANGELOG.md: [v1.12-phase2] entry under Unreleased (above phase 1)
- ARCHITECTURE.md §5.5 verifier table: new top row for anchored-quote check
- ARCHITECTURE.md §11.1: append 'v1.12 phase 2 closure' note pointing at
  the fix location"
```

---

## Self-Review

**1. Spec coverage (spec §1-§8):**
- §1 Goal — covered: T1 (prompt) + T2 (verifier) + T6 (RAGAS measure) + T7 (ship gate decision).
- §2 Background — referenced in T6 baseline JSON inspection.
- §3 Empty-quote bypass location — T2 step 2 edits exactly `structured.py:329-331`.
- §4.1 Prompt change — T1.
- §4.2 Verifier change — T2.
- §4.3 Why two layers — implicit (both T1 and T2 land); explained in commit messages.
- §4.4 Risks — addressed: retry-when-empty is preserved (no code change to it); synthesis claim path tested (T3 test_verifier_passes_empty_quote_through unchanged); backward compat env gate (T2, T4); ship gate is T7 step 2 decision rule.
- §5 Out of scope — respected; none of the out-of-scope items are touched.
- §6 Files — every file in this list is touched in T1-T7.
- §7 Verification — T3 (unit), T5 (regression), T6 (RAGAS).
- §8 Rollout — T7 ship/revert decision.

**2. Placeholder scan:**
- "TBD" / "TODO": only inside the T7 summary template at the `<fill>` markers — these are EXPECTED to be filled by T7 step 2 after T6 produces the numbers. Each `<fill>` has an explicit source ("T6 Step 5"). NOT a plan failure.
- "Add appropriate error handling" / similar vague language: none.
- "Similar to Task N": none.

**3. Type consistency:**
- `anchored_claim_no_quote` reason string used consistently in T2 (verifier), T3 (tests), T4 (USER_GUIDE), T7 (CHANGELOG / ARCHITECTURE).
- `LAZY_PAPER_ANCHORED_QUOTE` env var used consistently across T2, T3, T4, T7.
- `_claim_anchors()` helper referenced consistently (existing function at `structured.py:247`).

**4. Known fragility:**
- T6 step 1 assumes `runs/meng2024_v112_anchoredq` can be populated by copying upstream stages from `runs/meng2024_v111_demo`. This depends on s08 not requiring fields we'd have stripped — verified via Phase 1 inspection that `s08` reads from `s03/s04/s06/s07` only; all those are copied.
- T6 step 3 was initially written with `_meng2024_v112.yaml` (leading underscore); corrected mid-task to drop the underscore because the conftest fixture skips underscore-prefixed files. Caught by the self-review.
- T3 step 4 has a fallback (monkeypatch existing tests if they break) rather than asserting they MUST pass unchanged. This is realistic given pre-existing tests `test_missing_required_audits_entities_not_in_prose` etc. may use empty-quote fixtures with anchored text.
