# lazy-paper — User Guide

## Who this is for

You have a scientific PDF and want a structured, multi-format analysis document from it — without writing code. This guide covers setup, your first run, and how to iterate on the output.

If you're an AI coding agent maintaining the repo, read `docs/AGENT_GUIDE.md` instead.

---

## First-time setup

### 1. Install uv and Python

lazy-paper uses [uv](https://github.com/astral-sh/uv) to manage its Python environment. You do **not** need a system Python install beyond what uv provides.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone the repo and set up the environment:

```bash
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"
```

### 2. System dependencies (macOS only)

WeasyPrint (used for PDF output) needs native libraries:

```bash
brew install pango gdk-pixbuf libffi cairo
```

On Linux or Windows, use Docker instead:

```bash
docker compose build
# then replace "uv run python -m cli run ..." with:
docker compose run --rm lazy-paper run ...
```

### 3. Create your .env file

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in the required tokens:

| Variable | What it is | Where to get it |
|---|---|---|
| `MINERU_TOKEN` | MinerU cloud OCR API key | [mineru.net](https://mineru.net/) — free tier available |
| `LLM_TEXT_API_KEY` | API key for the text LLM | [platform.deepseek.com](https://platform.deepseek.com/) or any OpenAI-compatible provider |
| `LLM_VISION_API_KEY` | API key for the vision LLM | [dashscope.aliyun.com](https://dashscope.aliyun.com/) (Qwen-VL) |
| `LLM_EMBEDDINGS_API_KEY` | API key for embeddings (v1.4+) | **Optional** — auto-inherits `LLM_VISION_API_KEY` if unset |

You do not need a separate embeddings key if your vision provider supports `text-embedding-3-small`. DashScope (Qwen-VL provider) does, so the default `.env.example` leaves `LLM_EMBEDDINGS_API_KEY` blank.

---

## Five-minute quickstart

Once your `.env` is filled in, run:

```bash
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --lang zh \
  --formats docx,pdf,html,pptx
```

Replace `papers/your-paper.pdf` with the path to your PDF. Replace the `--template` path with a section-outline `.docx` whose section titles match your paper's domain. The repo root ships two starters:

- `Table of Contents-Relaxor AFE-ZGY-HW.docx` — materials science (ferroelectrics, energy storage, related)
- `Table of Contents-CV-IMRaD.docx` — generic CV / ML / IMRaD (Introduction → Method → Experiments → Results → Discussion)

**Template-paper domain fit matters.** Section headings are inserted verbatim into the compose prompt; an off-domain template produces either out-of-scope disclaimers or — with Phase 4 prompt tailoring ON — content jammed under the wrong heading. See the [template-domain mismatch warning](#template-paper-domain-fit-required-for-good-output) under "Prompt tailoring" below.

Output lands at:

```
runs/mypaper/s09_render/
  preview.docx
  preview.pdf
  preview.html
  preview.pptx
```

A run takes 5–20 minutes depending on paper length and API latency. Each stage writes a `done.yaml` marker. If the run is interrupted, just re-run the same command — it resumes where it stopped.

---

## Choosing an OCR backend

| Backend | Flag | Best for | Notes |
|---|---|---|---|
| **MinerU** | `OCR_BACKEND=mineru` | Figure-heavy papers; multi-column layouts | Cloud API; requires `MINERU_TOKEN`; slightly slower |
| **PaddleOCR-VL** | `OCR_BACKEND=paddleocr` | Text-heavy papers; fast turnaround | Cloud API; requires `PADDLEOCR_TOKEN`; default in `.env.example` |

Set in `.env`, or override per-run:

```bash
OCR_BACKEND=mineru uv run python -m cli run ...
```

If your paper has many figures and the default PaddleOCR misses image bounding boxes, switch to MinerU.

---

## Choosing LLM providers

lazy-paper uses any OpenAI-compatible endpoint. The defaults in `.env.example` are:

- **Text LLM**: DeepSeek-Reasoner (chain-of-thought; good for analytical writing)
- **Vision LLM**: Qwen-VL-Max via DashScope (strong figure understanding)

To switch providers, edit these variables in `.env`:

```
LLM_TEXT_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-reasoner
LLM_TEXT_API_KEY=sk-...

LLM_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_VISION_MODEL=qwen-vl-max
LLM_VISION_API_KEY=sk-...
```

Tested alternatives:
- OpenAI: set `LLM_TEXT_BASE_URL=https://api.openai.com/v1`, `LLM_TEXT_MODEL=gpt-4o`
- Self-hosted vLLM or Ollama: set `LLM_TEXT_BASE_URL=http://localhost:8000/v1`

The vision LLM must support image input in the OpenAI messages format. The text LLM must support JSON-mode output.

---

## Recommended high-quality mode: Strategy KL

Turn on **Strategy KL** when you want literature-citation recovery on benchmark-style papers. KL re-checks every quote against the source (with LaTeX/OCR normalization), runs two drafts per section, and keeps the better one. If post-verify coverage of required mentions is low, it then issues one strengthened retry.

Add these lines to `.env`:

```
LAZY_PAPER_STRUCTURED=1             # structured compose + per-claim verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md # extracts author + comparator + cited_by_paper
LAZY_PAPER_BEST_OF_N=2              # 2 samples per section, round-robin merge
LAZY_PAPER_VERIFIER_THRESHOLD=0.85  # min quote-vs-chunk match score
LAZY_PAPER_RETRY_THRESHOLD=0.5      # post-verify coverage ≤ X triggers one retry
```

Optional advanced opt-in (v1.11.1):

```
LAZY_PAPER_AUTHOR_HARDREJECT=1      # promote author-not-in-chunk from advisory to hard reject
                                    # default 0 = advisory; flip to 1 only after telemetry
                                    # confirms precision on your corpus
```

Trade-offs:

- **Cost**: best-of-N=2 roughly doubles s08 LLM spend (s08 is the most expensive stage). Per-paper cost goes from ~$0.60–1.20 to ~$0.90–1.80.
- **Latency**: s08 takes about 1.7–2× longer.
- **Quality**: the verifier rejects unsupported claims. The retry-when-empty trigger then recovers comparator citations the default composer can drop.

Validated on the 18-paper v1.9.2 corpus + v1.10 9-paper variant test: **meng2024 T1 = 9/9/9 (stdev 0)** across three independent runs after informed-retry shipped in v1.9.0 (was floor 12, mean 15.0 in v1.8.1). Full data in `docs/archive/v1_9_validation_results.md` and `docs/archive/v1_10_variant_comparison.md`.

Leave these unset for the fast/cheap default composer — it gives good results on most papers at half the cost.

---

## Iterating on output

You don't need to re-run the whole pipeline to tweak the result. Each stage is independently re-runnable.

### Inspect intermediate artifacts

| Artifact | What it tells you |
|---|---|
| `runs/<id>/s03_chapter/chapters/` | How the PDF was split into chapters — check for mis-detected section boundaries |
| `runs/<id>/s06_context/context.yaml` | The paper's title, research system, keywords, and abbreviations used in all downstream prompts |
| `runs/<id>/s07_figure_analyze/fig_notes.yaml` | The vision-LLM's structured observation for each figure |
| `runs/<id>/s08_section_compose/chapters/` | The LLM-written sections — this is the main content of DOCX/PDF/HTML |
| `runs/<id>/s08_section_compose/critic_flags.yaml` | Quality flags raised by the regex critic (v1.4+) |

### Re-run a single stage

Use `--only` with `--force` to re-run just one stage:

```bash
# Re-run section composition without touching OCR or figure analysis
uv run python -m cli run \
  --pdf papers/mypaper.pdf \
  --template template.docx \
  --paper-id mypaper \
  --only s08_section_compose \
  --force

# Re-render all formats from already-composed chapters
uv run python -m cli run \
  --pdf papers/mypaper.pdf \
  --template template.docx \
  --paper-id mypaper \
  --only s09_render \
  --force \
  --formats docx,pdf,html,pptx
```

### Re-run a subset of stages

```bash
--only s08_section_compose,s09_render
```

Comma-separated stage names. Useful when you edit the template and want to re-compose + re-render without repeating OCR.

### Full reset for one paper

```bash
rm -rf runs/mypaper/{s05_template,s08_section_compose,s09_render}
uv run python -m cli run ... --paper-id mypaper
```

---

## v1.12 — optional features + default-on behaviour changes

### PDFFigures 2 sidecar — caption-anchored figure numbering

When MinerU OCR skips or mis-numbers a figure, the canonical `Figure N` printed in
the paper's caption text is lost. PDFFigures 2 (AI2) re-extracts that canonical
numbering directly from the caption regions, then reconciles against MinerU's
output. Off by default; enable with `--pdffigures2`.

Setup (docker-only — no host JVM install):

```bash
# One-time, ~5 min on first build
docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .
```

Then in `.env`: `PDFFIGURES2_JAR=docker`

Use:

```bash
uv run python -m cli run --pdf paper.pdf --template t.docx --pdffigures2 ...
```

The reconciliation report lands in `runs/<id>/s04_figures/_pdffigures2.yaml`:

```yaml
report:
  renames: [{from: "Fig. 2", to: "Fig. 3", score: 0.83}]   # MinerU mis-numbered Fig. 3 as Fig. 2
  keeps:   [{fig_id: "Fig. 1", reason: "no_caption_match", best_score: 0.12}]
```

Only renames when caption Jaccard ≥0.5; otherwise MinerU's numbering is kept.

### Entity dedup — author misattribution defence

Merges variant author / material mentions during s06 KG extraction
("Meng et al." + "Meng 2024" + "本工作" → one canonical entity). Defends against
the v1.11.1 author-misattribution bug class at the extraction layer (rather than
adding another verifier rule downstream). Off by default; enable with:

```bash
LAZY_PAPER_ENTITY_DEDUP=1
```

Adds one LLM call (~4K tokens, T=0.1) to s06. Soft-degrades to the original
entities on any LLM failure or malformed JSON.

### Anchored-quote enforcement (v1.12 phase 2) — default ON

Pre-v1.12, claims with an empty `cited_quote` skipped verification
entirely. The LLM exploited this to leave hard-to-source claims
unverified. Phase 2 closes the bypass:

- Claims whose text names a specific author (`Jiang et al.`) or numeric
  value with unit (`2.94 J/cm³`, `91.04%`) MUST carry a non-empty
  `cited_quote`. Empty quote on such a claim is rejected.
- Synthesis claims (no specific anchor in text) still pass without
  quote verification — backward compatible for cross-chunk summaries.

Opt-out for backward compat:

```bash
LAZY_PAPER_ANCHORED_QUOTE=0   # in .env
```

The opt-out exists for projects with existing baselines / regressed
prompts; new runs should leave it on.

### Prompt tailoring (v1.12 phase 4, opt-in)

The default s08 system prompt is tuned for materials-science papers (where
the project was first developed). For cross-domain papers (ML, biology,
chemistry, etc.), pass `LAZY_PAPER_PROMPT_TAILOR=1` to enable a two-stage
prompt construction:

1. **Pre-stage** (in `s06_context`): a cheap LLM call reads the paper's
   already-extracted `context.yaml` + the intro chapter, then emits
   `prompt_augment.yaml` with `domain_framing`, `terminology`,
   `metric_patterns`, and a `comparator_style` example drawn from THIS
   paper.
2. **Thinking stage** (in `s08`): the augment block is prepended to the
   generic system prompt. The thinking LLM sees a prompt tailored to this
   specific paper's domain rather than a one-size-fits-all template.

Enable in `.env`:

```bash
LAZY_PAPER_PROMPT_TAILOR=1
```

Cost: one extra LLM call per paper (~1K tokens, ~$0.001 on DeepSeek-chat).
On failure, the pre-stage soft-degrades to a `.failed` marker and s08
falls back to the vanilla prompt — never blocks the pipeline.

#### Template-paper domain fit (required for good output)

Prompt tailoring is **not a substitute for template selection**. The augment
block tells the LLM "this paper is about X, use these terms"; it does **not**
override the per-section heading that s08 still inserts from your template.
When the heading and the paper disagree (e.g. running the Relaxor AFE template
on an unCLIP CV paper), enabling Phase 4 actively makes things worse, because
the LLM now confidently writes paper-specific content under a wrong heading.

Measured impact on the unCLIP image-generation paper (10 Q/A, RAGAS faithfulness):

| Template | `LAZY_PAPER_PROMPT_TAILOR` | Faithfulness |
|---|---|---|
| Relaxor AFE (wrong domain) | 0 | 0.353 |
| Relaxor AFE (wrong domain) | 1 | **0.100** (regression) |
| CV-IMRaD (matched domain)  | 1 | **0.810** |

Rule of thumb: pick a template whose top-level section titles you would
expect to see in the paper's actual table of contents. The ship-with-repo
`Table of Contents-CV-IMRaD.docx` covers most ML / CV / IMRaD-style work.
For other domains, copy a starter and rewrite the headings — guidance
paragraphs and `{paper.system}` / `{paper.key_terms}` slots can stay.

---

## Troubleshooting

### OCR missed a figure

The figure image is in the PDF but didn't show up in the output.

1. Check `runs/<id>/s04_figures/figures.yaml` — is the figure ID listed?
2. If missing: switch OCR backend (`OCR_BACKEND=mineru` is better at detecting figures in dense layouts). Delete `s01_ocr/done.yaml` and re-run:
   ```bash
   rm runs/<id>/s01_ocr/done.yaml
   OCR_BACKEND=mineru uv run python -m cli run ... --paper-id <id>
   ```
3. If present in `figures.yaml` but not in output: check `s07_figure_analyze/fig_notes.yaml` — did the vision LLM analyze it? If not, delete `s07_figure_analyze/done.yaml` and re-run:
   ```bash
   rm runs/<id>/s07_figure_analyze/done.yaml
   uv run python -m cli run ... --paper-id <id> --only s07_figure_analyze,s08_section_compose,s09_render
   ```

### A chapter looks hallucinated

The output section contains facts not found in the source paper.

1. Check `runs/<id>/s08_section_compose/critic_flags.yaml` — look for `numeric_not_in_source` flags in that section.
2. Read the corresponding `<slug>.prompt.md` to see what evidence was fed to the LLM.
3. Check `runs/<id>/s06_context/context.yaml` — if the paper system/keyword field is wrong, it can bias generation. Delete `s06_context/done.yaml` and re-run context extraction.
4. Delete the specific section's cached output and re-run s08 with `--force`:
   ```bash
   rm runs/<id>/s08_section_compose/chapters/<slug>.md
   uv run python -m cli run ... --paper-id <id> --only s08_section_compose --force
   ```

### PPT layout looks wrong (bullets overflow or overlap)

This is usually a rendering artifact from very long bullet text.

1. Check `runs/<id>/s09_render/preview.pptx` — convert to PDF with LibreOffice and inspect:
   ```bash
   /Applications/LibreOffice.app/Contents/MacOS/soffice \
     --headless --convert-to pdf --outdir /tmp/ \
     runs/<id>/s09_render/preview.pptx
   ```
2. If bullets are too long, the section text in `s08_section_compose/chapters/` likely has very long sentences. Re-run s08 with `--force` — the LLM is stochastic, so a fresh call often produces shorter bullets.
3. For deeper PPT-layout debugging (per-slide audit, density caps, font fallback): run `uv run python scripts/audit_pptx.py runs/<id>/s09_render/preview.pptx` and inspect the per-slide flags.

### WeasyPrint segfaults on macOS

This happens when Homebrew's native libraries aren't found.

1. Verify the libraries are installed: `brew list | grep -E "pango|cairo|gdk"`.
2. If installed but still crashing, run with the Docker image:
   ```bash
   docker compose build
   docker compose run --rm lazy-paper run \
     --pdf papers/mypaper.pdf --template template.docx \
     --paper-id mypaper --formats docx,pdf,html,pptx
   ```
3. If you must run natively, ensure you're using `uv run` (not system Python). The system macOS Python 3.9 + WeasyPrint combination triggers segfaults reliably; uv's isolated Python 3.11 does not.

---

## Cost notes

### Rough per-paper estimate

For a typical 12-page materials science paper with 8 figures, using DeepSeek-Reasoner (text) + Qwen-VL-Max (vision) + DashScope embeddings:

| Stage | LLM calls | Approximate cost |
|---|---|---|
| s06_context (context + KG) | 2 text calls | ~$0.02 |
| s07_figure_analyze | 8 vision calls | ~$0.10–0.20 |
| s08_section_compose (15 sections) | 15 text calls + 1 embedding | ~$0.30–0.60 |
| s09_render (PPTX summarizer) | 17 text calls (outline + 15 + paper) | ~$0.20–0.40 |
| **Total** | | **~$0.60–1.20 / paper** |

Costs vary significantly with paper length, number of figures, and section count. Embeddings (for hybrid retrieval) are very cheap (~$0.001 for a full paper's worth of chunks).

### Capping spend with LLM_MAX_TOKENS_CEILING

Set `LLM_MAX_TOKENS_CEILING` in `.env` to cap every LLM call at a token budget:

```
LLM_MAX_TOKENS_CEILING=8000   # conservative
LLM_MAX_TOKENS_CEILING=40000  # default (generous for DeepSeek-Reasoner's CoT)
```

Lowering this can cause truncated JSON responses in analytical stages (s08, s09). If you see empty or malformed output, raise the ceiling back toward 40000.

### Reusing cached results

Because each stage writes `done.yaml`, re-running the same paper after the first full run is nearly free — all stages are skipped. You only pay for LLM calls when:

- You explicitly pass `--force`.
- You delete a stage's `done.yaml` or output directory.
- The PPTX summarizer's input hash changes (e.g. you changed the template, which changed the chapter titles fed to the outline LLM).
