# lazy-paper — AI Agent Guide

This document is written for an AI coding agent (Claude Code, Cursor, Copilot, etc.) that has been asked to maintain, extend, or debug this repository. It assumes you have already read `docs/INTERNAL/HANDOFF.md` and `docs/ARCHITECTURE.md`.

## TL;DR for agents

1. **Don't touch `runs/`** unless the user explicitly asks you to clean it. It's the verified-test corpus.
2. **Always run `uv run pytest -q` before and after any change**. If you break tests, fix them or revert. 253 should pass; live-LLM tests are gated behind `-m live`.
3. **Use `LLM_MAX_TOKENS_CEILING` env var to cap spend** in test runs (e.g. `LLM_MAX_TOKENS_CEILING=4000` for fast smoke tests).
4. **Don't bypass `llm.client.max_tokens()`**. All LLM calls go through it. Bumping a hardcoded `max_tokens=N` is a regression.
5. **Prompt edits require `_PROMPT_VERSION` bumps** in `stages/s09_render/pptx_summarizer.py` (or equivalent in other LLM stages) — otherwise cached responses won't invalidate.
6. **End-to-end verify before pushing**. Pick at least 2 of the 5 verified papers in `runs/`, clear `s09_render/`, re-run with `--only s09_render --force`. The PPT outline should produce 4–5 grouped sections with takeaway descriptions, not a flat per-chapter list.

---

## Workflow patterns

### When to use a subagent

Useful:
- **Long-running batch jobs** (re-rendering 5 papers takes 30–75 minutes). Dispatch as subagent so the main context isn't tied up watching.
- **Read-only code audit** (find hardcoded values, duplication, unused imports). Subagent with `subagent_type: Explore` is ideal — keeps the audit's verbose findings out of main context.
- **Focused refactor with clear acceptance** (e.g. "extract MIME helper, update 2 callers, run tests"). Dispatch with a precise prompt and a concrete test command.

Not useful:
- **Quick edits the main agent already understands**. Dispatching for a 3-line change wastes setup tokens.
- **Tasks that need rapid user feedback**. Subagent runs uninterruptable; if the user changes their mind, the subagent's work is wasted.

### Background commands vs subagents

- Use **`Bash` with `run_in_background: true`** for batch scripts (re-render scripts, long pipelines). You get a notification when the script exits; you can read its log file with `Read`.
- Use **`Agent` (subagent)** for tasks that need judgment + tool use, not just running a script.

### Cache invalidation gotchas

Four layers:
1. **Stage `done.yaml`**: bypassed with `--force`.
2. **`s05_template` content hash**: since v1.2.1, `done.yaml` records `template_sha256_16` and the CLI auto-invalidates s05 when the source docx changes — no `--force` needed. **However**, downstream stages (s08, s09) don't auto-invalidate when s05 refreshes; they still need `--force` (or directory removal) to pick up the new chapter titles.
3. **PPTX summarizer LLM cache** (`s09_render/llm_cache/`): keyed on SHA-256 of `_PROMPT_VERSION` + lang + input content. Bump the version constant when prompt semantics change.
4. **`s06`/`s07`/`s08` audit files**: written every run but the stage's `done.yaml` causes the whole stage to skip. Use `--force` or delete the stage dir.

If a paper produces wrong output and you suspect cache staleness, the bluntest fix is `rm -rf runs/<paper_id>/{s05_template,s08_section_compose,s09_render}` then re-run.

**Common gotcha**: editing `Table of Contents-*.docx` after a paper was already rendered. v1.2.1+ auto-invalidates s05, but you still need to wipe s08/s09 to propagate the new titles. The cleanest reset for one paper is:

```bash
rm -rf runs/<paper_id>/{s05_template,s08_section_compose,s09_render}
uv run python -m cli run --pdf <pdf> --template <docx> --paper-id <pid> \
  --only s05_template,s08_section_compose,s09_render --force --formats docx,pdf,html,pptx
```

### Common failure modes to watch for

| Symptom | Root cause | Fix |
|---|---|---|
| Empty PPT outline (flat 15-row list, no group descriptions) | DeepSeek-Reasoner reasoning tokens can eat the `max_tokens` budget before content is emitted | Outline calls use `max_tokens(16000)` + an explicit empty-response check; don't lower the budget for outline. |
| Front-half/back-half numbering inconsistency in chapter headings | Template `number` field is sparse (`''` for some, `'12'..'17'` for others); concatenating it into the heading produces mixed forms | s08 must not embed the template `number`; the PPT renderer adds a positional 01–N prefix. |
| `--only s08,s09` silently runs nothing | A regex/split bug in the `--only` parser | The CLI splits on comma and raises `SystemExit` for unknown stages — verify both behaviors stay intact if you touch `cli.py`. |
| Subagent dispatched but never completed | Likely context limit hit, session timeout, or agent ran into permission denial silently | Verify with `TaskOutput` or by checking the log file written by the script the subagent ran. Don't assume "subagent finished == work done". |

