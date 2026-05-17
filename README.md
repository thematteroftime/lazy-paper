# paper2md

> **Production deployment & hand-off:** see [HANDOFF.md](HANDOFF.md).

PDF + outline template → bilingual deep-analysis docx, via PaddleOCR-VL OCR + OpenAI-compatible LLM stages (Qwen-VL vision + DeepSeek text by default).

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
                              runs/<paper_id>/s09_render/preview.docx + mypaper_bundle/
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

### 3a. Run locally with uv (recommended)

Install [uv](https://github.com/astral-sh/uv) if you don't have it:

**macOS / Linux**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Set up the project venv:
```bash
uv sync                  # creates .venv/ and installs locked deps
uv pip install -e .[dev] # editable install + pytest
```

Run the pipeline:
```bash
uv run python -m cli run \
  --pdf "参考文献/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --lang zh
```

(Use `--lang en` for English output. Use `--force` to re-run completed stages. Use `--skip-ocr` if you already have s01_ocr artifacts.)

Outputs land in `runs/<paper_id>/`. The user-facing files are:
- `runs/<paper_id>/s09_render/preview.docx` — quick-look bilingual deep analysis
- `runs/<paper_id>/s09_render/mypaper_bundle/` — drop-in chapter markdown + figures for the `mypaper` toolchain

### 3b. Run in Docker (system-isolated)

If you don't want uv on your host, or want strict isolation:

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

The image is ~250 MB and pulls no model weights (all OCR/LLM is via cloud APIs).

## Running tests

```bash
uv run pytest -v                # 39 tests, skips live API tests by default
uv run pytest -v -m live        # runs the live LLM smoke tests (uses .env keys)
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
│   ├── _common.py        # shared YAML I/O, stage_dir, safe_parse_yaml
│   ├── s01_ocr/          # PDF → PaddleOCR-VL → doc_*.md + high-DPI imgs
│   ├── s02_clean/        # text cleaning (page headers, char repair, column-flow flag)
│   ├── s03_chapter/      # IMRaD section splitter
│   ├── s04_figures/      # figures.yaml + tables.yaml + mentions.yaml
│   ├── s05_template/     # outline.docx → template.yaml (sections + guidance + hints)
│   ├── s06_context/      # paper context via text LLM
│   ├── s07_figure_analyze/ # per-figure visual LLM (multi-panel support)
│   ├── s08_section_compose/# per-section text LLM
│   └── s09_render/       # mypaper bundle + preview docx
├── llm/
│   ├── client.py         # OpenAI-compatible client (vision + text roles)
│   ├── models.yaml       # role → default base_url / model
│   └── prompts/          # paper_context.md, figure_analyze.md, section_compose.md
└── runs/<paper_id>/      # per-paper stage artifacts (YAML + MD + DOCX + LLM audit)
```

Each stage is a self-contained folder with `runner.py` + `tests/`. Artifacts are written to `runs/<paper_id>/<stage>/`. Every LLM call persists its prompt and response next to the result for traceability.

## Identity / runtime separation

When you run `python -m cli run`, ALL LLM calls go through the OpenAI-compatible endpoints in your `.env`. Claude / Anthropic is NOT in the runtime loop. You can run this entirely on your local machine + your chosen LLM providers' APIs without any other dependencies.

## Switching languages / templates / LLM providers

- `--lang en` writes English; `--lang zh` writes Chinese (default)
- `--template <path>.docx` swaps the section outline at will
- To switch LLM provider: edit the `LLM_*_BASE_URL` / `LLM_*_API_KEY` / `LLM_*_MODEL` env vars (any OpenAI-compatible API works; tested with Qwen-VL & DeepSeek)
