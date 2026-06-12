# Knowledge Library (v1.14)

The library is a persistent, cross-paper store built from artifacts your runs
already produced. Ingesting costs **zero LLM calls** — the knowledge graph is
lifted from `runs/<paper-id>/s06_context/` and the chunk index (embeddings
included) from `runs/<paper-id>/s08_section_compose/retrieval.parquet`; if the
run never reached s08, ingest builds the index once (embeddings API only, no
LLM calls). Once ingested, a paper survives `runs/` cleanup and becomes
searchable alongside every other paper you have processed.

## Quickstart

```bash
# After a normal run (or on any past run that reached s08; with only s03 done, ingest builds the index once):
uv run python -m cli ingest mypaper

# Or in one shot:
uv run python -m cli run --pdf … --template … --paper-id mypaper --ingest

# Search across everything ingested:
uv run python -m cli query "energy regularization vs gait switching" --top-k 5
uv run python -m cli query "…" --papers mypaper,otherpaper   # restrict scope
uv run python -m cli query "…" --json                        # for agents
uv run python -m cli papers                                  # list contents
```

## Layout

Default root is `./library` (override with `LAZY_PAPER_LIBRARY_DIR` or
`--library-dir`). It is user data — gitignored, like `runs/`.

| Path | Contents |
|---|---|
| `manifest.yaml` | One entry per paper: title, kind, keywords, chunk/entity counts, aggregated LLM `total_tokens`, source run |
| `lancedb/` | Tables `chunks` (text + embedding, keyed by `paper_id`), `entities`, `relations` (the per-paper KG, merged) |
| `bm25/` + `bm25_ids.json` | Persisted sparse index over all chunks, rebuilt on each ingest |
| `papers/<id>/` | Archived `context.yaml`, `fig_notes.yaml`, `figures.yaml`, composed `sections/`, OCR `imgs/` |

## Semantics

- **Idempotent**: re-ingesting a paper replaces its rows; the manifest keeps one entry.
- **One embeddings model per library**: a dimension mismatch is rejected with
  an explanatory error. Mixing models silently would corrupt ranking.
- **Query** uses the same hybrid dense + BM25 + reciprocal-rank-fusion scheme
  as the in-run retriever (`llm/retriever.py`), so cross-paper ranking behaves
  like the ranking you already trust inside a run.
- **`kind: experiment`** is accepted by `ingest --kind` but reserved — the
  experiment-loop features land in a later release.

## Synthesize (v1.16)

`lazy-paper synthesize` answers research-direction questions across your whole
library (or a subset of papers) by gathering evidence from multiple sources and
composing a grounded markdown report with a single text-LLM call.

### Purpose

Given a topic ("energy regularization vs. multi-skill architectures on legged
robots"), the command collects evidence from the v1.14 library (manifest
metadata, archived `context.yaml` / `fig_notes.yaml`, and hybrid-retrieved
excerpts) and composes a five-section research-direction report. Every claim
drawn from the evidence must carry a `[src: paper_id]` marker; a deterministic
post-check warns on any marker that doesn't resolve to a library paper.

### Quickstart

```bash
uv run python -m cli synthesize --topic "energy regularization vs gait switching"
uv run python -m cli synthesize --topic "..." --papers paper-a,paper-b   # restrict scope
uv run python -m cli synthesize --topic "..." --lang en                  # English output (default: zh)
```

Output lands at `<library>/synth/<topic-slug>/report.md`, with audit sidecars:
`.prompt.md` and `.response.json` (written before the citation check, so a
rejected report is always inspectable).

### Report structure

The report has exactly five `##` sections in this order:

| Section | Contents |
|---|---|
| `## 主题综述` | Topic overview and framing across papers |
| `## 方法对比` | Markdown table — one row per paper: approach, key quantitative results, limitations |
| `## 证据与分歧` | Agreements and contradictions in the evidence |
| `## 研究空白` | Open questions not addressed by any paper in scope |
| `## 下一步建议` | 3–5 concrete, falsifiable next steps, each citing at least one `[src: ...]`; speculation is marked `(推测)` |

### Grounding contract

- Every factual claim drawn from the evidence carries `[src: paper_id]` using
  the exact paper ids in the library. Multiple sources: `[src: id1][src: id2]`.
- After composition, `check_citations` performs a deterministic scan and prints
  a `WARNING: [src:] markers not in library: ...` line for any id that does not
  appear in the library manifest.
