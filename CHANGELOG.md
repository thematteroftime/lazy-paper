# Changelog

All notable changes to lazy-paper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.11.1] — 2026-05-24

### Fixed — 4 HIGH bugs caught by cycle 11 sentence-level audit

v1.11.0 passed the architecture-review ship gate (hardcode scan, lang
threading, test count) but a follow-up precision audit (3 subagents
cross-checking output vs source paper) caught 4 HIGH issues that
surface-level checks missed. v1.11.0 was NOT pushed; v1.11.1 is the
first stable of the v1.11 line.

- **Bug #1+#2: Cross-chapter flagship-metric inconsistency**
  (`stages/s06_context/{kg_extract,runner}.py`,
  `llm/prompts/section_compose.md`). meng2024 ch07/09/13/15 emitted
  three different W_rec values for the same flagship sample because
  s08 was scavenging numbers from neighbouring comparator chunks. Fix:
  extract the flagship sample's `headline_metrics` from the KG
  (`mat_main --has_W_rec--> value`) and pipe them into `context.yaml`
  as a hard ground-truth block; prompt now instructs the composer to
  use those exact values for the flagship and never substitute
  comparator numbers.

- **Bug #3: Author misattribution in comparator citations**
  (`stages/s08_section_compose/structured.py`). meng2024 ch13
  attributed Ma et al.'s La(Mg1/2Zr1/2)O₃-doped-NBT result to Cao
  et al. (a real author on a different mechanism appearing in a
  neighbouring chunk). Fix: post-verify advisory check that flags any
  claim whose author-surname mentions don't appear in any cited chunk.
  Default mode is advisory (kept in `critic_flags.yaml` as
  `author_not_in_chunk_advisory`); set `LAZY_PAPER_AUTHOR_HARDREJECT=1`
  to promote to a hard rejection after telemetry confirms precision on
  your corpus.

