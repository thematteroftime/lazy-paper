# Architecture

## Pipeline overview

`lazy-paper` converts a scientific PDF into a multi-format analysis document through nine sequential stages. Each stage:

- reads inputs from the previous stage's output directory
- writes its own output directory under `runs/<paper_id>/<stage>/`
- writes a `done.yaml` marker on success

Stages are idempotent: if `done.yaml` exists the stage is skipped by default. The `--force` flag bypasses this check. The `--only <stage>` flag runs exactly one stage, relying on previous stages' existing outputs.

```
runs/<paper_id>/
  s01_ocr/            doc_*.md + imgs/*.jpg
  s02_clean/          doc_*.md (cleaned) + imgs/ (copied)
  s03_chapter/        chapters/chapter_*.md + manifest.yaml
  s04_figures/        figures.yaml + mentions.yaml + imgs/ (upscaled+merged)
  s05_template/       template.yaml
  s06_context/        context.yaml + paper_kg.parquet + paper_context.{prompt.md,response.json}
  s07_figure_analyze/ fig_notes.yaml + <fig_id>.{prompt.md,response.json}
  s08_section_compose/ chapters/*.md + retrieval.parquet + critic_flags.yaml + findings.yaml
                        + <slug>.{prompt.md,response.json}
  s09_render/         preview.{docx,pdf,html,pptx} + done.yaml + llm_cache/
  meta.yaml
```

Entry point: `cli.py::main` — parses args, resolves env vars, iterates `STAGE_ORDER`, calls `_run_one()` per stage.

## Stages

### s01_ocr

**Purpose**: Convert a PDF to per-page Markdown (`doc_0.md`, `doc_1.md`, …) with embedded `<img>` tags pointing to cropped figure images in `imgs/`.

**Input**: raw PDF file path (from `--pdf`).

**Output**: `doc_N.md` files + `imgs/*.jpg` + `done.yaml`.

**Key code**: `stages/s01_ocr/runner.py`

Two backends are supported, selected by `OCR_BACKEND` env var:

- **PaddleOCR-VL** (default in `.env.example`): uploads per-page PNG renders to the PaddleOCR AiStudio REST API (`https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`). Each page is converted to a PNG via `pypdfium2`, uploaded, polled until complete, and the resulting Markdown (with `<img>` tags encoding bounding boxes in the filename) is saved.
- **MinerU** (recommended for figure-heavy papers): `stages/s01_ocr/mineru.py` — calls the MinerU API with the full PDF, polls until done, downloads the result archive.

After OCR, `upscale_images()` re-renders each cropped image region from the PDF at 300 DPI using `pypdfium2`, replacing the lower-resolution OCR output. Coordinate mapping from OCR pixel space to PDF point space is calibrated per-page from existing image dimensions.

**Authentication**: `MINERU_TOKEN` or `PADDLEOCR_TOKEN` from `.env`.

---

### s02_clean

**Purpose**: Apply post-OCR corrections to the `doc_*.md` files from s01.

**Input**: `s01_ocr/` directory.

**Output**: cleaned `doc_*.md` + copied `imgs/` + `done.yaml`.

**Key code**: `stages/s02_clean/runner.py`

Three cleaning passes:

1. `strip_running_headers()` — identifies lines that appear verbatim in 3+ pages (running headers/footers) and removes them.
2. `repair_chars()` — fixes common OCR character artifacts: `(cid:0)` → `−`, chemical formula subscript repair (e.g. `TiO 2` → `TiO₂`), cation superscript repair.
3. `flag_corrupted_column_flow()` — detects lines where >60% of tokens are single characters (double-column reflow artifact) and wraps them in a comment marker.

The `imgs/` directory is copied verbatim so downstream stages can resolve image paths relative to the clean directory.

---

### s03_chapter

**Purpose**: Split the cleaned multi-page Markdown into per-chapter files using IMRaD section detection.

**Input**: `s02_clean/` directory.

**Output**: `chapters/chapter_NNN_<title>.md` + `manifest.yaml` + `done.yaml`.

