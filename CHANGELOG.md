# CHANGELOG

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