- **Bug #4: OCR text-prompts analysed as physics figures**
  (`stages/s04_figures/runner.py`, `stages/s07_figure_analyze/runner.py`).
  hif_2 ch15 emitted a fabricated physics critique of "图 43", which
  was actually an unCLIP appendix figure whose OCR'd caption was the
  literal generation prompt `(a) A high quality photo of a dog playing
  in a green field next to a lake.`. Fix: two-layer caption-stub
  filter (`is_generation_prompt_caption`) drops `(letter) A/An
  <curated descriptor> <medium> of` patterns at s04 (and again at s07
  as defence-in-depth for older baselines). Tight regex with a curated
  descriptor list keeps real materials captions ("(a) SEM image of
  NBST", "(a) Cross-section TEM of grain") untouched.

### Added — bilingual regression prevention (cycle 11 Audit C)

- `cli.py` now writes the `lang` field to `meta.yaml` — auditors and
  demo scripts can grep for baseline language without re-reading
  every `fig_notes.yaml`.
- `s07_figure_analyze` emits a stderr WARNING when `lang=zh` is
  requested but the first 5 `visual_summary` entries are < 30 % CJK
  chars (catches vision LLMs that silently ignored the
  `lang_instruction` — root cause of the v1.10 baseline pollution
  that affected 7/15 papers).
- `s09_render/builder.py` localises the "Untitled" fallback chapter
  heading to "未命名章节" for `lang=zh`.

### Tests

300 collected (net +4 vs v1.11.0's 296): caption-stub filter ×2,
headline_metrics ×3, author-chunk advisory/hard/false-positive ×3,
Untitled localise ×1 (+11 new); 7 v1.10 variant-matrix tests removed
when the scaffolding script set was deleted (see Docs cleanup below).

### Docs cleanup (companion)

17 stage-validation docs (v1.4 → v1.9.2) archived to `docs/archive/`
and `docs_zh/archive/` (git history preserved). 5 stale v1.10 variant-
matrix scripts deleted (`aggregate_*`, `collect_variant_metrics`,
`recheck_baseline`, `run_variant_matrix`) + the paired test file —
no live callers remained. `docs_zh/ARCHITECTURE.md` (v1.8 era,
545 lines) deleted as superset-duplicate of `docs/ARCHITECTURE.md`
(already in simplified Chinese, 906+ lines); `docs_zh/README.md`
redirects. README + README.zh now include a real-data pipeline
walkthrough showing meng2024 stage-by-stage data flow (v110 vs v111
demos illustrate headline_metrics + caption-stub fixes).

## [1.10.0] — 2026-05-23

### Added — Variant C: figure_ids hard constraint (3-cycle audit-validated)

Picks the winner of the v1.10 variant test (3 variants × 9 papers + 2 HIF
extended corpus = 33 LLM runs across 3 git worktrees). Full report:
`docs/v1_10_variant_comparison.md`.

- **`GroundedClaim.figure_ids: list[str]`** — schema field tells s09
  binding which figures the claim cites. Default `[]` (back-compat).
- **`_STRUCTURED_SYSTEM` prompt** adds "Figure citation requirement"
  section: for every figure listed in section_figures, write one claim
  with `figure_ids=["Fig. N"]` and the literal "Fig. N"/"图N" in text.
- **`verify_section_draft` advisory** — when an accepted claim's
  figure_ids don't appear literally in the text, an advisory entry
  (reason=`figure_hint_unmet`) is recorded; the claim is still kept.
- **`compose_structured` figure-retry pass** — when section_figures
  non-empty AND >=50% of available figures aren't mentioned in the
  verified draft, one strengthened retry call adds them. Swap guards
  (parity with retry-when-short β#3): require strictly more figure
  mentions AND >=1 verifier-accepted claim AND required-mention
  coverage not regressed.
- **Env-gated whitelist** — `LAZY_PAPER_FIGURE_ID_WHITELIST=1` strips
  unknown fig_ids from accepted claims (default OFF since cycle 1+2
  evidence shows "unknown" fig_ids are usually s04_figures OCR-vs-
  paper-actual numbering misalignment, not LLM hallucination).
- **Audit log split** — `critic_flags.yaml` now distinguishes
  `verifier_rejected` (real quote misses) from `figure_advisories`
  (`figure_hint_unmet` + `figure_id_unknown`). Operators no longer
  misread an inflated reject count.

### Fixed — normalize_ocr_latex BS3+BS4 (cross-variant lift)

`stages/_common/normalize.py`: surface 2 new normalize passes to
collapse the verifier's false-reject backlog (~41-74 per s08 run
per Auditor 2 cycle 1 inventory):

- **BS3** — LaTeX escape sequences `\%`, `\&`, `\_`, `\^`, `\$`
  lose their leading backslash so they match the LLM's unescaped
  quote. Mirrors the existing `reviewer.py::_LATEX_NOISE` regex.
- **BS4** — Unicode super/subscript folding via `unicodedata.NFKD`:
  `³` → `3`, `₂` → `2`, etc., so `J/cm³` matches the LLM's `J/cm3`.
  Greek letters (α/β/π) explicitly NOT decomposed. NFKD doesn't
  fold U+2212 minus / U+2013 en-dash / U+2014 em-dash to ASCII `-`,
  so a separate `_UNICODE_DASH` regex follows the NFKD pass.

BS1+BS2 (letter-spaced subscript) deferred to v1.11 due to inherent
OCR↔LLM asymmetry that BS3+BS4 don't share.

### Validation

- **33 LLM runs** across 3 worktrees (7 corpus + 2 HIF × 3 variants;
  meng2024 ×3 each for variance probe).
- **M1 zero-variance probe** (meng2024 T1, spec §7 floor ≤ baseline
  stdev 1503): A=310, B=713, C=358 — all PASS.
- **M2 figure embed ratio** (true distinct-figures, not panels): C
  hits 100% on every multi-figure paper (ali2025 26/26, hif_1 20/20,
  hif_2 17/17, he2023 8/8, meng2024 7/7); A/B mostly 10-30%.
- **M4 TestCase scores**: C preserves baseline meng2024 T1 = 9/9/9
  (only variant to do so) AND breaks baseline on ali2025_flash T4
  (4 → 5). A introduces variance (5/9/9, stdev 1.88), B is worst
  (5/17/15, stdev 5.25).
- **3 audit cycles** (cycle 1 + cycle 2 + cycle 3 final ship gate)
  with 3 specialist auditors each — caught 5 bugs in variant C
  (all fixed) + identified normalize BS3+BS4 (shipped) + 7 v1.11
  candidates ranked by ROI.

### Side effects

- `M2_figures_embedded` metric in `scripts/collect_variant_metrics.py`
  now counts `<figure>` blocks (one per distinct fig) instead of
  `<img>` tags (multi-panel inflated). New `M2_figures_hallucinated`
  field surfaces s04↔LLM numbering misalignment (v1.11 #2).

### Test suite

273 passed, 2 deselected (was 255 in v1.9.2 — 18 new tests: 11
normalize + 7 figure-hard-constraint).

### Deferred to v1.11

- **#1** normalize_ocr_latex BS1+BS2 (letter-spaced subscript) — M
- **#2** s04_figures caption-aware numbering (fix the OCR-vs-paper
  numbering misalignment that produces "phantom" hallucinations) — M
- **#3** prompt comparator gap (Jiang/Ma et al. systemically missed;
  build_required_mentions should scan full paper text) — M
- **#4** template-vs-paper subject-mismatch graceful degrade — L
- **#5** Variant B redesign: dynamic cap = min(comparator_count, 10) — S
- **#6** real-time LLM cost meter into metrics.yaml (M6) — S
- **#7** DOCX HYPERLINK dead-code fix (thread sources into renderers) — M
- **#8** _merge_drafts 60-char prefix + (author,value) dedup — S
- **#9** 6 hardcodes → env vars (spec §11) — S

## [1.9.2] — 2026-05-22

### Fixed — bugs surfaced by 2-auditor + 3-reviewer + 2-confirmation cycle

Two parallel bug-auditor subagents identified 19 candidate issues; cross-
checking confirmed 8 high-impact ones plus several follow-ups exposed by
the subsequent 3-review + 2-confirmation cycle. The headline fixes:

- **C1**: `retry-when-short` was comparing against a stale `accepted`
  variable from before `retry-when-empty` rebound `verified`/`rejected`.
  Wrong-output potential. Now rebinds `accepted = retry_accepted` after
  the empty-retry swap. (`structured.py::compose_structured`)
- **C2**: `retry-when-short` could swap one fully-ungrounded draft for
  another when both had 0 verifier-accepted claims (`0 >= 0` passed).
  Now requires `len(retry_accepted) >= 1`.
- **H1**: `_find_chunk_for_entity_span` fallback-2 print crashed on
  `None` entity.text. Defensive `(entity.text or "")[:60]`.
- **H2**: `_evidence_quote` `pad_right` formula could go negative for
  spans longer than `max_chars - 30`, silently producing
  empty/garbage snippets via negative-index slicing. Rewrote to
  anchor a `max_chars` window from `pad_left`.
- **H3**: `_evidence_quote` fallback now documents the known cross-doc
  snippet/chunk mismatch (a real fix is queued for v1.10).
- **M1 + critical CLI fix**: `s09_render/runner.py` now defaults to
  `HYPERLINK` for HTML format (was REMOVE for all formats). `cli.py`
  also updated to pass `None` when `--debug-citations` is absent, so
  the per-format default actually reaches CLI users (was inert).
  Together these honor the HtmlRenderer docstring "clickable
  citations by default" for end users.
- **M2**: HtmlRenderer env_mode adds `.strip()` before `.lower()` so
  trailing whitespace from `.env` doesn't silently break override.
- **M3**: best-of-N exception-swallow now logs the failed sample
  (`stage] best-of-N sample N failed: ...; continuing with M draft(s)`).
  Previously a rate-limit on sample N silently dropped it.

### Added — discriminating HTML mode tests

`test_citation_render.py`:
- `test_html_remove_strips_markers` now asserts `<sup` absence (not
  just `[span:` absence), discriminating REMOVE from HYPERLINK.
- `test_html_hyperlink_emits_anchor_and_sources_footer` exercises the
  default-by-runner HYPERLINK path.
- `test_html_env_override_remove` verifies `LAZY_PAPER_HTML_CITATIONS=remove`
  overrides.

### Changed

- `pyproject.toml` version bumped from stale `1.4.0` to current `1.9.2`.

### Deferred to v1.10

- `α#3` control-chars in HTML `title` attribute
- `α#7` best-of-N temperature can exceed 1.0 at `N≥5`
- `α#9` paper_id regex edge case for `_v<digit>`-suffixed inputs
- `α#10` `_merge_drafts` empty-drafts defensive guard
- `β#5` `_FIG_TOKEN_RE` missing CJK Extension A/B
- `β#7` test coverage for `_evidence_quote` fallback +
  `_find_chunk_for_entity_span` fallback-2
- 6 retry-temperature / figure-top_k / claim-range hardcodes
- H3 real fix (return matched doc + patch source_span consistently)

Tests: 255/255 pass (+2 from new HTML mode tests).

## [1.9.1] — 2026-05-22

### Fixed — 3-review + 2-audit cycle on v1.9.0

10 audit findings applied:

- HtmlRenderer signature default REMOVE was silently overridden by
  env default HYPERLINK; rewrote precedence so caller intent is
  honored when env is unset. Parameter default also bumped to
  HYPERLINK to match docstring.
- HtmlRenderer two-pass render's `body = template.render(...)` dead
  variable removed.
- length-retry coverage guard now compares verifier-accepted counts
  (not post-fallback claim counts).
- `_evidence_quote` fallback added for KG `doc='paper'` placeholder
  case (searches entity text in source_docs).
- `_find_chunk_for_entity_span` fallback-2 now logs (was silent).
- `scripts/evaluate.py` paper_id regex relaxed to accept `_v\d+[a-z]+`
  suffixes (e.g. `_v190b`).

### Doc

- `LAZY_PAPER_FIGURE_BIND` added to HANDOFF env-vars table (EN + ZH).
- ARCHITECTURE.md anchor-check wording: "must contain otherwise rejected"
  → "advisory" (matches v1.8.3 code change).
- Test count `250 → 253` in 4 stale doc spots (HANDOFF section 5,
  AGENT_GUIDE×2 lines).
- `docs_zh/v1_9_validation_results.md` created (ZH counterpart).

## [1.9.0] — 2026-05-22

### Added — informed-retry diagnosis for missing required mentions

The retry-when-empty trigger now generates a **per-entity diagnosis**
listing every missing required mention with its specific anchor token
(author surname OR linked numeric value). This is the
informed-retry pattern from OpenScholar / LitLLM — the LLM gets a
precise, deterministic checklist of which entities + which tokens to
include in the next draft, rather than a generic "you missed some"
reminder.

Example diagnosis embedded in the retry system prompt:

```
## CRITICAL — SPECIFIC REQUIRED MENTIONS MISSING
Your previous draft covered 1/5 required entities. The following entities are
NOT yet covered — your next draft MUST include each, with the specific anchor
token shown:

  - **comparator**: 'Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3'
      → write a claim containing "Jiang et al." or "Jiang 等人" OR "W_rec=2.94 J/cm³"
      → evidence chunk: [3]
  - **comparator**: 'La(Mg1/2Zr1/2)O3-modified Bi0.5Na0.5TiO3'
      → write a claim containing "Ma et al." or "Ma 等人" OR "W_rec=7.5 J/cm³"
      ...
```

### Validation — variance eliminated on the headline benchmark

**meng2024 T1 ch01 benchmark recovery (3 runs each):**

| Version | scores | Mean | Stdev | Floor |
|---|---|---|---|---|
| v1.7 KL | 13 / 1 / 1 | 5.0 | 6.9 | 1 |
| v1.8.1 KL | 12 / 17 / 16 | 15.0 | 2.6 | 12 |
| v1.8.3 KL (single-runs) | 5 / 1 / 1 / 1 / 1 | 1.8 | 1.8 | 1 |
| **v1.9 KL** | **9 / 9 / 9** | **9.0** | **0** 🏆 | **9** |

Informed-retry produces deterministic 9/17 on meng2024 across three
independent runs. The LLM's behavior is now stable — variance is zero
on this test, and the floor (9) is well above v1.7 KL's failure mode
(1) and above v1.8.3's regression (1-5).

Note: 9/17 is below v1.8.1's 12-17 *peak*. The remaining gap is
addressed by a structural fix queued for v1.9.x: STORM/LitLLM-style
per-comparator drafting + stitch (research note in commit `41f9f09`).
That fix forces structural coverage (each comparator gets its own
micro-draft) rather than relying on prompt-level instructions, and
should push the mean back to 12+. But the deterministic-9 floor is a
real win as-is.

### 13-paper corpus validation

All other TestCases preserved or improved vs v1.8.3:

| Test case | v1.8.3 | v1.9 | Status |
|---|---|---|---|
| meng2024 ch01 T1 | 5/17 (single) | 9, 9, 9 / 17 | **deterministic floor** |
| meng2024 ch10 T3 | 3/5 | 3, 3, 5 / 5 | within variance |
| yang2025 T2 | 3/3 ✓ | 3/3 ✓ | preserved |
| fu2020 T5 | 3/4 ✓ | 3/4 ✓ | preserved |
| chai2026 T6 | 4/4 ✓ | 4/4 ✓ | preserved |
| ali2025_flash T4 | 4/5 ✓ | 4/5 ✓ | preserved |

8 papers without dedicated TestCases (pamula / gaur / ge / he / liu /
pan / randall / yao): all 15/15 chapters with substantive content,
HTML clickable citations working, retry-when-empty fires 2-13×
per paper.

### Behavior change

Existing `retry-when-empty` callers see no API change; the diagnosis
is internal to the retry prompt. Cost stays one retry per failing
section (no extra LLM calls beyond what v1.8.3 already did). The
diagnosis adds ~300-500 tokens to the retry prompt — DeepSeek input
caching makes this nearly free across the N best-of-N samples.

Tests: 253/253 pass.

## [1.8.3] — 2026-05-21

### Added — HTML clickable citations, length-based retry, anchor advisory

**HTML HYPERLINK mode by default.** HTML output now renders each
`[span:doc:start-end]` marker as a `<sup><a href="#cite-N">[N]</a></sup>`
anchor and appends a `<section id="sources">` footer listing every
unique citation. The v1.8.x verifier already validates every quote
against its source; HYPERLINK mode surfaces that effort to the reader
as a click-to-jump trust signal. Disable with `LAZY_PAPER_HTML_CITATIONS=remove`.

**Length-based retry trigger** (`compose_structured`). When the
verified section is shorter than `LAZY_PAPER_MIN_SECTION_CHARS`
(default 500) or has fewer than `LAZY_PAPER_MIN_SECTION_CLAIMS` (4)
claims, one strengthened retry fires asking for more substantive
content. The retry is **rejected** if its result loses required-mention
coverage relative to the original draft.

**Anchor advisory in verifier.** When a claim names a specific author
(`<X> et al.` / `X 等人`) or numeric value (W_rec, η, %, J/cm³, …), the
verifier checks whether the cited_quote contains that anchor. Failing
the check is logged as `anchor_missing` advisory in `critic_flags.yaml`
but no longer triggers rejection — an earlier enforcement variant
killed correctly-written claims whose only fault was the LLM picking a
poorly-aligned quote from the same chunk.

**Chunk-find fallback** in `_find_chunk_for_entity_span`. When the KG
LLM fills `source_span` with a placeholder doc name (e.g.
`doc='paper'`), the lookup now falls back to entity-text substring
match in retrieved chunks, then to the first retrieved chunk. Without
this, all required-mentions would resolve to None and Strategy KL
silently degrades to the legacy path.

**Default PPTX in `--formats`**: `DEFAULT_FORMATS = ('docx', 'pdf',
'html', 'pptx')` — aligns with the README hero claim "DOCX · PDF ·
HTML · PPTX". CLI help now reads "default: all four". PPTX still uses
extra LLM calls; pass `--formats docx,pdf,html` to skip.

**Two paraphrase-resistant signals in s08:**
- `_claim_anchors(text)` extracts `(author, value)` tuples used by both
  the verifier advisory and `_claim_dedup_key`.
- `_claim_dedup_key` collapses near-duplicate claims sharing the same
  anchor set during best-of-N merge, so paraphrases of the same fact
  don't both survive into the rendered prose.

### Validation note (honest)

Re-validated on meng2024 / ali2025_flash / pan2025 with v1.8.3 KL:

| Paper | v1.8.1 baseline | v1.8.3 | Change |
|---|---|---|---|
| ali2025_flash T4 | 4/5 (v1.7 baseline) | **4/5** | retry-when-short fires 4× → ch14 length 683 → 2106 chars |
| pan2025 ch01 (no specific test) | rich | rich, retry empty=3 / short=5 | qualitatively better |
| meng2024 T1 ch01 | **floor 12, mean 15** (3 runs) | **5/17** (single run) | **partial regression** |
| meng2024 T3 ch10 | 5/3/2 (mean 3.3) | 3/5 | within variance |

The meng2024 T1 regression is the headline caveat: across five v1.8.3
iterations of the meng2024 paper, T1 ranged 1–5 (vs 12–17 in v1.8.1).
Root cause is **LLM sampling selectivity** — the LLM consistently
writes about the paper's own material instead of citing all four
literature comparators (Jiang/Ma/Zhang/Tang). The retry-when-empty
mechanism correctly fires (5× in the final run) but doesn't restore
all comparators. We chose to ship v1.8.3 because:

1. The ali2025_flash 0→4/5 win is real and reproducible.
2. The HTML clickable citations and chunk-find fallback are
   independent improvements that don't depend on the regression.
3. The fallback for KG `doc='paper'` placeholders fixes a previously
   undiagnosed silent degradation.
4. meng2024 T1 has always had wide variance — single-run regression
   may not reflect mean-of-N behavior; the v1.9 roadmap should run
   a 3-run mean before declaring final.

### Removed

- `llm/prompts/paper_kg_v2.md` (deprecated since v1.7; no documented
  use in shipping configs).
- `llm/citation/stream_processor.py` (630 LOC vendored from Onyx in
  v1.4 but never wired up; design is preserved in
  `llm/citation/__init__.py::process_text`, and attribution stays in
  `THIRD_PARTY_NOTICES.md`).

### Doc cleanup

- `docs/AGENT_GUIDE.md` + `docs_zh/AGENT_GUIDE.md`: removed
  "Already fixed in v1.1" / "In v1.3.4..." / "In v1.4.0..."
  log-style narrations; section titles now describe current behavior
  rather than version history.
- `docs/ARCHITECTURE.md` + `docs_zh/ARCHITECTURE.md` s08 section:
  three parallel subsections (KG sub-step / Strategy KL / legacy
  fallback) consolidated into two ("default path" / "legacy
  fallback").
- `docs/INTERNAL/HANDOFF.md` + `docs_zh/INTERNAL/HANDOFF.md`:
  "Verified state (as of v1.1.0)" replaced with the current 13-paper
  v1.8.2 corpus table; new env-var rows for
  `LAZY_PAPER_MIN_SECTION_CHARS`, `LAZY_PAPER_MIN_SECTION_CLAIMS`,
  `LAZY_PAPER_HTML_CITATIONS`, `LAZY_PAPER_FIGURE_BIND`.
- `docs/v1_7_validation_results.md`: superseded banner pointing
  forward to v1.8 reports.

Tests: 253/253 pass (up from 250; +3 covering length-retry and
figure-relevance).

## [1.8.2] — 2026-05-21

### Fixed — security + flow hardening (driven by 3-subagent audit)

A redundancy / security / hardcodes triple-audit surfaced fixable
issues. v1.8.2 ships the must-fix subset; speculative refactors are
deferred to v1.9.

**Security:**
- **HIGH — `--paper-id` path traversal** (`cli.py:234`): now always
  slugifies the user value, defending against `--paper-id
  "../../tmp/x"` writing outside `runs/`.
- **MEDIUM — zip-slip in MinerU extractor** (`stages/s01_ocr/mineru.py`):
  validates each `ZipInfo.filename` against `dest.resolve()` and
  refuses absolute paths or `..` segments.
- **LOW — error message redaction**: PaddleOCR HTTP errors no longer
  echo the response body (`r.text`) which can include upstream
  gateway headers; s09 render failures persist
  `type(exc).__name__ + str(exc)[:200]` instead of full `repr(exc)`.

**Flow:**
- **PaddleOCR infinite poll**: added `PADDLEOCR_TIMEOUT_S` deadline
  (default 1800s). The previous loop had no timeout and could hang
  forever on a stuck job.
- **Silent exception swallows removed** in `stages/s08_section_compose/runner.py::_build_retrieval_query` and `stages/s09_render/runner.py::PaperContext.__init__`. Both now log + fall back gracefully.

**Maintainability:**
- Shared `stages/_common/normalize.py` consolidates the OCR/LaTeX
  text normalizer that v1.8.1 introduced in `structured.py`.
- Dead `coverage_summary()` deleted from `stages/s08_section_compose/coverage.py`.
- `stages/s06_context/kg_extract.py` docstring now points at
  `paper_kg_v3.md` (the v1.7+ recommended prompt) instead of the
  removed `paper_kg_v2.md`.

### Added — env-overridable OCR knobs

| Variable | Default | Purpose |
|---|---|---|
| `MINERU_BASE_URL` | `https://mineru.net/api/v4` | self-hosted/proxied MinerU |
| `MINERU_TIMEOUT_S` | `1800` | hard deadline for MinerU poll |
| `MINERU_POLL_S` | `10` | poll interval |
| `PADDLEOCR_BASE_URL` | `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs` | self-hosted Paddle |
| `PADDLEOCR_MODEL` | `PaddleOCR-VL-1.5` | pin model version |
| `PADDLEOCR_TIMEOUT_S` | `1800` | hard deadline for Paddle poll |
| `PADDLEOCR_POLL_S` | `5` | poll interval |

### Validated — 10-paper corpus

Full coverage across 10 papers (5 with TestCases + 5 generic
pipeline-success). All 10 produced 15/15 chapters with substantive
output. The v1.8.1 retry-when-empty mechanism fires on 4 of the 9
newly-validated papers, confirming it's load-bearing.

The single outlier (ali2025_flash ch14 = 0/5) is analyzed in
`docs/v1_8_2_corpus_validation.md` as LLM sampling variance, not a
regression — v1.7 KL also varied widely on long survey sections.

### Architecture diagrams

`docs/ARCHITECTURE.md` now includes:
- **Pipeline data flow** (Mermaid flowchart, color-coded by stage class).
- **Strategy KL compose flow** (the v1.8.1 verifier + retry pipeline,
  including the 4-tier quote match).

Test count: 250/250 passing (unchanged).

## [1.8.1] — 2026-05-21

### Fixed — KL stability win (mean 5.0 → 15.0 on meng2024)

v1.7 KL's variance came from two interacting compose-side bugs:

1. **Verifier was killing good claims.** Source PDFs OCR W_rec values as
   LaTeX-form `$W _ { \mathrm { rec } }$`. The LLM correctly quoted the
   chunk, but substring-match against the raw LaTeX form lost ~50% of
   characters to whitespace differences. The verifier rejected the
   claims that actually cited Jiang/Ma/Zhang/Tang comparators.
2. **Retry-when-empty fired on pre-verify coverage.** The diagnostic
   measured "did the LLM mention this entity" *before* the verifier
   filtered. Coverage looked fine (~80%) so retry never triggered —
   then the verifier dropped the comparator-citing claims and the
   final prose was generic. Floor stayed at 1/17.

Fixes in `stages/s08_section_compose/structured.py`:

- `_normalize_for_match` strips LaTeX commands and collapses OCR
  digit-spacing (`5 . 0 0` → `5.00`) on both sides of the substring
  check. Catches the `$W _ { \mathrm`-vs-`$W_{\mathrm` divergence
  cleanly.
- `verify_section_draft` adds a chunk-ID slop fallback: if quote
  doesn't match the cited chunk, scan ALL retrieved chunks. When a
  match is found, the claim's `cited_chunk_ids` is patched.
- `compose_structured` computes coverage **post-verify** and retries
  with a strengthened prompt when `post_cov ≤ retry_threshold`.

**T1 meng2024 ch01 benchmark recovery (3 runs):**
mean **15.0 / 17**, stdev **2.6**, range **12 – 17**, floor **12**.

Compare:

| Strategy | Mean | Stdev | Range | Floor |
|---|---|---|---|---|
| **v1.8.1 KL** | **15.0** | **2.6** | **12 – 17** | **12** |
| v1.7 KL | 5.0 | 6.9 | 1 – 13 | 1 |
| v1.7 J | 6.3 | 1.5 | 5 – 8 | 5 |
| v1.3.3 baseline | ~12 | — | — | — |

All non-meng test cases preserved (no regressions):

| Test case | v1.8.1 KL score |
|---|---|
| T2 yang2025 ch01 fabrication resistance | 3/3 ✓ |
| T5 fu2020 ch01 basic | 3/4 ✓ |
| T6 chai2026 ch01 basic | 4/4 ✓ |

### Added — env-overridable verifier and retry thresholds

- `LAZY_PAPER_VERIFIER_THRESHOLD` (default 0.85) — minimum quote-vs-chunk
  match score for a claim to survive. Lower for paraphrase tolerance.
- `LAZY_PAPER_RETRY_THRESHOLD` (default 0.5) — post-verify coverage at
  or below which one strengthened retry call fires. Set higher for
  stricter coverage at higher LLM cost; set to 0 to disable retries.

Full validation analysis: `docs/v1_8_validation_results.md`.

## [1.7.0] — 2026-05-21

### Added — Strategy K (best-of-N merge) + Strategy L (KG-v3 author extraction)

Two new env-gated strategies. KL (their combination) **occasionally hits
13/17** on the meng2024 benchmark-recovery test — matching v1.3.3's
unconstrained-context baseline. But variance across runs is wide:

**T1 (meng2024 ch01 benchmark recovery, 3 KL runs):**
mean **5.0/17**, stdev **6.9**, range **1 – 13**.

Compare to **J (3 prior runs)**: mean **6.3/16**, stdev **1.5**, range **5 – 8**.

**KL is NOT the new default — J remains the better default.** KL ships
as opt-in (`LAZY_PAPER_BEST_OF_N=2 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md`)
for users who want to roll for occasional 13/17 outputs.

Full validation per-paper:

| Test case | KL score |
|---|---|
| T1 meng2024 ch01 (3 runs) | 13 / 1 / 1 (mean 5.0) |
| T2 yang2025 ch01 fabrication resistance | 3/3 ✓ |
| T3 meng2024 ch10 synthesis specificity (3 runs) | 2 / 3 / 4 (mean 3.0) ⚠ |
| T4 ali2025_flash ch14 comparison depth | 4/5 |
| T5 fu2020 ch01 basic | 3/4 |
| T6 chai2026 ch01 basic | 4/4 ✓ |

See `docs/v1_7_validation_results.md` for full analysis + v1.8 candidates
to address KL's high-variance floor.

Enable in production:

```bash
LAZY_PAPER_STRUCTURED=1 \
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
LAZY_PAPER_BEST_OF_N=2 \
uv run python -m cli run ...
```

### Strategy K — best-of-N merge

`LAZY_PAPER_BEST_OF_N=N` runs structured compose N times at temperatures
0.2, 0.35, 0.5, ... and union-merges via round-robin interleave; dedupe
on claim-text prefix (120 chars) only — two claims citing the same chunk
with different prose both survive. Caps at SectionDraft.claims max (14).
DeepSeek input caching keeps the chunk-list overhead almost free across
the N calls.

### Strategy L — KG-v3 + author extraction

`LAZY_PAPER_KG_PROMPT=paper_kg_v3.md` extends the closed entity schema
with `author` as the 11th type. The prompt requires every cited
`comparator` to also yield a first-author surname `author` entity
linked via `cited_by_paper`. `RequiredMention.author_text` surfaces
this to compose, which now asks the LLM to introduce comparators in
"X et al." form rather than bare chemical formulas.

`llm/paper_kg.py:EntityType` extended to include "author" (backward
compatible — v1/v2 parquets just won't have any author entities).

### Added — `scripts/evaluate.py` test harness

Replaces ad-hoc grep with 4 explicit `TestCase` definitions:
- T1 benchmark recovery (meng2024 ch01, 17 pts)
- T2 fabrication resistance (yang2025 ch01, 3 pts)
- T3 synthesis specificity (meng2024 ch10, 5 pts)
- T4 comparison depth (ali2025_flash ch14, 5 pts)

Plus citation-accuracy scorer (when `structured.json` present) via
fuzzy quote-match against chunk text, source-normalized for OCR
digit-spacing and LaTeX escapes. Markdown table to stderr; JSON to
stdout. Auto-detects paper id from run-dir suffix.

### Added — `docs/TEST_FRAMEWORK.md`

286-line manual: harness usage, scoring rules, current strategy
scorecards, recommended workflow for shipping a new strategy.

### Changed
- `_CHUNK_LEAK` regex now strips bare bracket form `[2,5]` / `[0,3]`
  in addition to `(chunk N)` parenthesis form (K's live run leaked
  the bracket form — LLM inlined the chunk-ID list literally).

### Known limitations
- KL regresses on T3 (meng2024 ch10 synthesis 4→2). Required-mentions
  list emphasizes survey-section citations, which crowds out
  synthesis-detail prose. Synthesis was never the headline defect —
  not blocking. v1.8 candidate: section-type-aware required-mentions
  caps.
- Strategy K alone (without L) scored 1/17 on T1 — both runs avoided
  bare chemical-formula comparators. K provides value ONLY when
  combined with L's author entities.

### Files added
- `llm/prompts/paper_kg_v3.md` (~40 LOC)
- `scripts/evaluate.py` (~420 LOC)
- `docs/TEST_FRAMEWORK.md` (~286 LOC)

## [1.6.0] — 2026-05-20

### Added — Strategy J (Perplexity pre-injection + Onyx rendering)

Env-gated by `LAZY_PAPER_STRUCTURED=1`. The strongest grounding pipeline
shipped so far. On meng2024 ch01 it lifts the "Jiang/Ma/Zhang/Tang
competitor literature benchmark" recovery from **0/16** (v1.4.2 default)
or **4.5/16** (v1.5 Strategy E mean) to **6.33/16** mean across 3 runs
(range 5–8). Floor lifted from 3 → 5.

Architecture (see `docs/v1_6_strategy_j_design.md` for details):
- **Pre-injection (Perplexity-style):** retrieved chunks pre-labeled
  with 0-based IDs in the USER message; a `field_validator` on
  `cited_chunk_ids` rejects any ID not in the retrieved set at
  Pydantic parse time. The LLM cannot hallucinate a citation that
  wasn't in its context.
- **instructor + Pydantic strict mode** (`Mode.MD_JSON` for DeepSeek
  R1 reasoning compatibility). One LLM call per section returns a
  `SectionDraft` with a list of `GroundedClaim` objects.
- **Required-mentions list (KG-v2 + coverage):** for survey-style
  sections (Introduction / Comparison / Discussion / etc.) the top-5
  most-distinctive comparator + claim entities from the KG are
  injected as a "Required mentions" block telling the LLM these are
  facts the section MUST cite. Soft-warn audit (`structured_audit`
  flag in `critic_flags.yaml`) when the final draft fails to cite any.
- **Verifier gate (ClarityArc-style):** each `cited_quote` is fuzzy-
  matched against its declared chunk via longest-contiguous-match
  ratio ≥ 0.85 (exact-substring → 1.0). Quotes that don't match are
  rejected post-hoc; if too many reject, the draft falls back to the
  unverified original (soft-degrade).
- **Onyx-vendored rendering** stays the same; `SectionDraft.render(mode=REMOVE|KEEP|HYPERLINK)`
  assembles claims into prose with optional `[span:doc:start-end]`
  markers.
- **Regex critic skipped when J ran:** the verifier gate already
  validates grounding. Running the LaTeX-blind regex critic on top
  was destroying J's structured numeric content (it false-flagged
  `2.94 J/cm³` because source has it as `$2 . 9 4 \mathrm{J/cm}^{3}$`,
  and the LLM revisor "fixed" by deleting). Critic now gated on
  `not structured_used`.

### Changed
- KG extraction `max_tokens` raised 16000 → 32000 (v2 prompt
  extracts ~2× more entities than v1; instructor's
  `IncompleteOutputException` was firing more frequently).

### Files added
- `stages/s08_section_compose/structured.py` (315 LOC) —
  `GroundedClaim`, `SectionDraft`, `RequiredMention`,
  `compose_structured()`, `verify_section_draft()`,
  `build_required_mentions()`, `select_top_required()`,
  `missing_required()`.
- `stages/s08_section_compose/tests/test_structured.py` (220 LOC) —
  13 unit tests (validator, verifier, builder, top-N, mocked compose).

### Notes
- Mean still below v1.3.3's 13/16 (the unconstrained-context-stuffing
  baseline). Each J run picks 2-3 of the 4 comparators, with different
  subsets each run. Union of 3 runs covers all 4. v1.7 candidate
  "best-of-N + merge" could close this gap.
- The author names ("Jiang", "Ma", "Zhang", "Tang") still don't appear;
  the LLM consistently uses the chemical formulas + values pattern
  instead. To recover author attribution, KG-v3 prompt would need to
  extract `author` as a separate entity type linked to comparator.

## [1.4.2] — 2026-05-20

### Changed
- **Expanded retrieval is now the default** for s08 section composition.
  The retrieval query is built from `section title + guidance + KG-scoped
  entity texts + keywords` rather than just `guidance`; `top_k` is 15
  (was 8); the excerpt context cap is 25K chars (was 15K). In a 4-way
  meng2024 A/B test this produced the largest, most complete chapters
  (avg 1932 bytes vs the v1.4.1 default's 1791) with the fewest critic
  flags (1 vs 3). `LAZY_PAPER_QUERY_EXPAND=1` is no longer needed — and
  no longer recognized.

### Added (env-gated, experimental)
- **`LAZY_PAPER_COVERAGE=1`** — per-section KG entity coverage check.
  `stages/s08_section_compose/coverage.py` scopes the KG to entities
  whose tokens overlap the section title/guidance, then flags
  in-scope entities missing from the draft (`entity_coverage_missing`
  Flag problem). The LLM critic revises to bring them back. Useful
  scaffolding for v1.5 once the KG extractor is taught to harvest
  competitor literature benchmarks (see `docs/v1_5_test_cases.md`).
- **`LAZY_PAPER_TWO_STEP=1`** — experimental outline → expand pipeline.
  Step 1: instructor → `SectionOutline` Pydantic. Step 2: expand each
  outline point with its pinned chunks. **Currently regresses chapter
  size** on meng2024 (avg dropped 1791→1259) because the per-point
  char budget is treated as a ceiling. Kept in tree for further
  development; do not enable in production.

### Documented
- `docs/v1_5_test_cases.md` — research scenarios for the three known
  regressions that no current strategy fixes: competitor-literature
  recovery (Jiang/Ma/Zhang/Tang in meng2024 ch01), cross-chapter
  numeric drift (meng2024 ch06 `5.1` vs ch10 `5.00`), depth loss on
  comparison sections (ali2025_flash ch14). Each scenario names the
  root cause and the candidate strategy (D section-aware queries,
  E richer KG extraction, F whole-paper coherence pass).

## [1.4.1] — 2026-05-20

### Added
- **Cross-section findings memory**: s08 prompt now includes a `{prior_findings}` block listing first-sentence summaries of the last 8 composed sections, with a "do not restate verbatim — refer back, build on, or contrast" instruction. Eliminates cross-chapter content overlap (e.g., the chemical-formula repetition observed in meng2024 v1.4.0 across ch01/ch03/ch10).
- **Language-guard retry**: composer post-checks the zh-character ratio of each section; when `--lang zh` was requested but the draft is < 30% Chinese and > 100 chars (LLM defaulted to source-paper language), it retries once with a hard "OUTPUT MUST BE WRITTEN IN CHINESE" system-prompt amendment.

### Validated
- meng2024 v1.4.1 vs v1.4.0: 30-char cross-chapter overlap dropped 35 → 4 windows (no 3-chapter overlaps remain); ch05 Chinese ratio 0% → 62.5%.

## [1.4.0] — 2026-05-20

### Added
- Reviewer LLM tier (`instructor` + `CritiqueRevision`) with dimensional scoring; revises drafts when regex flags appear, soft-accepts when revision fails.
- Vendored Onyx `citation_processor.py` (MIT) at `llm/citation/stream_processor.py`; see `THIRD_PARTY_NOTICES.md`.
- Citation rendering in DOCX + HTML with 3 modes (HYPERLINK / KEEP / REMOVE).
- `--debug-citations` CLI flag exposes `[span:...]` markers.
- `findings.yaml` per-paper memory (write-only stub for v1.5).
- Embeddings role inherits `LLM_VISION_*` credentials when `LLM_EMBEDDINGS_*` is absent (DashScope shares its endpoint).
- Section composer agent (`pydantic-ai-slim`) with 4 tools (`query_kg`, `retrieve`, `check_source`, `emit_section`) — **experimental, gated behind `LAZY_PAPER_AGENT=1`**.

### Changed
- s08 default path: retriever-fed prompt-stuffed compose → regex critic → LLM revise (when flagged) → write. The agent loop is kept in-tree but gated; live runs showed it occasionally emitting meta-commentary, so the retriever upgrade alone delivers the content win.
- Reviewer regex: compound units (`°C/s`, `K/s`) no longer false-match bare `°C`/`K`; OCR digit-spacing (`0 . 0 3 6`) and LaTeX escapes (`\%`, `\$`) normalized before search.
- KG extraction `max_tokens` raised from 8000 to 16000 (avoids `instructor.IncompleteOutputException` on dense-content papers).
- s08 `done.yaml` `agent` field reports `enabled`/`disabled` based on the env opt-in instead of always reading `ok`.

### Validated
- 13-paper corpus (3 known-defect + 10 random): 0 pipeline crashes, 195/195 sections, 13/13 KG ok, 13/13 retriever ok, 13/13 renders. 29 critic-flagged instances across all papers — all verified as real LLM numeric drift, not false positives.
- Known v1.3 defects fixed: yang2025 no longer fabricates `Wrec=8.6 J/cm³ at η=85%`; meng2024 ch10 now captures `tape-casting` and adds source-grounded grain-size data.

### Compatibility
- Hard cutover; rollback = `git checkout v1.3.4` or `v1.3.3`.
- PaperDB artifacts in `runs/<paper>/` are forward-compatible with v1.3.4.

## [1.3.4] — 2026-05-20

### Added
- PaperKG extraction in s06_context (10-type closed schema via `instructor`).
- Hybrid retriever (llama-index chunking + bm25s sparse + DashScope dense + RRF) in `llm/retriever.py`.
- Reviewer regex tier (`stages/s08_section_compose/reviewer.py`) — observe-only, writes `critic_flags.yaml`.
- `LLM_EMBEDDINGS_*` env vars (default DashScope `text-embedding-3-small`).

### Changed
- s08 evidence source: keyword-scored excerpts → top-8 hybrid retrieval (with KG entity-span boost).
- s08 `done.yaml` now records `retriever`, `kg`, `flagged_sections`.

### Compatibility
- Soft-degrade on every new sub-step. Setting `LLM_EMBEDDINGS_API_KEY=` blank reverts s08 to v1.3.3 keyword behavior.
- Rollback: `git checkout v1.3.3`.

## [1.3.3] - 2026-05-20

Section-divider layout becomes truly dynamic. v1.3.2 prevented over-truncation
but used uniform `row_h = usable_h / n_bullets`, which produced uneven visual
spacing when bullets had different wrap counts (1-line bullets had empty
space below; 2-line bullets crammed against the next). v1.3.3 measures each
bullet's needed height, places them with a constant inter-bullet gap, and
stretches the card height when content needs it — fonts shrink only as last
resort.

### Fixed — layout

- **Uneven bullet spacing in KEY POINTS card**: per-bullet height is now
  computed from estimated wrap count (chars / chars_per_line) with a
  proper empirical formula (~95 chars/line at 13pt × 6.35" wide).
  Bullets place cumulatively with a constant 0.18" gap, so visual spacing
  is even regardless of how many lines each bullet wraps to.
- **Card auto-stretches** from default 4.5" up to 5.4" (card_top..6.9")
  when content exceeds the default. Only after the stretched card still
  overflows does the algorithm compress inter-gap (down to 0.05") and
  finally shrink font as absolute last resort.
- **Blank-looking figure slide on `ali2025_flash` Fig. 28**: s07 vision-LLM
  output failed YAML defensive-parse (stray LaTeX), and the slide planner
  consumed `deep_observation=None`, leaving the left obs pane and caption
  header empty. `_read_fig_notes` now recovers `caption`,
  `deep_observation`, and `visual_summary` from the persisted `raw` text
  via regex when YAML parse failed.

### Added — planning

- `docs/v1_4_roadmap.md` — captures top 3 content-fidelity issues
  (template-driven hallucination, quoted-symbol drift, missed source
  facts) + top 3 pipeline-architecture improvements (per-section cache,
  T3 in s08, s07→s08 claim-consistency) found by two parallel read-only
  subagent audits. Will drive v1.4.0.

### Verified

- 10-paper s09 refresh (cache hits on most chapter LLMs; ali2025_flash and
  pamula2025 hit fresh cache after `_read_fig_notes` recovery changed
  inputs). All 4 formats produced.
- Audit: 3 total flags across 10 papers — all 3 are figure caption
  headers carrying English original titles on ZH-content slides
  (legitimate, not a defect).
- Truncation rate steady at 2.9% (was 42% pre-v1.3.2).
- Visual review of pamula2025 §4 (7 bullets, dynamic spacing, card
  stretched to fit), ali2025_flash Fig. 28 (caption + 3 obs recovered
  from raw, no longer blank), yang2025 §2 (consistent inter-bullet gap).

### Tests

189 passing (unchanged).

## [1.3.2] - 2026-05-20

Whitespace-vs-truncate audit. v1.3.1 left 42% of section-divider bullets ending
with `…` while substantial vertical whitespace remained on the card. v1.3.2
flips the trade-off — prefer **wrap to 2-3 lines** over single-line truncation.

### Changed

- `_BULLET_CAP_TABLE` recalibrated for every density to enable multi-line wrap.
  Each density's per-bullet box has > 2 line-heights of room; caps are now sized
  to ≈ 2-3 wrapped lines rather than 1:

  | n_bullets | font | row_h | old (CJK/ASCII) | new (CJK/ASCII) |
  |---|---|---|---|---|
  | 1 | 16pt | 3.40" | n/a (no key) | (150, 300) — up to 4 lines |
  | 2 | 16pt | 1.70" | n/a | (115, 225) |
  | 3 | 16pt | 1.13" | (60, 110) | (100, 200) |
  | 4 | 16pt | 0.85" | (60, 110) | (80, 150) |
  | 5 | 15pt | 0.68" | (55, 100) | (80, 160) |
  | 6 | 14pt | 0.57" | (50, 90)  | (90, 180) |
  | 7 | 13pt | 0.49" | (50, 95)  | (95, 190) |

- `_split_full_obs` `max_chars` now defaults proportionally to target (target=1
  → 500 chars; target=2 → 320; target=3 → 220). Single-observation figure
  slides now carry full s07 vision-LLM analysis instead of being clipped.

### Verified

- **Section-divider ellipsis rate dropped from 42% → 2.9%** (15 of 521 bullets
  across the 10-paper corpus). The remaining 15 truncations are legitimate
  overflows beyond the 2-line-wrap budget.
- Visual review of yang2025 §2 (7 bullets, all wrap to 2 lines, no ellipsis,
  no whitespace), fu2020 §1.1 combined slide (4 full bullets + 3 full obs),
  meng2024, chai2026 confirms wrap behavior is clean.

### Tests

189 passing (unchanged). 4 tests updated to reflect new cap table:
`test_bullet_caps_table_progression`, `test_truncate_bullet_dense_card`,
`test_section_divider_bullets_are_length_capped`,
`test_bug5_dense_bullet_cap_loosened`.

## [1.3.1] - 2026-05-20

Hardening release based on a per-slide audit of the v1.3.0 output across an
expanded 10-paper corpus. Eight defects classified into three families:

### Fixed — layout

- **`_combined` slide observations bled into wrapped bullets.** Bullets are now
  capped via `SlidePlanner._truncate_bullet(b, n_bullets)` so each fits one
  line; observations land below their allocated row.
- **Sparse KEY POINTS cards (≤5 bullets) silently truncated mid-formula** when
  LibreOffice interpreted `TEXT_TO_FIT_SHAPE` as clip-to-fit. Autofit is now
  applied only for dense (≥6 bullet) cards.
- **Single-observation figure slides wasted 80% of vertical space.** Density-
  adaptive font + row height: n=1 → 15pt/1.40", n=2 → 14pt/0.95", n=3 →
  13pt/0.70" (or 12pt/0.60" when crowded).
- **Figure caption header truncated at 50/55 chars mid-formula.** Raised to
  110/120 chars — the header box is 12" wide and easily fits.
- **7-bullet KEY POINTS cap loosened** from (45 CJK / 80 ASCII) to
  (50 / 95) — the previous cap was clipping XPS lists and similar.

### Fixed — content depth

- **T3 quant validator was rejecting 80%+ of EN chapter summaries** because
  conceptual chapters legitimately lack numeric anchors. The summarizer now
  soft-accepts the last shape-valid payload (still logs the strict-validation
  failure to stderr) — better to ship a complete-shape PPT than fall back to
  the rule-based 60-char paragraph snippet for most slides.
- **Priority-3 rule-based fallback used a hardcoded `[:60]` cut** that produced
  mid-word fragments like "probed by a co". The bullet now flows through
  `_truncate_bullet` like any other source, with ellipsis on overflow.
- **`pptx_summarize.md` had no `{lang_directive}`** — chapter summarizer
  occasionally produced Chinese bullets for `--lang en` papers when the
  context.yaml or first-chapter LLM bias leaked through. Added the same
  authoritative language directive that outline + paper-summary use.
  `_CHAPTER_PROMPT_VERSION` bumped v13-quant-validation →
  v13.1-lang-directive (caches auto-invalidate).
- **Figure observations fallback truncated full deep_observation at 200 chars**
  in `slide_planner.py:236/258` — discarded 70% of the s07 vision-LLM
  analysis. Replaced with `_split_full_obs(text, target=3)` that sentence-
  splits the full text into 2-3 chunks of ≤220 chars each.

### Fixed — font / rendering

- **Exotic Unicode punctuation rendered as boxes** (U+2011 non-breaking hyphen,
  U+202F narrow no-break space, U+200B zero-width space, …). The default PPT
  body fonts (Crimson Pro / Songti) lack glyphs for these. `normalize_math()`
  now maps them to ASCII equivalents via `_EXOTIC_PUNCT_FALLBACK`.
- **`_extract_group_preview_bullets` bypassed `normalize_math`**, so section-
  divider KEY POINTS bullets retained exotic Unicode. Now routes through
  `normalize_math` before truncation.

### Added — tooling

- `scripts/audit_pptx.py`: scans a rendered PPTX for layout/content defects
  (exotic codepoints, language drift, mid-formula truncation, empty
  paragraphs). Used as the per-slide validator before push.

### Tests

189 passing (+11 vs v1.3.0).

### Verified

10-paper corpus (4 existing + 6 new non-thin-film: fu2020 / ge2025 /
chai2026 / pamula2025 / meng2024 / gaur2022) — full pipeline OCR + LLM +
4-format render. Per-slide audit shows zero exotic-Unicode and zero
language-drift after the s09 v13.1 refresh.

## [1.3.0] - 2026-05-19

Quality release. Audit-driven LLM-output enforcement, adaptive PPT layout, deeper analytical context for the chapter composer, README design overhaul.

### Added — generation-depth enforcement

- **Quantitative content validator** (`pptx_summarizer.py`). Every chapter bullet must carry ≥1 numeric anchor (`%`, `J/cm³`, `kV/cm`, `°C`, etc.); paper-summary requires ≥3 quantitative bullets + a comparative/quantitative takeaway. Non-conforming responses trigger LLM retry. `_CHAPTER_PROMPT_VERSION` → `v13-quant-validation`, `_PAPER_PROMPT_VERSION` → `v13-quant-validation` (caches auto-invalidate).
- **Critique-vs-description guard** on figure observations. Rejects payloads where ALL observations for a figure use only descriptive verbs (`shows`, `depicts`, `illustrates`) without any critique marker (`limitation`, `missing`, `should`, `alternative`, `unclear`, …). Soft retry once.
- **Loud failure logging**. `summarize_outline`, `summarize`, and `summarize_paper` now emit a one-line `[pptx_summarizer] <method> failed for <label> after 3 retries: <ErrType>: <message>` to stderr when they exhaust retries. Was silent `return None` before — slides went out half-built without surfacing the cause.

### Added — analytical context

- s08 figure-observation truncation 100 → **400 chars**; caption truncation 120 → **300 chars**. Chapters can now cite specific caveats and numeric anchors from the vision-LLM analysis instead of paraphrasing the caption.
- s08 chapter-excerpt budget 8000 → **15000 chars**; for short papers (≤8 source chapters) the composer now sees the full text. Enables cross-chapter synthesis (contradiction detection) instead of keyword-window peeking.

### Added — PPT layout robustness

- **Adaptive outline rows**: `_outline_grouped` no longer uses a fixed 0.9" row height. Each row's height is computed from the takeaway's estimated wrap count; line-spacing tightens (1.2 → ~1.05) before any ellipsis trim is applied. Eliminates "row N+1 overlaps row N's wrapped second line" on yang2025-style 5-group outlines.
- **Density-adaptive KEY POINTS card**: `_truncate_bullet(text, n_bullets)` and `_bullet_caps` table. Sparse cards (≤4 bullets) keep up to 110 ASCII / 60 CJK chars at 16pt; dense cards (7 bullets) cap at 80 / 45 chars at 13pt. PowerPoint `TEXT_TO_FIT_SHAPE` autofit added as safety net so any residual overflow shrinks rather than overflowing.
- **Figure-slide observation vertical guard**: when 3 observations would crowd the area, font drops 13pt → 12pt and row height 0.70" → 0.60" so all three fit cleanly above the footer.

### Added — cross-renderer alignment

- HTML/PDF table styling matched to DOCX "Light Grid": bold header row, light-gray row banding, thin gray borders. `table.md-table` styles in `stages/s09_render/templates/styles.css`.

### Tests

- 172 → **178** passing. New regression coverage for `_has_quant` / `_is_descriptive_only` / `_lang_directive` / quant-validation retry path / density-adaptive bullet caps / outline adaptive rows / stderr failure logging.

### Docs

- README + README.zh redesigned around hero showcase, tech-stack badge row, scientific minimalism. Real PPT screenshots in `docs/assets/`.
- `CHANGELOG.md` 1.3.0 section; `pyproject.toml` 1.2.2 → 1.3.0; `HANDOFF.md` status updated.

## [1.2.2] - 2026-05-19

### Fixed

- **PPT outline generated Chinese group names even with `--lang en`** (`runs/yao2022/...preview.pptx` etc.). The outline prompt's "match input language" hint plus a Chinese-only JSON example biased DeepSeek-Reasoner toward Chinese output. Replaced with an explicit `{lang_directive}` placeholder substituted from `doc.lang` at build time. `_OUTLINE_PROMPT_VERSION` bumped `v12-extended-template` → `v13-lang-directive` so caches auto-invalidate.
- **`_is_low_diversity` over-rejected legitimate English outlines** (false-positive on yang2025: `" C"` bigram appeared in every name because each had a word starting with `C` — "Concept", "CBPS", "CBPS", "Computing"). Refactored to two regimes: CJK-dominant names use 2-4 char substring counts; ASCII-dominant names use whole-word tokens (length ≥ 3, stop-words excluded). Threshold raised to "token appears in EVERY group name" — catches the original `弛豫反铁电×4` degeneracy without rejecting paper-specific nouns recurring in N-1 of N names.

### Verified

- Re-rendered yang2025, randall2021, yao2022 with `--lang en` and all 4 formats (docx, pdf, html, pptx). All three now produce English-only LLM-grouped 4–5 section outlines with paper-specific names (CBPS / Perovskite / Ferrielectric PbZrO₃) and takeaways.
- 172 unit tests pass (+5 new: `TestIsLowDiversity` × 5 covering CJK over-similar / CJK diverse / EN paper-specific noun in majority / EN every-name repeat / small-group skip).

## [1.2.1] - 2026-05-19

### Fixed

- **Stale s05_template cache propagated obsolete Chinese-prefixed chapter titles into the final output** (`liu2022`, `pan2025` HTML/DOCX showed e.g. `合成与制备方法 · Synthesis and Preparation` for chapters 10–15 because their s05 cache predated the v15 template English-ification). Affected papers re-rendered from s05 forward; all chapter headings now align with the English-only template.

### Added

- `s05_template` `done.yaml` now records `template_sha256_16` — a 16-hex prefix of the source docx's SHA-256.
- `stages.s05_template.runner.is_cache_stale()` checks the cached hash against the current docx.
- CLI auto-invalidates s05 when the template content changed (no `--force` needed); a one-line `[s05_template] template content changed — invalidating cache` is logged. Legacy `done.yaml` (without the hash field) counts as stale defensively.
- 3 unit tests covering hash recording, stale detection, and legacy-done.yaml handling. Test count 164 → 167.

## [1.2.0] - 2026-05-19

### Fixed

- **PPT math subscripts rendering as plain ASCII** (Issue A in `docs/PPT_KNOWN_ISSUES.md`). LLM-emitted Unicode subscript letters (`aₚₕₒₜ`, U+2090–U+209C / U+1D62–U+1D6A) were silently dropped to base letters (`aphot`) when the active CJK body font lacked glyphs. `_math.py::normalize_math()` now collapses runs that contain Latin-letter subscripts back to `_<plain>` ASCII (`aₚₕₒₜ` → `a_phot`). Pure digit/operator subscripts (`H₂O`, `Pb₀.₆₅Ba₀.₃₅ZrO₃`) keep their Unicode form because they render fine in standard fonts.
- **KEY POINTS card row overlap when ≥6 bullets wrap to 2 lines** (Issue B). `_section_divider` now scales bullet font 16pt→13pt and marker 14pt→12pt when `n_bullets ≥ 6`, drops the `* 0.7` clamp on text-box height (text now uses the full row), and `SlidePlanner._truncate_bullet()` caps bullet length to ~38 CJK / ~70 ASCII chars with `…` suffix as defence-in-depth.

### Verified

- Re-rendered 5 verified papers (he2023, ali2025_flash, yang2025, liu2022, pan2025) with all 4 formats (docx, pdf, html, pptx). All 20 outputs produced cleanly.
- 164 unit tests pass (+6 new: Unicode subscript fallback, bullet truncation cap, section-divider integration).

## [1.1.0] - 2026-05-19

### Added

- `LLM_MAX_TOKENS_CEILING` env var (default 40000) caps every LLM call site through a shared `llm.client.max_tokens()` helper. Per-stage defaults are now generous (8K–16K) so DeepSeek-Reasoner's chain-of-thought tokens no longer starve final content.
- CLI `--only` now accepts comma-separated stage lists (`s08_section_compose,s09_render`) and rejects unknown stage names with a clear error.
- `stages/_common/images.py::image_to_data_url()` shared helper consumed by the HTML renderer and the LLM client (consolidates the previous duplicated MIME-encoding logic).
- New documentation: `docs/AGENT_GUIDE.md` (workflow patterns for AI agents maintaining the repo). `docs/INTERNAL/HANDOFF.md` rewritten to reflect verified v1.1 state.
- Unit tests: `max_tokens()` clamping, `--only` comma split, `--only` unknown-stage rejection.

### Changed

- s08 chapter heading no longer embeds the template's `number` field. The PPT outline renderer adds its own 01–N positional prefix, so chapter titles are consistent regardless of whether the template chapter carries an explicit number.
- PPT deep-observation font bumped from 11pt → 13pt; eyebrow now bold; row height 0.52" → 0.70" for comfortable italic reading.
- Per-stage LLM `max_tokens` defaults raised: s06 1500→4000, s07 2000→4000, s08 3000→12000, s09 outline 8000→16000, s09 summary/paper 2000→8000.
- Test count 134 → 158 (added cli + max_tokens coverage).

### Fixed

- CLI `--only s08,s09` was treated as a single literal stage name; both stages silently skipped. Now splits on comma and rejects unknown names.
- he2023 outline degenerated to a flat 15-row list because the LLM call hit max_tokens before emitting JSON (DeepSeek-Reasoner reasoning-token budget exhausted). Outline call now requests 16K tokens by default and detects empty responses explicitly so the retry loop short-circuits with a meaningful error.
- `_strip_md_heading()` in `pptx_summarizer` now also strips leading numeric prefixes (`12 X` → `X`), tolerating stale caches and LLM echo-back variations.

## [1.0.0] - 2026-05-18

Initial public release of lazy-paper.

### Added

- Multi-format renderer: DOCX, PDF, HTML, PPTX from a single Document model
- Two OCR backends: MinerU (default, figure-aware) and PaddleOCR-VL
- LLM-driven figure analysis (Qwen-VL vision LLM) and section composition (DeepSeek text LLM)
- Academic-defense styled PPTX with LLM-grouped 4-5 section outline, side-by-side bullets+figure slides, and rich closing with quantitative take-away
- Cross-chapter context injection in per-chapter LLM summarization (system, keywords, prior bullet, next heading)
- Soft-failure semantics: a single renderer failure does not abort other formats; partial state recorded in `done.yaml`
- `--retry-failed`: re-run only the formats marked as failed in a previous partial run
- `--only STAGE`: run a single named stage without re-running the full pipeline
- Pluggable PPT template via `--pptx-template`
- Speaker metadata on PPT title slide via `--presenter` and `--affiliation`
- Docker image with all system dependencies preinstalled (Pango, Cairo, gdk-pixbuf, WeasyPrint)
- macOS `DYLD_FALLBACK_LIBRARY_PATH` auto-augmentation for bare-metal WeasyPrint
- 153-test unit and integration suite; live LLM smoke tests gated behind `-m live`

### Architecture

- 9-stage pipeline with per-stage `done.yaml` idempotency markers
- Frozen `Document -> Chapter -> Block` dataclass tree as the cross-renderer contract
- `Renderer` ABC: each output format is a stateless subclass that consumes the Document and never mutates it
- `DocumentBuilder`: pure function — markdown chapters + fig_notes YAML in, frozen Document out
- `PptxSummarizer`: double-track LLM cache — input-hash key for reuse, prompt/response files for audit; `_PROMPT_VERSION` constant invalidates stale caches on prompt changes
- `SlidePlanner`: deterministic slide layout logic, no IO, accepts optional LLM summaries and outline
- `LLM` client: OpenAI-compatible; two roles (`vision`, `text`) configured via `models.yaml` and env vars

[Unreleased]: https://github.com/thematteroftime/lazy-paper/compare/v1.4.1...HEAD
[1.4.1]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.4.1
[1.4.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.4.0
[1.3.4]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.3.4
[1.3.3]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.3.3
[1.3.2]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.3.2
[1.3.1]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.3.1
[1.3.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.3.0
[1.2.2]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.2
[1.2.1]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.1
[1.2.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.0
[1.1.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.1.0
[1.0.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.0.0
