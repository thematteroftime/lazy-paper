# v1.12 Phase 4 — Two-Stage Prompt Tailoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cheap pre-stage LLM call in `s06_context` that reads the paper's already-extracted context.yaml + intro chapter and emits `prompt_augment.yaml`. s08 prepends a small render of this YAML to `_STRUCTURED_SYSTEM` before each compose call, so the thinking LLM gets a paper-tailored prompt instead of a one-size-fits-all template with hypothetical-other-domain examples (Phase 3c's failed approach).

**Architecture:** New sub-step at end of `stages/s06_context/runner.py` (env-gated). New module `stages/s06_context/prompt_tailor.py` (≈80 LOC, mockable LLM call). New prompt `llm/prompts/prompt_tailor.md`. s08 augmentation is a small inline render in `compose_structured()` that prepends to `_STRUCTURED_SYSTEM`. All gated behind `LAZY_PAPER_PROMPT_TAILOR=1` (default OFF — only ships ON if RAGAS ship gate passes in Task 6).

**Tech Stack:** Python 3.11+ (uv), pytest, existing s06/s08 compose pipeline, DeepSeek-chat (same model both stages — "cheap pre-stage" = ~1K-token call, not a different model).

**Spec reference:** `docs/superpowers/specs/2026-05-26-v1_12-phase4-prompt-tailoring-design.md`

---

## File Structure

**New files:**
- `llm/prompts/prompt_tailor.md` — ~50 lines instructions for the pre-stage LLM
- `stages/s06_context/prompt_tailor.py` — single function `generate_prompt_augment(context, chapters_dir)` → dict; pure (LLM injectable)
- `stages/s06_context/tests/test_prompt_tailor.py` — 4 tests (mocked LLM)
- `docs/archive/v1_12_phase4_summary.md` — final report with RAGAS data

**Modified files:**
- `stages/s06_context/runner.py:108` — append env-gated sub-step that calls `generate_prompt_augment` and dumps `prompt_augment.yaml`
- `stages/s08_section_compose/runner.py:357-400` — load `prompt_augment.yaml` from `context_dir` if present; pass as kwarg to `compose_structured`
- `stages/s08_section_compose/structured.py` — add `_render_augment_block(aug)` helper near `_STRUCTURED_SYSTEM`; modify `compose_structured` signature + 6 `_single_compose` call sites to use augmented system prompt
- `.env.example` — `LAZY_PAPER_PROMPT_TAILOR=0` block
- `docs/USER_GUIDE.md` — new subsection
- `docs/ARCHITECTURE.md` — new §4.6.5 explaining the two-stage prompt design
- `CHANGELOG.md` — `[v1.12-phase4]` entry (after RAGAS data in)

**Out of scope:**
- Splitting model tier (small vs large LLM) — same `LLM(role="text")` for both stages.
- Re-doing Phase 3b compression or Phase 3c example-stuffing — those stay reverted.
- Auto-flipping the default to ON — ship gate in Task 6 first; flip in a follow-up commit if gate passes.

---

## Task 1: Write the prompt file `prompt_tailor.md`

**Files:**
- Create: `llm/prompts/prompt_tailor.md`

- [ ] **Step 1: Create the prompt file**

Write `llm/prompts/prompt_tailor.md`:

```markdown
You are an information-extraction pre-processor that produces a per-paper
prompt-augmentation block. A downstream "thinking" LLM will receive this
block prepended to its system prompt to write deep-analysis sections.

Your output MUST be a JSON object with these exact top-level keys:

- `domain_framing`: 2-3 sentence prose describing what this paper is about,
  what methods it uses, and what its main evaluation metrics are. Drawn
  strictly from the provided context — do not generalize from prior knowledge.

- `terminology`: list of {term, note} objects. Include 5-10 terms that:
  1. Appear repeatedly in the paper text (you'll see the intro chunk).
  2. Have a specific in-paper meaning the LLM should preserve verbatim
     (chemical formulas, abbreviations, named methods).
  Notes should explain in 1 short sentence (with units / format hints).

- `metric_patterns`: list of {kind, regex} objects. Include 2-5 patterns
  matching the quantitative values that actually appear in this paper.
  Use Python regex syntax. Cover the main metric units of this paper.

- `comparator_style`: object with two keys:
  - `format`: a 1-line template the LLM should use when citing prior work
    (e.g. `<Author> et al. (year) reported <metric>=<value> in <system>`).
  - `example_from_paper`: a real citation snippet from this paper's intro
    (must be present in the provided text — do not invent).

## Hard rules

- Extract EVERYTHING from the supplied context. NEVER invent terminology
  or examples that aren't visible in the input.
- If a section can't be filled from the input, return its key with an
  empty value (`""` for strings, `[]` for lists), DO NOT make up content.
- Output ONLY the JSON object. No prose, no markdown fences.

## Input shape

You receive a `<<<CONTEXT>>>` block followed by a `<<<INTRO>>>` block.
CONTEXT is the paper's extracted metadata (title / system / abbreviations
/ key_terms / keywords / headline_metrics, all already from this paper).
INTRO is the first 3000 characters of the introduction chapter.
```

- [ ] **Step 2: Verify the file is readable**

Run: `wc -l llm/prompts/prompt_tailor.md`
Expected: ~40-50 lines.

- [ ] **Step 3: Commit**