### Anti-patterns to avoid

- **Editing the docx template by hand-coding the parse logic to special-case it.** If the template parsing is wrong, fix the parser (`stages/s05_template/runner.py`), not the template. The template is user data; the parser is yours.
- **Adding hardcoded paper-specific logic to fix one paper.** If `he2023` fails, fix the general code path so it can't fail. If you must special-case (e.g. a known bad PDF), gate it behind a flag.
- **Removing tests that fail after your change.** Diagnose first: is your change wrong, or is the test obsolete? Update the test only if its assertion no longer reflects intent.
- **Bumping prompt versions without re-rendering verified papers.** A version bump invalidates all caches → next user run will re-LLM everything → unexpected cost.
- **Marking a task complete because the build passes.** Visual review on actual output is part of "complete" for renderer changes. Convert PPT to PNG, look at it.

### Visual verification

The PPT renderer's bugs are usually visual (font too small, overlap, wrong language). Always render to PNG for inspection:

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice \
  --headless --convert-to pdf --outdir /tmp/preview \
  runs/<paper_id>/s09_render/preview.pptx

uv run --with pymupdf python -c "
import fitz
doc = fitz.open('/tmp/preview/preview.pdf')
for i in [0, 1, 4, 7]:
    if i < len(doc):
        doc[i].get_pixmap(dpi=120).save(f'/tmp/preview/s{i+1:02d}.png')
"
```

Then read the PNGs via the Read tool to inspect.

### Talking to the user

- Be **terse**. The user has spent hours iterating on PPT layout; they don't want narration.
- **State results and decisions directly**. "Fixed X by Y. 5 papers verified. Pushed." is better than "I have completed the work. Let me explain what I did."
- **Don't ask for permission for low-risk reversible work** (e.g. running tests, reading files). Do ask before pushing, before destructive `rm`, before `git push --force`.
- **Output paths matter**. When you finish a render, give the user the absolute paths to the artifacts so they can open them.

---

## PaperDB + retriever workflow patterns

### When to re-run KG extraction vs reuse it

`paper_kg.parquet` is written once by s06 and **survives `--force` on s06** by design. KG extraction is a full-paper LLM call; re-running it costs ~1 API call per paper and takes 15–30 seconds. Delete the file explicitly to force re-extraction:

```bash
rm runs/<paper_id>/s06_context/paper_kg.parquet
uv run python -m cli run ... --only s06_context --force
```

When to re-extract:
- The `kg_extract.py` prompt or schema changed (bump schema version).
- A paper produced a `kg_extract.failed` marker that you believe is spurious (e.g. transient API error).
- You manually edited chapter text and want the KG to reflect the edit.

When to leave it alone:
- Re-running s08 with `--force` (the KG is unchanged; only evidence retrieval and composition run fresh).
- Bumping `_CHAPTER_PROMPT_VERSION` in pptx_summarizer (that only invalidates the s09 cache, not the KG).

`retrieval.parquet` follows the same rule: it survives `--force` on s08 unless explicitly deleted or `retrieval.failed` is present.

### Debugging retriever quality

To inspect what evidence a section would receive without running the full pipeline:

```python
uv run python -c "
from llm.retriever import Retriever
r = Retriever.load('runs/<paper_id>/s08_section_compose/retrieval.parquet')
hits = r.retrieve('your query here', top_k=8)
for h in hits:
    print(h.score, h.text[:120])
"
```

If hits look irrelevant, check:
1. Was `retrieval.parquet` built from the correct chapter set? (check `done.yaml` in s08 for `retriever` field)
2. Is the query text close to actual section guidance? Use the template's guidance string verbatim.
3. Is KG entity boost helping or hurting? Try `entity_boost=[]` to isolate dense+BM25 baseline.

If `retrieval.failed` is present, s08 has already logged `[degraded] keyword fallback for <paper>` — check that the embedding API key (`LLM_EMBEDDINGS_API_KEY`, which auto-inherits from `LLM_VISION_API_KEY` if unset) is valid.

### Interpreting critic_flags.yaml

`s08_section_compose/critic_flags.yaml` is produced by `reviewer.regex_check()` after each section is composed. Format:

```yaml
- section: "Introduction"
  flags:
    - span: [42, 55]
      claim: "8.6 J/cm³"
      problem: numeric_not_in_source
      evidence: null
    - span: [120, 132]
      claim: "Fig. 99"
      problem: fig_not_in_yaml
      evidence: null
