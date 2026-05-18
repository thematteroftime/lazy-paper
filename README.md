# paper2md

> **Production deployment & hand-off:** see [HANDOFF.md](HANDOFF.md).

PDF + outline template → bilingual deep-analysis documents in 4 formats (DOCX, PDF, HTML, PPTX), via PaddleOCR-VL OCR + OpenAI-compatible LLM stages (Qwen-VL vision + DeepSeek text by default).

```
PDF ──┬─ s01_ocr ─→ s02_clean ─→ s03_chapter ─→ s04_figures ──┐
      │                                                       │
template.docx ─ s05_template ──────────────────────────────────┤
                                                              │
                                                          s06_context (LLM text)
                                                          s07_figure_analyze (LLM vision)
                                                          s08_section_compose (LLM text)
                                                          s09_render
                                                              │
                              runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}
                                                       + mypaper_bundle/
```

## Quick start (any OS)

### 1. Get the code
```bash
git clone <repo> && cd paper2md
```

### 2. Configure API keys
```bash
cp .env.example .env
# Edit .env to add your PaddleOCR + Qwen-VL + DeepSeek keys.
```

You need three credentials:
- **PaddleOCR-VL** token from [Baidu AI Studio](https://aistudio.baidu.com)
- **Qwen-VL** (DashScope) key — for figure visual analysis
- **DeepSeek** key — for text generation

(You can swap any with another OpenAI-compatible vision/text model by editing `*_BASE_URL` and `*_MODEL`.)

### 3a. Run in Docker (recommended)

Docker is the recommended path — it ships with all system libraries (Pango/Cairo/gdk-pixbuf for PDF rendering) and an aligned Python 3.11, so nothing leaks onto your host.

```bash
docker build -t paper2md .

# One-off run:
docker run --rm \
  -v "$(pwd)/runs:/app/runs" \
  -v "$(pwd)/参考文献:/app/参考文献" \
  -v "$(pwd)/.env:/app/.env:ro" \
  paper2md run \
    --pdf "/app/参考文献/your-paper.pdf" \
    --template "/app/Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id mypaper --lang zh
```

Or use docker compose (volume mounts pre-wired in `docker-compose.yml`):
```bash
docker compose run --rm paper2md run \
  --pdf "参考文献/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper --lang zh
```

The image is ~280 MB and pulls no model weights (all OCR/LLM is via cloud APIs).

### 3b. Run locally with uv (bare-metal)

If you prefer running on the host: install [uv](https://github.com/astral-sh/uv), then bring in a managed Python (NOT the macOS system 3.9 — that's known to segfault with WeasyPrint) and the project deps.

```bash
# Install uv (macOS / Linux):
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install uv (Windows PowerShell):
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Pin a uv-managed Python and create the venv:
uv python install 3.11
uv venv --python 3.11
uv pip install -e .[dev]
```

WeasyPrint (used for PDF rendering) needs system graphics libraries:

| OS | Install |
|---|---|
| macOS | `brew install pango gdk-pixbuf libffi cairo` |
| Debian/Ubuntu | `sudo apt install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8` |
| Windows | WeasyPrint requires the GTK runtime — we recommend the Docker path instead. `docx`/`html`/`pptx` work without GTK. |

Then run:
```bash
uv run python -m cli run \
  --pdf "参考文献/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper --lang zh
```

(Use `--lang en` for English output. Use `--force` to re-run completed stages. Use `--skip-ocr` if you already have s01_ocr artifacts.)

Outputs land in `runs/<paper_id>/`. The user-facing files are:
- `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}` — bilingual deep analysis in your chosen formats
- `runs/<paper_id>/s09_render/mypaper_bundle/` — drop-in chapter markdown + figures for the `mypaper` toolchain

## Output Formats

`s09_render` can produce four formats, controlled by `--formats` (comma-separated):

| Format | Default | Notes |
|---|---|---|
| `docx` | ✓ | Self-contained Word file (Times New Roman + 宋体 for Chinese) |
| `pdf`  | ✓ | Same content as docx, rendered via WeasyPrint from the shared HTML template |
| `html` | ✓ | Single self-contained HTML file (images embedded as base64) |
| `pptx` |   | Opt-in (uses LLM to compress bullets + figure observations into 20–40 slides) |

Examples:

```bash
# Default: docx + pdf + html (no LLM calls beyond the existing s06–s08 stages)
paper2md run --pdf paper.pdf --template tpl.docx

# All four formats (PPT adds LLM calls for bullets/figure one-liners)
paper2md run --pdf paper.pdf --template tpl.docx --formats docx,pdf,html,pptx

# Only PPT, with rule-based bullet extraction (no extra LLM calls)
paper2md run --pdf paper.pdf --template tpl.docx --formats pptx --pptx-bullets rule
```

### Soft failure & retry

If one format fails (e.g. WeasyPrint trips on a malformed image), the other formats still complete. The failed format is recorded in `done.yaml.formats[<fmt>] = {error: ...}` and `done.yaml.partial = true`. Re-run only the failed formats with:

```bash
paper2md run --pdf paper.pdf --template tpl.docx --only s09_render --retry-failed
```

(The `--only` and `--retry-failed` flags re-execute just the render stage and just the formats marked as failed in the prior `done.yaml`.)

### PPT cache

When `--formats` includes `pptx` and `--pptx-bullets=llm` (the default for PPT), each chapter's LLM summary is cached at `runs/<paper_id>/s09_render/llm_cache/<chapter>.json`. Re-runs with identical input reuse the cache (zero LLM calls). The cache directory also stores `.prompt.md` and `.response.json` for audit.

## Running tests

```bash
uv run pytest -v               # ~98 tests, skips live API tests by default
uv run pytest -v -m live       # runs the live LLM smoke tests (uses .env keys)
```

## Backends & quality

paper2md ships with two OCR backends. Switch via the `OCR_BACKEND` env var (or `--ocr-backend` if you prefer a CLI flag; not currently exposed but `OCR_BACKEND` works the same).

### PaddleOCR-VL (default)

Set `OCR_BACKEND=paddleocr` (default) + `PADDLEOCR_TOKEN`. Free cloud API; fast; handles formulas and tables well. **Limitation**: panel-by-panel figure crops, sometimes missing top portions of figures or capturing journal-template sidebars. paper2md post-processes via `stages/s04_figures::_merge_figure_subpanels` to merge sub-panels back into one figure when multiple bboxes share a caption.

### MinerU (recommended for figure-heavy papers)

Set `OCR_BACKEND=mineru` + `MINERU_TOKEN`. Uses DocLayout-YOLO to detect WHOLE figures at native PDF resolution. Empirically validated on multiple papers:
- li2022 Fig. 5 (η/Wrec scatter + TEM/SAED/HR-TEM): MinerU keeps full η axis 60–100; PaddleOCR misses the η=100 top
- zhang2025_thinfilms Fig. 8 / Fig. 12 (Wiley layout): MinerU cleanly excludes the journal's vertical sidebar text; PaddleOCR includes it as a stripe of text

Trade-off: MinerU is ~30% slower per page (cloud queue) and you need a `MINERU_TOKEN` from https://mineru.net/. The downstream stages (s02–s09) are backend-agnostic — same `doc_<N>.md` + `imgs/*.jpg` contract.

If `OCR_BACKEND=mineru` is set but `MINERU_TOKEN` is missing, the CLI fails fast.

## Project layout

```
paper2md/
├── cli.py                # single entry: python -m cli run --pdf ... --template ...
├── stages/
│   ├── _common/          # shared YAML I/O, stage_dir, safe_parse_yaml, bbox helpers, done-marker
│   ├── s01_ocr/          # PDF → PaddleOCR-VL or MinerU → doc_*.md + high-DPI imgs
│   ├── s02_clean/        # text cleaning (page headers, char repair, column-flow flag)
│   ├── s03_chapter/      # IMRaD section splitter
│   ├── s04_figures/      # figures.yaml + tables.yaml + mentions.yaml
│   ├── s05_template/     # outline.docx → template.yaml (sections + guidance + hints)
│   ├── s06_context/      # paper context via text LLM
│   ├── s07_figure_analyze/ # per-figure visual LLM (multi-panel support)
│   ├── s08_section_compose/# per-section text LLM
│   └── s09_render/       # Document model + 4 renderers (docx/pdf/html/pptx) + SlidePlanner + PptxSummarizer + mypaper bundle
├── llm/
│   ├── client.py         # OpenAI-compatible client (vision + text roles)
│   ├── models.yaml       # role → default base_url / model
│   └── prompts/          # paper_context.md, figure_analyze.md, section_compose.md, pptx_summarize.md
└── runs/<paper_id>/      # per-paper stage artifacts (YAML + MD + DOCX + PDF + HTML + PPTX + LLM audit)
```

Each stage is a self-contained folder with `runner.py` + `tests/`. Artifacts are written to `runs/<paper_id>/<stage>/`. Every LLM call persists its prompt and response next to the result for traceability.

## Identity / runtime separation

When you run `python -m cli run`, ALL LLM calls go through the OpenAI-compatible endpoints in your `.env`. Claude / Anthropic is NOT in the runtime loop. You can run this entirely on your local machine + your chosen LLM providers' APIs without any other dependencies.

## Switching languages / templates / LLM providers

- `--lang en` writes English; `--lang zh` writes Chinese (default)
- `--template <path>.docx` swaps the section outline at will
- To switch LLM provider: edit the `LLM_*_BASE_URL` / `LLM_*_API_KEY` / `LLM_*_MODEL` env vars (any OpenAI-compatible API works; tested with Qwen-VL & DeepSeek)
