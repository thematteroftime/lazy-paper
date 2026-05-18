# CHANGELOG

## v0.6 — multi-format renderer + PPT v9 academic-defense design (2026-05-18)

### Multi-format renderer (s09_render redesign)

- `s09_render` rebuilt around a format-neutral document model (`model.py`) and a shared builder (`builder.py`) that assembles the model from stage YAML. Four independent renderer classes live in `stages/s09_render/renderers/`: `docx.py`, `pdf.py`, `html.py`, `pptx.py`.
- HTML and PDF renderers use a Jinja2 template (`templates/preview.html.j2` + `templates/styles.css`). PDF is rendered via WeasyPrint from the same HTML; the two formats share one template pass.
- Soft-failure semantics: if one renderer raises, the other formats complete. Failed formats are recorded in `done.yaml` as `formats.<fmt> = {error: ...}` and `done.yaml.partial = true`.
- `--retry-failed` flag re-runs only the formats recorded as failed in the prior `done.yaml`. Used with `--only s09_render`.
- Docker image bumped to Python 3.11; apt layer adds `libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8` for WeasyPrint.
- macOS local path: `conftest.py` and `cli.py` auto-augment `DYLD_FALLBACK_LIBRARY_PATH` so WeasyPrint finds the brew-installed Pango/Cairo without shell-level export.

### New CLI flags

- `--formats <fmt,...>` — select any subset of `docx,pdf,html,pptx`; default is `docx,pdf,html`.
- `--pptx-bullets {llm,rule}` — `llm` (default) uses the cached LLM summarizer; `rule` extracts bullets deterministically from s08 YAML without LLM calls.
- `--pptx-template <file.pptx>` — use a custom slide master for the PPTX renderer.
- `--pptx-subtitle <text>` — subtitle line on the PPT title slide.
- `--presenter <name>` — presenter name on the PPT title slide.
- `--affiliation <lab>` — affiliation line on the PPT title slide.
- `--only <stage>` — run only the named stage (e.g. `--only s09_render`).
- `--retry-failed` — combined with `--only s09_render`, re-renders only formats marked failed.

### PPT academic-defense design (v9 final)

- Visual identity: cream background (#FFFDF5), charcoal text (#1C1C1C), serif display font for titles, sans-serif body.
- Section divider slides: left-anchored label + right key-points card with ❶❷❸❹❺ numbered bullets.
- Content slides: combined bullets + figure layout; ◇ markers for figure observation lines.
- Closing slide: 5–7 analytical bullets + single highlighted take-away sentence drawn from `summarize_paper` LLM call.
- Two new LLM calls per paper (both cached in `llm_cache/`): `summarize_outline` (groups 11 template chapters into 4–5 logical sections via `pptx_outline.md` prompt) and `summarize_paper` (5–7 closing bullets + takeaway via `pptx_paper_summary.md` prompt). Per-chapter `summarize` call is already cached from s06–s08.
- `pptx_summarizer.py` manages cache read/write and both LLM calls. `slide_planner.py` maps the document model + outline grouping to a slide sequence.

### Math normalization

- `stages/s09_render/_math.py` — `normalize_math()` converts common LaTeX Greek letters (η, σ, α, …) and sub/sup notation (^{3}, _{2}) to Unicode. Serves as a safety-net for any LaTeX that slips through LLM prompts requesting Unicode directly.

### Code cleanup

- Dead code and redundant helpers removed: -176 lines net across s09_render and cli.py.
- All 134 tests pass (up from 51 at v0.5 baseline).

## v0.5 — MinerU as default, 46-paper batch (2026-05-17)

- `OCR_BACKEND` default changed from `paddleocr` to `mineru` (empirically wins on figure completeness and Wiley sidebar exclusion).
- Both backends remain supported; switch via env var.
- Batch-converted 47 PDFs (46 unique by content) from `参考文献/弛豫反铁电/` + `参考文献/可能用到文献/`. All produce clean previews and mypaper bundles under `runs/<paper_id>/`.
- `upload/` final deliverable: 45 `preview.docx` (one per unique source PDF filename; two cross-folder filename duplicates collapse to one each). Each file named `<original-pdf-stem>.docx` for easy lookup.
- Existing `test_dispatch_default_is_paddleocr` renamed to `test_dispatch_default_is_mineru` to reflect the new default.
- Hand-off documentation added: `HANDOFF.md`.
- Tests: 51 passed.

## v0.4 — MinerU backend (2026-05-17)

- Added `stages/s01_ocr/mineru.py`: ~170-line MinerU cloud API client (POST `/file-urls/batch` → PUT signed URL → poll `/extract-results/batch/<id>` → unzip → `_content_list_to_docs`).
- `stages/s01_ocr/runner.py::run(*, pdf, out_dir, token, backend=None)` now dispatches by `backend` arg or `OCR_BACKEND` env var. Default = `paddleocr` (existing behavior preserved). New value: `mineru`.
- `cli.py` resolves the backend-specific token (`PADDLEOCR_TOKEN` vs `MINERU_TOKEN`) and passes it to `_s01.run`.
- `.env.example` adds `OCR_BACKEND=paddleocr` and `MINERU_TOKEN=` rows.
- 3 new unit tests in `stages/s01_ocr/tests/test_mineru.py`: per-page split, empty-page skip, sequential image numbering.
- Caption-number injection: `_ensure_figure_number` repairs MinerU OCR's occasional "Figure ." (missing digit) by inferring N from sequential image order. Validated on li2022 (Fig. 2's caption was "Figure ." in MinerU output; fix maps it to "Figure 2." correctly).
- Verified on li2022 (7/7 figs clean, Fig. 5 complete with full η axis) and zhang2025_thinfilms (13/13 figs clean, no Wiley sidebar bleed on Fig. 8/12).
- Tests: 48 passed total.

