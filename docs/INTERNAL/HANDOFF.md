# lazy-paper — Production Hand-off

> **Status:** shipped · **Tests:** 250/250 pass · **End-to-end verified on 13+ papers** (10-paper v1.8.2 corpus + 3-paper v1.8.1 stability validation) · **Last release:** v1.8.2 (2026-05-21)
>
> **v1.8.1 makes Strategy KL the recommended high-quality default.** Fixes
> two compose-side bugs that caused v1.7 KL's 1 – 13 variance: (a) the
> verifier now normalizes LaTeX/OCR forms before substring matching, so
> good comparator-citing claims are no longer rejected for whitespace
> differences in `$W _ { \mathrm { rec } }$` etc.; (b) the retry-when-empty
> trigger now measures coverage POST-verify, so it fires when the verifier
> has just dropped comparator claims and one strengthened LLM call can
> recover them. On meng2024 ch01 (the headline benchmark-recovery test):
> v1.8.1 KL = floor 12/17, mean 15.0, range 12–17 (was floor 1, mean 5.0
> in v1.7 KL). No regressions on yang2025/fu2020/chai2026. See
> `docs/v1_8_validation_results.md` for full analysis.
>
> v1.4.x foundations (PaperDB / two-tier critic / Onyx citation
> processor) remain unchanged. The pydantic-ai section agent
> (`LAZY_PAPER_AGENT=1`) is still opt-in. See CHANGELOG.md for the full
> v1.4.0 → v1.8.1 release trail.

This is the doc to read first if you are picking the project up cold — whether you are a human maintainer or an AI agent. It tells you what exists, what works, what's been verified, and where to make changes.

---

## 1. What this project does

`lazy-paper` is a 9-stage pipeline that turns a scientific paper PDF + a Markdown outline template (`.docx`) into a multi-format deep-analysis document set: DOCX, PDF, HTML, and PPTX. Each stage writes to `runs/<paper_id>/<stage>/` and is independently re-runnable.

- **OCR**: MinerU (default, figure-aware) or PaddleOCR-VL
- **Text LLM**: any OpenAI-compatible endpoint (DeepSeek-Reasoner by default)
- **Vision LLM**: any OpenAI-compatible endpoint (Qwen-VL by default)
- **Output**: `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`

---

## 2. Quick start

```bash
# Install
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"

# Configure
cp .env.example .env       # then fill in MINERU_TOKEN + LLM_*_API_KEY

# Run end-to-end
uv run python -m cli run \
  --pdf "papers/he2023.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id he2023 --lang zh \
  --formats docx,pdf,html,pptx
```

WeasyPrint (PDF) needs system libs:

```bash
# macOS
brew install pango gdk-pixbuf libffi cairo

# Linux/Docker
# Already in Dockerfile; for bare-metal Linux: apt install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

Docker users: `docker compose build && docker compose run --rm lazy-paper run --pdf ...`

---

## 3. Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OCR_BACKEND` | No | `mineru` | `mineru` or `paddleocr` |
| `MINERU_TOKEN` | If `OCR_BACKEND=mineru` | — | API token from https://mineru.net/ |
| `PADDLEOCR_TOKEN` | If `OCR_BACKEND=paddleocr` | — | Token from Baidu AI Studio |
| `LLM_VISION_BASE_URL` | Yes | DashScope | OpenAI-compatible base URL for vision LLM |
| `LLM_VISION_API_KEY` | Yes | — | Vision LLM key |
| `LLM_VISION_MODEL` | No | `qwen-vl-max-latest` | Vision model name |
| `LLM_TEXT_BASE_URL` | Yes | DeepSeek | OpenAI-compatible base URL for text LLM |
| `LLM_TEXT_API_KEY` | Yes | — | Text LLM key |
| `LLM_TEXT_MODEL` | No | `deepseek-reasoner` | Text model name |
| `LLM_MAX_TOKENS_CEILING` | No | `40000` | Caps `max_tokens` for every LLM call (single knob to constrain spend or quota) |
| `LLM_EMBEDDINGS_BATCH_SIZE` | No | `10` | Per-batch size when embedding chunks in the retriever (`llm/retriever.py`) |
| `LAZY_PAPER_STRUCTURED` | No | unset | `1` enables instructor-based structured compose with verifier (recommended for v1.8.1+) |
| `LAZY_PAPER_KG_PROMPT` | No | `paper_kg.md` | KG-extraction prompt file. Use `paper_kg_v3.md` for author-entity extraction (Strategy L) |
| `LAZY_PAPER_BEST_OF_N` | No | `1` | Number of independent draft samples per section. `2` enables Strategy K best-of-N merge |
| `LAZY_PAPER_VERIFIER_THRESHOLD` | No | `0.85` | Minimum quote-vs-chunk substring/fuzzy match score |
| `LAZY_PAPER_RETRY_THRESHOLD` | No | `0.5` | Post-verify coverage at or below which the retry-when-empty call fires. `0` disables retries |
| `LAZY_PAPER_AGENT` | No | unset | `1` enables the experimental pydantic-ai tool-calling agent compose path |
| `LAZY_PAPER_TWO_STEP` | No | unset | `1` enables the experimental outline→expand two-step compose path |
| `LAZY_PAPER_WHOLE_PAPER` | No | unset | `1` injects the whole paper text into each section compose (high cost) |
| `LAZY_PAPER_COVERAGE` | No | unset | `1` adds entity-coverage flags to `critic_flags.yaml` |
| `LAZY_PAPER_CHUNK_SIZE` | No | `400` | Retriever chunk size (chars) |
| `LAZY_PAPER_CHUNK_OVERLAP` | No | derived | Retriever chunk overlap |
| `LAZY_PAPER_HIERARCHICAL` | No | unset | `1` enables parent-child hierarchical retrieval |
| `LAZY_PAPER_PARENT_SIZE` | No | `2000` | Parent chunk size when hierarchical retrieval is on |
| `LAZY_PAPER_PARENT_OVERLAP` | No | `200` | Parent chunk overlap |
| `MINERU_BASE_URL` | No | `https://mineru.net/api/v4` | MinerU API base URL (override for self-hosted/proxy) |
| `MINERU_TIMEOUT_S` | No | `1800` | Hard deadline for MinerU polling (large PDFs may need more) |
| `MINERU_POLL_S` | No | `10` | MinerU poll interval |
| `PADDLEOCR_BASE_URL` | No | `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs` | PaddleOCR API endpoint |
| `PADDLEOCR_MODEL` | No | `PaddleOCR-VL-1.5` | PaddleOCR model name |
| `PADDLEOCR_TIMEOUT_S` | No | `1800` | Hard deadline for PaddleOCR polling |
| `PADDLEOCR_POLL_S` | No | `5` | PaddleOCR poll interval |