**Key code**: `stages/s03_chapter/runner.py`

`detect_science_anchor()` matches lines against a set of canonical section names (`SECTION_ANCHORS`: abstract, introduction, experimental, results, discussion, conclusion, references, etc.) plus numbered headings (`1. Introduction`, `2.1 Methods`, …). Each anchor starts a new chapter file. Content before the first anchor goes into `chapter_000_Preface.md`.

Chapters below `min_chars` (default 1) are discarded. The chapter manifest records title, file name, and character count.

---

### s04_figures

**Purpose**: Build a structured index of all figures, including their canonical IDs, captions, chapter mentions, and merged multi-panel images.

**Input**: `s02_clean/` (source docs for bbox calibration), `s03_chapter/chapters/` (chapter text for mention detection), PDF file.

**Output**: `figures.yaml` (list of figure dicts with `fig_id`, `caption`, `image_abs_path`, `source_doc`) + `mentions.yaml` (map `chapter_filename -> [fig_id, …]`) + `done.yaml`.

**Key code**: `stages/s04_figures/runner.py`

Three phases:

1. **Detection**: scans `doc_*.md` for `<img>` tags and `Fig. N` / `Table N` caption patterns. Each figure entry records the canonical `fig_id` (normalized to `Fig. N` form), caption text, source document, and image relative path (which encodes the OCR bounding box).

2. **Mention detection**: scans chapter files for `Fig. N` and Chinese-form `图N` references to build the `mentions.yaml` map.

3. **Multi-panel merge**: `_merge_figure_subpanels()` groups entries sharing the same `fig_id`, computes the union bounding box across all sub-panels on the same PDF page, and re-renders a single merged image at 300 DPI using `pypdfium2`. The per-page coordinate scale is calibrated from existing image dimensions via `_calibrate_scale()`.

---

### s05_template

**Purpose**: Parse the user-supplied section-outline `.docx` into a structured list of sections with titles, guidance text, and content hints.

**Input**: `--template` path (a `.docx` file).

**Output**: `template.yaml` (list of section nodes) + `done.yaml`.

**Key code**: `stages/s05_template/runner.py`

`parse_template()` walks `python-docx` paragraph objects. Numbered paragraphs (`1. Title`, `2.1 Subtitle`) and top-level list items become section nodes. Sub-bullets become `children[]` and their text is folded into the parent's `guidance` field. `_is_guidance_line()` filters out instruction text masquerading as headings. Each node carries `hints.needs_table` and `hints.needs_figure` boolean flags derived from keyword matching.

---

### s06_context

**Purpose**: Extract paper-level context (title, research system, keywords, abbreviations) via a single text LLM call, then build the PaperDB layer for the paper.

**Input**: `s03_chapter/chapters/` (first 1-2 chapters).

**Output**: `context.yaml` + `paper_kg.parquet` + `paper_context.prompt.md` + `paper_context.response.json` + `done.yaml`.

**Key code**: `stages/s06_context/runner.py`, `stages/s06_context/kg_extract.py`

Reads up to 20,000 characters from the abstract and introduction chapters. Calls `LLM(role="text")` with the `llm/prompts/paper_context.md` prompt. The LLM returns YAML; `safe_parse_yaml()` parses the response defensively. The parsed `context.yaml` is consumed by s07, s08, and s09 to inject paper-specific context into all downstream prompts.

#### v1.4: KG sub-step

After `context.yaml` is written, `kg_extract.build_paper_kg()` extracts a structured knowledge graph from all chapter text using `instructor` (typed Pydantic LLM output). The extraction uses a **10-type closed schema**:

| Type | Covers |
|---|---|
| `material` | primary study materials |
| `dopant` | substituents / dopants |
| `parameter` | experimental or simulation parameters |
| `value` | numeric measurements |
| `unit` | physical units |
| `figure` | figure references |
| `table` | table references |
| `claim` | key claims / findings |
| `method` | synthesis or characterization methods |
| `comparator` | comparison benchmarks |

