# paper2md — Production Hand-off

> Status: **shipped**. 134/134 tests pass. 18 papers (current batch) + 46 historical papers processed end-to-end. 4 output formats: DOCX, PDF, HTML, PPTX.

---

## 1. What this project does

paper2md is a 9-stage pipeline that accepts a scientific PDF and a Markdown outline template (`.docx`) and produces `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}` (any combination of the four formats, controlled by `--formats`) plus `runs/<paper_id>/s09_render/mypaper_bundle/`, a set of chapter Markdown files + extracted figures + README that drop directly into the `mypaper/` thesis-typesetting project. OCR is handled by MinerU (default) or PaddleOCR-VL. All LLM inference runs through user-supplied OpenAI-compatible endpoints (Qwen-VL for vision, DeepSeek for text by default).

---

## 2. Quick Start

### Lane A — Local (macOS / Linux)

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Set up venv and install deps
uv sync && uv pip install -e .[dev]

# 3. Configure credentials
cp .env.example .env   # fill in MINERU_TOKEN, LLM_VISION_API_KEY, LLM_TEXT_API_KEY

# 4. Run the pipeline
uv run python -m cli run \
  --pdf "参考文献/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper --lang zh
```

### Lane B — Local (Windows PowerShell)

```powershell
# 1. Install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Set up venv and install deps
uv sync; uv pip install -e .[dev]

# 3. Configure credentials
Copy-Item .env.example .env   # fill in tokens in your editor

# 4. Run the pipeline
uv run python -m cli run `
  --pdf "参考文献/your-paper.pdf" `
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" `
  --paper-id mypaper --lang zh
```

### Lane C — Docker

```bash
# 1. Build image (~250 MB, no model weights bundled)
docker build -t paper2md .

# 2. Configure credentials
cp .env.example .env   # fill in tokens

# 3. (Optional) use docker compose — volumes pre-wired
#    or run directly:
docker run --rm \
  -v "$(pwd)/runs:/app/runs" \
  -v "$(pwd)/参考文献:/app/参考文献" \
  -v "$(pwd)/.env:/app/.env:ro" \
  paper2md run \
    --pdf "/app/参考文献/your-paper.pdf" \
    --template "/app/Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id mypaper --lang zh

# 4. Outputs appear in runs/<paper_id>/s09_render/
```

Useful flags: `--force` re-runs completed stages; `--skip-ocr` reuses existing s01 artifacts; `--lang en` for English output; `--formats docx,pdf,html,pptx` to select output formats; `--only s09_render --retry-failed` to re-render only the formats that failed in a prior run.

PPT-specific flags: `--pptx-bullets {llm,rule}` (default: `llm`); `--pptx-template <file.pptx>` to use a custom slide master; `--pptx-subtitle <text>`; `--presenter <name>`; `--affiliation <lab>`.

---

## 3. Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OCR_BACKEND` | No | `mineru` | `mineru` or `paddleocr` — selects OCR backend |
| `MINERU_TOKEN` | If `OCR_BACKEND=mineru` | — | API token from https://mineru.net/ |
| `PADDLEOCR_TOKEN` | If `OCR_BACKEND=paddleocr` | — | Token from Baidu AI Studio |
| `LLM_VISION_BASE_URL` | Yes | — | Base URL for the vision LLM (e.g. DashScope Qwen-VL endpoint) |
| `LLM_VISION_API_KEY` | Yes | — | API key for the vision LLM |
| `LLM_VISION_MODEL` | No | `qwen-vl-max` | Model name for vision LLM |
| `LLM_TEXT_BASE_URL` | Yes | — | Base URL for the text LLM (e.g. DeepSeek endpoint) |
| `LLM_TEXT_API_KEY` | Yes | — | API key for the text LLM |
| `LLM_TEXT_MODEL` | No | `deepseek-chat` | Model name for text LLM |

All variables can be set in `.env` (copied from `.env.example`). See `llm/models.yaml` for defaults.

---

## 4. Architecture Overview

```
PDF ──┬─ s01_ocr ──→ s02_clean ──→ s03_chapter ──→ s04_figures ──┐
      │                                                           │
template.docx ── s05_template ─────────────────────────────────── ┤
                                                                  │
                                              s06_context         │ (LLM text)
                                              s07_figure_analyze  │ (LLM vision)
                                              s08_section_compose │ (LLM text)
                                              s09_render ─────────┘
                                                  │
                           runs/<paper_id>/s09_render/
                               ├── preview.docx        (--formats docx)
                               ├── preview.pdf         (--formats pdf, via WeasyPrint)
                               ├── preview.html        (--formats html, base64 images)
                               ├── preview.pptx        (--formats pptx, LLM-grouped slides)
                               ├── llm_cache/          (per-chapter + outline + summary cache)
                               └── mypaper_bundle/     (chapter MDs + figures + README)
```

