# Changelog

All notable changes to lazy-paper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
