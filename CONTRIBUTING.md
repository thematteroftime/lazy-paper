# Contributing to lazy-paper

## Development setup

```bash
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env  # add your API keys
```

## Running tests

```bash
uv run pytest             # 250 tests, ~25s
uv run pytest -m live     # live LLM smoke tests (skipped by default)
```

## Code style

- 4-space indent, no tabs
- Type hints on public function signatures
- Prefer dataclasses over plain dicts for structured data
- Renderers must consume the `Document` model and never mutate it
- LLM prompts live in `llm/prompts/*.md` with `.replace(...)` placeholders

## Pull request guidelines

- Branch off `main`, name like `feat/<topic>` or `fix/<topic>`
- One commit per logical change preferred; squash on merge is fine
- All tests must pass: `uv run pytest -q`
- For renderer changes, add a smoke test in `stages/s09_render/tests/`
- For new pipeline stages, mirror the `runner.py` + `tests/` layout of existing stages

## Reporting issues

When reporting a paper that does not process correctly, attach:

- The `runs/<paper_id>/<stage>/done.yaml` for the failing stage
- The relevant `.prompt.md` and `.response.json` from `runs/<paper_id>/...` if applicable
- The OCR backend used (`OCR_BACKEND` env var)