The extractor makes one LLM call via `instructor.from_openai(LLM('text').client, mode=Mode.JSON)` with `response_model=PaperKG`. On success, the entity + relation graph is serialized to `paper_kg.parquet` (via `pyarrow`). Each entity carries a `source_span` pointing back to the exact character range in the chapter text.

**Soft-degrade**: if `instructor` fails to parse a valid `PaperKG` after two retries, the runner writes a `kg_extract.failed` marker file and returns `None`. Downstream stages check for this marker and fall back to keyword-based behavior — the pipeline never aborts.

Similarly, the hybrid retrieval index (`retrieval.parquet`) is built from the chapter chunks; if the embedding API is unavailable the runner writes `retrieval.failed` and s08 uses keyword excerpts instead.

---

### s07_figure_analyze

**Purpose**: Analyze each figure with a vision LLM to produce structured observations for each figure.

**Input**: `s04_figures/figures.yaml` + `s04_figures/mentions.yaml` + `s03_chapter/chapters/` (for text excerpts) + `s06_context/context.yaml`.

**Output**: `fig_notes.yaml` (list of structured figure analysis dicts) + per-figure `<fig_id>.prompt.md` + `<fig_id>.response.json` + `done.yaml`.

**Key code**: `stages/s07_figure_analyze/runner.py`

For each canonical `fig_id` in `figures.yaml`:

1. Collects all sub-panel image paths for that figure ID.
2. Extracts up to 6,000 characters of chapter text where the figure is mentioned (`_excerpts()`).
3. Calls `LLM(role="vision")` with the figure images + prompt template from `llm/prompts/figure_analyze.md`.
4. Writes `<fig_id>.prompt.md` and `<fig_id>.response.json` for audit.
5. Parses the YAML response into a structured note dict containing `fig_id`, `caption`, `deep_observation`, `image_paths`.

Output language (Chinese/English) is controlled by `--lang` via `LANG_INSTRUCTIONS`.

---

### s08_section_compose

**Purpose**: Write the full body of each output section in the target language, driven by the template outline, using retriever-fed evidence and (optionally) a pydantic-ai tool-calling agent.

**Input**: `s05_template/template.yaml` + `s03_chapter/chapters/` + `s06_context/context.yaml` + `s06_context/paper_kg.parquet` + `s07_figure_analyze/fig_notes.yaml` + `s04_figures/figures.yaml` + `retrieval.parquet`.

**Output**: `chapters/<slug>.md` (one per template section) + `retrieval.parquet` + `critic_flags.yaml` + `findings.yaml` + per-section `<slug>.prompt.md` + `<slug>.response.json` + `done.yaml`.

**Key code**: `stages/s08_section_compose/runner.py`, `stages/s08_section_compose/reviewer.py`, `stages/s08_section_compose/agent.py`

#### Default per-section algorithm (v1.4)

For each section node in `template.yaml`:

1. **Evidence retrieval**: load `Retriever` from `retrieval.parquet` and call `retriever.retrieve(section.guidance, top_k=8, entity_boost=[e.id for e in kg.scoped_to(section)])`. The RRF-fused ranked list of chunks (dense cosine + BM25 sparse) is boosted for chunks whose character spans overlap with KG entity spans relevant to this section. Falls back to legacy keyword excerpts if `retrieval.failed` or `kg_extract.failed` marker is present.

2. **Composition**: calls `LLM(role="text")` with the `llm/prompts/section_compose.md` prompt, injecting paper context, section metadata, retrieved evidence chunks, and figure notes.

3. **Regex critic (observe-only)**: `reviewer.regex_check(draft, source_docs, kg, fig_yaml)` scans the draft for:
   - numeric values not found in source documents (with unit normalization via `_units.normalize()`)
   - `Fig. N` / `Table N` references not present in `figures.yaml`
   - chemical formulas or symbol bindings not present in the KG

   Any `Flag` objects produced are appended to `critic_flags.yaml`. In v1.3.4 the critic is **observe-only** — it records flags but does not trigger rewriting.

