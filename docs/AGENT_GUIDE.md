# lazy-paper — AI Agent Guide

This document is written for an AI coding agent (Claude Code, Cursor, Copilot, etc.) that has been asked to maintain, extend, or debug this repository. It assumes you have already read `docs/INTERNAL/HANDOFF.md` and `docs/ARCHITECTURE.md`.

## TL;DR for agents

1. **Don't touch `runs/`** unless the user explicitly asks you to clean it. It's the verified-test corpus.
2. **Always run `uv run pytest -q` before and after any change**. If you break tests, fix them or revert. 158 should pass; live-LLM tests are gated behind `-m live`.
3. **Use `LLM_MAX_TOKENS_CEILING` env var to cap spend** in test runs (e.g. `LLM_MAX_TOKENS_CEILING=4000` for fast smoke tests).
4. **Don't bypass `llm.client.max_tokens()`**. All LLM calls go through it. Bumping a hardcoded `max_tokens=N` is a regression.
5. **Prompt edits require `_PROMPT_VERSION` bumps** in `stages/s09_render/pptx_summarizer.py` (or equivalent in other LLM stages) — otherwise cached responses won't invalidate.
6. **End-to-end verify before pushing**. Pick at least 2 of the 5 verified papers in `runs/`, clear `s09_render/`, re-run with `--only s09_render --force`. The PPT outline should produce 4–5 grouped sections with takeaway descriptions, not a flat per-chapter list.

---

## Workflow patterns observed during v1.0–v1.1 development

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

Three layers:
1. **Stage `done.yaml`**: bypassed with `--force`.
2. **PPTX summarizer LLM cache** (`s09_render/llm_cache/`): keyed on SHA-256 of `_PROMPT_VERSION` + lang + input content. Bump the version constant when prompt semantics change.
3. **`s06`/`s07`/`s08` audit files**: written every run but the stage's `done.yaml` causes the whole stage to skip. Use `--force` or delete the stage dir.

If a paper produces wrong output and you suspect cache staleness, the bluntest fix is `rm -rf runs/<paper_id>/{s08_section_compose,s09_render}` then re-run.

### Common failure modes seen in development

| Symptom | Root cause | Fix |
|---|---|---|
| Empty PPT outline (flat 15-row list, no group descriptions) | LLM returned empty content (DeepSeek-Reasoner reasoning tokens ate `max_tokens` budget) | Already fixed in v1.1: `max_tokens(16000)` for outline + explicit empty-response check. Don't lower it. |
| Front-half/back-half numbering inconsistency in chapter headings | s08 was concatenating template's `number` field; template had `number:''` for some, `'12'..'17'` for others | Already fixed in v1.1: s08 no longer embeds number. PPT renderer adds positional 01–N prefix. |
| `--only s08,s09` silently runs nothing | `--only` didn't split on comma | Already fixed in v1.1: `--only s08,s09` now works; unknown stages raise SystemExit. |
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

## File map for orientation

```
cli.py                          # entrypoint; argparse + stage dispatch
conftest.py                     # pytest-wide fixtures; macOS DYLD shim

llm/
  client.py                     # LLM class (OpenAI-compatible) + max_tokens() helper
  models.yaml                   # role -> env_prefix + default model
  prompts/*.md                  # one prompt per LLM call site

stages/_common/                 # shared helpers (yaml, paths, done-marker, images, bbox)
stages/sNN_<name>/runner.py     # stage entrypoint; called by cli._run_one
stages/sNN_<name>/tests/        # per-stage unit tests

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

1. `uv run pytest -q` → 158 pass, 2 deselected.
2. End-to-end smoke on at least 2 papers (re-run `--only s09_render --force`).
3. Update `CHANGELOG.md` Unreleased section.
4. Commit with a clear message (explain the *why*, not just the *what*).
5. `git push origin main` only after the user confirms.
6. If the change is user-visible, mention output paths in your final message.
