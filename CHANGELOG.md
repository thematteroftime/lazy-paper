# Changelog

All notable changes to lazy-paper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/thematteroftime/lazy-paper/compare/v1.2.2...HEAD
[1.2.2]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.2
[1.2.1]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.1
[1.2.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.2.0
[1.1.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.1.0
[1.0.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.0.0