**Dataflow**: s01 converts the PDF to per-page Markdown + image crops. s02–s04 clean text, split sections, and extract figure/table metadata into YAML. s05 parses the `.docx` outline into a structured template. s06–s08 call the LLMs to build context, analyze figures, and compose section prose. s09 assembles the output: `builder.py` constructs a format-neutral document model from stage YAML; each renderer (`renderers/docx.py`, `renderers/pdf.py`, `renderers/html.py`, `renderers/pptx.py`) independently emits its format. The PPTX renderer additionally invokes `pptx_summarizer.py` for two cached LLM calls (`summarize_outline` and `summarize_paper`) and uses `slide_planner.py` to lay out the slide sequence. Math normalization (`_math.py::normalize_math`) converts any residual LaTeX Greek/sub/sup escapes to Unicode. If one format fails (e.g. WeasyPrint on a corrupt image), the remaining formats complete and the failure is recorded in `done.yaml` for targeted retry via `--only s09_render --retry-failed`. Every stage writes its artifacts to `runs/<paper_id>/<stage>/`; every LLM call persists `.prompt.md` / `.response.json` files for traceability. Stages are independently re-runnable via `--force`.

---

## 5. Key Empirical Findings (Figure Extraction)

- **MinerU uses DocLayout-YOLO to detect whole figures** as single bounding boxes at native PDF resolution; PaddleOCR-VL segments figures panel-by-panel, requiring post-processing in `s04_figures::_merge_figure_subpanels` to reconstruct composite figures.
- **Wiley layout sidebar contamination**: Wiley journals render a narrow vertical sidebar (journal branding text). PaddleOCR-VL sometimes includes this stripe in the rightmost panel's crop. MinerU's whole-figure detection cleanly excludes it. Confirmed on `zhang2025_thinfilms` Fig. 8 and Fig. 12.
- **Panel-top clipping**: Single-bbox figures from PaddleOCR can lose the top few pixels of a panel when the caption immediately precedes the figure in reading order and the bbox snaps to caption geometry. MinerU is robust here because DocLayout-YOLO predicts figure extent independently of caption position. Confirmed on `li2022` Fig. 5 (η/Wrec scatter — full η=60–100 axis visible with MinerU, clipped with PaddleOCR).
- **Validated on 18 papers (current batch)** from `参考文献/弛豫反铁电/` plus 46 historical papers, spanning NBT, AN, PMN, KNN, and PbZrO₃ ceramic families. Current-batch highlights: he2023, ali2025_flash (26 figures), pamula2025 (5 figs), zhang2025_thinfilms (Wiley layout), meng2024 (14 figs). Zero crashes across all runs.

---

## 6. Known Limitations

- **LLM paraphrasing in s08**: The section composer (`s08_section_compose`) sometimes produces lightly paraphrased summaries rather than tight analytical prose. Tune the system/user prompt in `llm/prompts/section_compose.md` for your domain vocabulary and desired depth.
- **Figure–caption pairing assumes markdown order**: s04 pairs captions to the nearest preceding image in the Markdown produced by s01/s02. This assumption holds for scholarly PDFs after MinerU or PaddleOCR layout normalization, but may fail on unusual multi-column layouts where captions appear far from their figures in reading order.
- **LaTeX in captions**: Math-heavy figure captions are passed through `_math.py::normalize_math()` which converts common Greek letters and sub/sup notation to Unicode. Unusual or deeply nested LaTeX constructs that normalize_math does not cover will pass through as raw LaTeX; consider a targeted pre-processing pass on `figures.yaml::caption` fields for very heavy notation domains.
- **PPT slide text assumes one dominant LLM-text role**: The PPTX renderer works best when each section has a clear analytical narrative. Papers with highly technical, dense equation-per-line prose (e.g. pure theory sections) may produce slides with long single bullets that benefit from manual editing.
- **WeasyPrint on Windows**: PDF rendering requires the GTK runtime (Pango/Cairo). On Windows we recommend the Docker path; `docx`, `html`, and `pptx` formats work without GTK.

---

## 7. Where to Make Changes