4. **LLM critic (v1.4.0)**: if `reviewer.regex_check()` produces flags, `reviewer.llm_review(draft, flags, evidence)` is called. The reviewer uses `instructor` with `response_model=CritiqueRevision`, which carries `revised_draft`, `quote_fidelity`, `grounding`, `synthesis_depth` (all 1–4 Likert scores), and `notes`. The revised draft replaces the original. A second regex pass runs; any remaining flags are soft-accepted with a logged warning.

5. **Findings stub**: `findings.append_verified_claims(section.title, claims)` appends verified claims from the reviewed draft to `findings.yaml` (write-only in v1.4; consumed by a future cross-chapter coherence agent in v1.5).

6. Write the chapter Markdown to `chapters/<slug>.md`.

#### Optional pydantic-ai agent path (experimental, env-gated)

Set `LAZY_PAPER_AGENT=1` to replace step 2 with a `pydantic-ai` tool-calling agent loop. The agent (`stages/s08_section_compose/agent.py`) is given four tools:

| Tool | Signature | Purpose |
|---|---|---|
| `query_kg` | `(entity_type, filter?) → list[dict]` | Query the KG by type; types are the 10-type closed schema. |
| `retrieve` | `(query, top_k=8, entity_boost?) → list[dict]` | Hybrid dense+BM25 retrieval; top_k clamped to 12. |
| `check_source` | `(claim, expected_value?) → dict` | Substring + unit-normalized lookup; returns `{found, span, evidence}`. |
| `emit_section` | `(draft) → str` | Terminal call; validates ≥1 `[span:...]` citation marker, ends the tool loop. |

The agent runs up to `max_iters=8` tool cycles before forcing an `emit_section` call. Any exception in the agent loop causes the runner to fall back to legacy compose for that section, logging `[degraded] agent fallback for <section.title>`.

**Why env-gated**: live runs revealed the agent occasionally returns meta-commentary ("I will now write…") instead of section prose. The flag lets you opt in on a known-good environment while the default path remains stable.

---

### s09_render

**Purpose**: Build the `Document` model from composed chapters + figure notes, then render to all requested output formats.

**Input**: `s08_section_compose/chapters/` + `s07_figure_analyze/fig_notes.yaml` + `s06_context/context.yaml`.

**Output**: `preview.{docx,pdf,html,pptx}` + `mypaper_bundle/` + `done.yaml`.

**Key code**: `stages/s09_render/runner.py`

See subsections below for component details.

#### DocumentBuilder

`stages/s09_render/builder.py::DocumentBuilder`

Pure transform — no IO. Accepts `chapters_md` (dict of filename → Markdown text) and `fig_notes` (list of figure dicts). Returns a frozen `Document`.

- Chapters are sorted lexically (matching `s08_section_compose` naming).
- Each chapter's Markdown is split into `Paragraph` blocks on double-newlines.
- Figures are embedded as `FigureBlock` objects in the first chapter that references them (by `fig_id` literal or Chinese-form `图N`). Each figure is embedded at most once across the entire document.

#### Renderer ABC

`stages/s09_render/renderers/base.py::Renderer`

Abstract base class. Each renderer must declare `extension: ClassVar[str]` and implement `render(doc: Document, out_path: Path) -> None`. Renderers must not mutate the input `Document`.

Renderers register themselves in the `RENDERERS` dict by importing their modules in `runner.py`. The registry maps extension string → renderer class.

#### Four renderers

| File | Class | Key dependencies |
|------|-------|-----------------|
| `renderers/docx.py` | `DocxRenderer` | `python-docx` |
| `renderers/html.py` | `HtmlRenderer` | `jinja2`, base64 image embedding |
| `renderers/pdf.py`  | `PdfRenderer`  | `weasyprint`, re-uses the HTML template |
| `renderers/pptx.py` | `PptxRenderer` | `python-pptx`, `SlidePlanner`, `PptxSummarizer` |