```

**Current behavior:** the regex tier gates the LLM tier — `reviewer.llm_review()` only runs when `regex_check()` returns ≥1 flag. Check `critic_flags.yaml` to understand why an LLM critic revision was triggered, or to audit s08 output quality post-hoc when no LLM critic ran.

Problem codes and what they mean:

| Code | Meaning |
|---|---|
| `numeric_not_in_source` | A numeric value (with unit) in the draft doesn't appear in any source chunk after unit normalization. |
| `fig_not_in_yaml` | A `Fig. N` or `Table N` reference in the draft doesn't match any entry in `figures.yaml`. |
| `formula_not_in_kg` | A chemical formula or symbol binding in the draft doesn't match any KG entity. |
| `unit_mismatch` | Two values refer to the same quantity but with incompatible units (e.g. kV/cm vs MV/cm, failing normalization). |

### Opting into the experimental pydantic-ai agent

The section agent (`stages/s08_section_compose/agent.py`) is gated behind `LAZY_PAPER_AGENT=1`. To enable:

```bash
LAZY_PAPER_AGENT=1 uv run python -m cli run ... --only s08_section_compose --force
```

The agent runs up to 8 tool cycles per section (`query_kg`, `retrieve`, `check_source`, then `emit_section`). Each tool call is logged to stderr. Watch for:

- `[degraded] agent fallback for <section>` — agent hit an error or iter cap; section was composed via legacy path.
- Sections where the draft contains meta-commentary ("I will now synthesize…") — the agent returned prose about writing instead of actual section text. This is why the flag exists; the default path is stable.

Do not enable `LAZY_PAPER_AGENT=1` in CI or automated batch runs until the agent output has been audited on your specific paper corpus.

### Citation render modes and --debug-citations

By default, `[span:doc_X:Y-Z]` citation markers are stripped from DOCX and HTML output (mode: `REMOVE`). To expose them for debugging:

```bash
uv run python -m cli run ... --debug-citations
```

This switches the citation adapter to `KEEP` mode, leaving markers in place as literal text. Use this when:

- Auditing whether retrieved chunks are cited in the final prose.
- Checking that `emit_section` correctly required ≥1 citation before accepting a draft.
- Tracing a hallucination back to which retrieval chunk (or absence thereof) was responsible.

PPTX speaker notes always carry the markers regardless of `--debug-citations`.

---

## File map for orientation

```
cli.py                          # entrypoint; argparse + stage dispatch
conftest.py                     # pytest-wide fixtures; macOS DYLD shim

llm/
  client.py                     # LLM class (OpenAI-compatible) + max_tokens() helper
  models.yaml                   # role -> env_prefix + default model
  prompts/*.md                  # one prompt per LLM call site
  retriever.py                  # Retriever: build_index() + retrieve() (llama-index + bm25s + RRF)
  citation/
    __init__.py                 # process_text() — REMOVE / KEEP / HYPERLINK modes
    models.py                   # SearchDoc / CitationInfo helpers

stages/_common/                 # shared helpers (yaml, paths, done-marker, images, bbox)
stages/sNN_<name>/runner.py     # stage entrypoint; called by cli._run_one
stages/sNN_<name>/tests/        # per-stage unit tests

stages/s06_context/
  runner.py                     # context.yaml + triggers kg_extract
  kg_extract.py                 # instructor-driven 10-type KG → paper_kg.parquet

stages/s08_section_compose/
  runner.py                     # retriever-fed compose + reviewer orchestration
  agent.py                      # pydantic-ai agent (LAZY_PAPER_AGENT=1)
  reviewer.py                   # regex_check() + llm_review() (CritiqueRevision)
  _units.py                     # unit normalization (kV/cm ↔ MV/cm, etc.)

stages/s09_render/
  builder.py                    # markdown chapters -> immutable Document
  model.py                      # Document / Chapter / Block dataclasses
  slide_planner.py              # Document -> SlideDeck (deterministic)
  pptx_summarizer.py            # LLM-backed summarize_outline / summarize / summarize_paper (cached)
  renderers/{base,docx,html,pdf,pptx}.py
  templates/                    # Jinja2 templates for html/pdf renderers

docs/
  ARCHITECTURE.md               # per-stage contract (read after this file)
  AGENT_GUIDE.md                # you are here
  USER_GUIDE.md                 # end-user runbook (setup, quickstart, iteration, troubleshooting)
  INTERNAL/HANDOFF.md           # production hand-off summary
  INTERNAL/superpowers/         # historical specs + plans

tests/                          # cross-cutting tests (cli, llm client, etc.)
runs/                           # gitignored — per-paper artifacts (5 verified papers committed locally)

CHANGELOG.md                    # Keep-a-Changelog format
README.md                       # human-oriented quick start
CONTRIBUTING.md                 # contribution norms
```

---

## When you're done

1. `uv run pytest -q` → 253 pass, 2 deselected.
2. End-to-end smoke on at least 2 papers (re-run `--only s09_render --force`).
3. Update `CHANGELOG.md` Unreleased section.
4. Commit with a clear message (explain the *why*, not just the *what*).
5. `git push origin main` only after the user confirms.
6. If the change is user-visible, mention output paths in your final message.