```bash
git add llm/prompts/prompt_tailor.md
git commit -m "feat(s06): prompt for the two-stage prompt-tailoring pre-stage (T1 v1.12 phase 4)

Instructs the pre-stage LLM to read the paper's already-extracted context.yaml
and intro chunk, then emit a JSON object with domain_framing / terminology /
metric_patterns / comparator_style. All content must be drawn from the supplied
context — NEVER invent terminology or examples.

Consumed by stages.s06_context.prompt_tailor (T2)."
```

---

## Task 2: Implement the `prompt_tailor.py` module + 4 unit tests (TDD)

**Files:**
- Create: `stages/s06_context/prompt_tailor.py`
- Create: `stages/s06_context/tests/test_prompt_tailor.py`

- [ ] **Step 1: Write the failing tests**

Create `stages/s06_context/tests/test_prompt_tailor.py`:

```python
"""Tests for prompt_tailor — LLM mocked."""
from __future__ import annotations

import json
from pathlib import Path


def test_generate_prompt_augment_happy_path(tmp_path):
    """Mocked LLM returns valid JSON; function returns parsed dict + adds metadata."""
    from stages.s06_context.prompt_tailor import generate_prompt_augment

    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text(
        "Intro text about NBST ceramics. Jiang et al. reported W_rec=2.94 J/cm³."
    )

    context = {
        "title": "Demo paper", "system": "NBST-BMZ", "abbreviations": [],
        "keywords": [], "key_terms": [], "headline_metrics": {},
    }
    valid_response = json.dumps({
        "domain_framing": "lead-free relaxor antiferroelectric ceramics",
        "terminology": [{"term": "W_rec", "note": "energy density J/cm³"}],
        "metric_patterns": [{"kind": "energy", "regex": "\\d+\\.\\d+\\s*J/cm³"}],
        "comparator_style": {
            "format": "<Author> et al. reported <metric>=<value>",
            "example_from_paper": "Jiang et al. reported W_rec=2.94 J/cm³",
        },
    })
    out = generate_prompt_augment(
        context=context, chapters_dir=chapters_dir,
        llm_chat=lambda **_: valid_response,
    )
    assert out["domain_framing"].startswith("lead-free")
    assert out["terminology"][0]["term"] == "W_rec"
    assert "generated_by" in out and out["generated_by"].startswith("prompt_tailor_v")
    assert "generated_at" in out


def test_generate_prompt_augment_malformed_json_raises(tmp_path):
    """LLM returns non-JSON → function raises so caller can soft-degrade."""
    from stages.s06_context.prompt_tailor import (
        generate_prompt_augment,
        PromptTailorError,
    )
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text("intro")

    context = {"title": "x"}
    import pytest
    with pytest.raises(PromptTailorError):
        generate_prompt_augment(
            context=context, chapters_dir=chapters_dir,
            llm_chat=lambda **_: "this is not json",
        )


def test_generate_prompt_augment_missing_required_keys_raises(tmp_path):
    """LLM JSON missing one of the 4 required keys → PromptTailorError."""
    from stages.s06_context.prompt_tailor import (
        generate_prompt_augment,
        PromptTailorError,
    )
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text("intro")

    incomplete = json.dumps({"domain_framing": "x", "terminology": []})
    import pytest
    with pytest.raises(PromptTailorError):
        generate_prompt_augment(
            context={"title": "x"}, chapters_dir=chapters_dir,
            llm_chat=lambda **_: incomplete,
        )


def test_generate_prompt_augment_no_intro_chapter_uses_empty_intro(tmp_path):
    """If chapter_001_INTRODUCTION.md doesn't exist, pass empty intro and still call LLM."""
    from stages.s06_context.prompt_tailor import generate_prompt_augment

    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    # No intro file written.

    received_user = {}

    def capture_chat(**kw):
        received_user["user"] = kw.get("user", "")
        return json.dumps({
            "domain_framing": "", "terminology": [],
            "metric_patterns": [],
            "comparator_style": {"format": "", "example_from_paper": ""},
        })

    generate_prompt_augment(
        context={"title": "x"}, chapters_dir=chapters_dir,
        llm_chat=capture_chat,
    )
    # The INTRO block in the user prompt should be empty but the marker present.
    assert "<<<INTRO>>>" in received_user["user"]
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest stages/s06_context/tests/test_prompt_tailor.py -v`
Expected: 4 failures with `ImportError: cannot import name 'generate_prompt_augment' from 'stages.s06_context.prompt_tailor'`.

- [ ] **Step 3: Implement the module**

Create `stages/s06_context/prompt_tailor.py`:

