# Changelog

All notable changes to lazy-paper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/thematteroftime/lazy-paper/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.1.0
[1.0.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.0.0