---

## 4. Architecture, one paragraph

PDF → 9 stages → 4 output formats. s01–s04 do OCR / cleaning / chaptering / figure extraction (deterministic, no LLM). s05 parses the outline template. s06–s08 are the three LLM-driven stages (paper context, per-figure analysis, per-chapter composition). s09 builds an immutable `Document` model and dispatches to 4 renderers (docx/html/pdf/pptx), each one a stateless subclass of `Renderer`. The PPTX renderer additionally invokes `PptxSummarizer` for 4–5 section grouping (`summarize_outline`), per-chapter bullets (`summarize`), and the closing slide (`summarize_paper`); these are cached on input-hash so re-runs are zero-LLM when inputs are unchanged. Every LLM call writes its prompt + response to disk for audit. Every stage writes `done.yaml` and is skipped on re-run unless `--force`. See `docs/ARCHITECTURE.md` for the full per-stage breakdown.

```
PDF ──┬─ s01_ocr → s02_clean → s03_chapter → s04_figures ──┐
      │                                                     │
template.docx ── s05_template ─────────────────────────── ──┤
                                                            │
                                          s06_context       │ (text LLM)
                                          s07_figure_analyze│ (vision LLM)
                                          s08_section_compose│(text LLM)
                                          s09_render ───────┘
                                              │
                       runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}
```

---

## 5. Verified state

End-to-end validated on a 13-paper corpus under Strategy KL (v1.8.1+). Most
recent comprehensive run: 2026-05-21, full report in
`docs/v1_8_2_corpus_validation.md`.

| Paper | Pipeline | Notable score |
|---|---|---|
| meng2024 (3 runs) | 15/15 chapters each | T1 benchmark recovery 12 / 17 / 16 (mean 15.0, floor 12) |
| yang2025 | 15/15 | T2 fabrication-resistance 3/3 ✓ |
| fu2020 | 15/15 | T5 basic 3/4 ✓ |
| chai2026 | 15/15 | T6 basic 4/4 ✓ |
| ali2025_flash | 15/15 | T4 comparison depth 0/5 ⚠ (LLM sampling variance; see corpus report) |
| gaur2022 | 15/15 | generic ✓ (retry-when-empty fires 2×) |
| ge2025 | 15/15 | generic ✓ (retry 2×) |
| he2023 | 15/15 | generic ✓ |
| liu2022 | 15/15 | generic ✓ |
| pamula2025 | 15/15 | generic ✓ (retry 3×) |
| pan2025 | 15/15 | generic ✓ (retry 2×) |
| randall2021 | 15/15 | generic ✓ |
| yao2022 | 15/15 | generic ✓ |

