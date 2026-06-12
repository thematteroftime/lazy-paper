# Template Authoring

`lazy-paper template` turns YOUR research question into the outline the
pipeline runs on — instead of picking the closest hand-written template (the
single most load-bearing choice, see README), you generate one that matches
both the paper and your intent.

## Quickstart

```bash
# From a new PDF (text-layer prescan, no OCR API):
uv run python -m cli template --idea "can this transfer to bipeds?" \
  --pdf papers/mypaper.pdf --lang en

# From an existing run (richer: chapters, captions, context):
uv run python -m cli template --idea "能量项的代价与约束" --run mypaper

# Grounded in your knowledge library (adds cross-paper comparison questions):
uv run python -m cli template --idea "..." --run mypaper --use-library
```

Output: `templates/auto-<idea-slug>.docx` + `.prompt.md` / `.response.json`
audit sidecars. The console prints the full outline for review.

## The contract

- The docx is **plain Word** — open it, edit titles/questions, delete or add
  sections. Human review is the intended last step, not an afterthought.
- It round-trips **deterministically** through stage s05: numbered lines
  ("1 Title") become section headings; every question is a plain paragraph
  and lands in that section's `guidance`. A self-check parses the file with
  the real s05 parser right after writing and hard-fails on any drift.
- Then run the pipeline as usual: `… run --pdf <paper> --template <generated>`.

## Knobs

| Flag | Effect |
|---|---|
| `--idea` (required) | Your lens; ≥ half of all questions must serve it |
| `--pdf` / `--run` | Prescan source: cheap text layer vs existing artifacts |
| `--use-library` | Inject library manifest + idea-relevant excerpts; forces ≥ 2 named cross-paper comparison questions |
| `--sections N` | Outline width (default 6) |
| `--lang zh\|en` | Language of titles and questions |
