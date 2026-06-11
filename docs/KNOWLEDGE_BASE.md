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