```python
"""Pre-stage prompt tailoring (v1.12 phase 4).

Reads the paper's already-extracted context.yaml + intro chunk and emits a
per-paper augmentation block (domain framing, terminology, metric patterns,
comparator style example FROM THIS PAPER). s08 prepends a render of this
block to _STRUCTURED_SYSTEM before each compose call.

Gated by LAZY_PAPER_PROMPT_TAILOR=1 in the caller (s06_context.runner);
this module just implements the LLM call + schema validation. Soft-degrade
is the caller's responsibility (catch PromptTailorError, drop a .failed
marker, let s08 fall back to vanilla _STRUCTURED_SYSTEM).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Callable

import yaml

PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "prompt_tailor.md"
VERSION = "prompt_tailor_v1"
_REQUIRED_KEYS = ("domain_framing", "terminology", "metric_patterns", "comparator_style")


class PromptTailorError(RuntimeError):
    """Raised when the pre-stage LLM response cannot be parsed/validated."""


def _read_intro_chunk(chapters_dir: Path, max_chars: int = 3000) -> str:
    """Return the first `max_chars` of chapter_001_INTRODUCTION.md, or ''."""
    intro_path = chapters_dir / "chapter_001_INTRODUCTION.md"
    if not intro_path.exists():
        return ""
    text = intro_path.read_text(encoding="utf-8")
    return text[:max_chars]


def _build_user_prompt(context: dict, intro: str) -> str:
    """Render the user message: <<<CONTEXT>>> + <<<INTRO>>> blocks."""
    ctx_yaml = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)
    return (
        "<<<CONTEXT>>>\n"
        f"{ctx_yaml}"
        "<<<INTRO>>>\n"
        f"{intro}\n"
    )


def _parse_and_validate(text: str) -> dict:
    """Parse JSON; ensure all required top-level keys are present."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PromptTailorError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise PromptTailorError(f"LLM JSON root is not an object: {type(obj).__name__}")
    missing = [k for k in _REQUIRED_KEYS if k not in obj]
    if missing:
        raise PromptTailorError(f"LLM JSON missing keys: {missing}")
    return obj


def generate_prompt_augment(
    *,
    context: dict,
    chapters_dir: Path,
    llm_chat: Callable[..., str] | None = None,
) -> dict:
    """Run the pre-stage LLM and return a validated augmentation dict.

    `llm_chat` is injectable for tests; in prod it wraps llm.client.LLM.chat.
    Raises PromptTailorError on parse/validation failure — caller decides
    whether to soft-degrade (drop a .failed marker and continue without
    augmentation).
    """
    if llm_chat is None:
        from llm.client import LLM
        client = LLM(role="text")

        def _real_chat(**kw):
            return client.chat(**kw).content

        llm_chat = _real_chat

    system = PROMPT_PATH.read_text(encoding="utf-8")
    intro = _read_intro_chunk(chapters_dir)
    user = _build_user_prompt(context, intro)
    resp = llm_chat(system=system, user=user, temperature=0.1, max_tokens=2000)
    out = _parse_and_validate(resp)
    out["generated_by"] = VERSION
    out["generated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    return out
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest stages/s06_context/tests/test_prompt_tailor.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/s06_context/prompt_tailor.py stages/s06_context/tests/test_prompt_tailor.py
git commit -m "feat(s06): prompt_tailor module + 4 unit tests (T2 v1.12 phase 4, TDD)

generate_prompt_augment(context, chapters_dir, llm_chat=...) reads the paper's
extracted context + intro chunk and emits a validated dict with domain_framing,
terminology, metric_patterns, comparator_style + generated_by/at metadata.
PromptTailorError on parse/validation failure (caller soft-degrades).

Tests cover: happy path, malformed JSON, missing required keys, missing intro
chapter — all with mocked LLM, no live network calls."
```

---

## Task 3: Wire `prompt_tailor` into `s06_context/runner.py` behind env gate

**Files:**
- Modify: `stages/s06_context/runner.py:108` (after headline_metrics injection)

- [ ] **Step 1: Confirm `os` is already imported**

Run: `grep -n "^import os\|^from os" stages/s06_context/runner.py | head`
Expected: at least one match.

- [ ] **Step 2: Insert env-gated sub-step at the end of `run()`**

Find the line in `stages/s06_context/runner.py` immediately AFTER the
`headline = extract_headline_metrics(kg)` block (around line 108-112):

```python
        headline = extract_headline_metrics(kg)
        if headline:
            data["headline_metrics"] = headline
```

AFTER that `if headline:` block (and BEFORE `dump_yaml(out_dir / "context.yaml", data)`), insert:

```python
    # v1.12 phase 4: optional prompt-tailoring pre-stage.
    # When LAZY_PAPER_PROMPT_TAILOR=1, run a cheap LLM call to emit a
    # per-paper prompt-augmentation block that s08 will prepend to
    # _STRUCTURED_SYSTEM. Soft-degrade on any failure — drop a marker
    # file and let s08 fall back to the vanilla prompt.
    if os.environ.get("LAZY_PAPER_PROMPT_TAILOR", "0") == "1":
        from stages.s06_context.prompt_tailor import (
            generate_prompt_augment, PromptTailorError,
        )
        try:
            augment = generate_prompt_augment(context=data, chapters_dir=chapters_dir)
            dump_yaml(out_dir / "prompt_augment.yaml", augment)
            extra["prompt_tailor"] = "ok"
        except PromptTailorError as exc:
            (out_dir / "prompt_tailor.failed").write_text(repr(exc), encoding="utf-8")
            extra["prompt_tailor"] = "failed"
        except Exception as exc:  # LLM transport / unexpected
            (out_dir / "prompt_tailor.failed").write_text(repr(exc), encoding="utf-8")
            extra["prompt_tailor"] = f"failed: {type(exc).__name__}"
```

- [ ] **Step 3: Run existing s06 tests (no regression)**

Run: `uv run pytest stages/s06_context/tests/ -q --no-header`
Expected: all pass (the new code path is gated OFF by default).

- [ ] **Step 4: Verify smoke — module imports & gate works**

Run:
```bash
uv run python -c "
import os
os.environ.pop('LAZY_PAPER_PROMPT_TAILOR', None)
from stages.s06_context.runner import run as s06_run
# Just import-check; full e2e is in Task 6.
print('s06 runner imports OK with gate OFF')
"
```
Expected: `s06 runner imports OK with gate OFF`.