DOCX + HTML are always produced. PDF / PPTX are produced only when the
`--formats` flag includes them; the v181 corpus runs above produced docx+html
only. Output path: `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`.

**Tests**: 250 (2 deselected `-m live`). Run with `uv run pytest -q`.

---

## 6. Where to make changes

| Goal | File / action |
|---|---|
| Add a new outline template | Pass `--template <new>.docx` (no code change) |
| Switch LLM provider | Edit `LLM_*_BASE_URL` / `LLM_*_MODEL` in `.env` (any OpenAI-compatible) |
| Change output language | Pass `--lang en` or `--lang zh` |
| Select output formats | Pass `--formats docx,pdf,html,pptx` (subset of `docx,pdf,html,pptx`) |
| Retry a failed format | Pass `--only s09_render --retry-failed` |
| Add a new pipeline stage | See "Adding a new LLM stage" in `docs/ARCHITECTURE.md` |
| Tune figure merging | `stages/s04_figures/runner.py::_merge_figure_subpanels()` |
| Adjust LLM prompts | `llm/prompts/{paper_context,figure_analyze,section_compose,pptx_outline,pptx_summarize,pptx_paper_summary}.md` |
| Customize PPT title/subtitle | `--presenter`, `--affiliation`, `--pptx-subtitle` |
| Customize PPT slide master | `--pptx-template <file.pptx>` |
| Switch PPT bullet mode | `--pptx-bullets {llm,rule}` |
| Constrain LLM cost | Set `LLM_MAX_TOKENS_CEILING` (e.g. `8000` to keep under quota) |

---

## 7. Known limitations

- **LLM paraphrasing in s08**: section composer can produce slightly paraphrased summaries instead of tight analytical prose. Tune `llm/prompts/section_compose.md` for your domain vocabulary.
- **Figure–caption pairing**: s04 pairs captions to the nearest preceding image in OCR'd Markdown. Robust for standard scholarly layouts; may misalign on multi-column papers with very distant caption placement.
- **LaTeX in captions**: `_math.py::normalize_math()` covers Greek + common sub/sup. Heavy nested LaTeX may pass through raw.
- **PPT density**: papers with dense equation-per-line prose (theory-heavy) may produce slides with long single bullets that benefit from manual editing.
- **WeasyPrint on Windows**: needs the GTK runtime (Pango/Cairo). Use Docker, or stick to docx/html/pptx without GTK.
- **Outline groups can repeat across same-template papers**: if 18 papers share the same `template.docx`, their s09 outline groups may end up structurally similar because the chapter headings are identical. Mitigated by paper-specific keyword injection in `llm/prompts/pptx_outline.md`; not eliminable without per-paper templates.

---

## 8. Files you may safely delete

| Path | Notes |
|---|---|
| `runs/<paper_id>/s01_ocr/` | Large raw OCR output. Re-generatable with `--force`. Keep if you want to skip re-OCR. |
| `runs/<paper_id>/*/*.prompt.md` and `*.response.json` | LLM audit trail. Safe to delete; re-generated on re-run. |
| `lazy_paper.egg-info/` | Editable-install metadata. Recreated by `uv pip install -e .` |
| `__pycache__/` anywhere | Recreated by Python. |
| `runs/<paper_id>/s09_render/llm_cache/` | Cache for PPT LLM calls. Deleting forces full re-summarization on next run. |

Do **not** delete `runs/<paper_id>/s09_render/preview.*` — those are the final outputs.

---

## 9. AI agent quickstart

If you are an LLM-driven coding agent picking up this repo:

1. Read this file first.
2. Read `docs/ARCHITECTURE.md` for the stage-by-stage contract.
3. Read `docs/AGENT_GUIDE.md` for the AI-specific workflow (subagent patterns, when to dispatch, anti-patterns observed during the v1.0–v1.1 development).
4. Always run `uv run pytest -q` before and after any change.
5. When extending the pipeline, follow the stage layout: `stages/sNN_<name>/runner.py` + `stages/sNN_<name>/tests/`. Register in `cli.py::STAGE_ORDER`.
6. When extending PPT layout, edit `stages/s09_render/renderers/pptx.py` and bump the relevant `_PROMPT_VERSION` in `pptx_summarizer.py` if you change anything that affects LLM prompts (cache invalidation).
7. End-to-end verification on at least 2 papers is the bar before push. Use the 5 verified papers in `runs/`.

---

## 10. Release history

