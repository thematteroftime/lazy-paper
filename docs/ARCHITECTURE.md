# lazy-paper architecture

> A maintainer-level reference for the 9-stage pipeline that turns a PDF research paper into bilingual DOCX/PDF/HTML/PPTX deep analysis. Code version **v1.19-garden** (2026-06-12). 390 pytest tests. This file covers the per-paper pipeline; the knowledge-base loop layered on top (library / synthesize / experiments / advise / garden, v1.14-v1.19) is documented in [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md).
>
> Install, CLI flags, and provider setup live in [README.md](../README.md) and [USER_GUIDE.md](USER_GUIDE.md). This file is the "how the system works" side.
>
> A Chinese version with the same structure (and a few extra design notes) lives at [`docs_zh/ARCHITECTURE.md`](../docs_zh/ARCHITECTURE.md).

---

## Contents

1. [One-line definition](#1-one-line-definition)
2. [Design philosophy](#2-design-philosophy)
3. [Directory layout](#3-directory-layout)
4. [Pipeline overview (s01 → s09)](#4-pipeline-overview-s01--s09)
5. [s08_section_compose internals](#5-s08_section_compose-internals)
6. [Figure pipeline (s04 + s07 + s09)](#6-figure-pipeline-s04--s07--s09)
7. [Template system (s05 + placeholders)](#7-template-system-s05--placeholders)
8. [LLM client (`llm/client.py`)](#8-llm-client-llmclientpy)
9. [Test layout](#9-test-layout)
10. [Configuration and env vars](#10-configuration-and-env-vars)
11. [v1.11 design decisions](#11-v111-design-decisions)
12. [Known limits / v1.12 candidates](#12-known-limits--v112-candidates)

---

## 1. One-line definition

lazy-paper turns one scientific PDF + one `.docx` section-outline template into **four files** (DOCX / PDF / HTML / PPTX) in either Chinese or English. One command, nine stages, every step resumable.

"Deep analysis" means each section carries quantitative anchors (real numbers), citation markers (`[span:doc:start-end]`), and figure references bound to real `fig_id`s — a critical reading of the paper, not a summary. The LLM output shape is enforced by `instructor`-validated Pydantic models.

---

## 2. Design philosophy

### 2.1 Why nine stages instead of one big LLM call?

A single mega-prompt for "PDF → deep analysis" runs into four walls:

- **No cache.** Edit one prompt line and you re-run OCR (minutes + dollars).
- **No audit.** When an answer is wrong, which step caused it?
- **No parallelism.** Stages cannot fail and retry independently.
- **No context window.** A 30-page paper + 20 figures + outline easily passes 100K tokens.

So lazy-paper splits work into nine stages. Each stage **reads the previous stage's output directory, writes its own, and drops a `done.yaml` marker**.

- Any stage failure resumes from the last `done.yaml` on the next run.
- Any prompt change can be retried locally with `--force --only s08_section_compose`.
- Every LLM call writes `<name>.prompt.md` and `<name>.response.json` to disk for review.

### 2.2 Strict Pydantic schemas (Strategy J / KL)

s06 (KG extraction) and s08 (section compose) both wrap the LLM call in `instructor` so the response must satisfy a Pydantic model:

```python
class GroundedClaim(BaseModel):
    text: str = Field(min_length=2)
    cited_chunk_ids: list[int] = Field(default_factory=list)
    cited_quote: str = ""
    figure_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("cited_chunk_ids")
    def _check_chunk_ids(cls, ids, info):
        allowed = info.context.get("allowed_chunk_ids")
        if allowed and any(i not in allowed for i in ids):
            raise ValueError(...)   # instructor will retry
        return ids
```

The LLM must return JSON that matches the schema, or `instructor` retries (`max_retries=3`). The validator also rejects "cited a chunk that was never injected" — a common hallucination. This **pre-injected candidates + schema validation** pattern (Perplexity-style) is the heart of s08 grounding.

### 2.3 What "Strategy KL" means

Strategy KL is the recommended s08 compose path since v1.8.1. Three env vars switch it on:

```bash
LAZY_PAPER_STRUCTURED=1               # instructor compose + per-claim verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md   # KG extracts author entities, linked to comparators
LAZY_PAPER_BEST_OF_N=2                # two LLM samples per section, round-robin merge
```

Together they lifted literature-citation recovery on meng2024 from ~10 to a stable 15 / 17 (mean across three runs).

The letters: **K** = best-of-N merge, **L** = structured compose + verifier. Code lives in `_STRUCTURED_SYSTEM`, `_single_compose`, `_merge_drafts`.

### 2.4 Stay simple

Per project `CLAUDE.md`: every changed line must trace to a request, no speculative abstractions, no abstractions for single call sites.

v1.11 was a first-principles refactor (commit `a4d90ab`) that **deleted** three over-engineered modules (cross-citation reject 40 LOC + figure-retry pass 85 LOC + ad-hoc headline-metric prompt rule). See §11.

---

## 3. Directory layout

```
paper2md/
├── cli.py                       # only entrypoint: parse args → chain 9 stages
├── conftest.py                  # macOS-only DYLD_FALLBACK_LIBRARY_PATH shim for pytest
├── pyproject.toml               # uv-managed; 3.11+; setuptools build
├── .env.example                 # every env var documented
├── llm/
│   ├── client.py                # OpenAI-compatible client + max_tokens ceiling
│   ├── models.yaml              # role config: vision / text / embeddings
│   ├── retriever.py             # hybrid retrieval: BM25 + dense + RRF + entity boost
│   ├── paper_kg.py              # PaperKG (Entity / Relation, parquet I/O)
│   ├── prompts/                 # 8 system+user prompt files
│   └── citation/                # [span:doc:start-end] marker rendering (Onyx port)
├── stages/
│   ├── _common/                 # slugify / stage_dir / yaml_io / mark_done / normalize_ocr_latex
│   ├── s01_ocr/                 # PDF → OCR → doc_*.md + imgs/
│   ├── s02_clean/               # strip running headers / repair chars / flag corrupted columns
│   ├── s03_chapter/             # split by IMRaD anchor (bilingual)
│   ├── s04_figures/             # pair figures + captions; merge panels; build mentions map
│   ├── s05_template/            # parse outline .docx into a tree
│   ├── s06_context/             # LLM extracts paper context + KG (instructor)
│   ├── s07_figure_analyze/      # one vision-LLM call per figure
│   ├── s08_section_compose/     # the heavy stage — template-driven grounded prose
│   └── s09_render/              # four renderers (docx / pdf / html / pptx)
├── tests/                       # top-level pytest (CLI / retriever / KG / citation / harness)
├── docs/                        # English docs (you are here)
├── docs_zh/                     # Chinese docs (same shape)
├── scripts/                     # audit_pptx / evaluate / fetch_katex / pdffigures2_sidecar
├── templates/                   # outline-template `.docx` examples
└── runs/                        # per-run artifacts + outputs (gitignored)
```

Tests live in two places: each stage has a `tests/` subdirectory next to it (locality), and `tests/` at the repo root covers CLI, shared libraries, and cross-stage integration. See §9.

---

## 4. Pipeline overview (s01 → s09)

```
                                                 ┌──▶ preview.docx
PDF  +  outline.docx                             ├──▶ preview.pdf
       │                                         ├──▶ preview.html
       ▼                                         └──▶ preview.pptx
  s01_ocr  ▶  s02_clean  ▶  s03_chapter ─┐
                                         │
  s04_figures ─────────┐                 ├─▶ s09_render
                       ├─▶ s06_context ──┤        ▲
  s05_template ────────┤    (+ KG)       │        │
                       │                 │        │
  s07_figure_analyze ──┴─▶ s08_section_compose ───┘
                              (Strategy KL: retriever + verifier + retry)
```

Each stage's entrypoint is `runner.py::run(...)` with keyword args, dispatched by `cli.py::_run_one()`. `STAGE_ORDER` is fixed in `cli.py:46-50`.

### 4.1 s01_ocr — PDF to markdown + images

| Field | Value |
|---|---|
| **Input** | `.pdf` + token (MinerU or PaddleOCR) |
| **Output** | `doc_<N>.md` (one per page) + `imgs/<bbox-encoded>.jpg` |
| **Key files** | `stages/s01_ocr/runner.py`, `stages/s01_ocr/mineru.py` |
| **Entrypoint** | `runner.py::run()` dispatches on `OCR_BACKEND` env to `_mineru.run` or `_run_paddleocr` |

Two backends:
- **MinerU** (`OCR_BACKEND=mineru`, default) — better image quality, better fit for figure-heavy papers.
- **PaddleOCR-VL** (`OCR_BACKEND=paddleocr`) — alternative. Runner polls the cloud job until `state=done`.

**upscale_images** (`runner.py:29-202`): PaddleOCR returns ~130-DPI crops, too blurry. Runner re-renders the source PDF page at 300 DPI via `pypdfium2`, then re-crops using the bbox encoded in the filename (`..._X1_Y1_X2_Y2.jpg`). The decoder is `bbox_from_filename` in `stages/_common/bbox.py`.

### 4.2 s02_clean — OCR post-processing

| Field | Value |
|---|---|
| **Input** | `s01_ocr/doc_*.md` + `imgs/` |
| **Output** | Same shape, cleaned text |
| **Key file** | `stages/s02_clean/runner.py` |

Three jobs:
1. **`strip_running_headers`** (`runner.py:11`) — short lines repeating ≥3 times across pages get dropped (headers / footers).
2. **`repair_chars`** (`runner.py:31`) — `(cid:0)` → `−`; bare `O 2` → `O₂` (oxide subscript repair).
3. **`flag_corrupted_column_flow`** (`runner.py:46`) — lines where single-character tokens exceed 60 % get a `<!-- corrupted-column-flow -->` comment so downstream can skip them without losing the text.

### 4.3 s03_chapter — split by IMRaD anchor

| Field | Value |
|---|---|
| **Input** | `s02_clean/doc_*.md` |
| **Output** | `chapters/chapter_<NNN>_<slug>.md` + `chapter_index.yaml` |
| **Key file** | `stages/s03_chapter/runner.py` |

**Bilingual section anchors live in `SECTION_ANCHORS`** (`runner.py:14-27`):
```python
SECTION_ANCHORS = {
    # English IMRaD
    "abstract", "introduction", "methods", "results", "discussion",
    "conclusion", "references", ...
    # Chinese equivalents
    "摘要", "引言", "实验", "结果", "讨论", "结论", "参考文献", ...
}
```

**Adding a new language** starts here: drop the matching titles into this set. Without it, a paper in the new language collapses into one chapter and everything downstream breaks.

`detect_science_anchor` (`runner.py:37`) matches `[# number] [chapter no.] <Title>` with `_ANCHOR_LINE_RE`. The title must start with `[A-Z一-鿿]`. On a match, `flush()` finalises the accumulated lines into a chapter.

**Number-prefix recognition (v1.13)**: the chapter-number group accepts arabic (`1.`, `2.3.`) **or** roman (`I.`, `II.`, `III.`, …). IEEE / conference papers whose top-level sections are roman-numbered previously collapsed into one big `Preface` chapter; with roman support they split correctly. The v1.13 expansion also added `related work / background / problem statement / approach / system overview / evaluation / ablation / limitations / future work` and their Chinese equivalents to `SECTION_ANCHORS` so robotics / RL paper structures register.

### 4.4 s04_figures — pair figures, merge panels, build mention map

| Field | Value |
|---|---|
| **Input** | `s02_clean/doc_*.md` + `s03_chapter/chapters/` + the source PDF |
| **Output** | `figures.yaml`, `tables.yaml`, `mentions.yaml` |
| **Key file** | `stages/s04_figures/runner.py` |

**Bilingual regex (top-level constants)** (`runner.py:18-26`):
```python
FIG_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*((?:Fig(?:ure)?\.?|图)\s*\d+[A-Za-z]?)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
TAB_CAP_RE = re.compile(r"(?:^|<div[^>]*>)\s*((?:Table|表)\s*\d+)...")
FIG_MENTION_RE = re.compile(r"(?:Fig(?:ure)?\.?|图)\s*(\d+)([a-z])?", re.IGNORECASE)
```

To add a language, extend the `Fig(?:ure)?\.?|图` alternation with the new prefix. This is what v1.11 added — before that, Chinese papers lost every figure mention.

**`_normalize_fig_id`** (`runner.py:29`) collapses `Fig 3`, `Figure 3a`, `图 3` into the canonical `Fig. 3` / `Fig. 3a`. Every downstream stage (s07, s09, s08 figure binding) keys on this canonical form.

**`_merge_figure_subpanels`** (`runner.py:135`) takes panel crops that share a `fig_id` (e.g. `Fig. 3` has a/b/c) and merges them into one union-bbox image re-rendered from the PDF. Per-page scale is calibrated by `_calibrate_scale`, with `min(sx, sy)` uniform scaling so we don't stretch one axis and bleed into a neighbouring figure.

`mentions.yaml` is a reverse index `{chapter_filename: [Fig. 1, Fig. 3, ...]}` that s07 uses to pull surrounding text.

**`is_generation_prompt_caption` (v1.11.1, `runner.py:28-56`)** is a caption-stub filter. It drops captions matching `(letter) A/An <curated descriptor> <medium> of …` (typical example: the DALL-E paper's OCR returned the literal generation prompt `(a) A high quality photo of a dog playing in a green field next to a lake.` — `hif_2` Fig 43 was being fed to vision-LLM as physics). This is the first of two defence layers; s07 skips again (see §4.7). The descriptor list is strict so real captions like `"(a) SEM image of NBST"` survive.

**MinerU `chart`-vs-`image` typing (v1.13, `stages/s01_ocr/mineru.py`)**. MinerU's `content_list.json` classifies scientific plots (line / bar / scatter) as `type: chart` with `chart_caption`, and photographs / vector diagrams as `type: image` with `image_caption`. Before v1.13 `_content_list_to_docs` only walked `image`, so a figure-rich text-PDF whose plots are all `chart` (e.g. arXiv:2403.20001v2 returned 16 raw `images/` files but only 2 `image`-typed entries) lost 10/12 figures and mis-labeled the two survivors. Fix: handle both types, fall back to `chart_caption` when `image_caption` is empty. Same fix flow makes `_ensure_figure_number` skip number injection for sub-panel captions like `"(a) Straight Line Walking"` — s04's nearest-caption pairing then correctly groups the four panels under the real `Fig. 3:` caption that sits a few lines below.

**PDFFigures 2 reconciliation (v1.12 phase 1, opt-in, `runner.py:374+`)** — when `--pdffigures2` is set and `PDFFIGURES2_JAR=docker` is in env, s04 invokes AI2's PDFFigures 2 sidecar (`scripts/pdffigures2_sidecar.py` → docker → JSON) after the MinerU pass. `reconcile_with_pdffigures2()` matches each MinerU figure against pdffigures2's caption-anchored figure list via bag-of-words Jaccard ≥0.5 and overwrites `fig_id` to the canonical "Figure N" the paper itself prints. Audit trail at `_pdffigures2.yaml`. **Docker-only by design**: project policy bans host JVM installs; the Dockerfile (`Dockerfile.pdffigures2`) is a 2-stage build (sbtscala → eclipse-temurin-jre) producing `lazy-paper/pdffigures2:0.1.0`. Closes the v1.12 known limit "caption-aware numbering" from §12. Default OFF until measured impact lands.

### 4.5 s05_template — parse the outline docx

| Field | Value |
|---|---|
| **Input** | user-supplied `.docx` outline (e.g. `Table of Contents-Relaxor AFE-ZGY-HW.docx`) |
| **Output** | `template.yaml` (tree) + `done.yaml` (with `template_sha256_16` fingerprint) |
| **Key file** | `stages/s05_template/runner.py` |

**`parse_template`** (`runner.py:89`) walks `python-docx` paragraphs and uses style (List Paragraph vs normal) plus a numbering regex (`_NUMBERED_RE`) to decide whether a line is a new section heading or guidance under the previous one. `_is_guidance_line` (`runner.py:50`) filters out `(`, `-`, `→`, leading-lowercase, and verb-starters (`"Provide"`, `"Discuss"`) — clearly instructions, not section titles.

**Fingerprint cache (`is_cache_stale`, `runner.py:161`)** — `done.yaml` records `template_sha256_16`. The CLI calls `is_cache_stale` from `_run_one()`. When the user edits the docx, s05 auto-invalidates on the next run — no `--force` needed (added in v1.10; before, edits silently propagated stale titles to the output).

### 4.6 s06_context — paper context + KG

| Field | Value |
|---|---|
| **Input** | `s03_chapter/chapters/` |
| **Output** | `context.yaml`, `paper_kg.parquet`, `paper_kg.rel.parquet` |
| **Key files** | `stages/s06_context/runner.py`, `stages/s06_context/kg_extract.py` |

Two independent LLM calls:

**Step 1 — paper context** (`runner.py:52`): text LLM reads the abstract / intro and extracts title, system, keywords, key_terms, abbreviations. Result lands in `context.yaml` and is consumed by every downstream stage.

**Step 2 — KG extraction** (`kg_extract.py::build_paper_kg`): `instructor` forces the LLM to return a `PaperKG` (`llm/paper_kg.py`). 10 / 11-type closed schema:
```
material, dopant, parameter, value, unit, figure, table,
claim, method, comparator, author  (author added in v1.7 KG-v3)
```

Each Entity carries `source_span = (doc_name, char_start, char_end)`, used by s08's `build_required_mentions` to pin the entity back to its retrieval chunk.

**Soft-degrade on failure**: the LLM may fail schema parsing, parquet may not write, source may be empty. The failure writes a `kg_extract.failed` marker; s08 sees the marker and falls back to the v1.3.3 legacy compose path. **KG failure never breaks the rest of the pipeline.**

**Step 3 — headline_metrics injection (v1.11.1)**: after KG build, the runner reads `mat_main --has_W_rec--> value` / `--has_eta-->` relations and writes the flagship sample's headline numbers into a `headline_metrics` block in `context.yaml`:

```yaml
headline_metrics:
  flagship: "0.8Bi(Mg0.5Ti0.5)O₃-0.2BaTiO₃"
  W_rec: 5.00
  eta: 90.09
```

The "FLAGSHIP GROUND TRUTH" block in `llm/prompts/section_compose.md` reads these numbers and pins the composer to them rather than letting it scavenge a comparator's neighbouring value (the v1.10 meng2024 ch07/09/13/15 cross-chapter `W_rec` drift bug). Implementation: `stages/s06_context/runner.py:73-86` + `kg_extract.py:61`.

**Prompt switching**: `LAZY_PAPER_KG_PROMPT=paper_kg_v3.md` uses the 11-type prompt (with author); default `paper_kg.md` is the 10-type. Strategy KL requires v3 because the compose prompt depends on `<Author> et al.` citation form.

**Step 4 — entity dedup (v1.12 phase 1, opt-in)**: when `LAZY_PAPER_ENTITY_DEDUP=1`, the runner adds a LightRAG-inspired disambiguation pass after KG build. A single LLM call (T=0.1, ≤4K tokens) clusters variant mentions of the same real-world entity within one type ("Meng et al." + "Meng 2024" + "本工作" → one canonical author). The canonical id is the first member of each cluster; relations are remapped and triples deduped; `paper_kg.parquet` is re-written so downstream stages see the canonical KG. Defends against the v1.11.1 Bug #3 (author misattribution) class at the extraction layer rather than another verifier rule. Soft-degrades to inputs on LLM failure or malformed JSON; defensive `_ensure_coverage` adds singleton clusters for any id the LLM forgot so dedup never silently drops entities. Implementation: `stages/s06_context/entity_dedup.py` (140 LOC) + `llm/prompts/entity_dedup.md`. Audit in `done.yaml.extra.entity_dedup` (before/after counts).

### 4.6.5 prompt_tailor (v1.12 phase 4, opt-in)

When `LAZY_PAPER_PROMPT_TAILOR=1`, s06_context appends a cheap pre-stage
LLM call after KG extraction. It reads:

- `context.yaml` (just-written): title, system, abbreviations, keywords,
  key_terms, headline_metrics
- `chapters_dir/chapter_001_INTRODUCTION.md` first 3000 chars (or empty
  if no intro)

It emits `prompt_augment.yaml` with four top-level keys:

| Key | Purpose |
|---|---|
| `domain_framing` | 2-3 sentence prose about what THIS paper is and does |
| `terminology` | list of {term, note} pairs drawn from THIS paper's text |
| `metric_patterns` | list of {kind, regex} matching numeric patterns in THIS paper |
| `comparator_style` | {format, example_from_paper} citation template + real instance |

s08 calls `_render_augment_block(aug)` to render these four blocks as a
markdown prefix, prepended to `_STRUCTURED_SYSTEM` before every compose
LLM call (see `compose_structured`'s `augment_block` kwarg). The prefix
applies to best-of-N initial draft pair, retry-when-empty, and
retry-when-short branches — all 4 call sites use a local `system_prompt`
variable that resolves to `augment_block + _STRUCTURED_SYSTEM` when an
augment is present, else just `_STRUCTURED_SYSTEM` (byte-identical
fallback when the flag is OFF).

**Design rationale.** Phase 3c tried to make `_STRUCTURED_SYSTEM`
domain-agnostic by adding "Smith et al. ResNet-50 on ImageNet" examples
alongside the materials ones. RAGAS regressed (meng2024 −9pp, ali2025
−4pp) — the LLM treated the extra examples as permission to drift.
Phase 4 reverses the design: the static prompt stays clean and focused
(materials-tuned methodology), while a per-paper augment block does
runtime specialization. Generalization moves from prompt-body to
architecture. Measured Phase 4 result: meng2024 0.55→0.68 (+13pp);
ali2025 0.49→0.67 (+18pp).

**Soft-degrade.** Any pre-stage failure (PromptTailorError, LLM transport,
unexpected exception) writes a `prompt_tailor.failed` marker and s06
completes normally. s08 sees no `prompt_augment.yaml` and falls back to
the vanilla `_STRUCTURED_SYSTEM` — pipeline never blocks.

Implementation: `stages/s06_context/prompt_tailor.py` (~95 LOC) + `llm/prompts/prompt_tailor.md` (40 lines).

### 4.7 s07_figure_analyze — vision LLM per figure

| Field | Value |
|---|---|
| **Input** | `s04_figures/figures.yaml` + `s04_figures/mentions.yaml` + `s03_chapter/chapters/` + `s06_context/context.yaml` |
| **Output** | `fig_notes.yaml` (one entry per figure) + `<fig_id>.{prompt.md,response.json}` |
| **Key file** | `stages/s07_figure_analyze/runner.py` |

One vision-LLM call per `fig_id` (Qwen-VL-Max by default):
1. `_excerpts` (`runner.py:18`) pulls ±1 paragraph of text around each figure mention (bilingual search).
2. All panel crops for the `fig_id` go into the prompt; `panel_note` tells the LLM to read them as one figure.
3. The LLM follows the `figure_analyze.md` prompt and returns YAML with `visual_summary`, `text_claim_check[]`, `deep_observation`, `caption`.
4. `safe_parse_yaml` (`stages/_common/yaml_io.py`) tolerates stray fences and LaTeX; if parsing fails, the raw text lands under `raw` and the s09 builder uses regex to rescue the fields.

`LANG_INSTRUCTIONS` (`runner.py:53`) is the bilingual switch — add a row to support a new output language.

**v1.11.1 guards:**
- **Caption-stub skip** (`runner.py:93-96`): if `is_generation_prompt_caption` matches, the vision-LLM call is skipped entirely (defence in depth on top of s04, in case s04 ran before the filter was added).
- **zh-ratio guard** (`runner.py:151+`): when `--lang zh` but the first five `visual_summary` entries are under 30 % CJK, stderr prints a WARNING — some vision LLMs silently ignore `lang_instruction` (the v1.10 baseline-pollution issue, with seven of fifteen papers affected and zero detection at the time).

### 4.8 s08_section_compose — the heavy stage

See §5 for the full breakdown. In one paragraph:

| Field | Value |
|---|---|
| **Input** | s05 template + s03 chapters + s06 context+KG + s07 fig_notes + s04 figures |
| **Output** | `chapters/<NN>-<slug>.md` (one per section) + audit files |
| **Key files** | `stages/s08_section_compose/runner.py` (dispatch), `structured.py` (Strategy KL core, 1380 lines) |

For each template node, one of three compose paths runs:
1. `LAZY_PAPER_STRUCTURED=1` + KG + retriever → Strategy KL (`structured.compose_structured`)
2. `LAZY_PAPER_AGENT=1` + KG + retriever → pydantic-ai agent (`agent.run_section_agent`)
3. Default fallback → `_legacy_compose` (prompt-stuffed)

Every path can fall back; nothing crashes the pipeline.

**`reviewer.py` two-tier architecture.** After each section composes, `reviewer.regex_check()` (line 71) scans the source chunks + KG for four flag classes (`numeric_not_in_source` / `fig_not_in_yaml` / `formula_not_in_kg` / `unit_mismatch`) and writes `critic_flags.yaml`. Only when the regex tier raises ≥1 flag does `llm_review()` (line 199) fire one LLM critique that produces a targeted `CritiqueRevision`. The two gates keep most quality checks at zero LLM cost while reserving LLM critique for the prose with the highest defect risk. The Strategy KL verifier (§5.5) and the reviewer are orthogonal: the verifier decides claim-level accept/reject/advisory inside the compose path; the reviewer is a post-compose audit that can selectively rewrite.

### 4.9 s09_render — four renderers, four output files

| Field | Value |
|---|---|
| **Input** | `s08_section_compose/chapters/` + `s07_figure_analyze/fig_notes.yaml` + `s06_context/context.yaml` |
| **Output** | `preview.{docx,pdf,html,pptx}` + `mypaper_bundle/` |
| **Key files** | `stages/s09_render/runner.py`, `builder.py`, `model.py`, `renderers/{docx,html,pdf,pptx}.py` |

**The Document model is the intermediate data structure** (`model.py`):
```python
@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                          # "zh" | "en"
    chapters: tuple[Chapter, ...]

class Chapter:  heading, level, blocks  # blocks: Paragraph | FigureBlock | TableBlock

@dataclass(frozen=True)
class Paragraph:
    text: str                          # Unicode-normalized (DOCX / PPTX / print PDF)
    raw_text: str = ""                 # LaTeX-preserving (HTML / KaTeX); "" → use text
```

**Why a dual text field (v1.13).** DOCX and PPTX cannot render LaTeX, so
they need Unicode (`α_en`, `Σ|τ||q̇|`, `R²`). HTML hands LaTeX straight
to KaTeX, which renders much better than any Unicode approximation. The
builder fills both fields and lets each renderer pick: HTML walks
`raw_text` through `iter_html_runs(...)` and emits `<span data-tex>`;
DOCX walks `text` through `iter_runs(...)` and emits italic / bold runs;
PPTX takes `text` as-is. WeasyPrint reads the HTML's Unicode fallback
inside each `<span data-tex>` since it never runs the KaTeX script.

**`DocumentBuilder.build()`** (`builder.py:22`) converts markdown into a Document. **Figure binding** lives here: `_is_referenced` (`builder.py:113`) checks whether `Fig. N` / `图N` / `图 N` appears in the chapter body. A hit embeds the figure in a `FigureBlock`, and **each figure embeds at most once across the whole document** (first referencing chapter wins).

**`_UNTITLED_FALLBACK` (v1.11.1, `builder.py:13`)**: `{"zh": "未命名章节", "en": "Untitled"}` — when the markdown lacks an H1/H2 heading, the chapter heading is filled in by `lang`-aware fallback (before v1.11.1, Chinese papers could end up with the English literal "Untitled" mid-document).

**Four renderers, all subclass `Renderer` (`renderers/base.py`)**:
- `docx.py` — `python-docx`; East-Asia font Song Ti for Chinese, Times New Roman for Western; **v1.13** adopts the shared design tokens (accent `#D97757` for chapter numbers + heading left border, secondary gray for captions, italic accent-bordered deep-observation aside) via OOXML `<w:pBdr>` / `<w:rFonts>`.
- `html.py` — Jinja2 + base64 images; HYPERLINK mode renders `[span:doc:start-end]` as clickable `<sup>[1]</sup>` superscripts with a sources footer; **v1.13** emits `<span class="math-inline|math-auto" data-tex="…">unicode-fallback</span>` so KaTeX (linked from CDN by default, inlined when `LAZY_PAPER_INLINE_KATEX=1`) replaces the fallback on first paint while WeasyPrint and a raw "view source" still show something readable.
- `pdf.py` — reuses HtmlRenderer output and runs it through WeasyPrint; the `@media print` block in `styles.css` suppresses topbar / TOC / controls and styles the Unicode math fallback as italic serif inline.
- `pptx.py` — `python-pptx`; `slide_planner` assigns slide kinds (title / outline / section_divider / bullets / figure / closing_rich); bullets come from `pptx_summarizer` (LLM); responses are cached at `out_dir/llm_cache/`. PPTX is unchanged in v1.13.

**Design system origin.** The visual language was developed by Claude Design from a reference image; the HTML demo ([`docs/assets/lazy-paper-demo.html`](assets/lazy-paper-demo.html)) is the contract `html.py` + `styles.css` were ported from. Renderers are stateless / per-doc; tokens live in `styles.css` `:root` so the three accent themes (`orange / teal / indigo`) require zero Python changes.

**Partial-failure tolerance** (`runner.py:124-132`): one renderer failing does not block the others. The error lands in `done.yaml.formats[fmt]`; `partial: true` triggers a CLI WARNING. `--retry-failed` reruns only the failed formats.

---

## 5. s08_section_compose internals

s08 is about 40 % of repo complexity (`structured.py` 1380 lines, `runner.py` 632 lines). Block by block:

### 5.1 The three compose paths

Key branch in `runner.py::run` (`runner.py:442-546`):

```
                    ┌── LAZY_PAPER_STRUCTURED=1 + kg + retriever ──▶ Strategy KL
                    │       (structured.compose_structured)
for each template ─┼── LAZY_PAPER_AGENT=1 + kg + retriever ──▶ pydantic-ai agent
node                │       (agent.run_section_agent)
                    └── default / any failure ─────────────────────▶ _legacy_compose
                            (prompt-stuffed, runner.py:233)
```

Strategy KL failure → falls back to legacy; legacy does not fall back (it is the floor). Every fallback prints `[s08] ... failed: ... ; falling back to ...` to stderr so you can see it during a run.

### 5.2 Strategy KL — core data flow

```
                  ┌─ template node (title + guidance)
                  │
   ┌──────────────▼────────────┐
   │ _build_retrieval_query    │  title + guidance + KG-scoped entity texts + keywords
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ retriever.retrieve(top_k=15) │  dense + BM25 + RRF (+ optional entity boost)
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ build_required_mentions   │  survey chapter → all comparator entities
   │ select_top_required(cap=5) │  non-survey → token-overlap entities only
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ _figure_relevance(top_k=4) │  only when LAZY_PAPER_FIGURE_BIND=1; Jaccard picks figures
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐  ┌──────────────────────┐
   │ best-of-N compose         │──▶ _single_compose × N  │  N=BEST_OF_N, temp 0.2/0.4/0.6
   │ (instructor + Pydantic)   │  └──────────────────────┘
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ _merge_drafts             │  round-robin interleave + 3-layer dedup signature
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ verify_section_draft      │  4 verifiers: schema-prefix / quote-match / OOS / figure
   └──────────────┬────────────┘
                  │
            ┌─────┴─────┐
            │           │
   coverage > 0.5      else
            │           │
            │      ┌────▼─────────┐
            │      │ retry-when-empty │  1 strengthened retry listing each missing entity
            │      └────┬─────────┘
            │           │
            └─────┬─────┘
                  │
   ┌──────────────▼────────────┐
   │ retry-when-short          │  fires when prose < MIN_CHARS or claims < MIN_CLAIMS
   │ (3-layer swap guard)      │  only swap if strictly better
   └──────────────┬────────────┘
                  │
            draft.render(mode="REMOVE")
                  │
            chapters/<NN>-<slug>.md
```

The entrypoint is `structured.py::compose_structured` (line 989) — the largest function in the file.

### 5.3 The GroundedClaim schema

```python
class GroundedClaim(BaseModel):                     # structured.py:57
    text: str = Field(min_length=2)
    cited_chunk_ids: list[int] = Field(default_factory=list)
    cited_quote: str = Field(default="")
    figure_ids: list[str] = Field(default_factory=list, max_length=3)
```

Why each field:
- `text` is the prose the reader sees; `min_length=2` blocks empty strings.
- `cited_chunk_ids` are 0-based indexes into the 15 chunks retrieved for this section. The validator rejects out-of-range ids (Perplexity pre-injection pattern).
- `cited_quote` is a verbatim slice from the chunk, for the verifier. Empty string skips verification (some claims are synthesis statements with no single verbatim source).
- `figure_ids` is capped at 3 by `max_length`. Meta-Auditor M2 found one ali2025_flash ch11 case where a single claim cited 62 figures.

```python
class SectionDraft(BaseModel):                      # structured.py:94
    claims: list[GroundedClaim] = Field(min_length=2, max_length=14)
```

`min_length=2` so out-of-scope sections still emit two explanation claims; `max_length=14` caps per-section run-away (preventing 30-claim sections).

### 5.4 How the composer prompt is built

**System prompt** = `_STRUCTURED_SYSTEM` (`structured.py:720`). Contains:
- chunk-only citation rule + how to read required mentions;
- strict `<Author> et al.` form when `author_text` is set;
- FORBIDDEN list (schema prefix, duplicate facts, forward-looking design suggestions like "consider adding La doping");
- Figure citation requirement (`figure_ids=["Fig. N"]` plus the literal "Fig. N" / "图N" in the text);
- DOMAIN MISMATCH OVERRIDE (when the source paper doesn't touch the section topic, emit two or three "source paper does not address …" claims).

**User prompt** is assembled in `compose_structured` (line 1027):
```
## Section to write
- Title: ...
- Guidance: ...

## Paper context (first 3000 chars)

## Available chunks (cite ONLY these 0-based IDs)
[0] (chapter_xxx.md chars 0-400)
    <first 1200 chars of chunk 0>
[1] ...
...
[14] ...

## Required mentions (you MUST cover each)
- comparator: "BiFeO3-based..."
  author: "Jiang et al." (use this form...)
  evidence_chunk_id: 3
  evidence_quote: "..."
  linked_values: W_rec=2.94 J/cm³

## Figures topically relevant to this section  (only when FIGURE_BIND=1)
- Fig. 3: ...
    visual: ...
    observation: ...

## Already established in prior sections
§1 ...
§2 ...

Emit the SectionDraft JSON now.
```

`_single_compose` (line 844) wraps the OpenAI client in `instructor.from_openai(..., mode=Mode.MD_JSON)` for schema-validated calls and passes `validation_context={"allowed_chunk_ids": set(range(len(chunks)))}` into the validator above.

### 5.5 What the verifier does (`verify_section_draft`, line 286)

For each claim, the checks below decide **reject / accept / accept-with-advisory**:

| Check | Action | Implementation |
|---|---|---|
| **Anchored claim w/o quote** (v1.12 phase 2) — claim text names author or value+unit anchor; `cited_quote` empty | Reject (`anchored_claim_no_quote`); `LAZY_PAPER_ANCHORED_QUOTE=0` opts out | line 329-345 |
| **Schema prefix leak** — `text` starts with `GroundedClaim:` / `Claim:` | Reject | line 323 |
| **Quote vs chunk match** — `cited_quote` matches a cited chunk with fuzzy score ≥ 0.85 | Reject if no match | line 332-354 |
| **Chunk-id slop fallback** — quote matches a different chunk | Patch `cited_chunk_ids`, accept | line 343-354 |
| **Anchor advisory** — claim text says "Jiang et al." / "2.94 J/cm³" but the quote does not contain the token | Advisory only (logged, still accepted) | line 361-366 |
| **figure_ids whitelist** — figure_ids not in section_figures | `LAZY_PAPER_FIGURE_ID_WHITELIST=1` (default) → rewrite text "Fig. N" → "源论文相关图示", drop figure_ids; `=0` advisory only | line 383-437 |
| **Figure mention literal** — figure_ids non-empty but text lacks literal "Fig. N" / "图N" | Advisory (`figure_hint_unmet`) | line 438-454 |
| **OOS chapter overflow** — any claim hits OOS-opener regex and accepted > 3 | Truncate to first 3 | line 463-480 |
| **Results section thin numerics** — title contains results/性能/结果 but anchors < 2 and claims ≥ 3 | Advisory (logged, not rejected) | line 482-495 |
| **Author-not-in-chunk (v1.11.1)** — claim text mentions "Author Y et al." but the surname does not appear in any cited chunk text | Advisory by default (`author_not_in_chunk_advisory`); `LAZY_PAPER_AUTHOR_HARDREJECT=1` promotes to hard reject | line 470-497 |

**4-tier quote match (`_quote_in_chunk`, line 170)**:
1. exact substring → 1.0
2. case-insensitive → 0.99
3. **normalized** (`normalize_ocr_latex` collapses LaTeX cmds / OCR digit spaces / NFKD super-/subscripts / Unicode dashes → ASCII) → 0.97
4. fuzzy longest-common-substring → coverage ratio

Tier 3 is the key one — it lets LaTeX-form OCR like `$W _ { \mathrm { rec } }$` match the LLM's `W_{rec}`. See `stages/_common/normalize.py`.

### 5.6 retry-when-empty and retry-when-short

Two independent triggers (`compose_structured` line 1090-1268):

**retry-when-empty** — post-verify required-mention coverage ≤ `LAZY_PAPER_RETRY_THRESHOLD` (default 0.5).
- Re-sends the prompt with each missing entity's specific anchor hint appended to the system prompt (`"Jiang et al." or "Jiang 等人"` / `"W_rec=2.94 J/cm³"`).
- Swap to the retry only when it has strictly fewer missing entities.

**retry-when-short** — verified prose < `LAZY_PAPER_MIN_SECTION_CHARS` (default 500) or claims < `LAZY_PAPER_MIN_SECTION_CLAIMS` (default 4).
- Re-sends the prompt with "previous draft only X chars, write 5-8 substantive claims" appended.
- Three-layer swap guard (added in audit β#3):
  1. Longer prose
  2. Accepted claim count ≥ original AND ≥ 1 (no silent 0 → 0 swap)
  3. Required-missing does not regress

**Why two retries instead of one merged retry**: empty and short are different problems. A section can have full required coverage but still be sparse (3 short claims); another can have many claims but lose the key comparator. A merged prompt blurs the diagnosis signal.

### 5.7 LOCALES + UNKNOWN_FIGURE_LABEL — bilingual mechanism

Top-level constants in `structured.py:34-42`:

```python
LOCALES = ("zh", "en")

UNKNOWN_FIGURE_LABEL = {
    "zh": "源论文相关图示",
    "en": "a figure referenced in the source",
}
```

**v1.11 collapsed the per-locale strings into this one place — adding a language means editing here plus the matching tables in s03/s04/s07.**

`verify_section_draft(..., lang=...)` consumes the dict (line 421): when figure_id whitelist fires, the in-text `Fig. N` / `图N` is replaced with the locale-aware neutral phrase so the reader never sees a dead link.

**Full checklist for adding (say) `ja`**:

| File | Location | Change |
|---|---|---|
| `stages/s03_chapter/runner.py:14` | `SECTION_ANCHORS` | add 「要旨」「序論」「方法」「結果」「結論」 |
| `stages/s04_figures/runner.py:18-26` | `FIG_CAP_RE`, `TAB_CAP_RE`, `FIG_MENTION_RE` | extend `图\|Fig` to `图\|図\|Fig`, `表\|Table` to `表\|Table` |
| `stages/s07_figure_analyze/runner.py:53` | `LANG_INSTRUCTIONS` | add `"ja": "Write ... in Japanese ..."` |
| `stages/s08_section_compose/runner.py:195` | `LANG_INSTRUCTIONS` | same |
| `stages/s08_section_compose/structured.py:34` | `LOCALES`, `UNKNOWN_FIGURE_LABEL` | add `"ja"` entry |
| `stages/s09_render/builder.py:120` | `_make_label` | decide whether `Fig.` becomes `図` in Japanese |
| `cli.py:215` | `--lang choices=("en","zh")` | add `"ja"` |

`section_compose.md` is lang-neutral (`{lang_instruction}` placeholder) and does not need editing.

---

## 6. Figure pipeline (s04 + s07 + s09)

```
PDF  ─▶ s01_ocr ─▶ doc_*.md ──┐                    s07 vision LLM
   ▼                          │                    ┌────────────┐
   └▶ raw imgs/<bbox>.jpg ────┤   pair img↔caption │ deep_observation
        (~130 DPI)            │   merge sub-panels │ visual_summary
                              ▼                    │ text_claim_check
                         s04_figures               │ caption (shorter)
                              │                    └────┬───────┘
                              │ figures.yaml             │ fig_notes.yaml
                              │   mentions.yaml          │
                              ▼                          ▼
                         s09_render (DocumentBuilder)
                              │
                              │ _is_referenced(fid, body):
                              │   if "Fig. N" in body or "图N" in body or "图 N" in body
                              │
                              ├─▶ FigureBlock(image_paths, caption, deep_observation)
                              │   (each fig_id embeds at most once)
                              │
                              ▼
                         renderers (docx / html / pdf)
                              docx: WD_ALIGN.CENTER + 「【深度观察】」prefix
                              html: base64-embed → <img>
                              pdf:  via HtmlRenderer + WeasyPrint
```

### Hard constraint: bilingual regex

s04 (caption + mention extraction), s07 (surrounding-text search), s08 verifier (figure literal), and s09 builder (binding) all use **paired bilingual regex**. Miss one place and the whole chain breaks (before v1.11, Chinese papers had near-zero figure embedding).

| Stage | File:line | regex |
|---|---|---|
| s04 caption | `s04_figures/runner.py:18` | `FIG_CAP_RE = r"...(?:Fig(?:ure)?\.?\|图)\s*\d+..."` |
| s04 mention | `s04_figures/runner.py:26` | `FIG_MENTION_RE = r"(?:Fig(?:ure)?\.?\|图)\s*(\d+)([a-z])?"` |
| s07 excerpt | `s07_figure_analyze/runner.py:25` | `r"(?:\bFig(?:ure)?\.?\|图)\s*{fig_num}(?![0-9])"` |
| s08 verifier figure literal | `structured.py:444` | `rf"Fig\.\s*{num}\|图\s*{num}"` |
| s09 binding | `builder.py:113-120` | `fig_id in body or f"图{num}" in body or f"图 {num}" in body` |

s09 uses substring matching (not regex) because it only checks for literal containment — simple and zero false positives.

### Figure-binding uniqueness

`DocumentBuilder.build()` keeps an `embedded: set[str]` shared across chapters: the first chapter that references Fig. 3 wins; later chapters that also write "as shown in figure 3" do not re-embed. This is the motivation for v1.10 Variant C's **figure_ids hard constraint** — the LLM must place the `fig_id` in the right (most relevant) chapter on the first reference, otherwise binding goes to a weaker context.

---

## 7. Template system (s05 + placeholders)

### 7.1 s05 parsing

Input is a user-written `.docx` where each section is a numbered or list-styled paragraph followed by guidance lines. Example:
```
1. Background and motivation
   Discuss the AFE-RFE transition; tabulate prior W_rec records.
   - Compare with PbZrO3 baselines.
2. Synthesis route
   ...
```

`parse_template` returns a tree YAML:
```yaml
- level: 1
  number: "1"
  title: "Background and motivation"
  guidance: "Discuss the AFE-RFE transition; tabulate prior W_rec records.\nCompare with PbZrO3 baselines."
  hints: {needs_table: true, needs_figure: false}
  children:
    - {title: "Compare with PbZrO3 baselines", guidance: ""}
```

`hints` is inferred by regex on the guidance (`_NEEDS_TABLE_RE` / `_NEEDS_FIGURE_RE`) and reaches the s08 prompt.

### 7.2 Placeholder substitution (s08)

Guidance may contain `{paper.title}` / `{paper.system}` / `{paper.keywords}` / `{paper.figures}`. Before composing, s08 calls `substitute_placeholders` (`runner.py:127`) to resolve them.

Available keys live in `_build_paper_data` (`runner.py:32`): title, system, keywords, key_terms, abbreviations, figures, tables, fig_observations_brief.

Unknown keys are **kept verbatim** rather than silently removed, so a typo is visible to the author.

---

## 8. LLM client (`llm/client.py`)

### 8.1 Role abstraction

`llm/models.yaml` defines three roles:

```yaml
vision:
  env_prefix: LLM_VISION
  default_base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  default_model: qwen-vl-max-latest
  supports_images: true
text:
  env_prefix: LLM_TEXT
  default_base_url: https://api.deepseek.com/v1
  default_model: deepseek-chat
  supports_images: false
embeddings:
  env_prefix: LLM_EMBEDDINGS
  fallback_env_prefix: LLM_VISION   # share DashScope key
  default_model: text-embedding-v3
```

`LLM(role="text")` reads `{prefix}_API_KEY` / `{prefix}_BASE_URL` / `{prefix}_MODEL`. **`fallback_env_prefix`** lets embeddings reuse the vision key by default, so a one-key setup still works.

### 8.2 chat()

```python
def chat(self, *, system, user, images=(), temperature=0.2, max_tokens=2000) -> LLMResponse:
```

Returns `LLMResponse(content, model, usage, latency_ms)`. Images use `image_to_data_url` (base64 inline). Only roles with `supports_images=true` accept image input; the rest raise.

### 8.3 max_tokens calculation

```python
def max_tokens(default: int) -> int:                # llm/client.py:24
    raw = os.environ.get("LLM_MAX_TOKENS_CEILING")
    ceiling = int(raw) if raw and raw.strip().isdigit() else 40000
    return min(default, max(1, ceiling))
```

Every call site picks its own default (s06 KG = 32000, s08 compose = 12000, s07 figure = 4000). `LLM_MAX_TOKENS_CEILING` (default 40000) caps them all. Drop the ceiling to cut cost.

### 8.4 No internal cache

The text/vision LLM calls themselves are **not** cached (DeepSeek's input-prefix cache is provider-side, transparent here). The one explicit cache is in s09 `pptx_summarizer` (`out_dir/llm_cache/`), keyed on chapter-input hash + prompt version, so PPT bullets do not re-LLM on re-runs.

---

## 9. Test layout

### 9.1 Where tests live

```
conftest.py                                  # macOS DYLD injection (Pango/Cairo)
tests/                                        # top-level: CLI + libs + harness
  conftest.py
  test_cli.py                                # CLI argparse + --only/--force/--retry-failed
  test_cli_retry_failed.py
  test_llm_client.py                         # role resolution + max_tokens clamp
  test_llm_smoke.py                          # live marker (skipped by default)
  test_paper_kg.py                           # parquet roundtrip
  test_retriever.py                          # BM25 + RRF + entity boost
  test_citation.py                           # [span:...] marker rendering
  test_evaluate_harness.py                   # scripts/evaluate harness
  test_common/                               # mirror tests for stages/_common
    test_paths.py, test_bbox.py, test_yaml_io.py, test_done.py

stages/<stage>/tests/                         # each stage owns its tests (locality)
  s01_ocr/tests/        test_runner / test_mineru / test_dispatch
  s02_clean/tests/      test_runner
  s03_chapter/tests/    test_runner (with bilingual anchor tests)
  s04_figures/tests/    test_runner
  s05_template/tests/   test_runner (with cache-stale tests)
  s06_context/tests/    test_runner / test_kg_extract
  s07_figure_analyze/tests/  test_runner
  s08_section_compose/tests/
    test_structured.py          # GroundedClaim / verify_section_draft / merge
    test_figure_hard_constraint.py  # Variant C figure_ids behaviour
    test_runner.py
    test_substitution.py
    test_units.py
    test_reviewer.py
    test_agent.py
  s09_render/tests/
    test_builder.py             # DocumentBuilder + figure binding
    test_model.py
    test_runner.py
    test_renderers_smoke.py
    test_citation_render.py
    test_slide_planner.py
    test_pptx_summarizer.py
    test_cache_reuse.py
    test_partial_failure.py
  _common/tests/        test_normalize.py    # 4-tier OCR/LaTeX folding
```

### 9.2 Markers

```toml
[tool.pytest.ini_options]
markers = ["live: tests that call real LLM/OCR APIs (skipped by default; run via -m live)"]
addopts = "-m 'not live'"
```

`uv run pytest -q` runs **300 passing, 2 deselected (live)** in under five seconds. `uv run pytest -m live` actually hits the LLM/OCR endpoints.

### 9.3 What the categories cover

| Category | Representative file | What it tests |
|---|---|---|
| **regex** | `stages/_common/tests/test_normalize.py` | OCR → LLM 4-tier folding (LaTeX cmd / digit space / NFKD / dash) |
| **schema** | `s08/tests/test_structured.py` | `GroundedClaim` validator rejects out-of-set chunk ids; `SectionDraft` min/max length |
| **dedup** | `s08/tests/test_structured.py::test_merge_drafts_*` | (author, value) anchor / distinctive token / 120-char prefix 3-tier fallback |
| **verifier** | `s08/tests/test_figure_hard_constraint.py` | figure_id_unknown rewrite; figure_hint_unmet advisory; OOS overflow cap |
| **figure binding** | `s09/tests/test_builder.py` | bilingual substring detection; each figure embeds once |
| **partial failure** | `s09/tests/test_partial_failure.py` | one renderer failing does not block the others; `--retry-failed` reruns only failed formats |
| **cache** | `s05/tests/test_runner.py`, `s09/tests/test_cache_reuse.py` | template SHA-16 stale detection; pptx LLM cache invalidates on prompt version bump |

---

## 10. Configuration and env vars

See `.env.example` for the canonical list.

### 10.1 Required

| Variable | Purpose |
|---|---|
| `OCR_BACKEND` | `mineru` (recommended) or `paddleocr` |
| `MINERU_TOKEN` | required when `OCR_BACKEND=mineru`, from https://mineru.net |
| `PADDLEOCR_TOKEN` | required when `OCR_BACKEND=paddleocr` |
| `LLM_VISION_API_KEY` | s07 vision LLM key (default DashScope) |
| `LLM_TEXT_API_KEY` | s06/s08/s09 text LLM key (default DeepSeek) |

**v1.11.1 — `meta.yaml.lang` persistence** (`cli.py:262-266`): every `lazy-paper run` writes `--lang` into `runs/<paper_id>/meta.yaml`. External auditors and demo scripts no longer need to grep `fig_notes.yaml` to recover a run's baseline language (the v1.10 baseline-pollution diagnosis pain point: there was no single source of truth for run-lang).

### 10.2 Switching LLM endpoints

Each role accepts `_BASE_URL` / `_MODEL` overrides:

```bash
LLM_TEXT_BASE_URL=https://api.openai.com/v1
LLM_TEXT_MODEL=gpt-4o
LLM_TEXT_API_KEY=sk-...
```

Tested against OpenAI / Anthropic-compatible gateways / self-hosted vLLM / Ollama.

### 10.3 Strategy KL (recommended)

```bash
LAZY_PAPER_STRUCTURED=1               # structured compose + verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md   # 11-type KG (with author)
LAZY_PAPER_BEST_OF_N=2                # 2 LLM samples, round-robin merge
```

### 10.4 v1.10 figure binding

```bash
LAZY_PAPER_FIGURE_BIND=1              # s08 adds section_figures block to the prompt
                                       # + used to trigger figure-retry (cut in v1.11, see §11)
LAZY_PAPER_FIGURE_ID_WHITELIST=1      # default ON. Verifier rejects unknown fig_ids and
                                       # rewrites "Fig. N" / "图N" to UNKNOWN_FIGURE_LABEL.
                                       # =0 falls back to advisory-only (old behaviour)
```

### 10.5 Depth mode (opt-in)

```bash
LAZY_PAPER_MIN_SECTION_CHARS=1200     # retry-when-short threshold (default 500)
LAZY_PAPER_BEST_OF_N=3                # 3 samples (override above)
LAZY_PAPER_MIN_SECTION_CLAIMS=4       # retry-when-short claim floor (default 4)
```

### 10.6 Verifier / retry fine-tune

```bash
LAZY_PAPER_VERIFIER_THRESHOLD=0.85    # quote-vs-chunk fuzzy match threshold
LAZY_PAPER_RETRY_THRESHOLD=0.5        # post-verify coverage ≤ this triggers retry-when-empty
LAZY_PAPER_REQUIRED_CAP=5             # non-survey required-mention cap
LAZY_PAPER_AUTHOR_HARDREJECT=0        # v1.11.1: author-not-in-chunk is advisory by default;
                                       # =1 promotes to hard reject
```

### 10.7 Retriever tuning

```bash
LAZY_PAPER_CHUNK_SIZE=400             # default 400 (Strategy G experiment)
LAZY_PAPER_CHUNK_OVERLAP=80
LAZY_PAPER_HIERARCHICAL=1             # parent-child chunks + auto-merge (Strategy H)
LAZY_PAPER_PARENT_SIZE=2000
LAZY_PAPER_PARENT_OVERLAP=200
LLM_EMBEDDINGS_BATCH_SIZE=10          # DashScope cap
```

### 10.8 Global cap

```bash
LLM_MAX_TOKENS_CEILING=40000          # clamp max_tokens on every LLM call (default 40000)
LAZY_PAPER_HTML_CITATIONS=hyperlink   # HTML cite marker mode
                                       # hyperlink (default) / keep / remove
```

### 10.9 Rendering (v1.13)

```bash
LAZY_PAPER_INLINE_KATEX=1             # inline KaTeX CSS + JS + 20 woff2 fonts as
                                       # data: URIs (preview.html ~440 KB → ~1.08 MB),
                                       # so single-file HTML works offline.
                                       # Default OFF → link cdn.jsdelivr.net at runtime.
                                       # First-time setup:
                                       #   uv run python scripts/fetch_katex.py
                                       # populates stages/s09_render/templates/vendor/katex/.
```

### 10.10 OCR backends (v1.13)

```bash
MINERU_FORCE_OCR=1                    # default ON (was hard-coded OFF). Forces MinerU's
                                       # layout-OCR path instead of trusting the text layer —
                                       # essential for figure-rich text-PDFs whose vector
                                       # plots would otherwise be skipped.
MINERU_ENABLE_TABLE=1                 # default ON.
MINERU_ENABLE_FORMULA=1                # default ON.
MINERU_KEEP_RAW=0                     # default OFF. Set to 1 to preserve the unzipped
                                       # MinerU response (_mineru_raw/) for diagnosis when
                                       # figure recall regresses on a specific paper.
MINERU_MODEL_VERSION=                 # default empty (cloud picks). Reserved hook for
                                       # future MinerU API model parameter; the only
                                       # currently-accepted value is "" (omit field).
```

### 10.9 Experimental / legacy

```bash
LAZY_PAPER_AGENT=1                    # pydantic-ai agent path (4 tools, ~8 iterations)
LAZY_PAPER_TWO_STEP=1                 # outline → expand two-step compose (Strategy B)
LAZY_PAPER_WHOLE_PAPER=1              # skip retriever, feed full text (Strategy I)
```

Kept as fallbacks for regression testing; none are on by default.

---

## 11. v1.11 design decisions

v1.11.0 was a **first-principles refactor** (commit `a4d90ab`) that **cut** three over-engineered modules. v1.11.1 added 4 HIGH bug fixes from the cycle-11 sentence-level audit (v1.11.0 was not pushed; v1.11.1 is the first stable v1.11). The reasoning is recorded here so we don't reintroduce them.

### 11.1 cross-citation reject (cut)

**What it did**: v1.10 added ~40 LOC in the verifier that rejected a claim when the cited author was not in the retrieval chunk's citation list.

**Why cut**: the real cause was that claims with `cited_quote == ""` were silently accepted, letting author hallucinations sneak past the quote-grounding gate. The fix belongs in the **prompt** (force author claims to carry a quote), not in another verifier-side rejection layer. Spending 40 LOC for one paper's edge case (ali2025 ch08) was not worth it. **Deferred to v1.12 with an orthogonal reference-list check** (the cited author must appear in `paper.references`).

**Code marker**: `structured.py:368-372` has `# v1.11 architecture-review CUT: cross-citation reject was 40 LOC...`

**v1.12 phase 2 closure**: the underlying defect — empty `cited_quote` bypassing the verifier — was finally fixed in v1.12 phase 2 with the anchor-aware empty-quote branch at `structured.py:329-345` (see §5.5 verifier table top row). Pair with the HARD RULE addition to `_STRUCTURED_SYSTEM` (the s08 compose system prompt). The orthogonal reference-list check originally proposed here was NOT implemented; the anchor-based approach proved sufficient. Measured impact: meng2024's empty-`cited_quote` rate dropped from 32% to 0%; ali2025_flash RAGAS faithfulness +5.4pp.

### 11.2 figure-retry pass (cut)

**What it did**: v1.10 Variant C added ~85 LOC after the verifier — when ≥ 50 % of `section_figures` were not literally mentioned in the verified draft, re-send the prompt asking the LLM to fill them in.

**Why cut**: the figure-retry swap guard was buggy enough to need three repair rounds, and the v1.11 DEEP figure-claim prompt rule (`_STRUCTURED_SYSTEM`'s "DEEP figure-claim discipline" block, line 786) now forces every figure-citing claim to carry a specific panel + number + mechanism upstream. The prompt already handles the placeholder problem figure-retry tried to fix; keeping both is duplicate effort.

**Code marker**: `structured.py:1270-1273` has `# v1.11 architecture-review CUT: figure-retry was 85 LOC...`

### 11.3 headline-metric prompt rule (cut)

**What it did**: v1.10 briefly added a prompt rule forcing every section's opening sentence to be a "headline metric" (e.g. "this work achieves W_rec=8.6 J/cm³").

**Why cut**: identical phrasing made the prose monotonous. The rule fit results sections but felt mechanical in discussion / conclusion. **Already covered by the general quantitative-validation regex + retry-when-short** — no dedicated prompt rule needed.

### 11.4 Kept (Tier 1) from cycles 5-7

- `_SCHEMA_PREFIX_RE` rejects "GroundedClaim:" / "Claim:" prefix leakage (cycle 5 Meta)
- `_claim_dedup_anchors` uses value+unit composite as the dedup key (cycle 5 A3 — bugfix for "5 GPa" and "5 J/cm³" sharing a key)
- `_OOS_CLAIM_RE` + `_MAX_OOS_CLAIMS=3` chapter-level OOS cap (cycle 6 Meta — hif_2 ch04 emitted 1 OOS opener + 11 off-topic claims that the per-claim cap could not catch)
- DOMAIN MISMATCH OVERRIDE prompt path (cycle 5)
- `normalize_ocr_latex` BS3 (`\%` and other LaTeX escapes) + BS4 (NFKD super/subscript + Unicode dash) (cycle 2 Auditor 2)

### 11.5 v1.11.1 — 4 HIGH bug fixes (cycle 11)

v1.11.0 passed the architecture-review ship gate (hardcode scan + lang threading + test count) but the cycle-11 sentence-level audit (3 subagents cross-checking output vs source paper) caught 4 more HIGH issues. v1.11.0 was never pushed; v1.11.1 is the first v1.11 stable.

- **Bug #1 + #2 — flagship metric cross-chapter drift**: meng2024 ch07/09/13/15 gave three different `W_rec` values for the same flagship sample. Cause: s08 scavenged a comparator's neighbouring numbers from retrieval chunks. Fix: s06 extracts the flagship's `headline_metrics` from the KG into `context.yaml`; the prompt's "FLAGSHIP GROUND TRUTH" block pins the composer to those exact numbers. See §4.6 Step 3.
- **Bug #3 — author misattribution**: meng2024 ch13 attributed Ma et al.'s La(Mg)-doped-NBT result to Cao et al. (a different author in a nearby chunk). Fix: post-verify advisory `author_not_in_chunk_advisory`, default advisory, `LAZY_PAPER_AUTHOR_HARDREJECT=1` promotes to hard reject. See §5.5 verifier table, last row.
- **Bug #4 — OCR text-prompt treated as physics figure**: hif_2 ch15 fabricated a physics critique for "图 43"; that figure was actually a unCLIP appendix whose OCR'd caption was the literal generation prompt `(a) A high quality photo of a dog…`. Fix: two-layer `is_generation_prompt_caption` filter (s04 + s07 defence in depth). See §4.4.
- **Bilingual regression prevention** (Audit C): `cli.py` writes `meta.yaml.lang`; s07 zh-ratio guard; `s09_render/builder.py` localises `_UNTITLED_FALLBACK`. See §4.7 / §4.9 / §10.1.

---

## 12. Known limits / v1.12 candidates

From CHANGELOG v1.10 "Deferred to v1.11" still open:

- **BS1+BS2 normalize**: letter-spaced subscripts (OCR outputs "L i 3 +" while the LLM writes "Li³⁺") are asymmetric between OCR and LLM, so the BS3+BS4 symmetric-folding strategy does not apply. Needs case-by-case handling; no schedule.
- ~~**s04 caption-aware numbering**~~: **shipped** in v1.12 phase 1 as `--pdffigures2`, opt-in. See §4.4 "PDFFigures 2 reconciliation".
- **comparator gap**: `build_required_mentions` only searches KG entities for comparators, but some papers cite work in the references list without naming it as an entity. We need to scan the body text for "Et al. ... reported" patterns.
- **template-paper mismatch graceful degrade**: when an AFE template runs against a deep-learning paper, s08 produces OOS overflow ("源论文未涉及...") in every section instead of falling back to a generic paper structure.
- **DOCX HYPERLINK dead code**: the DOCX renderer still does not consume `citation_mode=HYPERLINK` — only KEEP/REMOVE. The sources list needs wiring into the docx renderer.
- **6 hardcodes → env vars**: `cap=5`, `top_k=4`, `parameter spread 0.2*i`, etc. in `structured.py` should be env-controlled per spec §11.
- **real-time LLM cost meter**: `usage` is written to each response.json but not aggregated; v1.12 should add `total_tokens / total_cost` to `done.yaml`.
- **dedup signature optimisation**: the merge_drafts fallback prefix is still 120 chars; short claims (60-100 chars) can miss dedup because their prefixes do not match.

---

## References (in-repo)

- User guide: [`docs/USER_GUIDE.md`](USER_GUIDE.md)
- Agent / AI collaboration: [`docs/AGENT_GUIDE.md`](AGENT_GUIDE.md)
- Chinese architecture doc: [`docs_zh/ARCHITECTURE.md`](../docs_zh/ARCHITECTURE.md)
- Full changelog: [`CHANGELOG.md`](../CHANGELOG.md)
- Third-party notices: [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
