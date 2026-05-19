# lazy-paper

> Turn a PDF research paper into a structured, multi-format deep analysis: DOCX, PDF, HTML, and PPTX.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

`lazy-paper` is a 9-stage CLI pipeline. Feed it a scientific paper PDF and a section-outline template, get back a bilingual deep-analysis document set in your formats of choice. Each stage is self-contained, auditable, and resumable.

## Highlights

- **Four output formats from one source**: DOCX, PDF (WeasyPrint), HTML (self-contained, base64 images), PPTX (academic-defense styled, LLM-grouped sections)
- **Pluggable OCR**: MinerU (default, figure-aware) or PaddleOCR-VL
- **Pluggable LLMs**: any OpenAI-compatible endpoint (Qwen-VL for vision, DeepSeek for text by default)
- **Resumable + auditable**: every stage writes `done.yaml`; every LLM call persists its prompt and response
- **Soft failure with targeted retry**: one renderer crashing does not block the others; `--retry-failed` re-runs only the failed format
- **Single env knob to constrain LLM cost**: `LLM_MAX_TOKENS_CEILING`
- **Docker-first**: slim Python 3.11 image with Pango/Cairo/gdk-pixbuf preinstalled

## Who is this for?

- **Researchers** producing literature reviews who want a one-shot pipeline from PDF to slides + handout
- **Lab managers** building a paper-summary workflow on a shared queue
- **AI agents** asked to extend or maintain the pipeline (see [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md))

If you want a tool to read each paper *for* you, this isn't it. `lazy-paper` produces a strong first draft you must still review and refine. The pipeline is honest about what came from LLM inference (everything in `*.response.json`) and what is deterministic.

## Quick start

### Local (Python 3.11+ via uv)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"

# WeasyPrint needs system graphics libs on macOS:
brew install pango gdk-pixbuf libffi cairo
```

### Docker (recommended for Windows or shared servers)

```bash
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
docker compose build
```

### Configure

```bash
cp .env.example .env
# Edit .env: OCR_BACKEND + MINERU_TOKEN or PADDLEOCR_TOKEN
#            LLM_VISION_API_KEY (Qwen-VL)
#            LLM_TEXT_API_KEY   (DeepSeek)
```

### Run

```bash
# Bare metal
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --formats docx,pdf,html,pptx \
  --lang zh

# Docker
docker compose run --rm lazy-paper run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper --lang zh
```

Output: `runs/<paper-id>/s09_render/preview.{docx,pdf,html,pptx}`.

## Output formats

| Format | Notes |
|---|---|
| `docx` | Self-contained Word file; Times New Roman + Song Ti for Chinese |
| `pdf`  | Same content as DOCX, rendered through WeasyPrint from a shared HTML template |
| `html` | Single file with base64-embedded images — emailable, viewable in any browser |
| `pptx` | Academic-defense styled: cream/charcoal palette, serif title, LLM-grouped 4–5 section outline, side-by-side bullets+figure slides, rich closing with quantitative take-away |

Select formats with `--formats docx,pptx` (any subset; default `docx,pdf,html`).

### PPTX customization

```bash
lazy-paper run --pdf x.pdf --template t.docx \
  --presenter "Dr. Smith" --affiliation "Acme University" \
  --pptx-subtitle "Energy storage materials" \
  --pptx-template "my-slide-master.pptx"
```

## Pipeline

```
PDF --> s01_ocr (MinerU | PaddleOCR-VL)
     -> s02_clean
     -> s03_chapter   (IMRaD splitting)
     -> s04_figures   (figure detection, multi-panel merge)
     -> s05_template  (outline parsing)
     -> s06_context   (text LLM: title, system, keywords)
     -> s07_figure_analyze (vision LLM, per figure)
     -> s08_section_compose (text LLM, per chapter)
     -> s09_render    (Document model -> 4 renderers)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for per-stage contracts.

## CLI reference

```
lazy-paper run --pdf PATH --template PATH [options]

Required
  --pdf PATH                Source paper PDF
  --template PATH           Section outline (.docx)

Options
  --paper-id ID             Per-paper run-directory slug (default: derived from PDF stem)
  --runs-dir PATH           Where artifacts go (default: ./runs)
  --lang {zh,en}            Output language (default: zh)
  --skip-ocr                Assume s01_ocr outputs already exist
  --force                   Re-run stages even if marked done
  --only STAGE[,STAGE...]   Run only these stages (comma-separated, must be in STAGE_ORDER)
  --formats LIST            Comma list: docx,pdf,html,pptx (default: docx,pdf,html)
  --pptx-bullets {llm,rule} PPT bullet generation strategy (default: llm)
  --pptx-template PATH      Custom .pptx slide-master base (optional)
  --pptx-subtitle TEXT      Override the PPT subtitle line
  --presenter TEXT          Speaker name on PPT title slide
  --affiliation TEXT        Institution on PPT title slide
  --retry-failed            In --only s09_render, re-run only formats marked partial in done.yaml
```

## Switching providers

`lazy-paper` works with any OpenAI-compatible vision and text endpoint. Edit the `LLM_*_BASE_URL`, `LLM_*_API_KEY`, `LLM_*_MODEL` env vars. Tested with Qwen-VL (via DashScope) and DeepSeek-Reasoner; should work with OpenAI, Anthropic-compatible gateways, and self-hosted vLLM/Ollama servers.

For OCR, set `OCR_BACKEND=mineru` (recommended for figure-heavy papers) or `OCR_BACKEND=paddleocr`.

`LLM_MAX_TOKENS_CEILING` (default `40000`) caps every LLM call site through a shared helper. Per-stage defaults are intentionally generous (8K–16K) so DeepSeek-Reasoner's chain-of-thought tokens don't starve the final JSON content. Lower this ceiling to constrain spend or fit a stricter quota.

## Development

```bash
uv pip install -e ".[dev]"
uv run pytest -q          # 158 tests
uv run pytest -m live     # live LLM smoke tests (requires real keys)
```

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the per-stage data contracts before adding code.

If you are an AI agent maintaining this repo, read [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) first — it codifies the patterns and anti-patterns observed during the v1.0 → v1.1 development cycle.

For contribution norms see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Documentation map

| File | Audience | Purpose |
|---|---|---|
| `README.md` | First-time user (human) | Install + run + format choice |
| `docs/ARCHITECTURE.md` | Maintainer / extender | Per-stage data contracts, how to add a stage or format |
| `docs/AGENT_GUIDE.md` | AI coding agent | Workflow patterns, cache gotchas, anti-patterns |
| `docs/INTERNAL/HANDOFF.md` | Next maintainer | Verified state, where to make changes, known limitations |
| `CHANGELOG.md` | Anyone | Release-by-release diff |
| `CONTRIBUTING.md` | External contributor | Branch, test, PR norms |

## License

MIT — see `LICENSE`.
