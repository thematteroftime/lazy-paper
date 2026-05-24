# lazy-paper — Production Hand-off

> **Status:** shipped · **Tests:** 300/300 pass (2 deselected `-m live`) · **End-to-end verified on 9-paper variant test + 18-paper v1.9.2 corpus + v1.11.1 sentence-level audit** · **Last release:** v1.11.2 (2026-05-24, erratum: `scripts/audit_grep.py` + "Audit pitfall" TEST_FRAMEWORK note)
>
> **v1.11.2** is a tooling/erratum release — zero pipeline behaviour
> changed vs v1.11.1. Cycle 12 audit #1 flagged ali2025_flash ch13 as
> fabricating three baseline values; two independent meta auditors then
> falsified the report (OCR-tokenised LaTeX char streams `1 7 . 3` —
> plain `grep` misses). A hotfix candidate added a prompt rule + numeric
> verifier advisory and was reverted before commit after specs confirmed
> real regressions on real chapters. Ship: `scripts/audit_grep.py` (the
> OCR-tolerant replacement) + "Audit pitfall" section in TEST_FRAMEWORK
> so subagent audits don't repeat the methodology error.
>
> **Known v1.11.3 candidate** (deferred for its own diagnostic cycle):
> meng2024 ch06 binds `W_rec=5.00 J/cm³ / η=90.09%` to "180 kV/cm"
> (source: 340 kV/cm) + fabricates `E_b=214 kV/cm` (no such value);
> meng2024 ch07 dropped its `5.00 J/cm³` reference between v1.10 and
> v1.11.1. A single-line cap fix attempt (retriever cap 12→24) was
> tried and reverted (no fix on ch06, -60% chapter collapse). The real
> root cause is structural to the v1.10→v1.11.1 STRUCTURED-path
> migration and needs a dedicated audit cycle, not a one-line patch.
>
> **v1.11.1** lands 4 HIGH bug fixes caught by a cycle-11 sentence-level
> audit (3 subagents cross-checking output vs source paper). v1.11.0
> passed the architecture-review ship gate but did NOT push; v1.11.1 is
> the first stable of the v1.11 line.
>
> - **Bug #1+#2 (flagship metric drift)** — meng2024 ch07/09/13/15 had
>   three different W_rec values for the same flagship sample. Fix:
>   extract `headline_metrics` from the KG (`mat_main --has_W_rec-->`)
>   into `context.yaml` as a hard ground-truth block; prompt now
>   instructs composer to use those exact numbers.
> - **Bug #3 (author misattribution)** — meng2024 ch13 attributed
>   Ma et al.'s result to Cao et al. Fix: post-verify advisory
>   `author_not_in_chunk_advisory`; default advisory,
>   `LAZY_PAPER_AUTHOR_HARDREJECT=1` promotes to hard reject.
> - **Bug #4 (OCR text-prompt as physics figure)** — hif_2 ch15
>   fabricated a critique of "图 43" which was actually an unCLIP
>   appendix figure whose OCR'd caption was the literal generation
>   prompt. Fix: two-layer caption-stub filter
>   (`is_generation_prompt_caption`) at s04 + s07 defense-in-depth.
> - **Bilingual regression prevention** — `cli.py` writes
>   `meta.yaml.lang`; s07 emits stderr WARNING when `lang=zh` but the
>   first 5 visual_summary entries are < 30 % CJK chars; s09 builder
>   localises Untitled fallback chapter heading to "未命名章节".
>
> **v1.11.0** was a first-principles refactor (commit `a4d90ab`) that
> cut 3 over-engineered modules from v1.10: cross-citation reject
> (~40 LOC), figure-retry pass (~85 LOC), headline-metric prompt rule.
> Rationale recorded in `docs/ARCHITECTURE.md` §11.
>
> **v1.10.0** ships **Variant C — figure_ids hard constraint**: schema-level
> figure citation + figure-retry pass + env-gated whitelist. Picked from a
> 3-variant × 9-paper × 3-audit-cycle test (33 LLM runs, 9 specialist
> auditors). Hits true 100% figure embedding on multi-figure papers
> (ali2025_flash 26/26, hif_1 20/20, hif_2 17/17), preserves meng2024 T1
> = 9/9/9 zero-variance, and breaks baseline on ali2025_flash T4 (4→5).
> Also ships `normalize_ocr_latex` BS3+BS4 (LaTeX escape collapsing +
> Unicode NFKD) to lift verifier accuracy across all variants. Full
> validation in `docs/v1_10_variant_comparison.md`.
>
> **v1.9.2** lands 8 high-impact bug fixes (2-auditor + 3-reviewer +
> 2-confirmation cycle) on top of v1.9.0's informed-retry. The fixes
> preserve meng2024 T1 = 9/9/9 zero variance across 18-paper validation
> (13 corpus + 5 newly OCR'd). HTML clickable citations are now the
> default for end users. Full report: `docs/v1_9_2_20_paper_validation.md`.
>
> **v1.9.0 ships informed-retry that eliminates meng2024 T1 variance.**
> The previous retry-when-empty used a generic "you missed required
> mentions" instruction. v1.9 now generates a per-entity diagnosis listing
> each missing required mention with its specific anchor token
> (author surname OR linked numeric value), giving the LLM a deterministic
> checklist instead of a vague reminder. Three independent meng2024 runs
> all score exactly **9/17** on T1 benchmark recovery — variance reduced
> from stdev 2.6 (v1.8.1) to **stdev 0** (v1.9). Full corpus validation
> + analysis in `docs/v1_9_validation_results.md`.
>
> **v1.8.x foundations remain unchanged.** Strategy KL is still the
> recommended high-quality default. The verifier normalizes LaTeX/OCR
> forms before substring matching (so good comparator-citing claims are no longer rejected for whitespace
> differences in `$W _ { \mathrm { rec } }$` etc.); the retry-when-empty
> trigger measures coverage POST-verify, so it fires when the verifier
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
| `LAZY_PAPER_RETRY_THRESHOLD` | No | `0.5` | Post-verify coverage at or below which the retry-when-empty call fires. `0` means retry only when ALL required mentions are missing |
| `LAZY_PAPER_MIN_SECTION_CHARS` | No | `500` | If the verified section is shorter than this, fire one extra retry asking the LLM to thicken it. `0` disables length-based retry |
| `LAZY_PAPER_MIN_SECTION_CLAIMS` | No | `4` | Same as above but on claim count. Either condition triggers retry |
| `LAZY_PAPER_HTML_CITATIONS` | No | `hyperlink` | HTML citation rendering: `hyperlink` (clickable per-claim anchors + sources footer), `keep`, or `remove` |
| `LAZY_PAPER_FIGURE_BIND` | No | unset | `1` enables figure-section binding: for each section, the top-4 topically-relevant figures are surfaced in the compose prompt so the LLM doesn't cite an off-topic figure. Off by default; observed regression on meng2024 T1 when on, so use selectively. |
| `LAZY_PAPER_FIGURE_ID_WHITELIST` | No | `1` (on) | v1.10. Verifier strips unknown `fig_id`s from accepted claims and replaces in-text `Fig. N` / `图N` with the lang-aware `UNKNOWN_FIGURE_LABEL`. Set `0` to revert to advisory-only. |
| `LAZY_PAPER_AUTHOR_HARDREJECT` | No | `0` (advisory) | v1.11.1. When `1`, post-verify drops any claim whose author-surname mentions don't appear in any cited chunk text. Default is advisory (`author_not_in_chunk_advisory` recorded in `critic_flags.yaml`); promote to hard reject only after telemetry confirms precision on your corpus. |
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

Most recent validation: **v1.10 — 3-variant × 9-paper × 3-audit-cycle test
(2026-05-23)**, full report in `docs/v1_10_variant_comparison.md`. Plus
the v1.8.x 13-paper corpus (`docs/v1_8_2_corpus_validation.md`, 2026-05-21)
that established Strategy KL as production-ready.

Headline numbers under **Variant C** (winner, v1.10 default with
`LAZY_PAPER_FIGURE_BIND=1`):

| Paper | Pipeline | M2 fig embed | M4 TestCase |
|---|---|---|---|
| meng2024 (3 runs) | 15/15 each | 7/7 (100%) | T1 = 9/9/9 (stdev 0) ✓ floor; T3 = 4/4/4 |
| yang2025 | 15/15 | 5/5 | T2 = 3/3 ✓ |
| fu2020 | 15/15 | (baseline only) | T5 = 3/4 ✓ |
| chai2026 | 15/15 | 2/2 | T6 = 4/4 ✓ |
| ali2025_flash | 15/15 | **26/26 (100%)** | T4 = **5/5 🏆 (broke baseline 4)** |
| gaur2022 | 15/15 | 1/1 | generic ✓ |
| he2023 | 15/15 | 8/8 (100%) | generic ✓ |
| pan2025 | 15/15 | 4/4 | generic ✓ |
| hif_1 (Adv Mat survey, 62p, v1.10 +) | 15/15 | **20/20 (100%)** | (cross-domain) |
| hif_2 (DALL-E 2, 17 figs, v1.10 +) | 15/15 | **17/17 (100%)** | (cross-domain) |

For variant A/B M2/M4 comparison + zero-variance stdev table, see
`docs/v1_10_variant_comparison.md` §3.

**Important — environment unlocks M2 figure binding**: the 100% column
above requires `LAZY_PAPER_FIGURE_BIND=1`. Without it, variant C still
benefits (LLM volunteers figure refs from the base prompt + schema
captures them), but rate is lower — see `.env.example` for the full
recommended env combo and `docs/v1_10_variant_comparison.md §7` for
the env-on vs env-off numbers.

DOCX + HTML are always produced. PDF / PPTX are produced only when the
`--formats` flag includes them; the v181 corpus runs above produced docx+html
only. Output path: `runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`.

**Tests**: 300 (2 deselected `-m live`). Run with `uv run pytest -q`.

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
3. Read `docs/AGENT_GUIDE.md` for the AI-specific workflow (subagent patterns, when to dispatch, current best practices distilled from the v1.0 → v1.11 release cycle).
4. Always run `uv run pytest -q` before and after any change.
5. When extending the pipeline, follow the stage layout: `stages/sNN_<name>/runner.py` + `stages/sNN_<name>/tests/`. Register in `cli.py::STAGE_ORDER`.
6. When extending PPT layout, edit `stages/s09_render/renderers/pptx.py` and bump the relevant `_PROMPT_VERSION` in `pptx_summarizer.py` if you change anything that affects LLM prompts (cache invalidation).
7. End-to-end verification on at least 2 papers is the bar before push. Use the 5 verified papers in `runs/`.

---

## 10. Release history

Full per-version details in `CHANGELOG.md`. Highlights:

- **v1.11.1** (2026-05-24): 4 HIGH bug fixes from cycle-11 sentence-level audit (flagship metric drift, author misattribution, OCR text-prompt-as-figure, bilingual regression prevention). 300 tests.
- **v1.11.0** (2026-05-23, not pushed): first-principles refactor (`a4d90ab`) — cut cross-citation reject, figure-retry pass, headline-metric prompt rule (3 over-engineered modules deleted). 297 tests.
- **v1.10.0** (2026-05-23): Variant C — figure_ids hard constraint, picked from a 3-variant × 9-paper × 3-audit-cycle test. Hits 100% figure embedding on multi-figure papers; meng2024 T1 = 9/9/9 zero variance.
- **v1.9.2** (2026-05-22): 8 high-impact bug fixes from a 2-auditor + 3-reviewer + 2-confirmation cycle; HTML clickable citations become default.
- **v1.9.0** (2026-05-22): informed-retry — per-entity diagnosis with anchor tokens; meng2024 T1 stdev 2.6 → **0**.
- **v1.8.x** (2026-05-21): Strategy KL becomes recommended default (LaTeX/OCR normalization in verifier, retry-when-empty post-verify); meng2024 T1 floor 1 → 12.
- **v1.7 / v1.6 / v1.5** (2026-05-20 / 19): KL → J → strategy-matrix evaluation harness (`scripts/evaluate.py`), 4-step v1.4 plan executed.
- **v1.4 plan** (planning, 2026-05-20, rewritten after 2nd research pass): research-validated **4-step** roadmap (archived `docs/archive/v1_4_roadmap.md`). Category-correct anchor projects: **Microsoft GraphRAG** + **ByteDance DeerFlow** + **OpenScholar / AllenAI** + **agentic-rag-for-dummies**. Architecture: PaperKG extractor + hierarchical parent-child hybrid retriever + 15× section sub-agents + two-tier critic.
- **v1.3.3** (2026-05-20): dynamic section-divider layout. Per-bullet height measured from estimated wrap count; bullets placed cumulatively with constant 0.18" inter-bullet gap; card stretches from 4.5" to up to 5.4" when content needs it; font shrinks only as last resort. Also `_read_fig_notes` recovers caption/deep_observation from `raw` field via regex when s07 YAML defensive-parse failed (fixed ali2025_flash Fig. 28 blank-looking slide).
- **v1.3.2** (2026-05-20): whitespace-vs-truncate audit. `_BULLET_CAP_TABLE` recalibrated so every density allows multi-line wrap (2-3 lines per bullet) rather than 1-line + ellipsis. Section-divider ellipsis rate dropped 42% → 2.9% across the 10-paper corpus while preserving the 4.5" card height — bullets now fill the available vertical room with content instead of leaving it blank.
- **v1.3.1** (2026-05-20): hardening release. 8 PPT defects from per-slide audit fixed: `_combined` obs overlap, sparse-card autofit clip, single-obs space waste, caption-header 50/55-char cut, 7-bullet cap too tight, soft-accept on quant-validation failure (catastrophic for EN papers), Priority-3 fallback `[:60]` mid-word cut, chapter prompt lang directive, fallback obs 200-char truncation, exotic Unicode punctuation. Corpus expanded 4→10 papers (added fu2020 / ge2025 / chai2026 / pamula2025 / meng2024 / gaur2022). New `scripts/audit_pptx.py` per-slide validator. 189 tests.
- **v1.3.0** (2026-05-19): quality release. Post-LLM **quantitative-content validation** (chapter ≥1 quant bullet; paper ≥3 + comparative takeaway; figure observations rejected if all-descriptive). **Adaptive PPT layout**: outline rows auto-fit by wrap count, KEY POINTS card density-adaptive (16→13pt), figure-obs vertical guard. **Loud failure logging** at all 3 summarizer methods. s08 sees more context: figure-obs 100→400 chars, caption 120→300, chapter excerpts 8000→15000 (full text for ≤8-chapter papers). Cross-renderer table styling unified. README + README.zh redesigned with real PPT showcase images. 178 tests. Verified end-to-end on 4 papers covering EN+ZH, single-crystal/review/theoretical/thin-film topics.
- **v1.2.2** (2026-05-19): PPT outline now honors `--lang en` (was producing Chinese group names regardless). `_lang_directive` injected into `pptx_outline.md`; `_OUTLINE_PROMPT_VERSION` v12→v13. `_is_low_diversity` refactored to per-language regimes (CJK substrings vs English word tokens) with stricter "appears in every group" threshold — eliminates English false-positives.
- **v1.2.1** (2026-05-19): s05_template auto-invalidates when source docx changes (SHA-256 of docx in `done.yaml`); CLI logs "[s05_template] template content changed — invalidating cache" on auto-rerun. Fixes a class of bugs where pre-v15 stale Chinese-prefixed titles propagated into output for papers OCR'd before the template was English-ified.
- **v1.2.0** (2026-05-19): two PPT visual bugs (Unicode subscript font fallback, KEY POINTS card overlap on ≥6 bullets) — resolved. `_math.py` collapses Latin Unicode subscripts to `_<plain>`; `_section_divider` scales font down at n_bullets≥6; `SlidePlanner._truncate_bullet` caps length. 164 tests.
- **v1.1.0** (2026-05-19): outline LLM call max_tokens raised + env ceiling; chapter heading numbering unified; deep-observation font 11→13pt; CLI `--only` comma-split + unknown-stage validation; image-data-url helper consolidated; 158 tests.
- **v1.0.0** (2026-05-18): initial public release. 4 output formats, 9-stage pipeline, docker + bare-metal install paths.

---

## 11. Audit trail (cycle 10 → 12)

| Cycle | Date | Type | Headline finding |
|---|---|---|---|
| cycle 10 | 2026-05-22 | 5-paper variance check | v1.9.1 |
| cycle 10b | 2026-05-22 | 18-paper validation | v1.9.2 — 8 bug fixes |
| cycle 11 | 2026-05-23 | 3-variant × 9-paper matrix | v1.10.0 Variant C selected |
| cycle 11b | 2026-05-23 | architecture review | v1.11.0 cut 3 modules |
| cycle 11c | 2026-05-24 | sentence-level audit (3 subagents) | v1.11.1 — 4 HIGH bugs fixed |
| cycle 12 | 2026-05-24 | Audit A/B/C/D docs review | Stale scripts/tests deleted, historical docs archived, v1.11.1 docs synced |
