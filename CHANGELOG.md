# Changelog

All notable changes to lazy-paper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- 134-test unit and integration suite; live LLM smoke tests gated behind `-m live`

### Architecture

- 9-stage pipeline with per-stage `done.yaml` idempotency markers
- Frozen `Document -> Chapter -> Block` dataclass tree as the cross-renderer contract
- `Renderer` ABC: each output format is a stateless subclass that consumes the Document and never mutates it
- `DocumentBuilder`: pure function — markdown chapters + fig_notes YAML in, frozen Document out
- `PptxSummarizer`: double-track LLM cache — input-hash key for reuse, prompt/response files for audit; `_PROMPT_VERSION` constant invalidates stale caches on prompt changes
- `SlidePlanner`: deterministic slide layout logic, no IO, accepts optional LLM summaries and outline
- `LLM` client: OpenAI-compatible; two roles (`vision`, `text`) configured via `models.yaml` and env vars

[Unreleased]: https://github.com/thematteroftime/lazy-paper/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/thematteroftime/lazy-paper/releases/tag/v1.0.0
