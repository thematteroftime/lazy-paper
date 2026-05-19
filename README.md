# lazy-paper

> Turn a PDF research paper into a structured, multi-format deep analysis: DOCX, PDF, HTML, and PPTX.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

`lazy-paper` is a 9-stage CLI pipeline that takes a scientific paper PDF and a section-outline template, and produces a bilingual deep-analysis document set. Each stage is self-contained, audited, and resumable.

## Highlights

- **Four output formats from one source**: DOCX, PDF (via WeasyPrint), HTML (self-contained, base64 images), PPTX (academic-defense styled, LLM-grouped sections)
- **Pluggable OCR backends**: MinerU (default, figure-aware) or PaddleOCR-VL
- **Pluggable LLM providers**: any OpenAI-compatible endpoint (Qwen-VL for vision, DeepSeek for text by default)
- **Resumable + auditable**: every stage writes `done.yaml`; every LLM call persists its prompt and response
- **Soft failure with retry**: a single renderer crashing does not block other formats; `--retry-failed` re-runs only the failed ones
- **Docker-first**: ships with a slim Python 3.11 image with all system dependencies (Pango, Cairo, gdk-pixbuf) preinstalled

## Quick start

### Installation

#### Recommended: Docker

```bash
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
docker compose build
```

#### Local install (Python 3.11+, uv)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"
```

WeasyPrint requires system graphics libraries on macOS:

```bash
brew install pango gdk-pixbuf libffi cairo
```

### Configuration

Copy the env template and add your API keys:

```bash
cp .env.example .env
# Edit .env: OCR_BACKEND + MINERU_TOKEN or PADDLEOCR_TOKEN
#            LLM_VISION_API_KEY (Qwen-VL)
#            LLM_TEXT_API_KEY (DeepSeek)
```

### Run

```bash
# Docker
docker compose run --rm lazy-paper run \
  --pdf "papers/your-paper.pdf" \
  --template "template.docx" \
  --paper-id mypaper \
  --lang zh

# Bare metal
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "template.docx" \
  --paper-id mypaper \
  --formats docx,pdf,html,pptx \
  --lang zh
```

Output lands at `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`.

## Output formats

| Format | Notes |
|--------|-------|
| `docx` | Self-contained Word file; Times New Roman + Song Ti for Chinese |
| `pdf`  | Same content as DOCX, rendered through WeasyPrint from a shared HTML template |
| `html` | Single file with base64-embedded images — emailable, viewable in any browser |
| `pptx` | Academic-defense style: cream/charcoal palette, serif title, LLM-grouped 4-5 section outline, side-by-side bullets+figure slides, rich closing with quantitative take-away |

Select formats with `--formats`:

```bash
lazy-paper run --pdf x.pdf --template t.docx --formats docx,pptx
```

### PPTX customization

Pass speaker metadata and an optional template:

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
     -> s06_context   (LLM: title, system, keywords)
     -> s07_figure_analyze (vision LLM, per figure)
     -> s08_section_compose (text LLM, per chapter)
     -> s09_render    (Document model -> 4 renderers)
```

See `docs/ARCHITECTURE.md` for details.

## CLI reference

```
lazy-paper run --pdf PATH --template PATH [options]

Required:
  --pdf PATH                Source paper PDF
  --template PATH           Section outline (.docx)

Options:
  --paper-id ID             Per-paper run-directory slug (default: derived from PDF stem)
  --runs-dir PATH           Where artifacts go (default: ./runs)
  --lang {zh,en}            Output language (default: zh)
  --skip-ocr                Assume s01_ocr outputs already exist
  --force                   Re-run stages even if marked done
  --only STAGE              Run only this stage (e.g. s09_render)
  --formats LIST            Comma list: docx,pdf,html,pptx (default: docx,pdf,html)
  --pptx-bullets {llm,rule} PPT bullet generation strategy (default: llm)
  --pptx-template PATH      Custom .pptx as slide-master base for PPT output (optional)
  --pptx-subtitle TEXT      Override the PPT subtitle line
  --presenter TEXT          Speaker name on PPT title slide
  --affiliation TEXT        Institution on PPT title slide
  --retry-failed            In --only mode, re-run only formats marked partial in done.yaml
```

## Switching providers

`lazy-paper` works with any OpenAI-compatible vision and text endpoint. Edit the `LLM_*_BASE_URL`, `LLM_*_API_KEY`, `LLM_*_MODEL` env vars. Tested with Qwen-VL (via DashScope) and DeepSeek; should work with OpenAI, Anthropic-compatible gateways, and self-hosted vLLM/Ollama servers.

For OCR, set `OCR_BACKEND=mineru` (recommended for figure-heavy papers) or `OCR_BACKEND=paddleocr` (default in `.env.example`).

`LLM_MAX_TOKENS_CEILING` (default 40000) caps every LLM call. Per-stage defaults are intentionally generous (8K–16K) so DeepSeek-Reasoner's chain-of-thought tokens don't starve the final JSON content. Lower this ceiling to constrain spend or fit a stricter quota.

## Development

```bash
uv pip install -e ".[dev]"
uv run pytest             # 153 tests
uv run pytest -m live     # live LLM smoke tests (requires real keys)
```

See `CONTRIBUTING.md` for contribution norms.

## License

MIT — see `LICENSE`.