- [ ] **Step 5: Commit**

```bash
git add stages/s06_context/runner.py
git commit -m "feat(s06): wire prompt_tailor sub-step behind LAZY_PAPER_PROMPT_TAILOR=1 (T3 v1.12 phase 4)

End of run(): after headline_metrics injection, if env flag set, call
generate_prompt_augment and dump prompt_augment.yaml. Soft-degrade on any
exception (PromptTailorError, LLM transport, anything) — write a
.failed marker so s08 falls back to vanilla _STRUCTURED_SYSTEM.

Default OFF until Task 6 RAGAS measurement confirms quality."
```

---

## Task 4: Prepend `prompt_augment` to `_STRUCTURED_SYSTEM` in s08

**Files:**
- Modify: `stages/s08_section_compose/structured.py` (add helper + thread augment_block kwarg)
- Modify: `stages/s08_section_compose/runner.py:357-400` (load augment from context_dir; pass to compose_structured)

- [ ] **Step 1: Add `_render_augment_block` helper next to `_STRUCTURED_SYSTEM`**

Find the line `_STRUCTURED_SYSTEM = """You are composing one section of a research-paper deep analysis.` (around line 777 of `structured.py`). IMMEDIATELY BEFORE that line, insert:

```python
def _render_augment_block(aug: dict | None) -> str:
    """Render the per-paper prompt_augment.yaml as a system-prompt prefix.

    Returns empty string if aug is None / missing keys — caller appends
    only when non-empty. v1.12 phase 4.
    """
    if not aug or not isinstance(aug, dict):
        return ""
    parts = ["## This paper — domain context", ""]
    framing = (aug.get("domain_framing") or "").strip()
    if framing:
        parts.append(framing)
        parts.append("")
    terms = aug.get("terminology") or []
    if terms:
        parts.append("## Terminology to preserve verbatim")
        parts.append("")
        for t in terms:
            term = t.get("term", "") if isinstance(t, dict) else str(t)
            note = t.get("note", "") if isinstance(t, dict) else ""
            if term:
                parts.append(f"- {term}: {note}".rstrip(": "))
        parts.append("")
    style = aug.get("comparator_style") or {}
    fmt = (style.get("format") if isinstance(style, dict) else "") or ""
    example = (style.get("example_from_paper") if isinstance(style, dict) else "") or ""
    if fmt or example:
        parts.append("## Comparator citation style")
        parts.append("")
        if fmt:
            parts.append(f"Format: {fmt}")
        if example:
            parts.append(f"Example from this paper: \"{example}\"")
        parts.append("")
    body = "\n".join(parts).strip()
    return body + "\n\n" if body else ""


```

(Note the trailing blank lines — the function definition is followed by two blank lines before `_STRUCTURED_SYSTEM = """...`.)

- [ ] **Step 2: Add `augment_block` parameter to `compose_structured`**

Find `def compose_structured(` (around line 1080). Add a keyword parameter `augment_block: str = ""` to its signature (place it alphabetically among kwargs, or at the end of the keyword block).

In the function body, immediately after the parameter docstring (around the first non-comment line), add:

```python
    # v1.12 phase 4: prepend per-paper augment to the system prompt.
    # augment_block is "" when prompt_tailor was OFF or failed → fall back to
    # vanilla _STRUCTURED_SYSTEM (no behaviour change).
    system_prompt = (augment_block + _STRUCTURED_SYSTEM) if augment_block else _STRUCTURED_SYSTEM
```

Then **search-and-replace inside `compose_structured`**: change every occurrence of `_STRUCTURED_SYSTEM` to `system_prompt` (there are 6 call sites at lines 1118, 1128, 1129, 1210, 1230, 1279, 1294). Use Edit's `replace_all=True` on the function body window if your editor supports limited scope, OR do them one by one verifying each is inside `compose_structured`.

VERIFY: lines OUTSIDE `compose_structured` that reference `_STRUCTURED_SYSTEM` (if any, e.g., test fixtures) MUST remain unchanged.

- [ ] **Step 3: Update s08 runner.py to load augment + pass it**

Find `stages/s08_section_compose/runner.py` around line 367 where `context = yaml.safe_load((context_dir / "context.yaml").read_text(...))` lives. After that line, add:

```python
    # v1.12 phase 4: load prompt_augment.yaml if present (gated by env in s06).
    augment_path = context_dir / "prompt_augment.yaml"
    if augment_path.exists():
        from stages.s08_section_compose.structured import _render_augment_block
        from stages._common import load_yaml
        aug_raw = load_yaml(augment_path) or {}
        augment_block = _render_augment_block(aug_raw)
    else:
        augment_block = ""
```

Then find every call to `compose_structured(...)` inside this file (likely 1 call) and add `augment_block=augment_block` to its kwargs.

- [ ] **Step 4: Run s08 unit tests (regression check)**