- **v1.4 plan** (planning, 2026-05-20, rewritten after 2nd research pass): research-validated **4-step** roadmap in `docs/v1_4_content_roadmap.md`. Category-correct anchor projects: **Microsoft GraphRAG** (entity/KG grounding) + **ByteDance DeerFlow** (scoped sub-agent pattern) + **OpenScholar / AllenAI** (scientific self-reflective citation-grounded gen) + **agentic-rag-for-dummies** (LangGraph-shaped reference impl). Architecture: (1) PaperKG extractor (one LLM pass per paper, GraphRAG-stripped to single-doc mode); (2) hierarchical parent-child hybrid retriever (~200 LOC); (3) 15× section sub-agents with self-reflection retrieve-or-commit gate; (4) two-tier critic — Python regex first (numeric / Fig.N / chem-formula → grep source), LLM critic only if regex flags. **LangGraph still rejected** — lift the node-shape semantics ~150 LOC; no framework dep. Cost +50% per paper (regex tier does most verification for free). ~9 days; can split as v1.3.4 (steps 1+2+4a, 5 days) → v1.4.0 (steps 3+4b, 4 days). First draft (PaperQA2 / STORM / Sakana / DSPy) **dropped** — wrong categories. Awaiting maintainer greenlight.
- **v1.3.3** (2026-05-20): dynamic section-divider layout. Per-bullet height measured from estimated wrap count; bullets placed cumulatively with constant 0.18" inter-bullet gap; card stretches from 4.5" to up to 5.4" when content needs it; font shrinks only as last resort. Also `_read_fig_notes` recovers caption/deep_observation from `raw` field via regex when s07 YAML defensive-parse failed (fixed ali2025_flash Fig. 28 blank-looking slide).
- **v1.3.2** (2026-05-20): whitespace-vs-truncate audit. `_BULLET_CAP_TABLE` recalibrated so every density allows multi-line wrap (2-3 lines per bullet) rather than 1-line + ellipsis. Section-divider ellipsis rate dropped 42% → 2.9% across the 10-paper corpus while preserving the 4.5" card height — bullets now fill the available vertical room with content instead of leaving it blank.
- **v1.3.1** (2026-05-20): hardening release. 8 PPT defects from per-slide audit fixed: `_combined` obs overlap, sparse-card autofit clip, single-obs space waste, caption-header 50/55-char cut, 7-bullet cap too tight, soft-accept on quant-validation failure (catastrophic for EN papers), Priority-3 fallback `[:60]` mid-word cut, chapter prompt lang directive, fallback obs 200-char truncation, exotic Unicode punctuation. Corpus expanded 4→10 papers (added fu2020 / ge2025 / chai2026 / pamula2025 / meng2024 / gaur2022). New `scripts/audit_pptx.py` per-slide validator. 189 tests.
- **v1.3.0** (2026-05-19): quality release. Post-LLM **quantitative-content validation** (chapter ≥1 quant bullet; paper ≥3 + comparative takeaway; figure observations rejected if all-descriptive). **Adaptive PPT layout**: outline rows auto-fit by wrap count, KEY POINTS card density-adaptive (16→13pt), figure-obs vertical guard. **Loud failure logging** at all 3 summarizer methods. s08 sees more context: figure-obs 100→400 chars, caption 120→300, chapter excerpts 8000→15000 (full text for ≤8-chapter papers). Cross-renderer table styling unified. README + README.zh redesigned with real PPT showcase images. 178 tests. Verified end-to-end on 4 papers covering EN+ZH, single-crystal/review/theoretical/thin-film topics.
- **v1.2.2** (2026-05-19): PPT outline now honors `--lang en` (was producing Chinese group names regardless). `_lang_directive` injected into `pptx_outline.md`; `_OUTLINE_PROMPT_VERSION` v12→v13. `_is_low_diversity` refactored to per-language regimes (CJK substrings vs English word tokens) with stricter "appears in every group" threshold — eliminates English false-positives.
- **v1.2.1** (2026-05-19): s05_template auto-invalidates when source docx changes (SHA-256 of docx in `done.yaml`); CLI logs "[s05_template] template content changed — invalidating cache" on auto-rerun. Fixes a class of bugs where pre-v15 stale Chinese-prefixed titles propagated into output for papers OCR'd before the template was English-ified.
- **v1.2.0** (2026-05-19): two PPT visual bugs (Unicode subscript font fallback, KEY POINTS card overlap on ≥6 bullets) — resolved. `_math.py` collapses Latin Unicode subscripts to `_<plain>`; `_section_divider` scales font down at n_bullets≥6; `SlidePlanner._truncate_bullet` caps length. 164 tests.
- **v1.1.0** (2026-05-19): outline LLM call max_tokens raised + env ceiling; chapter heading numbering unified; deep-observation font 11→13pt; CLI `--only` comma-split + unknown-stage validation; image-data-url helper consolidated; 158 tests.
- **v1.0.0** (2026-05-18): initial public release. 4 output formats, 9-stage pipeline, docker + bare-metal install paths.