## v0.3 — visual-verified figure handling (2026-05-17)

- s04 caption pairing requires `caption_start > img_start` (directional). Prevents Fig.N+1's panels being attributed to Fig.N when they sit between Fig.N's caption and Fig.N+1's caption in markdown order.
- s04 `_merge_figure_subpanels` reinstated for multi-bbox figures, with uniform scale calibration (`min(sx, sy)` from per-page image-vs-bbox ratios) — avoids non-uniform stretching that previously caused vertical bleed.
- s04 `_merge_figure_subpanels` `margin_paddle_units` default lowered from 10 → 0 — prevents right-edge spillover into adjacent text columns.
- s04 `_expand_to_neighbors` (gap-fill) DISABLED by default — empirically the "gaps" are mostly body paragraphs PaddleOCR correctly excluded; expanding into them imports body text. Single-bbox figures stay as PaddleOCR detected.
- Stage 04 figures.yaml now uses `Fig_N_merged.jpg` naming for all merged outputs (was inconsistent before).
- DRY: shared `bbox_from_filename` / `BBOX_FROM_NAME` / `DOC_PAGE` consolidated in `stages/_common.py`.
- Validated on 8 real papers (he2023, li2022, pamula2025, zhang2025_ttb, yang2025_neuro, pan2025_tunable, pan2024_clamp, meng2024_moderate, zhang2025_thinfilms). All multi-bbox figures produce clean composites; remaining limitations are PaddleOCR detection gaps (single-bbox figures may miss panel edges; Wiley journals have a vertical sidebar text strip that can leak).

## v0.2 — bilingual + cross-platform (2026-05-17)

- Added `--lang en|zh` CLI flag plumbed through s07, s08, s09.
- s09_render switches font (Times New Roman only for en, +宋体 EastAsia for zh) and dimensions (11pt/14cm vs 10.5pt/13cm).
- README + Dockerfile + docker-compose.yml + .env.example added for Win/Mac/Linux/Docker portability.
- s09_render embeds each Fig.N at most once (dedup); supports Chinese figure references (图N) in body.
- High-DPI re-render (300 DPI from PDF via pypdfium2) applied automatically at end of s01_ocr — replaces PaddleOCR's ~130 DPI crops.

## v0.1 — initial folder-per-stage architecture

- 9 stages: s01_ocr → s02_clean → s03_chapter → s04_figures → s05_template → s06_context → s07_figure_analyze → s08_section_compose → s09_render
- LLM client supports OpenAI-compatible vision+text roles (Qwen-VL, DeepSeek, others via env-configurable base_url).
- Each LLM call audited via *.prompt.md / *.response.json files in run directory.
- YAML for all intermediate artifacts; mypaper-compatible bundle output.