The DOCX renderer applies Times New Roman for Latin text and Song Ti (宋体) for Chinese characters, with conditional East Asian font settings. The HTML renderer embeds all images as base64 data URLs to produce a single self-contained file. The PDF renderer renders the same HTML template through WeasyPrint.

#### SlidePlanner

`stages/s09_render/slide_planner.py::SlidePlanner`

Deterministic, no IO. Converts a `Document` + optional LLM summaries + outline into a `SlideDeck`. Slide types: `title`, `outline`, `section_divider`, `bullets`, `figure`, `combined`, `closing`, `closing_rich`. When an LLM outline is provided, chapters are grouped into 4-5 named sections; pure-bullet chapters are absorbed into their section divider slide.

#### PptxSummarizer

`stages/s09_render/pptx_summarizer.py::PptxSummarizer`

LLM-backed summarizer with double-track cache. Two passes when PPTX is requested:

1. `summarize_outline()`: groups chapters into 4-5 named sections using `llm/prompts/pptx_outline.md`. Includes per-chapter metadata (has_figures, n_paragraphs) in the prompt.
2. `summarize()`: per-chapter bullet generation using `llm/prompts/pptx_summarize.md`, enriched with cross-chapter context (system, keywords, section_name, prior_bullet, next_heading).
3. `summarize_paper()`: produces the closing-slide paper brief (5-7 bullets + one-sentence takeaway) using `llm/prompts/pptx_paper_summary.md`.

---

## PaperDB layer (v1.4+)

The PaperDB layer adds a per-paper structured knowledge store that persists across s06 and s08. It consists of two Parquet files written by s06 and consumed by s08.

### paper_kg.parquet

Written by `stages/s06_context/kg_extract.py`. Contains all entities and relations extracted from the paper by `instructor` using the 10-type closed schema.

**Schema**:

```
entities table:
  id          string    — stable UUID per entity
  type        string    — one of the 10 closed types
  text        string    — surface form as found in paper
  source_span struct    — {chapter: str, start: int, end: int}
  attributes  map       — type-specific (e.g. value + unit for `value` entities)

relations table:
  subject_id  string    — entity UUID
  predicate   string    — e.g. "has_value", "uses_method", "compared_to"
  object_id   string    — entity UUID
  source_span struct    — location in paper text
```

**Lifetime**: `paper_kg.parquet` is written once per paper and survives `--force` on s06 by design (KG extraction is expensive; delete the file explicitly to force re-extraction). If `kg_extract.failed` marker is present, s08 degrades to keyword fallback.

**Cross-reference**: `stages/s06_context/kg_extract.py`, `llm/retriever.py::Retriever.query_kg()`

### retrieval.parquet

Written by `llm/retriever.py::Retriever.build_index()` during s08 initialization. Contains dense-vector embeddings and BM25 index data for all chapter chunks.

**Schema**:

```
chunks table:
  chunk_id    string    — UUID
  chapter     string    — source chapter filename
  text        string    — chunk text (SentenceSplitter, 400 chars, overlap 80)
  start_char  int       — character offset in chapter
  end_char    int       — character offset in chapter
  embedding   list[f32] — dense vector (text-embedding-3-small, 1536-dim)
  bm25_tokens list[str] — pre-tokenized for BM25 index
```

BM25 term frequencies and the inverted index are serialized alongside the chunks table. Retrieval is ~12.5 ms for 500 chunks (pure numpy sparse ops via `bm25s`).

**Retrieval**: `Retriever.retrieve(query, top_k=8, entity_boost=[])` runs dense cosine similarity and BM25 in parallel, fuses results via Reciprocal Rank Fusion (RRF), then applies an entity-span boost: chunks whose `[start_char, end_char]` interval overlaps with any entity span in `entity_boost` get a rank promotion.

**Cross-reference**: `llm/retriever.py`, `stages/s08_section_compose/runner.py`

---

## Citation processing (v1.4+)

### Stream processor (vendored)

