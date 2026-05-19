# lazy-paper

> Turn a PDF research paper into a structured, multi-format deep analysis: **DOCX · PDF · HTML · PPTX** — in one command.

<p>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <a href="CHANGELOG.md"><img alt="Release" src="https://img.shields.io/badge/release-v1.2.0-blue"></a>
  <a href="#tests"><img alt="Tests" src="https://img.shields.io/badge/tests-164%20passing-22c55e"></a>
  <a href="docs/AGENT_GUIDE.md"><img alt="Agent-friendly" src="https://img.shields.io/badge/agent--friendly-yes-7c3aed"></a>
</p>

<p>
  <img alt="DeepSeek" src="https://img.shields.io/badge/LLM-DeepSeek--Reasoner-1f6feb">
  <img alt="Qwen-VL" src="https://img.shields.io/badge/Vision-Qwen--VL-ff7a00">
  <img alt="MinerU" src="https://img.shields.io/badge/OCR-MinerU%20%7C%20PaddleOCR--VL-0ea5e9">
  <img alt="WeasyPrint" src="https://img.shields.io/badge/PDF-WeasyPrint-0b7285">
  <img alt="python-pptx" src="https://img.shields.io/badge/PPT-python--pptx-c2410c">
  <img alt="python-docx" src="https://img.shields.io/badge/DOCX-python--docx-2563eb">
  <img alt="Jinja2" src="https://img.shields.io/badge/HTML-Jinja2-b91c1c">
</p>

**[English](README.md) · [简体中文](README.zh.md)**

---

`lazy-paper` is a 9-stage CLI pipeline. Feed it a scientific PDF and a section-outline template, get back a bilingual deep-analysis document set in your formats of choice. Each stage is self-contained, audited, and resumable.

## Highlights

- **Four output formats from one source**: DOCX, PDF (via WeasyPrint), HTML (self-contained, base64 images), PPTX (academic-defense styled, LLM-grouped sections)
- **Pluggable OCR**: MinerU (default, figure-aware) or PaddleOCR-VL
- **Pluggable LLMs**: any OpenAI-compatible endpoint — Qwen-VL for vision, DeepSeek-Reasoner for text by default
- **Resumable + auditable**: every stage writes `done.yaml`; every LLM call persists its prompt and response
- **Soft failure with targeted retry**: one renderer crashing does not block the others; `--retry-failed` re-runs only the failed format
- **One env knob to constrain LLM cost**: `LLM_MAX_TOKENS_CEILING`
- **Docker-first**: slim Python 3.11 image with Pango/Cairo/gdk-pixbuf preinstalled

## Who is this for?

- **Researchers** producing literature reviews who want a one-shot pipeline from PDF to slides + handout
- **Lab managers** building a paper-summary workflow on a shared queue
- **AI agents** asked to extend or maintain the pipeline — see [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md)

If you want a tool to read each paper *for* you, this isn't it. `lazy-paper` produces a strong first draft you must still review and refine. The pipeline is honest about what came from LLM inference (everything in `*.response.json`) and what is deterministic.

## Tech stack