- Anything beyond the evidence must be marked `(推测)`.
- Audit sidecars (`.prompt.md` / `.response.json`) are persisted before the
  marker check; a corrective retry runs once if the first attempt contains no
  `[src:]` markers at all.

### Evidence sources

`gather()` builds the evidence block from three layers:

1. **Manifest** — title and keywords for every paper in scope.
2. **Archived context/fig_notes** — up to 3 `critical_questions`, 4
   `headline_metrics` from `context.yaml`; up to 4 `deep_observation` /
   `visual_summary` entries from `fig_notes.yaml` per paper.
3. **Hybrid-retrieved excerpts** — the same dense + BM25 + RRF retriever used
   by the in-run pipeline, queried with the topic string (`--top-k 18` by
   default).

### Design note: s08 in-run context is deferred

`synthesize` deliberately does NOT inject s08 in-run library context. The
anchored-quote verifier treats author-named external citations as anchored
claims that require a local `cited_quote`; external citations from a synthesis
report would interact with those rules in ways that need their own grounding
design. s08 has a 5-reversal audit history and is not touched lightly. This
deferral is explicit and documented — it is not a gap to fill with a quick
patch.

## Experiments (v1.17)

Experiments become first-class library citizens — validated, deep-read, and
searchable alongside papers. After ingest, a single `query` call spans both
papers and experiments with no extra flags.

### Purpose

`exp-ingest` gives experiment bundles (curve images, metrics CSVs, lab notes,
`exp.yaml` manifest) the same treatment as papers: vision deep-read per curve
(cached in `exp_notes.yaml`), deterministic metrics digest, corpus
chunk+embedded into the **shared** `chunks` table (`kind="experiment"`). The
manifest records env/software/hyperparams/linked papers so the advisor (v1.18)
can reason across the paper↔experiment data layer.

### Bundle contract

An experiment bundle is a directory with the following layout:

| File / Dir | Required? | Description |
|---|---|---|
| `exp.yaml` | **REQUIRED** | Manifest: `title`, `env`, `software`, `hyperparams: {...}`, `papers: [paper_id...]`, `date` |
| `*.md` (e.g. `notes.md`) | optional | Free-form lab notes (any `*.md`) |
| `*.csv` (e.g. `metrics.csv`) | optional | Any CSV with a header row and numeric columns |
| `*.png` / `*.jpg` at top level or `curves/` | optional | Experiment curve images |

### Quickstart

```bash
uv run python -m cli exp-ingest my-exp-01/
uv run python -m cli exp-ingest my-exp-01/ --id custom-id   # override experiment id
uv run python -m cli exp-ingest my-exp-01/ --skip-vision    # skip vision LLM calls
uv run python -m cli exp-ingest my-exp-01/ --lang en        # English curve analysis (default: zh)

# After ingest, query spans papers AND experiments:
uv run python -m cli query "CoT convergence"
```

### What happens

1. **Validate** — `exp.yaml` is loaded; missing file or missing `title` exits with a clear message.
2. **Vision deep-read** — one vision LLM call per curve image → strict YAML
   (`visual_summary`, `deep_observation`, `anomalies`). Results cached in
   `exp_notes.yaml` inside the bundle; re-running is a no-op. Audit sidecars
   written beside it: `exp_notes.<stem>.prompt.md` and
   `exp_notes.<stem>.response.json`.
3. **Metrics digest** — deterministic, no LLM: per numeric column `min/max/last`
   and row count for every `*.csv`.
4. **Corpus** — `exp.yaml` dump + lab notes + metrics digest + curve analyses
   flattened into one document, then chunked (SentenceSplitter 400/80) and
   embedded into the **shared** `chunks` table with `kind="experiment"`.
5. **Archive** — bundle artifacts copied to `<library>/experiments/<id>/`
   (survives bundle deletion): `exp.yaml`, `exp_notes.yaml`, `*.md`, `*.csv`,
   curve images under `curves/`.
6. **Manifest** — entry added with `kind: experiment`, `env`, `software`,
   `hyperparams` keys, `papers` (linked paper ids), `n_chunks`,
   `embedding_dim`, `ingested_at`, `source_bundle`.

### Video deferral note

Video artifacts are not yet supported. Planned path: ffmpeg keyframe sampling
via Docker; extracted frames will reuse the curve vision pipeline exactly.