`llm/citation/stream_processor.py` is vendored from [Onyx](https://github.com/onyx-dot-app/onyx) (`backend/onyx/chat/citation_processor.py`, MIT license). The original MIT header and author attribution are preserved verbatim. Three Onyx-internal imports (`SearchDoc`, `CitationInfo`, `STOP_STREAM_PAT`) are replaced by local Pydantic models; all regex state-machine logic and rendering modes are retained unchanged.

**License**: see `THIRD_PARTY_NOTICES.md` for source repo, commit SHA, and MIT full text.

### Three rendering modes

| Mode | Behavior | When to use |
|---|---|---|
| `REMOVE` | Strips all `[span:doc_X:Y-Z]` markers — final output is clean prose. | **Default** for end users. |
| `KEEP` | Leaves markers in place as literal text. | Debugging retrieval attribution. |
| `HYPERLINK` | Converts markers to hyperlinks in DOCX/HTML output pointing to the source chunk. | QA review, citation audit. |

The mode is selected via `llm/citation/__init__.py::CitationAdapter`, which bridges lazy-paper's `Source`/`Citation` Pydantic models to the Onyx `SearchDoc`/`CitationInfo` interface.

### CLI flag

Pass `--debug-citations` to switch the mode to `KEEP`, exposing `[span:...]` markers in DOCX and HTML output. Default is `REMOVE`. The flag has no effect on PPTX (speaker notes carry the markers regardless).

**Cross-reference**: `llm/citation/__init__.py`, `llm/citation/stream_processor.py`, `stages/s09_render/renderers/docx.py`

---

## Cross-cutting concerns

### Resumability

Every stage writes `stages/_common/done.py::mark_done()` on success:

```python
dump_yaml(stage_path / "done.yaml", {"finished_at": time.time(), **extra})
```

`is_done(path)` returns `True` if `done.yaml` exists. The CLI skips stages where `is_done` is true unless `--force` is set. For s09_render, `done.yaml` also records a `formats` dict (extension → file path or error dict) and a `partial` flag.

### LLM token budgets

All LLM call sites route through `llm.client.max_tokens(default)`, which clamps to the `LLM_MAX_TOKENS_CEILING` env var (default 40000). Per-stage defaults:

| Stage | Call | Default `max_tokens` |
|---|---|---|
| s06_context | paper context | 4000 |
| s07_figure_analyze | per figure (vision) | 4000 |
| s08_section_compose | per chapter (text) | 12000 |
| s09_render / PptxSummarizer | `summarize_outline` | 16000 |
| s09_render / PptxSummarizer | `summarize` (per chapter) | 8000 |
| s09_render / PptxSummarizer | `summarize_paper` (closing) | 8000 |

DeepSeek-Reasoner consumes chain-of-thought tokens before emitting JSON content; budgets are deliberately generous to prevent the JSON payload from being truncated to an empty string. Empty-content responses now raise a meaningful error so the retry loop short-circuits cleanly.

### LLM cache

`PptxSummarizer` uses a double-track cache stored under `s09_render/llm_cache/`:

- **Reuse track**: `<slug>.json` containing `{"input_hash": ..., "payload": ...}`. If the stored `input_hash` matches the current input (computed by SHA-256 over prompt version + lang + chapter content + cross-chapter context), the LLM call is skipped.
- **Audit track**: `<slug>.prompt.md` and `<slug>.response.json` written alongside every cache entry, whether or not the LLM was called. The prompt and raw response are always accessible for inspection.

Cache invalidation is controlled by `_PROMPT_VERSION` constants (`_CHAPTER_PROMPT_VERSION`, `_OUTLINE_PROMPT_VERSION`, `_PAPER_PROMPT_VERSION`). Bumping a constant changes the SHA-256 input and forces a cache miss on next run.

All other LLM stages (s06, s07, s08) do not use the hash cache — they write prompt/response files per run for audit but re-call the LLM on every non-skipped invocation.

### Soft failure

In s09_render, each renderer is invoked inside a `try/except Exception`. On failure, the error is recorded in `done.yaml` under `formats.<ext>.error`, `partial` is set to `True`, and a warning is printed to stderr. Other renderers continue.

If all requested renderers fail, a `RuntimeError` is raised (hard failure). Otherwise the run completes with partial output.

`--retry-failed` (used with `--only s09_render`) reads the `done.yaml` from a previous partial run and re-runs only the formats listed under the `error` key.

### macOS WeasyPrint

`cli.py::_augment_dyld_for_macos_brew()` runs at import time (before any stage imports). It prepends `/opt/homebrew/lib` and `/usr/local/lib` to `DYLD_FALLBACK_LIBRARY_PATH`, ensuring WeasyPrint can find Pango, Cairo, and gdk-pixbuf installed via Homebrew. No-op on Linux (Docker) and Windows. A parallel shim runs in `conftest.py` for the test suite.

## Data model

```
Document (frozen dataclass)
  paper_title: str
  lang: str                      # "zh" | "en"
  chapters: tuple[Chapter, ...]

Chapter (frozen dataclass)
  heading: str
  level: int                     # 1 = H1
  blocks: tuple[Block, ...]      # Block = Paragraph | FigureBlock

Paragraph (frozen dataclass)
  text: str

FigureBlock (frozen dataclass)
  fig_id: str                    # canonical "Fig. 5"
  label: str                     # localized "Fig. 5" or "图 5"
  image_paths: tuple[Path, ...]  # one path per panel
  caption: str
  deep_observation: str
```

All fields are immutable after construction. Renderers dispatch on `isinstance(block, FigureBlock)` vs `isinstance(block, Paragraph)`.

```
SlideDeck (frozen dataclass)
  slides: tuple[Slide, ...]
  lang: str

Slide (frozen dataclass)
  kind: str      # title | outline | section_divider | bullets | figure | combined | closing | closing_rich
  title: str
  bullets: tuple[str, ...]
  image_paths: tuple[Path, ...]
  caption: str
  deep_observation: str
  observations: tuple[str, ...]
  notes: str     # speaker notes
```

## Adding a new output format

1. Create `stages/s09_render/renderers/<fmt>.py`. Subclass `Renderer`, set `extension = "<fmt>"`, implement `render(doc, out_path)`.
2. At the bottom of the new file, register: `RENDERERS["<fmt>"] = MyRenderer`.
3. In `stages/s09_render/runner.py`, add `import stages.s09_render.renderers.<fmt>  # noqa: F401`.
4. Add a smoke test to `stages/s09_render/tests/` that instantiates the renderer and calls `render()` with a minimal `Document`.

The renderer receives a frozen `Document`; it must not modify any field. If the format requires pre-processing (like PPTX does with `SlidePlanner`), perform it inside the renderer's constructor or `render()` method.

## Adding a new LLM stage

1. Create `stages/s<NN>_<name>/runner.py` following the pattern of s06 or s07:
   - `PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "<name>.md"`
   - `_PROMPT_VERSION = "v1"` constant for cache versioning
   - `run(*, ..., out_dir: Path) -> dict` function
   - Call `mark_done(out_dir, {...})` before returning
2. Add the prompt template to `llm/prompts/<name>.md`. Use `SYSTEM:` / `USER:` section markers and `{placeholder}` for runtime substitutions.
3. For LLM calls that need caching (expensive or repeated), implement `_make_hash(version, lang, *content_bytes)` + `_try_cache(slug, hash)` + `_write_cache(slug, hash, payload, prompt, response)` following `PptxSummarizer`.
4. Write prompt and response files (`<slug>.prompt.md`, `<slug>.response.json`) alongside every LLM call for auditability.
5. Register the stage in `cli.py`: add to `STAGE_ORDER`, add an `elif name == "s<NN>_..."` branch in `_run_one()`, and import the runner module at the top.
6. Add a `tests/` directory with at least one unit test that exercises the runner with fixture data and mocked LLM.