| Layer | Library / Service | Purpose |
|---|---|---|
| Runtime | **Python 3.11+** | uv-managed virtualenv recommended |
| PDF I/O | `pdfplumber`, `pypdfium2`, `Pillow` | text extraction, page rasterization, image processing |
| OCR | [MinerU](https://mineru.net/) (default) or [PaddleOCR-VL](https://ai.baidu.com/ai-doc/AISTUDIO) | cloud OCR |
| LLM client | `openai>=1.50` (OpenAI-compatible) | text + vision calls (one config, any provider) |
| Default text LLM | [DeepSeek-Reasoner](https://api-docs.deepseek.com/) | chain-of-thought analysis quality |
| Default vision LLM | [Qwen-VL-Max](https://help.aliyun.com/zh/dashscope/) (DashScope) | figure understanding |
| Templates | `python-docx`, `jinja2` | parse outline `.docx`, render HTML |
| Renderers | `python-docx`, `python-pptx`, `weasyprint`, `jinja2` | one renderer per output format |
| Config | `pyyaml`, `python-dotenv` | YAML artifacts + `.env` credentials |
| HTTP | `requests` | OCR API calls |
| Dev | `pytest>=8` | 164 tests |

## Quick start

### Local install (Python 3.11+, uv)

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
# Edit .env:
#   OCR_BACKEND + MINERU_TOKEN or PADDLEOCR_TOKEN
#   LLM_VISION_API_KEY (Qwen-VL via DashScope)
#   LLM_TEXT_API_KEY   (DeepSeek)
```

### Run

```bash
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --formats docx,pdf,html,pptx \
  --lang zh
```

Output lands at `runs/<paper-id>/s09_render/preview.{docx,pdf,html,pptx}`.

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
uv run python -m cli run --pdf x.pdf --template t.docx \
  --presenter "Dr. Smith" --affiliation "Acme University" \
  --pptx-subtitle "Energy storage materials" \
  --pptx-template "my-slide-master.pptx"
```

## Pipeline

```
PDF ──┬─ s01_ocr (MinerU | PaddleOCR-VL)
      │  ↓
      │  s02_clean → s03_chapter → s04_figures
template.docx → s05_template
                 ↓
              s06_context        (text LLM: title, system, keywords)
              s07_figure_analyze (vision LLM, per figure)
              s08_section_compose (text LLM, per chapter)
              s09_render → preview.{docx,pdf,html,pptx}
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
  --only STAGE[,STAGE...]   Run only these stages (comma-separated; must be in STAGE_ORDER)
  --formats LIST            Comma list: docx,pdf,html,pptx (default: docx,pdf,html)
  --pptx-bullets {llm,rule} PPT bullet generation strategy (default: llm)
  --pptx-template PATH      Custom .pptx slide-master base (optional)
  --pptx-subtitle TEXT      Override the PPT subtitle line
  --presenter TEXT          Speaker name on PPT title slide
  --affiliation TEXT        Institution on PPT title slide
  --retry-failed            In --only s09_render, re-run only formats marked partial in done.yaml
```

## Switching providers

`lazy-paper` works with any OpenAI-compatible vision and text endpoint. Edit the `LLM_*_BASE_URL`, `LLM_*_API_KEY`, `LLM_*_MODEL` env vars. Tested with Qwen-VL (DashScope) and DeepSeek-Reasoner; should work with OpenAI, Anthropic-compatible gateways, and self-hosted vLLM/Ollama servers.

For OCR, set `OCR_BACKEND=mineru` (recommended for figure-heavy papers) or `OCR_BACKEND=paddleocr`.

`LLM_MAX_TOKENS_CEILING` (default `40000`) caps every LLM call site through a shared helper. Per-stage defaults are intentionally generous (8K–16K) so DeepSeek-Reasoner's chain-of-thought tokens don't starve the final JSON content. Lower this ceiling to constrain spend or fit a stricter quota.

## Tests

```bash
uv run pytest -q          # 164 tests
uv run pytest -m live     # live LLM smoke tests (requires real keys)
```

## Known issues

None at this time. The two PPT visual issues triaged in [`docs/PPT_KNOWN_ISSUES.md`](docs/PPT_KNOWN_ISSUES.md) (math subscript font fallback, KEY POINTS card overlap on ≥6-bullet sections) were both fixed in v1.2.0 — see [`CHANGELOG.md`](CHANGELOG.md).

## Citation

If you use `lazy-paper` in academic work:

```bibtex
@software{lazy_paper,
  author  = {thematteroftime},
  title   = {lazy-paper: PDF research papers to multi-format deep analysis},
  url     = {https://github.com/thematteroftime/lazy-paper},
  version = {1.1.0},
  year    = {2026}
}
```

## Acknowledgements

- [MinerU](https://github.com/opendatalab/MinerU) — figure-aware PDF layout analysis
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — alternative OCR backend
- [DeepSeek](https://www.deepseek.com/) — text reasoning LLM
- [Qwen](https://github.com/QwenLM/Qwen) — vision LLM
- [WeasyPrint](https://github.com/Kozea/WeasyPrint), [python-pptx](https://github.com/scanny/python-pptx), [python-docx](https://github.com/python-openxml/python-docx) — rendering stack

## Documentation map

| File | Audience | Purpose |
|---|---|---|
| [`README.md`](README.md) | First-time user (English) | Install + run + format choice |
| [`README.zh.md`](README.zh.md) | 中文用户 | 安装 + 运行 + 格式选择 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Maintainer / extender | Per-stage data contracts, how to add a stage or format |
| [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) | AI coding agent | Workflow patterns, cache gotchas, anti-patterns |
| [`docs/PPT_KNOWN_ISSUES.md`](docs/PPT_KNOWN_ISSUES.md) | v1.2 implementer | Triaged PPT bugs with fix proposals |
| [`docs/INTERNAL/HANDOFF.md`](docs/INTERNAL/HANDOFF.md) | Next maintainer | Verified state, where to make changes, known limitations |
| [`CHANGELOG.md`](CHANGELOG.md) | Anyone | Release-by-release diff |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | External contributor | Branch, test, PR norms |

## License

MIT — see [`LICENSE`](LICENSE).