| Goal | File / Action |
|---|---|
| Add a new outline template | Pass `--template <new>.docx` — no code change needed |
| Switch LLM provider | Edit `LLM_*_BASE_URL` / `LLM_*_MODEL` in `.env` (any OpenAI-compatible API) |
| Change output language | Pass `--lang en` or `--lang zh` |
| Select output formats | Pass `--formats docx,pdf,html,pptx` (any subset; default is `docx,pdf,html`) |
| Retry a failed format | Pass `--only s09_render --retry-failed` |
| Add a new pipeline stage | Create `stages/sNN_<name>/runner.py` with a `run(**kwargs)` signature; register it in `cli.py::STAGE_ORDER` |
| Tune figure merging (PaddleOCR path) | `stages/s04_figures/runner.py` — `_merge_figure_subpanels`, `margin_paddle_units`, `_expand_to_neighbors` |
| Adjust LLM prompts | `llm/prompts/paper_context.md`, `figure_analyze.md`, `section_compose.md` |
| Adjust PPT-specific prompts | `llm/prompts/pptx_summarize.md` (per-chapter), `pptx_outline.md` (section grouping), `pptx_paper_summary.md` (closing slide) |
| Customize PPT slide master | Pass `--pptx-template <file.pptx>` — the renderer applies its layout over the given master |
| Customize PPT title slide | Pass `--presenter`, `--affiliation`, `--pptx-subtitle` |
| Switch PPT bullet mode | Pass `--pptx-bullets rule` (no LLM calls) or `--pptx-bullets llm` (default, cached) |
| Change default OCR backend | Set `OCR_BACKEND` in `.env.example` and document; code dispatch is in `stages/s01_ocr/runner.py` |

---

## 8. Files You May Safely Delete

These are development artifacts that are not part of the production pipeline:

| Path | Notes |
|---|---|
| `runs/<paper_id>/s01_ocr/` | Large raw OCR output. Re-generatable with `--force`. Keep if you want to skip re-OCR. |
| `runs/<paper_id>/*/\*.prompt.md` | LLM audit trail. Safe to delete; re-generated on re-run. |
| `runs/<paper_id>/*/\*.response.json` | LLM audit trail. Same as above. |
| `paper2md.egg-info/` | pip editable-install metadata. Recreated by `uv pip install -e .` |
| `docs/` | Internal design notes from development. Not referenced by the pipeline. |

Do NOT delete `runs/<paper_id>/s09_render/` — that's the final output.

---

## 9. What's Been Verified

- ✓ **134/134 unit tests pass** (`uv run pytest -v`)
- ✓ **18 papers (current batch) processed end-to-end** from `参考文献/弛豫反铁电/`; all produce clean `preview.{docx,pdf,html,pptx}` and `mypaper_bundle/`
- ✓ **46 historical papers** (prior batch) produce clean `preview.docx` and `mypaper_bundle/`
- ✓ **he2023** — end-to-end with all 4 output formats; PPT outline grouping + closing slide verified
- ✓ **ali2025_flash** — 26 figures; all embedded correctly across docx, html, pptx
- ✓ **pamula2025** — 5 figures; no WeasyPrint failures
- ✓ **zhang2025_thinfilms** — Wiley layout, 13 figures; zero sidebar contamination with MinerU; PPT layout clean
- ✓ **meng2024** — 14 figures; Rietveld refinement + SAED panels merged correctly
- ✓ **liu2022** — XRD / Raman / dielectric multi-panel figures extracted cleanly
- ✓ **li2022** — η/Wrec scatter with full y-axis (60–100 %); MinerU fix confirmed vs PaddleOCR clip
- ✓ **Math normalization**: Greek + sub/sup in LLM output rendered correctly via `_math.py::normalize_math()`
- ✓ **Soft failure**: simulated WeasyPrint failure — remaining formats complete; `done.yaml.partial=true` set; `--retry-failed` re-runs only the failed format
- ✓ **LLM cache**: re-run with unchanged input uses zero LLM calls for PPT (cache hit on all chapters + outline + summary)
- ✓ **Cross-platform**: macOS (DYLD_FALLBACK_LIBRARY_PATH auto-set for WeasyPrint), Linux, Windows (PowerShell + uv), Docker (Python 3.11, Pango/Cairo/gdk-pixbuf/libffi via apt) — all launch paths tested
- ✓ **All 5 milestone tags on main**: m1-common-split, m2-docx-migrated, m3-html-pdf-added, m4-pptx-added, m5-complete

---

## 10. Sister Project

`mypaper_bundle/` output is designed to feed **`mypaper/`** (thesis-grade typesetting project, separate repo). Each bundle contains:
- `chapters/<section_slug>.md` — composed bilingual section prose
- `figures/Fig_N.jpg` — extracted figures at ≥300 DPI
- `README.md` — figure inventory with captions

The `mypaper/` project reads these files directly — no conversion step needed.