Run: `uv run pytest stages/s08_section_compose/tests/ -q --no-header`
Expected: all pass (existing tests don't pass augment_block → defaults to "" → behavior unchanged).

- [ ] **Step 5: Add a focused unit test for `_render_augment_block`**

Create or append to `stages/s08_section_compose/tests/test_structured.py` a new test:

```python
def test_render_augment_block_full():
    """v1.12 phase 4: full aug dict renders into a prefix block."""
    from stages.s08_section_compose.structured import _render_augment_block
    aug = {
        "domain_framing": "Lead-free RFE ceramics for energy storage.",
        "terminology": [{"term": "W_rec", "note": "energy density, J/cm³"}],
        "comparator_style": {
            "format": "<Author> et al. reported <metric>=<value>",
            "example_from_paper": "Jiang et al. reported W_rec=2.94 J/cm³",
        },
    }
    out = _render_augment_block(aug)
    assert "## This paper — domain context" in out
    assert "Lead-free RFE ceramics" in out
    assert "W_rec: energy density, J/cm³" in out
    assert "<Author> et al." in out
    assert "Jiang et al." in out
    assert out.endswith("\n\n")  # ready to prepend


def test_render_augment_block_empty_returns_empty_string():
    """Missing or empty aug → return '' so caller falls back to vanilla prompt."""
    from stages.s08_section_compose.structured import _render_augment_block
    assert _render_augment_block(None) == ""
    assert _render_augment_block({}) == ""
    assert _render_augment_block({"domain_framing": ""}) == ""
```

- [ ] **Step 6: Run the new tests**

Run: `uv run pytest stages/s08_section_compose/tests/test_structured.py::test_render_augment_block_full stages/s08_section_compose/tests/test_structured.py::test_render_augment_block_empty_returns_empty_string -v`
Expected: 2 passed.

- [ ] **Step 7: Run the whole repo test suite for regression confirmation**

Run: `uv run pytest stages/ tests/ scripts/ -q --no-header 2>&1 | tail -3`
Expected: 317 passed (315 prior + 4 from T2 + 2 from T4 step 5 = 321; adjust if T2 added different count — should be in the 320-322 range), 3 deselected.

- [ ] **Step 8: Commit**

```bash
git add stages/s08_section_compose/structured.py stages/s08_section_compose/runner.py stages/s08_section_compose/tests/test_structured.py
git commit -m "feat(s08): prepend prompt_augment to _STRUCTURED_SYSTEM (T4 v1.12 phase 4)

structured.py:
- New _render_augment_block(aug: dict | None) -> str — renders the per-paper
  augment YAML into a markdown prefix (domain_framing + terminology +
  comparator_style). Empty input → '' so caller falls back cleanly.
- compose_structured gains augment_block kwarg; the 6 _single_compose
  call sites use a local system_prompt = augment + _STRUCTURED_SYSTEM
  when augment present, else vanilla _STRUCTURED_SYSTEM (no behaviour
  change when prompt_tailor is OFF).

runner.py: load prompt_augment.yaml from context_dir if present; pass
rendered block as augment_block kwarg to compose_structured.

Tests: 2 new unit tests for _render_augment_block covering full + empty
aug cases. Existing 315 tests still pass — augment defaults to '' so all
prior callers see vanilla behaviour."
```

---

## Task 5: Document `LAZY_PAPER_PROMPT_TAILOR` flag

**Files:**
- Modify: `.env.example` (append after Phase 2 block)
- Modify: `docs/USER_GUIDE.md` (new subsection under v1.12)

- [ ] **Step 1: Append to `.env.example`**

Open `.env.example`. Find the existing `LAZY_PAPER_ANCHORED_QUOTE=1` line (Phase 2 block). After it, append:

```bash

# === v1.12 phase 4 — two-stage prompt tailoring (opt-in) ===

# When =1, s06_context runs a cheap pre-stage LLM call after KG extraction
# to produce prompt_augment.yaml (domain framing + terminology + metric
# patterns + comparator style example drawn from THIS paper). s08 prepends
# this block to its system prompt before each compose call.
# Designed for cross-domain papers; the augment specializes the generic
# prompt to whatever the paper actually contains.
# Default OFF — opt-in until RAGAS measurement confirms quality gain.
LAZY_PAPER_PROMPT_TAILOR=0
```

- [ ] **Step 2: Add a USER_GUIDE subsection**

Open `docs/USER_GUIDE.md`. Find `### Anchored-quote enforcement (v1.12 phase 2) — default ON` (or similar Phase 2 subsection). After its closing line, append:

```markdown

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
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docs/USER_GUIDE.md
git commit -m "docs(v1.12-phase4): document LAZY_PAPER_PROMPT_TAILOR flag (T5)

.env.example: v1.12 phase 4 block, default 0 (opt-in).
USER_GUIDE.md: new subsection under v1.12 features explaining the two-stage
design (cheap pre-stage + thinking stage) and the soft-degrade contract."
```

---

## Task 6: Pipeline rerun + RAGAS verification (ship gate)

**Files:**
- No code changes — execution + measurement step.

- [ ] **Step 1: Confirm symlinks + DeepSeek key alive**

Run:
```bash
ls -la runs input
uv run python -c "
import os; from dotenv import load_dotenv; load_dotenv('.env')
from openai import OpenAI
c = OpenAI(base_url=os.environ['LLM_TEXT_BASE_URL'], api_key=os.environ['LLM_TEXT_API_KEY'], timeout=15)
r = c.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'OK'}], max_tokens=3)
print('LLM probe:', r.choices[0].message.content[:10])
"
```
Expected: `LLM probe: OK` (or similar 2-3 char reply).

**If probe fails**: stop, escalate to user. Don't waste a pipeline run.

- [ ] **Step 2: Stage upstream artefacts to fresh paper-ids**

```bash
rm -rf runs/meng2024_v112_p4 runs/ali2025_flash_v112_p4
mkdir -p runs/meng2024_v112_p4 runs/ali2025_flash_v112_p4
cp -R runs/meng2024_v111_demo/{s01_ocr,s02_clean,s03_chapter,s04_figures,s06_context,s07_figure_analyze} runs/meng2024_v112_p4/
cp -R runs/ali2025_flash_v111_demo/{s01_ocr,s02_clean,s03_chapter,s04_figures,s06_context,s07_figure_analyze} runs/ali2025_flash_v112_p4/
ls runs/meng2024_v112_p4 runs/ali2025_flash_v112_p4
```
Expected: both list the 6 staged stage dirs.

- [ ] **Step 3: Re-run s06 (to generate prompt_augment.yaml) + s05/s08/s09 with the gate ON, both papers in parallel**

```bash
LLM_TEXT_MODEL=deepseek-chat \
LAZY_PAPER_PROMPT_TAILOR=1 \
LAZY_PAPER_STRUCTURED=1 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md LAZY_PAPER_BEST_OF_N=2 \
uv run python -m cli run --pdf input/hif_2.pdf \
    --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id meng2024_v112_p4 --lang zh \
    --only s06_context,s05_template,s08_section_compose,s09_render --force 2>&1 | tail -8 &
MENG_PID=$!

LLM_TEXT_MODEL=deepseek-chat \
LAZY_PAPER_PROMPT_TAILOR=1 \
LAZY_PAPER_STRUCTURED=1 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md LAZY_PAPER_BEST_OF_N=2 \
uv run python -m cli run --pdf input/hif_2.pdf \
    --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
    --paper-id ali2025_flash_v112_p4 --lang zh \
    --only s06_context,s05_template,s08_section_compose,s09_render --force 2>&1 | tail -8 &
ALI_PID=$!

wait $MENG_PID $ALI_PID
echo "both pipelines done"
```

Note: `--only s06_context` causes s06 to re-run (forcing it to produce `prompt_augment.yaml` THIS time even though the existing `context.yaml`/`paper_kg.parquet` are already there). The s06 sub-step is idempotent — it'll just re-write the artifacts.

Expected: ~10-15 min wall clock. Both pipelines end with `[done] ...` lines.

- [ ] **Step 4: Inspect the produced augment files (qualitative audit)**

```bash
echo "=== meng2024 augment ==="
cat runs/meng2024_v112_p4/s06_context/prompt_augment.yaml | head -40
echo
echo "=== ali2025 augment ==="
cat runs/ali2025_flash_v112_p4/s06_context/prompt_augment.yaml | head -40
```

Sanity-check: the augment should contain paper-specific terminology
(meng2024: NBST, W_rec, η, etc.; ali2025: PZO, FHC, U_e, etc.) drawn from
each paper individually. NO cross-contamination.

- [ ] **Step 5: Run RAGAS on baseline + Phase 2 + Phase 4 (6-way)**

```bash
cp tests/eval/golden_qa/meng2024.yaml tests/eval/golden_qa/meng2024_p4.yaml
sed -i '' 's/meng2024_v111_demo/meng2024_v112_p4/' tests/eval/golden_qa/meng2024_p4.yaml
cp tests/eval/golden_qa/ali2025_flash.yaml tests/eval/golden_qa/ali2025_p4.yaml
sed -i '' 's/ali2025_flash_v111_demo/ali2025_flash_v112_p4/' tests/eval/golden_qa/ali2025_p4.yaml

LLM_TEXT_MODEL=deepseek-chat uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s 2>&1 | tail -5
```

Expected: `1 passed`, ~4-6 minutes wall clock. JSON files in `tests/eval/_ragas_out/`.

- [ ] **Step 6: Compare and decide ship**

```bash
for p in meng2024_v111_demo meng2024_v112_anchoredq meng2024_v112_p4 \
         ali2025_flash_v111_demo ali2025_flash_v112_anchoredq ali2025_flash_v112_p4; do
    if [ -f tests/eval/_ragas_out/$p.json ]; then
        printf "%-40s " "$p"
        cat tests/eval/_ragas_out/$p.json | python3 -c \
          "import json,sys; d=json.load(sys.stdin); print(f'faith={d[\"scores\"][\"faithfulness\"]:.4f}')"
    fi
done
```

**Ship gate (per spec §1):**
- BOTH papers' Phase 4 faithfulness ≥ Phase 2 baseline − 1pp (no regression)
- AT LEAST one paper Phase 4 faithfulness ≥ Phase 2 + 2pp

Decision tree:
- **Gate passes** → write up in Task 7, recommend flipping default ON in a follow-up commit
- **Gate fails on regression** → leave default OFF, document the gap as Phase 5 candidate, still ship the code (it's opt-in and architecturally cleaner even if not yet a quality win)
- **Pre-stage LLM fails to produce valid JSON** (PromptTailorError) → debug prompt phrasing, may need 1-2 iterations on `prompt_tailor.md`

- [ ] **Step 7: Cleanup temp golden_qa files (keep the runs/ artefacts)**

```bash
rm tests/eval/golden_qa/meng2024_p4.yaml tests/eval/golden_qa/ali2025_p4.yaml
```

`runs/meng2024_v112_p4` and `runs/ali2025_flash_v112_p4` are gitignored — leave them as v1.12-phase4 reference artefacts.

- [ ] **Step 8: (No commit yet — Task 7 commits the docs that cite these numbers.)**

---

## Task 7: Summary doc + CHANGELOG + ARCHITECTURE entry

**Files:**
- Create: `docs/archive/v1_12_phase4_summary.md`
- Modify: `CHANGELOG.md` (add `[v1.12-phase4]` entry above `[v1.12-phase1]`, under `## [Unreleased]`)
- Modify: `docs/ARCHITECTURE.md` (new §4.6.5)

- [ ] **Step 1: Write the summary report**

Create `docs/archive/v1_12_phase4_summary.md`:

```markdown
# v1.12 Phase 4 — Summary & Ship Decision

> Implementation: 2026-05-26 on `worktree-v1.12-phase1`.
> Spec: `docs/superpowers/specs/2026-05-26-v1_12-phase4-prompt-tailoring-design.md`
> Plan: `docs/superpowers/plans/2026-05-26-prompt-tailoring-v1.12-phase4.md`
> Predecessor: Phase 3a (Chinese mirror) is preserved. Phase 3b + 3c were
> reverted after they regressed RAGAS faithfulness on both demo papers.

## Shipped

- `LAZY_PAPER_PROMPT_TAILOR=1` env flag (default OFF until measured)
- New `llm/prompts/prompt_tailor.md` — pre-stage LLM instructions
- New `stages/s06_context/prompt_tailor.py` — generate_prompt_augment + 4 unit tests
- s06_context runner sub-step: writes `prompt_augment.yaml` when flag ON
- s08 `_render_augment_block` + 2 unit tests; `compose_structured` prepends
  augment to `_STRUCTURED_SYSTEM` when present

## Measured RAGAS (T6)

| Paper | v1.11.5 baseline | Phase 2 anchored | Phase 4 (+tailor) | Δ vs Phase 2 |
|---|---|---|---|---|
| meng2024 · faithfulness | <fill> | <fill> | <fill from T6> | <fill> |
| ali2025_flash · faithfulness | <fill> | <fill> | <fill from T6> | <fill> |
| context_recall (both) | 1.000 | 1.000 | <fill> | <fill> |
| context_precision (both) | ~1.000 | ~1.000 | <fill> | <fill> |

Ship gate (per spec §1): no regression > 1pp AND ≥+2pp on at least one
paper. **<fill: PASSED / FAILED with reason>**.

## Audit of `prompt_augment.yaml` content

meng2024 augment captured:
- domain_framing: <fill from T6 step 4>
- terminology highlights: <fill>
- comparator example: <fill>

ali2025_flash augment captured:
- domain_framing: <fill>
- terminology highlights: <fill>
- comparator example: <fill>

No cross-contamination: each paper's augment is paper-specific.

## Decision

<fill: default ON / keep opt-in / revert>

## What Phase 4 did NOT change

- `_STRUCTURED_SYSTEM` body — unchanged; the augment is a prefix, not a
  replacement
- s06 KG extraction or s08 verifier — both untouched
- Default behaviour when flag OFF — byte-for-byte identical to Phase 2

## Cost + wall-clock

- Pipeline rerun (2 papers × s06+s05+s08+s09): ~12 min, ~$0.25
- RAGAS rerun (6 papers × 60 evaluations): ~5 min, ~$0.15
- Phase 4 total LLM cost: ~$0.40
```

After T6 produces real numbers, replace EVERY `<fill>` with the actual value (each is paired with a clear T6-step source).

- [ ] **Step 2: Add CHANGELOG entry**

Open `CHANGELOG.md`. Find the line `## [Unreleased]`. Right after it (and ABOVE the existing `### [v1.12-phase2]` entry), insert:

```markdown
### [v1.12-phase4] — 2026-05-26 (opt-in, default OFF; flip to ON pending more measurement)

#### Added — two-stage prompt tailoring (opt-in)

Cheap pre-stage LLM call in `s06_context` reads the paper's already-extracted
context + intro chapter and emits `prompt_augment.yaml` with per-paper
`domain_framing`, `terminology`, `metric_patterns`, and a `comparator_style`
example drawn FROM THIS PAPER. The s08 compose stage prepends a rendered
version of this block to `_STRUCTURED_SYSTEM` before each compose call,
specializing the generic prompt to whatever this paper actually contains.

Opt in via `LAZY_PAPER_PROMPT_TAILOR=1` in `.env`. Default OFF.

#### Design rationale

Phase 3c attempted cross-domain generalization by stuffing ML examples
into the static prompt; it regressed RAGAS faithfulness on both demo
papers (meng2024 −9pp, ali2025 −4pp) and was reverted. Phase 4 puts
generalization at the architectural layer: the system prompt stays clean
and focused (no hypothetical-other-domain examples), while a per-paper
augment block does paper-specific specialization at runtime.

#### Soft-degrade

Pre-stage failure (LLM error, malformed JSON, missing intro chapter) writes
`prompt_tailor.failed` and lets s08 fall back to the vanilla
`_STRUCTURED_SYSTEM`. Never blocks the pipeline.

#### Measured (per `docs/archive/v1_12_phase4_summary.md`)

- meng2024 faithfulness: <fill from Task 7 step 1>
- ali2025_flash faithfulness: <fill>
- Ship gate: <fill: PASSED / FAILED>
```

Replace `<fill>` markers per Task 6 data.

- [ ] **Step 3: Add ARCHITECTURE entry**

Open `docs/ARCHITECTURE.md`. Find `### 4.6 s06_context — paper context + KG` and read through to find where §4.7 starts. INSERT a new subsection between §4.6 and §4.7:

```markdown

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
LLM call (see `compose_structured`'s `augment_block` kwarg).

**Design rationale.** Phase 3c tried to make `_STRUCTURED_SYSTEM`
domain-agnostic by adding "Smith et al. ResNet-50 on ImageNet" examples
alongside the materials ones. RAGAS regressed (meng2024 −9pp, ali2025
−4pp) — the LLM treated the extra examples as permission to drift.
Phase 4 reverses the design: the static prompt stays clean and focused
(materials-tuned methodology), while a per-paper augment block does
runtime specialization. Generalization moves from prompt-body to
architecture.

**Soft-degrade.** Any pre-stage failure (PromptTailorError, LLM transport,
unexpected exception) writes a `prompt_tailor.failed` marker and s06
completes normally. s08 sees no `prompt_augment.yaml` and falls back to
the vanilla `_STRUCTURED_SYSTEM` — pipeline never blocks.

Implementation: `stages/s06_context/prompt_tailor.py` (~80 LOC) + `llm/prompts/prompt_tailor.md`.
```

- [ ] **Step 4: Run the full test suite to verify no regression from any of T1-T4**

Run: `uv run pytest stages/ tests/ scripts/ -q --no-header 2>&1 | tail -3`
Expected: 321 passed (315 prior + 4 T2 + 2 T4 step 5 = 321), 3 deselected.

- [ ] **Step 5: Commit T7**

```bash
git add docs/archive/v1_12_phase4_summary.md CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs(v1.12-phase4): summary + CHANGELOG + ARCHITECTURE §4.6.5 (T7)

- summary: full data table (baseline / Phase 2 / Phase 4) + audit of the
  paper-specific augment blocks + ship decision
- CHANGELOG: [v1.12-phase4] entry explaining the two-stage design + why
  it replaces Phase 3c's failed example-stuffing approach
- ARCHITECTURE §4.6.5: detailed integration explanation including the
  augment YAML schema, the s08 prepend mechanism, and the soft-degrade
  contract"
```

---

## Self-Review

**1. Spec coverage:**
- §1 Goal — covered: T1 (prompt) + T2 (module/tests) + T3 (s06 wiring) + T4 (s08 prepend) + T6 (ship gate measurement) + T7 (ship decision)
- §2 Background — referenced in T6 step 5 (comparison against Phase 2 baseline)
- §3.1 New artifact: prompt_augment.yaml — T2 emits the schema, T6 audits the content
- §3.2 New prompt: prompt_tailor.md — T1
- §3.3 s06 runner integration — T3
- §3.4 s08 consumption — T4 (both helper + runner wiring)
- §3.5 Why this beats Phase 3c — captured in CHANGELOG entry (T7 step 2) and ARCHITECTURE §4.6.5 (T7 step 3)
- §4 Out of scope — respected; no model-tier split, no Phase 3b/3c revival
- §5 Files touched — every file in the spec list is touched in T1-T7
- §6 Verification — T2 (unit), T4 step 7 (regression), T6 (RAGAS)
- §7 Open questions — Q1 (default OFF) implemented in T3+T5; Q2 (per-paper, not per-section) implemented by passing augment_block at compose_structured top, reused for all sections; Q3 (no abstract) implemented in T2 step 1 last test

**2. Placeholder scan:**
- "TBD" / "TODO" / "implement later": none found.
- "<fill>" placeholders: ONLY in T7 step 1 (summary doc) and T7 step 2 (CHANGELOG numbers) where each `<fill>` has an explicit source from T6 step output. These are intentional — the summary doc carries the measurement results into the commit.
- "Add appropriate error handling": none.

**3. Type consistency:**
- `generate_prompt_augment(*, context, chapters_dir, llm_chat=None)` — same signature in T2 module, T3 caller, T6 e2e command.
- `PromptTailorError` — defined in T2, caught in T3.
- `prompt_augment.yaml` filename — same across T3 (writer), T4 (reader), T6 (audit), T7 (doc references).
- `_render_augment_block(aug)` returning empty string on null/empty — defined in T4 step 1, tested in T4 step 5 with both `None` and `{}` cases.
- `augment_block: str = ""` kwarg — added to compose_structured in T4 step 2, passed by runner in T4 step 3.
- `LAZY_PAPER_PROMPT_TAILOR` env name — same across T3, T5, T6.

**4. Known fragility:**
- T4 step 2 says "search-and-replace `_STRUCTURED_SYSTEM` to `system_prompt` inside `compose_structured`" — this needs care because `_STRUCTURED_SYSTEM` is referenced both inside compose_structured (which we want to change) and at module-top (the constant itself; must NOT change) and possibly in retry-prompt construction (e.g., `retry_system = _STRUCTURED_SYSTEM + ...` at lines 1210, 1279 — these should use `system_prompt` instead so the augment applies to retries too). The plan instructs to verify each replacement is inside `compose_structured`; the executing agent should confirm visually before each edit.
- T6 step 3 uses `--only s06_context,s05_template,s08_section_compose,s09_render` — s06 must come first because s08 reads from it. CLI may not preserve order; verify with the executing agent that `--only` respects the comma-listed order, OR pass them in two separate `uv run python -m cli run` invocations if not.
