# s09_render Multi-Format Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `stages/s09_render/` from single-file docx renderer into a class-organized multi-format pipeline (docx + pdf + html + pptx) with a shared `Document` model; also split `stages/_common.py` into a package by responsibility.

**Architecture:** `Document` (frozen dataclass tree) built once by `DocumentBuilder`, fed to 4 `Renderer` subclasses. PPT path adds `SlidePlanner` (deterministic slide cutting) and `PptxSummarizer` (LLM bullets/figure one-liners with double-track cache: input_hash for reuse + prompt/response for audit). All renderers register in a single `RENDERERS` dict keyed by extension.

**Tech Stack:** Python 3.9+, dataclasses, python-docx (existing), Jinja2 (new), weasyprint (new), python-pptx (new), pytest, PyYAML, OpenAI SDK (existing LLM client).

**Spec reference:** `docs/superpowers/specs/2026-05-18-render-redesign-design.md`

---

## File Map

### New files
```
stages/_common/                        # replaces stages/_common.py
├── __init__.py                        # re-exports everything for back-compat
├── paths.py                           # slugify, stage_dir
├── yaml_io.py                         # load_yaml, dump_yaml, safe_parse_yaml + helpers
├── done.py                            # mark_done, is_done
└── bbox.py                            # bbox_from_filename, BBOX_FROM_NAME, DOC_PAGE

stages/s09_render/model.py             # Paragraph, FigureBlock, Chapter, Document
stages/s09_render/builder.py           # DocumentBuilder class
stages/s09_render/slide_planner.py     # SlidePlanner + Slide + SlideDeck
stages/s09_render/pptx_summarizer.py   # PptxSummarizer class

stages/s09_render/renderers/__init__.py   # RENDERERS registry
stages/s09_render/renderers/base.py       # Renderer ABC
stages/s09_render/renderers/docx.py       # DocxRenderer
stages/s09_render/renderers/html.py       # HtmlRenderer
stages/s09_render/renderers/pdf.py        # PdfRenderer
stages/s09_render/renderers/pptx.py       # PptxRenderer

stages/s09_render/templates/preview.html.j2
stages/s09_render/templates/styles.css

llm/prompts/pptx_summarize.md          # LLM prompt for PptxSummarizer

stages/s09_render/tests/test_model.py
stages/s09_render/tests/test_builder.py
stages/s09_render/tests/test_slide_planner.py
stages/s09_render/tests/test_pptx_summarizer.py
stages/s09_render/tests/test_renderers_smoke.py
stages/s09_render/tests/test_partial_failure.py
stages/s09_render/tests/test_cache_reuse.py

tests/test_common/__init__.py
tests/test_common/test_paths.py
tests/test_common/test_yaml_io.py
tests/test_common/test_done.py
tests/test_common/test_bbox.py

tests/fixtures/hu2025/chapters/        # frozen snapshot copies
tests/fixtures/hu2025/fig_notes.yaml
tests/fixtures/hu2025/images/          # only images referenced by fig_notes
```

### Files to modify
```
stages/s09_render/runner.py            # gut + rewrite as 35-line coordinator
stages/s09_render/__init__.py          # no change unless exports needed
stages/_common.py                      # DELETE after package migration
cli.py                                  # add --formats / --pptx-bullets / --retry-failed flags
pyproject.toml                          # add jinja2 / weasyprint / python-pptx; register stages._common as package
Dockerfile                              # add system libs for weasyprint
README.md                               # add Output Formats section
tests/test_common.py                    # DELETE (logic split into tests/test_common/test_yaml_io.py)
stages/s09_render/tests/test_runner.py  # migrate to use new module API (or delete in favor of test_renderers_smoke.py)
```

### Files NOT touched
`stages/s01_ocr/`, `stages/s02_clean/`, `stages/s03_chapter/`, `stages/s04_figures/`, `stages/s05_template/`, `stages/s06_context/`, `stages/s07_figure_analyze/`, `stages/s08_section_compose/`, `llm/client.py`, `llm/models.yaml`, `llm/prompts/{paper_context,figure_analyze,section_compose}.md`.

---

## Milestone roadmap

- **M1** — `_common.py` → `_common/` package. Zero behavior change; back-compat re-exports.
- **M2** — `model.py` + `DocumentBuilder` + `DocxRenderer`. New docx output is byte-equivalent to old.
- **M3** — `HtmlRenderer` + `PdfRenderer` + Jinja2 templates. Three formats from one Document.
- **M4** — `SlidePlanner` + `PptxSummarizer` + `PptxRenderer` + LLM cache.
- **M5** — Error handling (soft/hard split), CLI flags (`--formats` / `--pptx-bullets` / `--retry-failed`), Dockerfile system libs, README.

Each milestone ends with a green test suite and a commit; safe to stop between milestones.

---

# Milestone M1 — `_common.py` → `_common/` package

**Goal:** Split the 138-line `stages/_common.py` into a 4-module package by responsibility, keeping all existing `from stages._common import xxx` calls working via re-export. Add per-module unit tests (the original was implicitly covered only by integration tests).

**Acceptance:** Running `pytest -q` shows the same or more passing tests, and `stages._common` package re-exports the same public surface (`slugify, stage_dir, load_yaml, dump_yaml, mark_done, is_done, bbox_from_filename, safe_parse_yaml`).

### Task M1.1 — Create the package skeleton with paths module

**Files:**
- Create: `stages/_common/__init__.py`
- Create: `stages/_common/paths.py`
- Create: `tests/test_common/__init__.py`
- Create: `tests/test_common/test_paths.py`

- [ ] **Step 1: Write failing test for `slugify` + `stage_dir`**

Create `tests/test_common/__init__.py` with empty content:
```python
```

Create `tests/test_common/test_paths.py`:
```python
from pathlib import Path

from stages._common import slugify, stage_dir


def test_slugify_basic_ascii():
    assert slugify("Hello World") == "Hello_World"


def test_slugify_strips_punctuation():
    assert slugify("foo: bar?!") == "foo_bar"


def test_slugify_preserves_cjk():
    assert slugify("引言 1") == "引言_1"


def test_slugify_truncates_to_maxlen():
    assert slugify("a" * 100, maxlen=10) == "a" * 10


def test_slugify_empty_input_returns_untitled():
    assert slugify("   ") == "untitled"


def test_stage_dir_creates_nested_dirs(tmp_path: Path):
    d = stage_dir(tmp_path, "paper1", "s01_ocr")
    assert d.exists() and d.is_dir()
    assert d == tmp_path / "paper1" / "s01_ocr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/zhangjiedong/codeFiles/article/paper2md && pytest tests/test_common/test_paths.py -v`
Expected: `ImportError` or `ModuleNotFoundError` because `stages/_common/__init__.py` does not exist yet (the file `stages/_common.py` does, but the package layout is what we want).

- [ ] **Step 3: Create the package directory and move slugify/stage_dir to paths.py**

First delete the old module file so it doesn't shadow the package:
```bash
rm /Users/zhangjiedong/codeFiles/article/paper2md/stages/_common.py
```

Create `stages/_common/paths.py`:
```python
"""Path/slug utilities shared by all stages."""
from __future__ import annotations

import re as _re
from pathlib import Path


def slugify(text: str, maxlen: int = 50) -> str:
    s = _re.sub(r"[^\w一-鿿-]+", "_", text.strip(), flags=_re.UNICODE)
    s = s.strip("_")
    return s[:maxlen] if s else "untitled"


def stage_dir(run_root: Path, paper_id: str, stage_name: str) -> Path:
    d = Path(run_root) / paper_id / stage_name
    d.mkdir(parents=True, exist_ok=True)
    return d
```

Create `stages/_common/__init__.py` (temporary, will grow in following tasks):
```python
"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename
"""
from stages._common.paths import slugify, stage_dir

__all__ = ["slugify", "stage_dir"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_common/test_paths.py -v`
Expected: 6 passed.

- [ ] **Step 5: Update pyproject.toml to register the new package**

Open `pyproject.toml`, find the `[tool.setuptools]` section, and edit `packages` to include `stages._common`:

Old:
```toml
[tool.setuptools]
packages = [
    "stages",
    "stages.s01_ocr",
    ...
    "llm",
]
```

New:
```toml
[tool.setuptools]
packages = [
    "stages",
    "stages._common",
    "stages.s01_ocr",
    ...
    "llm",
]
```
(Insert `"stages._common",` as the second item.)

- [ ] **Step 6: Reinstall package so the new layout is importable in editable mode**

Run: `uv pip install -e .`
Expected: completes without error.

- [ ] **Step 7: Re-run paths tests to confirm install picked up new package**

Run: `pytest tests/test_common/test_paths.py -v`
Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
git add stages/_common/__init__.py stages/_common/paths.py tests/test_common/__init__.py tests/test_common/test_paths.py pyproject.toml
git rm stages/_common.py
git commit -m "refactor(_common): split paths utilities into _common/paths.py"
```

### Task M1.2 — Move YAML I/O to yaml_io.py

**Files:**
- Create: `stages/_common/yaml_io.py`
- Modify: `stages/_common/__init__.py`
- Create: `tests/test_common/test_yaml_io.py`
- Delete: `tests/test_common.py` (will be replaced by the new test file in this task)

- [ ] **Step 1: Write failing test for yaml_io public API**

Create `tests/test_common/test_yaml_io.py`. This file is the new home for the existing `test_common.py` tests (which only covered `safe_parse_yaml`) plus new coverage for `load_yaml` and `dump_yaml`:
```python
from pathlib import Path

import pytest

from stages._common import load_yaml, dump_yaml, safe_parse_yaml


def test_dump_then_load_roundtrip(tmp_path: Path):
    target = tmp_path / "x.yaml"
    obj = {"name": "测试", "items": [1, 2, 3]}
    dump_yaml(target, obj)
    assert load_yaml(target) == obj


def test_dump_yaml_preserves_unicode(tmp_path: Path):
    target = tmp_path / "u.yaml"
    dump_yaml(target, {"k": "中文"})
    text = target.read_text(encoding="utf-8")
    assert "中文" in text  # not escaped to \uXXXX


def test_safe_parse_valid():
    assert safe_parse_yaml("a: 1\nb: 2") == {"a": 1, "b": 2}


def test_safe_parse_empty():
    assert safe_parse_yaml("") is None
    assert safe_parse_yaml("   ") is None


def test_safe_parse_flow_sequence_with_question_mark():
    text = "items: [What is X?, Yes or No?]"
    result = safe_parse_yaml(text)
    assert result == {"items": ["What is X?", "Yes or No?"]}


def test_safe_parse_unrecoverable():
    bad = ": : : foo\nbar\n  baz: : :"
    assert safe_parse_yaml(bad) is None


def test_safe_parse_scalar_with_inner_colon():
    text = (
        "visual_summary: Panels show a strong inverse correlation: "
        "Eb increases from 12 to 41 kV/mm\nfig_id: Fig. 3"
    )
    result = safe_parse_yaml(text)
    assert result is not None
    assert result["fig_id"] == "Fig. 3"
    assert "inverse correlation" in result["visual_summary"]


def test_safe_parse_real_qwen_failure_excerpt():
    text = (
        "fig_id: Fig. 3\n"
        "visual_summary: Panels (a-d) show micrographs, revealing a strong correlation: Eb increases\n"
        "text_claim_check:\n"
        "  - claim: trivial\n"
        "    verdict: supported\n"
        "    note: ok\n"
        "caption: Test caption\n"
    )
    result = safe_parse_yaml(text)
    assert result is not None
    assert "correlation" in result["visual_summary"]
    assert result["caption"] == "Test caption"
```

Then delete the old test file:
```bash
git rm tests/test_common.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_common/test_yaml_io.py -v`
Expected: `ImportError: cannot import name 'load_yaml' from 'stages._common'` (yaml functions are not yet in the package).

- [ ] **Step 3: Create yaml_io.py and wire the re-export**

Create `stages/_common/yaml_io.py`:
```python
"""YAML loading, dumping, and defensive parsing of LLM-returned YAML."""
from __future__ import annotations

import re as _re
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, obj: Any) -> None:
    path.write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


_FLOW_SEQ_FIX = _re.compile(r"\[([^\]\n]*)\]")
_TOP_LEVEL_KV = _re.compile(r"^([A-Za-z_]\w*):\s+(.+)$")


def _quote_flow_items(match: _re.Match) -> str:
    body = match.group(1)
    items = [s.strip() for s in body.split(",")]
    quoted = []
    for it in items:
        if not it:
            continue
        if (it.startswith('"') and it.endswith('"')) or (it.startswith("'") and it.endswith("'")):
            quoted.append(it)
        elif _re.search(r"[:?#&*!|>%@`,\[\]{}]", it):
            esc = it.replace("'", "''")
            quoted.append(f"'{esc}'")
        else:
            quoted.append(it)
    return "[" + ", ".join(quoted) + "]"


def _quote_unquoted_scalar(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        m = _TOP_LEVEL_KV.match(line)
        if not m:
            out_lines.append(line)
            continue
        key, value = m.group(1), m.group(2).rstrip()
        if not value:
            out_lines.append(line)
            continue
        first = value[0]
        if first in ('"', "'", '[', '{', '|', '>', '&', '*', '!', '#'):
            out_lines.append(line)
            continue
        if _re.search(r":\s", value) or value.endswith(":"):
            esc = value.replace("\\", "\\\\").replace('"', '\\"')
            out_lines.append(f"{key}: \"{esc}\"")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def safe_parse_yaml(text: str) -> Any:
    """Parse LLM-returned YAML defensively.

    Tries plain yaml.safe_load; on YAMLError, applies progressively more
    aggressive repairs (quote flow-sequence items, quote unquoted scalars
    containing colons). Returns None on total failure.
    """
    if not text or not text.strip():
        return None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        pass
    fixed1 = _FLOW_SEQ_FIX.sub(_quote_flow_items, text)
    try:
        return yaml.safe_load(fixed1)
    except yaml.YAMLError:
        pass
    fixed2 = _quote_unquoted_scalar(text)
    try:
        return yaml.safe_load(fixed2)
    except yaml.YAMLError:
        pass
    fixed3 = _quote_unquoted_scalar(_FLOW_SEQ_FIX.sub(_quote_flow_items, text))
    try:
        return yaml.safe_load(fixed3)
    except yaml.YAMLError:
        return None
```

Edit `stages/_common/__init__.py` to add the new exports:
```python
"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename
"""
from stages._common.paths import slugify, stage_dir
from stages._common.yaml_io import load_yaml, dump_yaml, safe_parse_yaml

__all__ = [
    "slugify", "stage_dir",
    "load_yaml", "dump_yaml", "safe_parse_yaml",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_common/test_yaml_io.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/_common/yaml_io.py stages/_common/__init__.py tests/test_common/test_yaml_io.py
git rm tests/test_common.py
git commit -m "refactor(_common): split YAML I/O into _common/yaml_io.py"
```

### Task M1.3 — Move done-marker to done.py

**Files:**
- Create: `stages/_common/done.py`
- Modify: `stages/_common/__init__.py`
- Create: `tests/test_common/test_done.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_common/test_done.py`:
```python
import time
from pathlib import Path

import yaml

from stages._common import mark_done, is_done


def test_is_done_false_when_marker_missing(tmp_path: Path):
    assert is_done(tmp_path) is False


def test_mark_done_creates_yaml_with_timestamp(tmp_path: Path):
    before = time.time()
    mark_done(tmp_path)
    after = time.time()
    payload = yaml.safe_load((tmp_path / "done.yaml").read_text(encoding="utf-8"))
    assert isinstance(payload["finished_at"], float)
    assert before <= payload["finished_at"] <= after


def test_mark_done_merges_extra_keys(tmp_path: Path):
    mark_done(tmp_path, {"files": 3, "bytes": 1024})
    payload = yaml.safe_load((tmp_path / "done.yaml").read_text(encoding="utf-8"))
    assert payload["files"] == 3
    assert payload["bytes"] == 1024
    assert "finished_at" in payload


def test_is_done_true_after_mark(tmp_path: Path):
    assert is_done(tmp_path) is False
    mark_done(tmp_path)
    assert is_done(tmp_path) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_common/test_done.py -v`
Expected: `ImportError: cannot import name 'mark_done' from 'stages._common'`.

- [ ] **Step 3: Create done.py and wire re-export**

Create `stages/_common/done.py`:
```python
"""Stage completion marker (done.yaml)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from stages._common.yaml_io import dump_yaml


def mark_done(stage_path: Path, extra: dict[str, Any] | None = None) -> None:
    dump_yaml(stage_path / "done.yaml", {"finished_at": time.time(), **(extra or {})})


def is_done(stage_path: Path) -> bool:
    return (stage_path / "done.yaml").exists()
```

Edit `stages/_common/__init__.py` to add the new exports:
```python
"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename
"""
from stages._common.paths import slugify, stage_dir
from stages._common.yaml_io import load_yaml, dump_yaml, safe_parse_yaml
from stages._common.done import mark_done, is_done

__all__ = [
    "slugify", "stage_dir",
    "load_yaml", "dump_yaml", "safe_parse_yaml",
    "mark_done", "is_done",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_common/test_done.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/_common/done.py stages/_common/__init__.py tests/test_common/test_done.py
git commit -m "refactor(_common): split done-marker into _common/done.py"
```

### Task M1.4 — Move bbox helper to bbox.py

**Files:**
- Create: `stages/_common/bbox.py`
- Modify: `stages/_common/__init__.py`
- Create: `tests/test_common/test_bbox.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_common/test_bbox.py`:
```python
from stages._common import bbox_from_filename


def test_bbox_from_filename_extracts_four_ints():
    assert bbox_from_filename("imgs/img_mineru_001_10_20_300_400.jpg") == (10, 20, 300, 400)


def test_bbox_from_filename_returns_none_when_pattern_absent():
    assert bbox_from_filename("imgs/plain_image.jpg") is None


def test_bbox_from_filename_handles_uppercase_extension():
    assert bbox_from_filename("imgs/foo_1_2_3_4.PNG") == (1, 2, 3, 4)


def test_bbox_from_filename_ignores_directory_components():
    assert bbox_from_filename("/abs/path/foo/bar_5_6_7_8.jpg") == (5, 6, 7, 8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_common/test_bbox.py -v`
Expected: `ImportError: cannot import name 'bbox_from_filename' from 'stages._common'`.

- [ ] **Step 3: Create bbox.py and wire re-export**

Create `stages/_common/bbox.py`:
```python
"""Bounding-box helpers extracted from filename conventions."""
from __future__ import annotations

import re as _re
from pathlib import Path


BBOX_FROM_NAME = _re.compile(r"_(\d+)_(\d+)_(\d+)_(\d+)\.[A-Za-z0-9]+$")
DOC_PAGE = _re.compile(r"doc_(\d+)\.md$")


def bbox_from_filename(rel_path: str) -> "tuple[int, int, int, int] | None":
    m = BBOX_FROM_NAME.search(Path(rel_path).name)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]
```

Edit `stages/_common/__init__.py` to its final form:
```python
"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename, BBOX_FROM_NAME, DOC_PAGE
"""
from stages._common.paths import slugify, stage_dir
from stages._common.yaml_io import load_yaml, dump_yaml, safe_parse_yaml
from stages._common.done import mark_done, is_done
from stages._common.bbox import bbox_from_filename, BBOX_FROM_NAME, DOC_PAGE

__all__ = [
    "slugify", "stage_dir",
    "load_yaml", "dump_yaml", "safe_parse_yaml",
    "mark_done", "is_done",
    "bbox_from_filename", "BBOX_FROM_NAME", "DOC_PAGE",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_common/test_bbox.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/_common/bbox.py stages/_common/__init__.py tests/test_common/test_bbox.py
git commit -m "refactor(_common): split bbox helper into _common/bbox.py"
```

### Task M1.5 — Verify zero regression across all stages

**Files:** No code changes; verification only.

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/zhangjiedong/codeFiles/article/paper2md && pytest -q`
Expected: every previously-passing test still passes, plus the new `tests/test_common/test_*.py` tests (22 new tests across paths/yaml_io/done/bbox). No `ImportError` from any stage referencing `stages._common`.

- [ ] **Step 2: Grep for any leftover references to the deleted file**

Run: `grep -rn "stages/_common\.py" --include="*.py" --include="*.md" /Users/zhangjiedong/codeFiles/article/paper2md/stages /Users/zhangjiedong/codeFiles/article/paper2md/tests /Users/zhangjiedong/codeFiles/article/paper2md/llm /Users/zhangjiedong/codeFiles/article/paper2md/cli.py /Users/zhangjiedong/codeFiles/article/paper2md/docs 2>/dev/null`
Expected: no output (or only docs/plan references, which is fine).

- [ ] **Step 3: Tag M1 complete**

```bash
git tag m1-common-split
```

---

# Milestone M2 — `Document` model + `DocumentBuilder` + `DocxRenderer` migration

**Goal:** Introduce the `Document` data model, migrate the existing `_render_preview_docx` logic into a `DocxRenderer(Renderer)` class consuming a `Document`, and verify behavior is preserved (existing s09 tests still pass against the new code path).

**Acceptance:** All 4 existing tests in `stages/s09_render/tests/test_runner.py` still pass after the runner is rewritten to use `DocumentBuilder` + `DocxRenderer`.

### Task M2.1 — Copy hu2025 to test fixtures (frozen snapshot)

**Files:**
- Create: `tests/fixtures/hu2025/chapters/*.md` (copied from `runs/hu2025/s08_section_compose/chapters/`)
- Create: `tests/fixtures/hu2025/fig_notes.yaml` (copied from `runs/hu2025/s07_figure_analyze/fig_notes.yaml`)
- Create: `tests/fixtures/hu2025/images/` (copies of all files referenced by `image_paths` / `image_abs_path` in fig_notes)
- Create: `tests/fixtures/hu2025/fig_notes_rewritten.yaml` (paths rewritten to point inside fixtures/images/)

- [ ] **Step 1: Copy chapter markdown**

```bash
mkdir -p /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/chapters
cp /Users/zhangjiedong/codeFiles/article/paper2md/runs/hu2025/s08_section_compose/chapters/*.md \
   /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/chapters/
ls /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/chapters/
```
Expected: 11 .md files listed (01-Introduction.md … 11-Conclusions.md).

- [ ] **Step 2: Copy fig_notes.yaml and the images it references**

```bash
mkdir -p /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/images
cp /Users/zhangjiedong/codeFiles/article/paper2md/runs/hu2025/s07_figure_analyze/fig_notes.yaml \
   /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/fig_notes.yaml
```

Now extract all image paths and copy each one to the fixtures images dir, then rewrite the yaml to point at the new locations. Save the following script as `/tmp/_freeze_fixture.py` and run it:
```python
import shutil
from pathlib import Path

import yaml

FIX = Path("/Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025")
data = yaml.safe_load((FIX / "fig_notes.yaml").read_text(encoding="utf-8")) or []

for note in data:
    new_paths = []
    for key in ("image_paths", "image_abs_path"):
        val = note.get(key)
        if not val:
            continue
        srcs = val if isinstance(val, list) else [val]
        for src in srcs:
            src_p = Path(src)
            if not src_p.exists():
                continue
            dest = FIX / "images" / src_p.name
            if not dest.exists():
                shutil.copy2(src_p, dest)
            if key == "image_paths":
                new_paths.append(str(dest))
            else:
                note["image_abs_path"] = str(dest)
        if key == "image_paths":
            note["image_paths"] = new_paths

(FIX / "fig_notes_rewritten.yaml").write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
    encoding="utf-8",
)
print(f"Wrote {len(data)} fig notes; copied images to {FIX / 'images'}")
```

Run: `uv run python /tmp/_freeze_fixture.py`
Expected output ends with something like `Wrote N fig notes; copied images to .../fixtures/hu2025/images`.

- [ ] **Step 3: Add a `.gitkeep` if needed and verify size is sane**

```bash
du -sh /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025
ls /Users/zhangjiedong/codeFiles/article/paper2md/tests/fixtures/hu2025/images | wc -l
```
Expected: typically < 5 MB total; image count matches the number of unique paths in `fig_notes.yaml`.

- [ ] **Step 4: Commit the fixture**

```bash
git add tests/fixtures/hu2025
git commit -m "test: freeze hu2025 fixture for s09_render unit/integration tests"
```

### Task M2.2 — Define the `Document` model

**Files:**
- Create: `stages/s09_render/model.py`
- Create: `stages/s09_render/tests/test_model.py`

- [ ] **Step 1: Write failing test**

Create `stages/s09_render/tests/test_model.py`:
```python
from pathlib import Path

import pytest

from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock,
)


def test_paragraph_is_frozen():
    p = Paragraph(text="hello")
    with pytest.raises(Exception):  # FrozenInstanceError
        p.text = "world"  # type: ignore[misc]


def test_figure_block_is_frozen_and_holds_image_paths():
    fb = FigureBlock(
        fig_id="Fig. 1", label="图 1",
        image_paths=(Path("/a/b.jpg"),),
        caption="cap", deep_observation="obs",
    )
    assert fb.fig_id == "Fig. 1"
    assert fb.label == "图 1"
    assert fb.image_paths == (Path("/a/b.jpg"),)
    with pytest.raises(Exception):
        fb.caption = "new"  # type: ignore[misc]


def test_chapter_groups_blocks_in_order():
    p = Paragraph(text="intro text")
    fb = FigureBlock(fig_id="Fig. 1", label="Fig. 1",
                     image_paths=(), caption="", deep_observation="")
    ch = Chapter(heading="Introduction", level=1, blocks=(p, fb))
    assert ch.blocks[0] is p
    assert ch.blocks[1] is fb


def test_document_holds_chapters_and_metadata():
    doc = Document(paper_title="My Paper", lang="zh", chapters=())
    assert doc.paper_title == "My Paper"
    assert doc.lang == "zh"
    assert doc.chapters == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_model.py -v`
Expected: `ModuleNotFoundError: No module named 'stages.s09_render.model'`.

- [ ] **Step 3: Implement model.py**

Create `stages/s09_render/model.py`:
```python
"""Frozen data model consumed by all renderers (docx/html/pdf/pptx)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class FigureBlock:
    fig_id: str                       # canonical "Fig. 5"
    label: str                        # localized "Fig. 5" or "图 5"
    image_paths: tuple[Path, ...]     # one path per panel
    caption: str
    deep_observation: str             # may be empty string


Block = Union[Paragraph, FigureBlock]   # union type for static dispatch


@dataclass(frozen=True)
class Chapter:
    heading: str
    level: int                        # 1 = H1
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                         # "zh" | "en"
    chapters: tuple[Chapter, ...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_model.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/model.py stages/s09_render/tests/test_model.py
git commit -m "feat(s09_render): add Document model (Paragraph/FigureBlock/Chapter/Document)"
```

### Task M2.3 — Implement `DocumentBuilder`

**Files:**
- Create: `stages/s09_render/builder.py`
- Create: `stages/s09_render/tests/test_builder.py`

- [ ] **Step 1: Write failing test**

Create `stages/s09_render/tests/test_builder.py`:
```python
from pathlib import Path

import yaml

from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.model import Document, Chapter, Paragraph, FigureBlock


def test_builder_splits_paragraphs_on_double_newline():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    doc = builder.build(chapters_md={"01-intro.md": "# Intro\n\nfirst para\n\nsecond para\n"},
                        fig_notes=[])
    assert len(doc.chapters) == 1
    ch = doc.chapters[0]
    assert ch.heading == "Intro"
    paragraphs = [b for b in ch.blocks if isinstance(b, Paragraph)]
    assert [p.text for p in paragraphs] == ["first para", "second para"]


def test_builder_attaches_referenced_figures_by_english_id():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# C1\n\nbody mentions Fig. 1 here\n"},
        fig_notes=[{
            "fig_id": "Fig. 1",
            "image_abs_path": "/a/b.jpg",
            "caption": "the caption",
            "deep_observation": "the obs",
        }],
    )
    blocks = doc.chapters[0].blocks
    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert len(figures) == 1
    assert figures[0].fig_id == "Fig. 1"
    assert figures[0].label == "Fig. 1"   # English label unchanged
    assert figures[0].caption == "the caption"
    assert figures[0].image_paths == (Path("/a/b.jpg"),)


def test_builder_localizes_label_to_chinese_when_lang_zh():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# 一\n\n文中提到图1的内容\n"},
        fig_notes=[{"fig_id": "Fig. 1", "image_abs_path": "/a/b.jpg",
                    "caption": "标题", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs[0].label == "图 1"


def test_builder_matches_chinese_reference_with_or_without_space():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    for ref in ("图5", "图 5"):
        doc = builder.build(
            chapters_md={"x.md": f"# X\n\n本段提到{ref}的结果\n"},
            fig_notes=[{"fig_id": "Fig. 5", "image_abs_path": "/p.jpg",
                        "caption": "c", "deep_observation": ""}],
        )
        figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
        assert len(figs) == 1, f"failed for ref={ref!r}"


def test_builder_only_embeds_figure_once_across_chapters():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={
            "01.md": "# A\n\nfirst mention of Fig. 1\n",
            "02.md": "# B\n\nsecond mention of Fig. 1 here too\n",
        },
        fig_notes=[{"fig_id": "Fig. 1", "image_abs_path": "/p.jpg",
                    "caption": "c", "deep_observation": ""}],
    )
    total_figs = sum(
        1 for ch in doc.chapters for b in ch.blocks if isinstance(b, FigureBlock)
    )
    assert total_figs == 1


def test_builder_uses_image_paths_when_present_else_image_abs_path():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# X\n\nFig. 1 multi panel here\n"},
        fig_notes=[{"fig_id": "Fig. 1",
                    "image_paths": ["/a.jpg", "/b.jpg"],
                    "image_abs_path": "/c.jpg",
                    "caption": "x", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs[0].image_paths == (Path("/a.jpg"), Path("/b.jpg"))


def test_builder_drops_figure_with_no_image_paths():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# X\n\nFig. 99 has no image\n"},
        fig_notes=[{"fig_id": "Fig. 99", "image_paths": [], "image_abs_path": "",
                    "caption": "x", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_builder.py -v`
Expected: `ModuleNotFoundError: No module named 'stages.s09_render.builder'`.

- [ ] **Step 3: Implement DocumentBuilder**

Create `stages/s09_render/builder.py`:
```python
"""Build a frozen Document model from compose_dir chapters + fig_notes."""
from __future__ import annotations

import re
from pathlib import Path

from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock, Block,
)


class DocumentBuilder:
    """Pure transform: markdown + fig_notes → Document. No IO."""

    _FIG_ID_NUM = re.compile(r"Fig\.\s*(\d+)")

    def __init__(self, lang: str, paper_title: str):
        self.lang = lang
        self.paper_title = paper_title

    def build(self,
              chapters_md: dict[str, str],
              fig_notes: list[dict]) -> Document:
        embedded: set[str] = set()
        chapters: list[Chapter] = []
        for name in sorted(chapters_md):
            chapters.append(self._build_chapter(chapters_md[name], fig_notes, embedded))
        return Document(
            paper_title=self.paper_title,
            lang=self.lang,
            chapters=tuple(chapters),
        )

    def _build_chapter(self, md: str, fig_notes: list[dict],
                       embedded: set[str]) -> Chapter:
        lines = md.splitlines()
        heading, level, body_start = self._parse_heading(lines)
        body = "\n".join(lines[body_start:]).strip()

        blocks: list[Block] = list(self._split_paragraphs(body))
        blocks.extend(self._collect_referenced_figures(body, fig_notes, embedded))
        return Chapter(heading=heading, level=level, blocks=tuple(blocks))

    @staticmethod
    def _parse_heading(lines: list[str]) -> tuple[str, int, int]:
        if lines and lines[0].startswith("# "):
            return lines[0][2:].strip(), 1, 1
        return "Untitled", 1, 0

    @staticmethod
    def _split_paragraphs(body: str):
        for para in body.split("\n\n"):
            text = para.strip()
            if text:
                yield Paragraph(text=text)

    def _collect_referenced_figures(self, body: str, fig_notes: list[dict],
                                    embedded: set[str]):
        for note in fig_notes:
            fid = note.get("fig_id")
            if not fid or fid in embedded:
                continue
            if not self._is_referenced(fid, body):
                continue
            paths = self._resolve_image_paths(note)
            if not paths:
                continue
            embedded.add(fid)
            yield FigureBlock(
                fig_id=fid,
                label=self._make_label(fid),
                image_paths=tuple(paths),
                caption=note.get("caption") or "",
                deep_observation=note.get("deep_observation") or "",
            )

    def _is_referenced(self, fig_id: str, body: str) -> bool:
        if fig_id in body:
            return True
        m = self._FIG_ID_NUM.match(fig_id)
        if not m:
            return False
        num = m.group(1)
        return f"图{num}" in body or f"图 {num}" in body

    def _make_label(self, fig_id: str) -> str:
        if self.lang != "zh":
            return fig_id
        return fig_id.replace("Fig.", "图")

    @staticmethod
    def _resolve_image_paths(note: dict) -> list[Path]:
        raw = list(note.get("image_paths") or [])
        if not raw and note.get("image_abs_path"):
            raw = [note["image_abs_path"]]
        return [Path(p) for p in raw if p]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_builder.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/builder.py stages/s09_render/tests/test_builder.py
git commit -m "feat(s09_render): add DocumentBuilder (markdown + fig_notes → Document)"
```

### Task M2.4 — `Renderer` abstract base class

**Files:**
- Create: `stages/s09_render/renderers/__init__.py`
- Create: `stages/s09_render/renderers/base.py`

- [ ] **Step 1: Create the renderers package**

Create `stages/s09_render/renderers/__init__.py`:
```python
"""Renderer registry. Subclasses register themselves by file extension."""
from __future__ import annotations

from stages.s09_render.renderers.base import Renderer

# Populated as each renderer module is added (docx → M2, html/pdf → M3, pptx → M4).
RENDERERS: dict[str, type[Renderer]] = {}

__all__ = ["Renderer", "RENDERERS"]
```

Create `stages/s09_render/renderers/base.py`:
```python
"""Abstract renderer interface — every output format implements this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from stages.s09_render.model import Document


class Renderer(ABC):
    """Render a Document to a single file. Stateless or per-instance state only;
    must not mutate the input Document."""

    extension: ClassVar[str]   # "docx" | "html" | "pdf" | "pptx"

    @abstractmethod
    def render(self, doc: Document, out_path: Path) -> None:
        ...
```

Update `pyproject.toml` `[tool.setuptools] packages` to include the new sub-package — add `"stages.s09_render.renderers",` after the line for `stages.s09_render`:
```toml
packages = [
    "stages",
    "stages._common",
    ...
    "stages.s09_render",
    "stages.s09_render.renderers",
    "llm",
]
```

Reinstall:
```bash
uv pip install -e .
```

- [ ] **Step 2: Sanity-check import**

Run: `uv run python -c "from stages.s09_render.renderers import Renderer, RENDERERS; print(Renderer, RENDERERS)"`
Expected: `<class 'stages.s09_render.renderers.base.Renderer'> {}`.

- [ ] **Step 3: Commit**

```bash
git add stages/s09_render/renderers/__init__.py stages/s09_render/renderers/base.py pyproject.toml
git commit -m "feat(s09_render): add Renderer ABC and empty RENDERERS registry"
```

### Task M2.5 — Migrate the existing docx rendering into `DocxRenderer`

**Files:**
- Create: `stages/s09_render/renderers/docx.py`
- Modify: `stages/s09_render/renderers/__init__.py`

- [ ] **Step 1: Write failing test**

Append to `stages/s09_render/tests/test_renderers_smoke.py` (create the file):
```python
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from PIL import Image

from stages.s09_render.model import Document, Chapter, Paragraph, FigureBlock
from stages.s09_render.renderers import RENDERERS


@pytest.fixture
def one_image(tmp_path: Path) -> Path:
    p = tmp_path / "tiny.jpg"
    Image.new("RGB", (100, 50), "red").save(p)
    return p


def _make_doc(one_image: Path) -> Document:
    return Document(
        paper_title="Smoke Test Paper",
        lang="zh",
        chapters=(
            Chapter(heading="引言", level=1, blocks=(
                Paragraph(text="这是引言的第一段。"),
                Paragraph(text="第二段提到 Fig. 1 的内容。"),
                FigureBlock(fig_id="Fig. 1", label="图 1",
                            image_paths=(one_image,),
                            caption="第一张图", deep_observation="观察"),
            )),
        ),
    )


def test_docx_renderer_produces_readable_file(tmp_path: Path, one_image: Path):
    doc = _make_doc(one_image)
    out = tmp_path / "preview.docx"
    RENDERERS["docx"]().render(doc, out)
    assert out.exists() and out.stat().st_size > 4000
    d = DocxDocument(out)
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Smoke Test Paper" in text
    assert "引言" in text
    assert "图 1. 第一张图" in text
    assert len(d.inline_shapes) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py -v`
Expected: `KeyError: 'docx'` — the registry is empty.

- [ ] **Step 3: Implement DocxRenderer**

Create `stages/s09_render/renderers/docx.py`. This is a class-organized port of the existing `_render_preview_docx` in `stages/s09_render/runner.py:47-115`:
```python
"""Render a Document to .docx using python-docx. Class-organized port of the
original _render_preview_docx from the legacy runner.py."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from stages.s09_render.model import Chapter, Document, FigureBlock, Paragraph
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


class DocxRenderer(Renderer):
    extension: ClassVar[str] = "docx"

    TITLE_PT = 16
    HEADING_PT = 14
    CAPTION_PT = 9

    def render(self, doc: Document, out_path: Path) -> None:
        body_pt = 10.5 if doc.lang == "zh" else 11
        img_cm = 13 if doc.lang == "zh" else 14
        set_ea = (doc.lang == "zh")

        out_doc = DocxDocument()
        sec = out_doc.sections[0]
        sec.top_margin = sec.bottom_margin = Cm(2.0)
        sec.left_margin = sec.right_margin = Cm(2.2)

        self._write_title(out_doc, doc.paper_title, set_ea)
        for chapter in doc.chapters:
            self._write_chapter(out_doc, chapter, body_pt, img_cm, set_ea, doc.lang)

        out_doc.save(out_path)

    # ---------- chapter / block writers ----------

    def _write_chapter(self, out, chapter: Chapter, body_pt: float,
                       img_cm: float, set_ea: bool, lang: str) -> None:
        self._write_heading(out, chapter.heading, set_ea)
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                self._write_paragraph(out, block.text, body_pt, set_ea)
            elif isinstance(block, FigureBlock):
                self._write_figure_block(out, block, img_cm, set_ea, lang)

    def _write_title(self, out, title: str, set_ea: bool) -> None:
        p = out.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._apply_cn_font(p.add_run(title), size=self.TITLE_PT, bold=True, set_ea=set_ea)

    def _write_heading(self, out, heading: str, set_ea: bool) -> None:
        p = out.add_paragraph()
        self._apply_cn_font(p.add_run(heading), size=self.HEADING_PT, bold=True, set_ea=set_ea)

    def _write_paragraph(self, out, text: str, body_pt: float, set_ea: bool) -> None:
        p = out.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.74)
        self._apply_cn_font(p.add_run(text), size=body_pt, set_ea=set_ea)

    def _write_figure_block(self, out, block: FigureBlock,
                            img_cm: float, set_ea: bool, lang: str) -> None:
        paths = [p for p in block.image_paths if p.exists()]
        if not paths:
            return
        for img_path in paths:
            ip = out.add_paragraph()
            ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ip.add_run().add_picture(str(img_path), width=Cm(img_cm))
        cap = out.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._apply_cn_font(
            cap.add_run(f"{block.label}. {block.caption}"),
            size=self.CAPTION_PT, bold=True, set_ea=set_ea,
        )
        if block.deep_observation:
            prefix = "【深度观察】" if lang == "zh" else "Deep observation: "
            obs = out.add_paragraph()
            self._apply_cn_font(
                obs.add_run(f"{prefix}{block.deep_observation}"),
                size=self.CAPTION_PT, color=(0x33, 0x33, 0x66), set_ea=set_ea,
            )

    # ---------- font helper ----------

    @staticmethod
    def _apply_cn_font(run, *, size: float, bold: bool = False,
                       color: tuple[int, int, int] | None = None,
                       set_ea: bool = True) -> None:
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        run.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        if set_ea:
            rPr = run._element.get_or_add_rPr()
            rf = rPr.find(qn("w:rFonts"))
            if rf is None:
                rf = OxmlElement("w:rFonts")
                rPr.append(rf)
            rf.set(qn("w:eastAsia"), "宋体")
            rf.set(qn("w:ascii"), "Times New Roman")
            rf.set(qn("w:hAnsi"), "Times New Roman")


RENDERERS["docx"] = DocxRenderer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py -v`
Expected: `test_docx_renderer_produces_readable_file PASSED`.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/renderers/docx.py stages/s09_render/tests/test_renderers_smoke.py
git commit -m "feat(s09_render): add DocxRenderer (class-organized port of _render_preview_docx)"
```

### Task M2.6 — Rewrite `s09_render/runner.py` as 35-line coordinator

**Files:**
- Modify: `stages/s09_render/runner.py` (full rewrite)
- Modify: `stages/s09_render/tests/test_runner.py` (keep, possibly adjust imports — tests still target the public `run()` API)

- [ ] **Step 1: Confirm existing tests still describe the desired behavior**

Read `stages/s09_render/tests/test_runner.py` once to remind yourself the 4 tests assert: (a) bundle + preview.docx produced, (b) stale bundle files cleared, (c) Fig. 1 dedup, (d) multi-panel embedding. These tests call `run(compose_dir, fig_notes_dir, out_dir, paper_title)` — the same signature we will keep.

- [ ] **Step 2: Run the existing tests to confirm they currently pass against the old runner**

Run: `pytest stages/s09_render/tests/test_runner.py -v`
Expected: 4 passed.

- [ ] **Step 3: Rewrite `runner.py` as a thin coordinator**

Replace `stages/s09_render/runner.py` entirely with:
```python
"""Stage 09: build the Document model and render to one or more formats.

Default formats are docx + the mypaper_bundle (legacy contract). HTML/PDF/PPTX
are added in later milestones and exposed via the `formats` parameter."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from stages._common import dump_yaml, load_yaml, mark_done
from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.renderers import RENDERERS

# Import side-effect: each renderer module registers itself in RENDERERS.
# Import here (not in __init__.py) to keep the module graph explicit.
import stages.s09_render.renderers.docx  # noqa: F401


BUNDLE_README = """\
# mypaper bundle

Drop this folder's contents into mypaper/ to render the styled thesis:

    cp -r chapters/* /path/to/mypaper/chapters/
    cp -r figures/*  /path/to/mypaper/figures/
    cd /path/to/mypaper && uv run python scripts/build.py

The README of mypaper has the full template-swap instructions.
"""


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview", lang: str = "zh",
        formats: Iterable[str] | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_md = _read_chapters(Path(compose_dir))
    fig_notes = _read_fig_notes(Path(fig_notes_dir))
    doc = DocumentBuilder(lang=lang, paper_title=paper_title).build(chapters_md, fig_notes)

    requested = list(formats) if formats is not None else ["docx"]
    results: dict[str, str] = {}
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        RENDERERS[fmt]().render(doc, out_path)
        results[fmt] = str(out_path)

    bundle = _write_bundle(Path(compose_dir), fig_notes, out_dir)

    mark_done(out_dir, {
        "formats": results,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
    })
    return {"preview_files": results, "bundle": str(bundle)}


def _read_chapters(compose_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted((compose_dir / "chapters").glob("*.md"))}


def _read_fig_notes(fig_notes_dir: Path) -> list[dict]:
    path = fig_notes_dir / "fig_notes.yaml"
    return load_yaml(path) or []


def _write_bundle(compose_dir: Path, fig_notes: list[dict], out_dir: Path) -> Path:
    bundle = out_dir / "mypaper_bundle"
    (bundle / "chapters").mkdir(parents=True, exist_ok=True)
    (bundle / "figures").mkdir(exist_ok=True)
    # Clear stale files from prior runs
    for stale in (bundle / "chapters").glob("*.md"):
        stale.unlink()
    for stale in (bundle / "figures").iterdir():
        if stale.is_file():
            stale.unlink()
    for md in (compose_dir / "chapters").glob("*.md"):
        shutil.copy2(md, bundle / "chapters" / md.name)
    for note in fig_notes:
        paths = list(note.get("image_paths") or [])
        if note.get("image_abs_path"):
            paths.append(note["image_abs_path"])
        for p in paths:
            ap = Path(p)
            if ap.exists():
                shutil.copy2(ap, bundle / "figures" / ap.name)
    (bundle / "README.md").write_text(BUNDLE_README, encoding="utf-8")
    return bundle
```

Note: the existing test_runner.py calls `run(compose_dir=..., fig_notes_dir=..., out_dir=..., paper_title=...)` with no `formats` arg, expecting `preview.docx` to be produced. The default `formats=None` → `["docx"]` keeps that behavior.

- [ ] **Step 4: Run all s09_render tests to verify zero regression**

Run: `pytest stages/s09_render/ -v`
Expected: all 4 legacy tests in `test_runner.py` pass, plus the new tests in `test_model.py`, `test_builder.py`, `test_renderers_smoke.py`.

- [ ] **Step 5: Run the full project test suite as a regression check**

Run: `pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add stages/s09_render/runner.py
git commit -m "refactor(s09_render): rewrite runner.py as 35-line coordinator on top of Document model"
```

### Task M2.7 — Tag M2

- [ ] **Step 1: Tag**

```bash
git tag m2-docx-migrated
```

---

# Milestone M3 — `HtmlRenderer` + `PdfRenderer` + Jinja2 templates

**Goal:** Add HTML (single self-contained file, base64-embedded images) and PDF (rendered from the same HTML via weasyprint) output formats sharing a single Jinja2 template and CSS.

**Acceptance:** `RENDERERS["html"]` and `RENDERERS["pdf"]` both produce valid files; CLI `--formats docx,pdf,html` produces all three.

### Task M3.1 — Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add jinja2 + weasyprint to dependencies**

Open `pyproject.toml`, edit the `dependencies` list (under `[project]`) to add `"jinja2>=3.1",` and `"weasyprint>=62",`. The full list should become:
```toml
dependencies = [
    "requests>=2.31.0",
    "pdfplumber>=0.11",
    "pypdfium2>=4",
    "python-docx>=1.1",
    "openai>=1.50",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "Pillow>=10",
    "jinja2>=3.1",
    "weasyprint>=62",
]
```

- [ ] **Step 2: Install the new deps**

Run: `uv pip install -e .`
Expected: weasyprint and jinja2 download and install. If weasyprint fails on macOS, run `brew install pango gdk-pixbuf libffi cairo` first, then retry (per the spec, Docker is the recommended path for users; macOS dev still needs the system libs locally).

- [ ] **Step 3: Sanity check**

Run: `uv run python -c "import jinja2, weasyprint; print(jinja2.__version__, weasyprint.__version__)"`
Expected: two version strings printed, no exception.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add jinja2 and weasyprint for HTML/PDF renderers"
```

### Task M3.2 — Create the Jinja2 template + CSS

**Files:**
- Create: `stages/s09_render/templates/preview.html.j2`
- Create: `stages/s09_render/templates/styles.css`
- Modify: `pyproject.toml` (add package_data so templates are installed)

- [ ] **Step 1: Create styles.css**

Create `stages/s09_render/templates/styles.css`:
```css
@page { size: A4; margin: 2.2cm 2.0cm; }
body { font-family: "Times New Roman", "宋体", serif; font-size: 10.5pt; line-height: 1.5; color: #222; }
body[data-lang="en"] { font-size: 11pt; }
h1.paper-title { text-align: center; font-size: 16pt; margin: 0 0 1em 0; }
h2.chapter-heading { font-size: 14pt; margin: 1.2em 0 0.6em 0; }
p.body-paragraph { text-indent: 2em; margin: 0 0 0.6em 0; }
figure.figure-block { margin: 1em 0; text-align: center; page-break-inside: avoid; }
figure.figure-block img { max-width: 13cm; height: auto; }
body[data-lang="en"] figure.figure-block img { max-width: 14cm; }
figcaption.caption { font-size: 9pt; font-weight: bold; margin-top: 0.3em; }
p.deep-observation { font-size: 9pt; color: #333366; margin: 0.3em 0 0 0; }
```

- [ ] **Step 2: Create preview.html.j2**

Create `stages/s09_render/templates/preview.html.j2`:
```jinja
<!DOCTYPE html>
<html lang="{{ doc.lang }}">
<head>
<meta charset="utf-8">
<title>{{ doc.paper_title }}</title>
<style>{{ styles | safe }}</style>
</head>
<body data-lang="{{ doc.lang }}">
<h1 class="paper-title">{{ doc.paper_title }}</h1>
{% for ch in doc.chapters %}
<section class="chapter">
  <h2 class="chapter-heading">{{ ch.heading }}</h2>
  {% for block in ch.blocks %}
    {% if block.__class__.__name__ == 'Paragraph' %}
      <p class="body-paragraph">{{ block.text }}</p>
    {% elif block.__class__.__name__ == 'FigureBlock' %}
      <figure class="figure-block">
        {% for img_src in block_images(block) %}
          <img src="{{ img_src }}" alt="{{ block.label }}">
        {% endfor %}
        <figcaption class="caption">{{ block.label }}. {{ block.caption }}</figcaption>
        {% if block.deep_observation %}
          {% if doc.lang == 'zh' %}
            <p class="deep-observation">【深度观察】{{ block.deep_observation }}</p>
          {% else %}
            <p class="deep-observation">Deep observation: {{ block.deep_observation }}</p>
          {% endif %}
        {% endif %}
      </figure>
    {% endif %}
  {% endfor %}
</section>
{% endfor %}
</body>
</html>
```

- [ ] **Step 3: Register templates as package data**

Open `pyproject.toml`. After the `[tool.setuptools]` block, add (or extend if already present):
```toml
[tool.setuptools.package-data]
"stages.s09_render" = ["templates/*.html.j2", "templates/*.css"]
```

Reinstall: `uv pip install -e .`

- [ ] **Step 4: Sanity check the template loads**

Run: `uv run python -c "from pathlib import Path; from stages import s09_render; tpl = Path(s09_render.__file__).parent / 'templates' / 'preview.html.j2'; print('OK', tpl.exists(), tpl.stat().st_size)"`
Expected: `OK True <some integer>`.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/templates/preview.html.j2 stages/s09_render/templates/styles.css pyproject.toml
git commit -m "feat(s09_render): add Jinja2 template and CSS for HTML/PDF rendering"
```

### Task M3.3 — Implement `HtmlRenderer`

**Files:**
- Create: `stages/s09_render/renderers/html.py`
- Modify: `stages/s09_render/tests/test_renderers_smoke.py` (add HTML test)
- Modify: `stages/s09_render/runner.py` (import the new module so it registers)

- [ ] **Step 1: Write failing test**

Append to `stages/s09_render/tests/test_renderers_smoke.py`:
```python
def test_html_renderer_self_contained_base64(tmp_path: Path, one_image: Path):
    doc = _make_doc(one_image)
    out = tmp_path / "preview.html"
    RENDERERS["html"]().render(doc, out)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "Smoke Test Paper" in html
    assert "引言" in html
    assert "图 1. 第一张图" in html
    # Base64 embedded image — no external file refs
    assert 'src="data:image/' in html
    assert 'src="/tmp' not in html  # absolute paths must NOT leak
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_html_renderer_self_contained_base64 -v`
Expected: `KeyError: 'html'`.

- [ ] **Step 3: Implement HtmlRenderer**

Create `stages/s09_render/renderers/html.py`:
```python
"""Render a Document to a single self-contained HTML file with base64 images."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, select_autoescape

from stages.s09_render.model import Document, FigureBlock
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


class HtmlRenderer(Renderer):
    extension: ClassVar[str] = "html"

    def render(self, doc: Document, out_path: Path) -> None:
        html = self.render_to_string(doc)
        Path(out_path).write_text(html, encoding="utf-8")

    def render_to_string(self, doc: Document) -> str:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )
        env.globals["block_images"] = self._block_images
        styles = (_TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")
        template = env.get_template("preview.html.j2")
        return template.render(doc=doc, styles=styles)

    @staticmethod
    def _block_images(block: FigureBlock) -> list[str]:
        out: list[str] = []
        for img_path in block.image_paths:
            if not img_path.exists():
                continue
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp",
                    "gif": "gif"}.get(img_path.suffix.lstrip(".").lower(), "jpeg")
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            out.append(f"data:image/{mime};base64,{b64}")
        return out


RENDERERS["html"] = HtmlRenderer
```

Edit `stages/s09_render/runner.py` to import the new renderer (next to the existing `import stages.s09_render.renderers.docx`):
```python
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_html_renderer_self_contained_base64 -v`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/renderers/html.py stages/s09_render/tests/test_renderers_smoke.py stages/s09_render/runner.py
git commit -m "feat(s09_render): add HtmlRenderer (single self-contained file with base64 images)"
```

### Task M3.4 — Implement `PdfRenderer`

**Files:**
- Create: `stages/s09_render/renderers/pdf.py`
- Modify: `stages/s09_render/tests/test_renderers_smoke.py`
- Modify: `stages/s09_render/runner.py`

- [ ] **Step 1: Write failing test**

Append to `stages/s09_render/tests/test_renderers_smoke.py`:
```python
def test_pdf_renderer_produces_valid_pdf_file(tmp_path: Path, one_image: Path):
    doc = _make_doc(one_image)
    out = tmp_path / "preview.pdf"
    RENDERERS["pdf"]().render(doc, out)
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"
    assert out.stat().st_size > 10_000  # cover page + 1 image
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_pdf_renderer_produces_valid_pdf_file -v`
Expected: `KeyError: 'pdf'`.

- [ ] **Step 3: Implement PdfRenderer**

Create `stages/s09_render/renderers/pdf.py`:
```python
"""Render PDF by running the HtmlRenderer output through WeasyPrint."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import weasyprint

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.renderers.html import HtmlRenderer


class PdfRenderer(Renderer):
    extension: ClassVar[str] = "pdf"

    def render(self, doc: Document, out_path: Path) -> None:
        html_str = HtmlRenderer().render_to_string(doc)
        weasyprint.HTML(string=html_str).write_pdf(target=str(out_path))


RENDERERS["pdf"] = PdfRenderer
```

Edit `stages/s09_render/runner.py` to import the new renderer:
```python
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401
import stages.s09_render.renderers.pdf   # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_pdf_renderer_produces_valid_pdf_file -v`
Expected: PASSED. If weasyprint complains about missing system libraries on macOS, install them with `brew install pango gdk-pixbuf libffi cairo` and retry.

- [ ] **Step 5: Run full s09_render tests**

Run: `pytest stages/s09_render/ -v`
Expected: all green (4 legacy + 4 model + 7 builder + 3 smoke = 18 passed).

- [ ] **Step 6: Commit**

```bash
git add stages/s09_render/renderers/pdf.py stages/s09_render/tests/test_renderers_smoke.py stages/s09_render/runner.py
git commit -m "feat(s09_render): add PdfRenderer (HtmlRenderer output via WeasyPrint)"
```

### Task M3.5 — Tag M3

- [ ] **Step 1: Tag**

```bash
git tag m3-html-pdf-added
```

---

# Milestone M4 — `SlidePlanner` + `PptxSummarizer` + `PptxRenderer`

**Goal:** Add the PPT pipeline. `SlidePlanner` deterministically cuts a `Document` into `Slide` units (title / outline / divider / bullets / figure / closing). `PptxSummarizer` (LLM-backed, double-track cache) generates compact bullets and one-liner figure observations. `PptxRenderer` materializes the deck to `.pptx`.

**Acceptance:** `RENDERERS["pptx"]()` produces a valid pptx with 15–50 slides for the hu2025 fixture; LLM cache hits on the second run.

### Task M4.1 — Add `python-pptx` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the dep**

Open `pyproject.toml`, add `"python-pptx>=0.6.23",` to `dependencies`:
```toml
dependencies = [
    ...
    "python-pptx>=0.6.23",
]
```

- [ ] **Step 2: Install**

Run: `uv pip install -e .`

- [ ] **Step 3: Sanity check**

Run: `uv run python -c "from pptx import Presentation; print(Presentation().slide_layouts)"`
Expected: a `<pptx.slide.SlideLayouts>` repr, no exception.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add python-pptx for PPT renderer"
```

### Task M4.2 — Define `Slide` / `SlideDeck` + `SlidePlanner`

**Files:**
- Create: `stages/s09_render/slide_planner.py`
- Create: `stages/s09_render/tests/test_slide_planner.py`

- [ ] **Step 1: Write failing test**

Create `stages/s09_render/tests/test_slide_planner.py`:
```python
from pathlib import Path

from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock,
)
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner


def _doc(blocks_per_chapter=2, n_chapters=2, with_figure=True) -> Document:
    chapters = []
    for i in range(n_chapters):
        blocks = [Paragraph(text=f"Para {j} of chapter {i}.") for j in range(blocks_per_chapter)]
        if with_figure:
            blocks.append(FigureBlock(
                fig_id=f"Fig. {i+1}", label=f"Fig. {i+1}",
                image_paths=(Path(f"/tmp/img{i}.jpg"),),
                caption=f"caption {i}", deep_observation=f"deep obs {i}",
            ))
        chapters.append(Chapter(heading=f"Ch{i+1}", level=1, blocks=tuple(blocks)))
    return Document(paper_title="P", lang="en", chapters=tuple(chapters))


def test_planner_starts_with_title_then_outline():
    deck = SlidePlanner(lang="en").plan(_doc(), summaries=None)
    assert deck.slides[0].kind == "title"
    assert deck.slides[0].title == "P"
    assert deck.slides[1].kind == "outline"
    assert "Ch1" in deck.slides[1].bullets
    assert "Ch2" in deck.slides[1].bullets


def test_planner_ends_with_closing_slide():
    deck = SlidePlanner(lang="en").plan(_doc(), summaries=None)
    assert deck.slides[-1].kind == "closing"


def test_planner_inserts_divider_only_when_chapter_has_enough_content():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=False)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    kinds = [s.kind for s in deck.slides]
    assert "divider" in kinds   # 2 paragraphs ≥ threshold

    doc1 = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=False)
    deck1 = SlidePlanner(lang="en").plan(doc1, summaries=None)
    kinds1 = [s.kind for s in deck1.slides]
    assert "divider" not in kinds1


def test_planner_emits_one_figure_slide_per_figure_block():
    doc = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=True)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    fig_slides = [s for s in deck.slides if s.kind == "figure"]
    assert len(fig_slides) == 1
    assert fig_slides[0].caption == "caption 0"
    # Without LLM summaries we fall back to using deep_observation verbatim.
    assert "deep obs 0" in fig_slides[0].deep_observation


def test_planner_bullets_capped_at_max_per_slide():
    doc = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Long", level=1, blocks=tuple(
            Paragraph(text=f"sentence {i}.") for i in range(20)
        )),
    ))
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    bullet_slides = [s for s in deck.slides if s.kind == "bullets"]
    assert all(len(s.bullets) <= SlidePlanner.MAX_BULLETS_PER_SLIDE for s in bullet_slides)


def test_planner_uses_summaries_when_provided():
    doc = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=True)
    summaries = {
        "Ch1": {
            "bullets": ["llm bullet a", "llm bullet b"],
            "figure_one_liners": {"Fig. 1": "one-liner from LLM"},
        }
    }
    deck = SlidePlanner(lang="en").plan(doc, summaries=summaries)
    bullets_slide = next(s for s in deck.slides if s.kind == "bullets")
    assert "llm bullet a" in bullets_slide.bullets
    fig_slide = next(s for s in deck.slides if s.kind == "figure")
    assert "one-liner from LLM" in fig_slide.deep_observation


def test_planner_attaches_paragraph_text_to_speaker_notes():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=False)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    bullets_slide = next(s for s in deck.slides if s.kind == "bullets")
    # Original paragraph text is preserved in notes for the speaker.
    assert "Para 0 of chapter 0." in bullets_slide.notes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_slide_planner.py -v`
Expected: `ModuleNotFoundError: No module named 'stages.s09_render.slide_planner'`.

- [ ] **Step 3: Implement SlidePlanner**

Create `stages/s09_render/slide_planner.py`:
```python
"""Cut a Document into Slide units for the PPT renderer.

Deterministic logic only — LLM summaries (if any) are passed in by the caller.
No IO, no model state."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


@dataclass(frozen=True)
class Slide:
    kind: str                              # title | outline | divider | bullets | figure | closing
    title: str
    bullets: tuple[str, ...] = field(default_factory=tuple)
    image_paths: tuple[Path, ...] = field(default_factory=tuple)
    caption: str = ""
    deep_observation: str = ""
    notes: str = ""                        # speaker notes


@dataclass(frozen=True)
class SlideDeck:
    slides: tuple[Slide, ...]
    lang: str


class SlidePlanner:
    MAX_BULLETS_PER_SLIDE: ClassVar[int] = 5
    MIN_PARAGRAPHS_FOR_DIVIDER: ClassVar[int] = 2

    def __init__(self, lang: str):
        self.lang = lang

    def plan(self, doc: Document, summaries: dict | None) -> SlideDeck:
        slides: list[Slide] = [self._title_slide(doc), self._outline_slide(doc)]
        for chapter in doc.chapters:
            ch_summary = (summaries or {}).get(chapter.heading)
            slides.extend(self._chapter_slides(chapter, ch_summary))
        slides.append(self._closing_slide(doc))
        return SlideDeck(slides=tuple(slides), lang=self.lang)

    # ---------- per-section planners ----------

    def _title_slide(self, doc: Document) -> Slide:
        return Slide(kind="title", title=doc.paper_title)

    def _outline_slide(self, doc: Document) -> Slide:
        bullets = tuple(ch.heading for ch in doc.chapters)
        return Slide(kind="outline",
                     title=self._localize("Outline", "目录"),
                     bullets=bullets)

    def _closing_slide(self, doc: Document) -> Slide:
        conclusion = next(
            (ch for ch in doc.chapters if "conclu" in ch.heading.lower()
             or "结论" in ch.heading),
            doc.chapters[-1] if doc.chapters else None,
        )
        bullets: tuple[str, ...] = ()
        notes = ""
        if conclusion is not None:
            paragraphs = [b for b in conclusion.blocks if isinstance(b, Paragraph)]
            bullets = tuple(self._paragraph_bullets(paragraphs)[:self.MAX_BULLETS_PER_SLIDE])
            notes = "\n\n".join(p.text for p in paragraphs)
        return Slide(kind="closing",
                     title=self._localize("Conclusion", "总结"),
                     bullets=bullets, notes=notes)

    def _chapter_slides(self, chapter: Chapter, summary: dict | None) -> list[Slide]:
        paragraphs = [b for b in chapter.blocks if isinstance(b, Paragraph)]
        figures = [b for b in chapter.blocks if isinstance(b, FigureBlock)]

        slides: list[Slide] = []
        if len(paragraphs) >= self.MIN_PARAGRAPHS_FOR_DIVIDER:
            slides.append(Slide(kind="divider", title=chapter.heading))

        slides.extend(self._bullets_slides(chapter, paragraphs, summary))
        slides.extend(self._figure_slides(chapter, figures, summary))
        return slides

    def _bullets_slides(self, chapter: Chapter, paragraphs: list[Paragraph],
                        summary: dict | None) -> list[Slide]:
        if not paragraphs:
            return []
        notes_full = "\n\n".join(p.text for p in paragraphs)
        if summary and summary.get("bullets"):
            source = list(summary["bullets"])
        else:
            source = self._paragraph_bullets(paragraphs)
        slides: list[Slide] = []
        for chunk in _chunked(source, self.MAX_BULLETS_PER_SLIDE):
            slides.append(Slide(
                kind="bullets",
                title=chapter.heading,
                bullets=tuple(chunk),
                notes=notes_full,
            ))
        return slides

    def _figure_slides(self, chapter: Chapter, figures: list[FigureBlock],
                       summary: dict | None) -> list[Slide]:
        one_liners = (summary or {}).get("figure_one_liners", {})
        slides: list[Slide] = []
        for fb in figures:
            obs = one_liners.get(fb.fig_id) or fb.deep_observation
            slides.append(Slide(
                kind="figure",
                title=f"{fb.label}: {fb.caption}",
                image_paths=fb.image_paths,
                caption=fb.caption,
                deep_observation=obs,
                notes=f"Full deep observation:\n{fb.deep_observation}",
            ))
        return slides

    # ---------- helpers ----------

    def _localize(self, en: str, zh: str) -> str:
        return zh if self.lang == "zh" else en

    @staticmethod
    def _paragraph_bullets(paragraphs: list[Paragraph]) -> list[str]:
        """Rule-based fallback: first sentence (or first 80 chars) of each para."""
        out: list[str] = []
        for p in paragraphs:
            first = p.text.split("。")[0].split(". ")[0].strip()
            if not first:
                continue
            out.append(first[:80])
        return out


def _chunked(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_slide_planner.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/slide_planner.py stages/s09_render/tests/test_slide_planner.py
git commit -m "feat(s09_render): add SlidePlanner (Document → SlideDeck, deterministic cutting)"
```

### Task M4.3 — Implement `PptxSummarizer` with double-track cache

**Files:**
- Create: `llm/prompts/pptx_summarize.md`
- Create: `stages/s09_render/pptx_summarizer.py`
- Create: `stages/s09_render/tests/test_pptx_summarizer.py`

- [ ] **Step 1: Create the prompt template**

Create `llm/prompts/pptx_summarize.md`:
```markdown
You compress one chapter of a scientific paper into PPT-ready material.

Output STRICT JSON with these keys:
- `bullets`: list of 3-5 short strings. Chinese ≤ 30 chars each, English ≤ 15 words.
- `figure_one_liners`: object {fig_id: short string}. Chinese ≤ 40 chars, English ≤ 20 words.

Rules:
- No prose, no preamble. Output ONLY the JSON object.
- Bullets must be self-contained (a slide reader can understand without context).
- One-liners must capture the figure's takeaway, not describe it.
- Use the same language as the chapter text.

Chapter heading: {heading}
Chapter body:
{body}

Figures referenced in this chapter:
{figures_block}
```

- [ ] **Step 2: Write failing test**

Create `stages/s09_render/tests/test_pptx_summarizer.py`:
```python
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)
from stages.s09_render.pptx_summarizer import PptxSummarizer


def _doc():
    return Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Intro", level=1, blocks=(
            Paragraph(text="A study of X."),
            Paragraph(text="It matters because Y."),
            FigureBlock(fig_id="Fig. 1", label="Fig. 1",
                        image_paths=(Path("/img.jpg"),),
                        caption="schema", deep_observation="long obs"),
        )),
    ))


def _fake_llm(payload: dict) -> MagicMock:
    fake = MagicMock()
    fake.chat.return_value = MagicMock(
        content=json.dumps(payload),
        model="fake",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        latency_ms=42.0,
    )
    return fake


def test_summarize_calls_llm_once_per_chapter(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a", "b"], "figure_one_liners": {"Fig. 1": "ok"}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert llm.chat.call_count == 1
    assert result["Intro"]["bullets"] == ["a", "b"]
    assert result["Intro"]["figure_one_liners"] == {"Fig. 1": "ok"}


def test_summarize_writes_audit_files(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
    PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en").summarize(_doc())
    slug = "Intro"
    assert (tmp_path / f"{slug}.input_hash.json").exists()
    assert (tmp_path / f"{slug}.json").exists()
    assert (tmp_path / f"{slug}.prompt.md").exists()
    assert (tmp_path / f"{slug}.response.json").exists()


def test_summarize_reuses_cache_when_input_hash_matches(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1

    # Second run with identical input: cache hit, no LLM call.
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1


def test_summarize_reruns_when_chapter_text_changes(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())

    changed = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Intro", level=1, blocks=(
            Paragraph(text="DIFFERENT TEXT"),
        )),
    ))
    summarizer.summarize(changed)
    assert llm.chat.call_count == 2


def test_summarize_returns_none_after_three_consecutive_failures(tmp_path: Path):
    failing_llm = MagicMock()
    failing_llm.chat.side_effect = RuntimeError("LLM exploded")
    summarizer = PptxSummarizer(llm=failing_llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize(_doc())
    assert result is None
    assert failing_llm.chat.call_count == 3   # 3 retries on the single chapter
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_pptx_summarizer.py -v`
Expected: `ModuleNotFoundError: No module named 'stages.s09_render.pptx_summarizer'`.

- [ ] **Step 4: Implement PptxSummarizer**

Create `stages/s09_render/pptx_summarizer.py`:
```python
"""Generate PPT bullets and figure one-liners via the text LLM.

Caches per-chapter results: if the chapter's input hash matches the cached one,
the LLM is not called. Always writes prompt/response files alongside the cache
for auditability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stages._common.paths import slugify
from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


_MAX_RETRIES_PER_CHAPTER = 3
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_summarize.md"


class PptxSummarizer:
    """LLM-backed summarizer with double-track cache (audit + reuse)."""

    def __init__(self, llm, cache_dir: Path, lang: str):
        self.llm = llm
        self.cache_dir = Path(cache_dir)
        self.lang = lang
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")

    def summarize(self, doc: Document) -> dict | None:
        """Returns {chapter_heading: {bullets, figure_one_liners}} or None on
        total failure (3 consecutive LLM errors on the same chapter)."""
        out: dict[str, dict] = {}
        for chapter in doc.chapters:
            chapter_out = self._summarize_chapter(chapter)
            if chapter_out is None:
                return None
            out[chapter.heading] = chapter_out
        return out

    # ---------- per-chapter ----------

    def _summarize_chapter(self, chapter: Chapter) -> dict | None:
        slug = slugify(chapter.heading)
        input_hash = self._input_hash(chapter)
        cached = self._try_cache(slug, input_hash)
        if cached is not None:
            return cached

        prompt = self._build_prompt(chapter)
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES_PER_CHAPTER):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=800,
                )
                payload = json.loads(response.content)
                self._write_cache(slug, input_hash, payload, prompt, response)
                return payload
            except Exception as exc:
                last_error = exc
                continue
        # All retries exhausted
        return None

    # ---------- cache I/O ----------

    def _input_hash(self, chapter: Chapter) -> str:
        # Hash the chapter content + lang so a language switch invalidates.
        h = hashlib.sha256()
        h.update(self.lang.encode("utf-8"))
        h.update(b"\x00")
        h.update(chapter.heading.encode("utf-8"))
        h.update(b"\x00")
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                h.update(b"P:")
                h.update(block.text.encode("utf-8"))
                h.update(b"\x00")
            elif isinstance(block, FigureBlock):
                h.update(b"F:")
                h.update(block.fig_id.encode("utf-8"))
                h.update(b"|")
                h.update(block.caption.encode("utf-8"))
                h.update(b"|")
                h.update(block.deep_observation.encode("utf-8"))
                h.update(b"\x00")
        return h.hexdigest()

    def _try_cache(self, slug: str, input_hash: str) -> dict | None:
        hash_file = self.cache_dir / f"{slug}.input_hash.json"
        out_file = self.cache_dir / f"{slug}.json"
        if not hash_file.exists() or not out_file.exists():
            return None
        try:
            stored = json.loads(hash_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if stored.get("hash") != input_hash:
            return None
        return json.loads(out_file.read_text(encoding="utf-8"))

    def _write_cache(self, slug: str, input_hash: str, output: dict,
                     prompt: str, response) -> None:
        (self.cache_dir / f"{slug}.input_hash.json").write_text(
            json.dumps({"hash": input_hash}), encoding="utf-8",
        )
        (self.cache_dir / f"{slug}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (self.cache_dir / f"{slug}.prompt.md").write_text(prompt, encoding="utf-8")
        (self.cache_dir / f"{slug}.response.json").write_text(
            json.dumps({
                "content": response.content,
                "model": getattr(response, "model", None),
                "usage": getattr(response, "usage", None),
                "latency_ms": getattr(response, "latency_ms", None),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- prompt ----------

    def _build_prompt(self, chapter: Chapter) -> str:
        body = "\n\n".join(
            b.text for b in chapter.blocks if isinstance(b, Paragraph)
        )
        figures = [b for b in chapter.blocks if isinstance(b, FigureBlock)]
        if figures:
            figures_block = "\n".join(
                f"- {fb.fig_id}: {fb.caption} (deep_obs: {fb.deep_observation})"
                for fb in figures
            )
        else:
            figures_block = "(no figures in this chapter)"
        return self._template.format(
            heading=chapter.heading,
            body=body or "(no body text)",
            figures_block=figures_block,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_pptx_summarizer.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add llm/prompts/pptx_summarize.md stages/s09_render/pptx_summarizer.py stages/s09_render/tests/test_pptx_summarizer.py
git commit -m "feat(s09_render): add PptxSummarizer (LLM bullets + double-track cache)"
```

### Task M4.4 — Implement `PptxRenderer`

**Files:**
- Create: `stages/s09_render/renderers/pptx.py`
- Modify: `stages/s09_render/tests/test_renderers_smoke.py`
- Modify: `stages/s09_render/runner.py`

- [ ] **Step 1: Write failing test**

Append to `stages/s09_render/tests/test_renderers_smoke.py`:
```python
def test_pptx_renderer_produces_valid_deck(tmp_path: Path, one_image: Path):
    from pptx import Presentation
    doc = _make_doc(one_image)
    out = tmp_path / "preview.pptx"
    RENDERERS["pptx"]().render(doc, out)
    assert out.exists() and out.stat().st_size > 10_000

    prs = Presentation(str(out))
    n = len(prs.slides)
    # Minimum: title + outline + at least one content + closing = 4
    assert n >= 4
    # First slide is the title
    title_shape = prs.slides[0].shapes.title
    assert title_shape is not None
    assert "Smoke Test Paper" in title_shape.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_pptx_renderer_produces_valid_deck -v`
Expected: `KeyError: 'pptx'`.

- [ ] **Step 3: Implement PptxRenderer**

Create `stages/s09_render/renderers/pptx.py`:
```python
"""Render a SlideDeck to .pptx via python-pptx.

Layout choices: use built-in Title Slide, Title and Content, and Blank layouts
from the default template (avoids shipping a custom .pptx master)."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pptx import Presentation
from pptx.util import Inches, Pt

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner


class PptxRenderer(Renderer):
    extension: ClassVar[str] = "pptx"

    def __init__(self, summaries: dict | None = None):
        self.summaries = summaries

    def render(self, doc: Document, out_path: Path) -> None:
        deck = SlidePlanner(lang=doc.lang).plan(doc, self.summaries)
        prs = Presentation()
        for slide in deck.slides:
            self._render_slide(prs, slide)
        prs.save(str(out_path))

    # ---------- per-kind layout dispatch ----------

    def _render_slide(self, prs: Presentation, slide: Slide) -> None:
        if slide.kind == "title":
            self._layout_title(prs, slide)
        elif slide.kind == "outline":
            self._layout_bullets(prs, slide)
        elif slide.kind == "divider":
            self._layout_title(prs, slide)
        elif slide.kind == "bullets":
            self._layout_bullets(prs, slide)
        elif slide.kind == "figure":
            self._layout_figure(prs, slide)
        elif slide.kind == "closing":
            self._layout_bullets(prs, slide)
        else:
            self._layout_bullets(prs, slide)

    # ---------- layouts ----------

    def _layout_title(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[0])  # Title Slide
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        self._attach_notes(s, slide.notes)

    def _layout_bullets(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        body = None
        for shape in s.placeholders:
            if shape.placeholder_format.idx == 1:
                body = shape
                break
        if body is not None and slide.bullets:
            tf = body.text_frame
            tf.text = slide.bullets[0]
            for bullet in slide.bullets[1:]:
                p = tf.add_paragraph()
                p.text = bullet
        self._attach_notes(s, slide.notes)

    def _layout_figure(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        # Place the first image (multi-panel: just use the first, keeping it simple)
        for img_path in slide.image_paths:
            if not img_path.exists():
                continue
            s.shapes.add_picture(
                str(img_path),
                left=Inches(1.0), top=Inches(1.5),
                width=Inches(8.0),
            )
            break
        if slide.deep_observation:
            tb = s.shapes.add_textbox(
                left=Inches(0.5), top=Inches(6.5),
                width=Inches(9.0), height=Inches(0.7),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            run = tf.paragraphs[0].add_run()
            run.text = slide.deep_observation
            run.font.size = Pt(12)
        self._attach_notes(s, slide.notes)

    @staticmethod
    def _attach_notes(s, notes: str) -> None:
        if not notes:
            return
        s.notes_slide.notes_text_frame.text = notes


RENDERERS["pptx"] = PptxRenderer
```

Edit `stages/s09_render/runner.py` to import the new renderer:
```python
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401
import stages.s09_render.renderers.pdf   # noqa: F401
import stages.s09_render.renderers.pptx  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_renderers_smoke.py::test_pptx_renderer_produces_valid_deck -v`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add stages/s09_render/renderers/pptx.py stages/s09_render/tests/test_renderers_smoke.py stages/s09_render/runner.py
git commit -m "feat(s09_render): add PptxRenderer (SlideDeck → .pptx via python-pptx)"
```

### Task M4.5 — Wire `PptxSummarizer` into the runner

**Files:**
- Modify: `stages/s09_render/runner.py`

- [ ] **Step 1: Add summarizer + pptx wiring to the runner**

Edit `stages/s09_render/runner.py`. Replace the body of `run()` to handle the new summarizer/pptx flow. The full updated file:
```python
"""Stage 09: build the Document model and render to one or more formats."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from stages._common import dump_yaml, load_yaml, mark_done
from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.renderers import RENDERERS

# Renderer registration side-effects:
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401
import stages.s09_render.renderers.pdf   # noqa: F401
import stages.s09_render.renderers.pptx  # noqa: F401


BUNDLE_README = """\
# mypaper bundle

Drop this folder's contents into mypaper/ to render the styled thesis:

    cp -r chapters/* /path/to/mypaper/chapters/
    cp -r figures/*  /path/to/mypaper/figures/
    cd /path/to/mypaper && uv run python scripts/build.py

The README of mypaper has the full template-swap instructions.
"""

DEFAULT_FORMATS = ("docx", "pdf", "html")


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview", lang: str = "zh",
        formats: Iterable[str] | None = None,
        pptx_bullets: str = "llm") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_md = _read_chapters(Path(compose_dir))
    fig_notes = _read_fig_notes(Path(fig_notes_dir))
    doc = DocumentBuilder(lang=lang, paper_title=paper_title).build(chapters_md, fig_notes)

    requested = list(formats) if formats is not None else list(DEFAULT_FORMATS)
    summaries = _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir)

    results: dict[str, str] = {}
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        if fmt == "pptx":
            renderer = RENDERERS[fmt](summaries=summaries)
        else:
            renderer = RENDERERS[fmt]()
        renderer.render(doc, out_path)
        results[fmt] = str(out_path)

    bundle = _write_bundle(Path(compose_dir), fig_notes, out_dir)
    pptx_state = _pptx_state(summaries, requested, pptx_bullets)

    mark_done(out_dir, {
        "formats": results,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
        "pptx_summarizer": pptx_state,
    })
    return {"preview_files": results, "bundle": str(bundle),
            "pptx_summarizer": pptx_state}


def _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir):
    if "pptx" not in requested or pptx_bullets != "llm":
        return None
    from llm.client import LLM
    from stages.s09_render.pptx_summarizer import PptxSummarizer
    llm = LLM("text")
    summarizer = PptxSummarizer(llm=llm, cache_dir=out_dir / "llm_cache", lang=doc.lang)
    return summarizer.summarize(doc)


def _pptx_state(summaries, requested, pptx_bullets) -> str:
    if "pptx" not in requested:
        return "not_requested"
    if pptx_bullets != "llm":
        return "rule"
    return "ok" if summaries is not None else "degraded"


def _read_chapters(compose_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted((compose_dir / "chapters").glob("*.md"))}


def _read_fig_notes(fig_notes_dir: Path) -> list[dict]:
    path = fig_notes_dir / "fig_notes.yaml"
    return load_yaml(path) or []


def _write_bundle(compose_dir: Path, fig_notes: list[dict], out_dir: Path) -> Path:
    bundle = out_dir / "mypaper_bundle"
    (bundle / "chapters").mkdir(parents=True, exist_ok=True)
    (bundle / "figures").mkdir(exist_ok=True)
    for stale in (bundle / "chapters").glob("*.md"):
        stale.unlink()
    for stale in (bundle / "figures").iterdir():
        if stale.is_file():
            stale.unlink()
    for md in (compose_dir / "chapters").glob("*.md"):
        shutil.copy2(md, bundle / "chapters" / md.name)
    for note in fig_notes:
        paths = list(note.get("image_paths") or [])
        if note.get("image_abs_path"):
            paths.append(note["image_abs_path"])
        for p in paths:
            ap = Path(p)
            if ap.exists():
                shutil.copy2(ap, bundle / "figures" / ap.name)
    (bundle / "README.md").write_text(BUNDLE_README, encoding="utf-8")
    return bundle
```

- [ ] **Step 2: Run the full s09 suite — legacy tests should still pass under the new default formats**

The existing `test_runner.py` tests don't pass `formats=`, so they'll hit `DEFAULT_FORMATS = ("docx", "pdf", "html")`. That means `preview.pdf` and `preview.html` will also be generated. Adjust the legacy assertions ONLY if they explicitly check that no other files exist — they don't (they only assert `preview.docx` and bundle contents). Run:
```bash
pytest stages/s09_render/ -v
```
Expected: all green. If a legacy test fails because weasyprint is missing in CI, install per Task M3.1.

- [ ] **Step 3: Commit**

```bash
git add stages/s09_render/runner.py
git commit -m "feat(s09_render): wire PptxSummarizer + multi-format renderer dispatch into runner"
```

### Task M4.6 — Tag M4

- [ ] **Step 1: Tag**

```bash
git tag m4-pptx-added
```

---

# Milestone M5 — Error handling, CLI flags, Docker, README

**Goal:** Make the runner survive single-renderer failures (write warning + done.yaml.partial=true), expose `--formats` / `--pptx-bullets` / `--retry-failed` on the CLI, add system libs to the Dockerfile, and update README.

### Task M5.1 — Soft-failure handling in the runner

**Files:**
- Modify: `stages/s09_render/runner.py`
- Create: `stages/s09_render/tests/test_partial_failure.py`

- [ ] **Step 1: Write failing test**

Create `stages/s09_render/tests/test_partial_failure.py`:
```python
from pathlib import Path
from unittest.mock import patch

import yaml
from PIL import Image

from stages.s09_render.runner import run


def _seed(compose: Path, fig_dir: Path):
    (compose / "chapters").mkdir(parents=True)
    (compose / "chapters" / "01.md").write_text("# C\n\nbody\n", encoding="utf-8")
    fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text("[]", encoding="utf-8")


def test_one_format_failure_does_not_block_others(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)

    # Make PdfRenderer.render raise, leave docx/html intact.
    with patch("stages.s09_render.renderers.pdf.PdfRenderer.render",
               side_effect=RuntimeError("pdf broken")):
        result = run(
            compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en",
            formats=["docx", "pdf", "html"],
        )

    assert (out_dir / "preview.docx").exists()
    assert (out_dir / "preview.html").exists()
    assert not (out_dir / "preview.pdf").exists()

    done = yaml.safe_load((out_dir / "done.yaml").read_text(encoding="utf-8"))
    assert done["partial"] is True
    assert "error" in done["formats"]["pdf"]
    assert done["formats"]["docx"].endswith("preview.docx")
    assert done["formats"]["html"].endswith("preview.html")
    assert result["partial"] is True


def test_all_formats_succeed_means_partial_is_false(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)
    run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
        paper_title="t", lang="en", formats=["docx", "html"])
    done = yaml.safe_load((out_dir / "done.yaml").read_text(encoding="utf-8"))
    assert done["partial"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest stages/s09_render/tests/test_partial_failure.py -v`
Expected: failures — runner does not currently catch per-format exceptions or write `partial`.

- [ ] **Step 3: Update the runner with try/except per format + partial flag**

Edit `stages/s09_render/runner.py`. Replace the format-loop section in `run()` with:
```python
    results: dict[str, object] = {}
    partial = False
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        try:
            if fmt == "pptx":
                renderer = RENDERERS[fmt](summaries=summaries)
            else:
                renderer = RENDERERS[fmt]()
            renderer.render(doc, out_path)
            results[fmt] = str(out_path)
        except Exception as exc:
            partial = True
            results[fmt] = {"error": repr(exc)}
            print(f"[s09_render] WARNING: {fmt} render failed: {exc}. "
                  f"Other formats continue.", flush=True)
```

Also update the `mark_done(...)` call and `return` to include `partial`:
```python
    mark_done(out_dir, {
        "formats": results,
        "partial": partial,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
        "pptx_summarizer": pptx_state,
    })
    return {
        "preview_files": results,
        "bundle": str(bundle),
        "pptx_summarizer": pptx_state,
        "partial": partial,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_partial_failure.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full s09 suite**

Run: `pytest stages/s09_render/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add stages/s09_render/runner.py stages/s09_render/tests/test_partial_failure.py
git commit -m "feat(s09_render): per-format soft failure with done.yaml.partial + stderr warning"
```

### Task M5.2 — Cache reuse integration test

**Files:**
- Create: `stages/s09_render/tests/test_cache_reuse.py`

- [ ] **Step 1: Write the test**

Create `stages/s09_render/tests/test_cache_reuse.py`:
```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from stages.s09_render.runner import run


def _seed(compose: Path, fig_dir: Path):
    (compose / "chapters").mkdir(parents=True)
    (compose / "chapters" / "01.md").write_text(
        "# Intro\n\nfirst para\n\nsecond para\n", encoding="utf-8")
    fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text("[]", encoding="utf-8")


def test_second_run_with_same_input_makes_zero_llm_calls(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content=json.dumps({"bullets": ["a", "b"], "figure_one_liners": {}}),
        model="fake", usage={}, latency_ms=1.0,
    )

    with patch("llm.client.LLM", return_value=fake_llm):
        run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en", formats=["pptx"], pptx_bullets="llm")
        first_calls = fake_llm.chat.call_count
        assert first_calls >= 1

        run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en", formats=["pptx"], pptx_bullets="llm")
        second_calls = fake_llm.chat.call_count
        assert second_calls == first_calls, \
            f"cache should have prevented new LLM calls (first={first_calls}, second={second_calls})"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest stages/s09_render/tests/test_cache_reuse.py -v`
Expected: PASSED on the first try (we already wrote the cache code in M4.3).

- [ ] **Step 3: Commit**

```bash
git add stages/s09_render/tests/test_cache_reuse.py
git commit -m "test(s09_render): integration test asserting LLM cache reuse across runs"
```

### Task M5.3 — Add CLI flags `--formats`, `--pptx-bullets`, `--retry-failed`

**Files:**
- Modify: `cli.py`
- Modify: `tests/test_cli.py` (extend coverage)

- [ ] **Step 1: Write failing test**

Append to `tests/test_cli.py` (file already exists; add a new test function at the bottom):
```python
def test_cli_passes_formats_to_s09(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PADDLEOCR_TOKEN", "fake")
    monkeypatch.setenv("LLM_VISION_API_KEY", "fake")
    monkeypatch.setenv("LLM_TEXT_API_KEY", "fake")

    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    tpl = tmp_path / "t.docx"
    from docx import Document as DocxDocument
    DocxDocument().save(tpl)

    captured: dict = {}

    def mk_runner(name):
        def fake_run(**kwargs):
            outd = kwargs["out_dir"]; outd.mkdir(parents=True, exist_ok=True)
            (outd / "done.yaml").write_text("ok\n", encoding="utf-8")
            if name == "stages.s09_render.runner.run":
                captured.update(kwargs)
            return {"name": name}
        return fake_run

    targets = [f"stages.{s}.runner.run" for s in [
        "s01_ocr", "s02_clean", "s03_chapter", "s04_figures", "s05_template",
        "s06_context", "s07_figure_analyze", "s08_section_compose", "s09_render",
    ]]
    patches = [patch(t, mk_runner(t)) for t in targets]
    for pp in patches: pp.start()
    try:
        from cli import main
        rc = main([
            "run", "--pdf", str(pdf), "--template", str(tpl),
            "--runs-dir", str(tmp_path / "runs"), "--paper-id", "p",
            "--formats", "docx,pptx", "--pptx-bullets", "rule",
        ])
    finally:
        for pp in patches: pp.stop()

    assert rc == 0
    assert captured.get("formats") == ["docx", "pptx"]
    assert captured.get("pptx_bullets") == "rule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cli_passes_formats_to_s09 -v`
Expected: argparse error or `KeyError`, because `--formats` flag does not exist yet.

- [ ] **Step 3: Add the flags + threading to cli.py**

Edit `cli.py`. In the `main()` function, after the existing `r.add_argument("--lang", ...)` line, add three new flags:
```python
    r.add_argument("--formats", default=None,
                   help="Comma-separated subset of docx,pdf,html,pptx "
                        "(default: docx,pdf,html — PPT is opt-in because it uses LLM)")
    r.add_argument("--pptx-bullets", choices=("llm", "rule"), default="llm",
                   help="How PPT bullets are generated (llm = quality, rule = offline)")
    r.add_argument("--retry-failed", action="store_true",
                   help="In --only mode, re-run only the formats marked partial in done.yaml")
```

In `_run_one()`, find the branch `elif name == "s09_render":` and replace the call with:
```python
    elif name == "s09_render":
        formats = _parse_formats(args.formats)
        _s09.run(
            compose_dir=stage_dir(run_root, paper_id, "s08_section_compose"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            out_dir=out,
            paper_title=args.paper_id or Path(args.pdf).stem,
            lang=args.lang,
            formats=formats,
            pptx_bullets=args.pptx_bullets,
        )
```

Add this helper at module scope (right above `_run_one`):
```python
def _parse_formats(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_cli_passes_formats_to_s09 -v`
Expected: PASSED.

- [ ] **Step 5: Make sure the original cli test still passes**

Run: `pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat(cli): add --formats / --pptx-bullets / --retry-failed flags for s09_render"
```

### Task M5.4 — Add system libs to Dockerfile

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Read the current Dockerfile**

```bash
cat /Users/zhangjiedong/codeFiles/article/paper2md/Dockerfile
```

- [ ] **Step 2: Add weasyprint system deps after any existing apt-get block**

Edit `Dockerfile`. Add this RUN before the line that installs Python packages:
```dockerfile
# System libs required by weasyprint (HTML→PDF rendering).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 \
        libcairo2 libgdk-pixbuf-2.0-0 \
        libffi8 \
 && rm -rf /var/lib/apt/lists/*
```

(If the existing Dockerfile already has `apt-get install` for other reasons, merge the package list in and keep a single layer.)

- [ ] **Step 3: Build the image to verify**

Run: `docker build -t paper2md:m5-check .`
Expected: build completes; if `libffi8` is unavailable on the chosen base image, fall back to `libffi-dev`. Note any change in the commit message.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "build(docker): add Pango/Cairo/gdk-pixbuf for weasyprint inside container"
```

### Task M5.5 — Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append the Output Formats section to README**

Edit `README.md`. Add a new top-level section just after the existing Quickstart (or wherever output is documented):
```markdown
## Output Formats

`s09_render` can produce four formats, controlled by `--formats` (comma-separated):

| Format | Default | Notes |
|---|---|---|
| `docx` | ✓ | Self-contained Word file (Times New Roman + 宋体 for Chinese) |
| `pdf`  | ✓ | Same content as docx, rendered via WeasyPrint from the shared HTML template |
| `html` | ✓ | Single self-contained HTML file (images embedded as base64) |
| `pptx` |   | Opt-in (uses LLM to compress bullets/figure observations) |

Examples:

```bash
paper2md run --pdf paper.pdf --template tpl.docx                       # docx + pdf + html
paper2md run --pdf paper.pdf --template tpl.docx --formats docx,pdf,html,pptx
paper2md run --pdf paper.pdf --template tpl.docx --formats pptx --pptx-bullets rule
```

### Dependencies

**Recommended path: Docker** (no host-side system libs):

```bash
docker compose run --rm paper2md run --pdf paper.pdf --template tpl.docx
```

**Bare-metal path** (advanced; requires system libs for WeasyPrint):

- macOS: `brew install pango gdk-pixbuf libffi cairo`
- Debian/Ubuntu: `apt install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8`
- Windows: WeasyPrint requires extra GTK runtime; we recommend using the Docker image on Windows. `docx`/`html`/`pptx` work without GTK.

### Soft failure & retry

If one format fails (e.g. WeasyPrint trips on a malformed image), the other formats still complete. The failed format is recorded in `done.yaml.formats[<fmt>] = {error: ...}` and `done.yaml.partial = true`. Re-run only the failed formats with:

```bash
paper2md run --pdf paper.pdf --template tpl.docx --only s09_render --retry-failed
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): document new --formats, Docker path, and soft-failure semantics"
```

### Task M5.6 — Implement `--retry-failed`

**Files:**
- Modify: `cli.py`
- Create: `tests/test_cli_retry_failed.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_cli_retry_failed.py`:
```python
from pathlib import Path
from unittest.mock import patch

import yaml

from cli import main


def test_retry_failed_only_reruns_formats_marked_in_done_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PADDLEOCR_TOKEN", "fake")
    monkeypatch.setenv("LLM_VISION_API_KEY", "fake")
    monkeypatch.setenv("LLM_TEXT_API_KEY", "fake")

    runs = tmp_path / "runs"
    paper_dir = runs / "p" / "s09_render"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("done.yaml").write_text(
        yaml.safe_dump({
            "partial": True,
            "formats": {
                "docx": "/x/preview.docx",
                "pdf":  {"error": "weasyprint failed"},
                "html": "/x/preview.html",
            },
        }), encoding="utf-8",
    )

    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    tpl = tmp_path / "t.docx"
    from docx import Document as DocxDocument
    DocxDocument().save(tpl)

    captured: dict = {}

    def fake_s09_run(**kwargs):
        captured.update(kwargs)
        (kwargs["out_dir"] / "done.yaml").write_text("ok\n", encoding="utf-8")
        return {}

    with patch("stages.s09_render.runner.run", side_effect=fake_s09_run):
        rc = main([
            "run", "--pdf", str(pdf), "--template", str(tpl),
            "--runs-dir", str(runs), "--paper-id", "p",
            "--only", "s09_render", "--retry-failed",
        ])

    assert rc == 0
    # Only the failed format(s) should have been requested
    assert captured.get("formats") == ["pdf"]
```

- [ ] **Step 2: Add `--only` and retry-failed handling to cli.py**

Examine the existing `cli.py` to check whether `--only` is already supported. If not, add it next to `--force`:
```python
    r.add_argument("--only", default=None,
                   help="Run only this single stage (e.g. s09_render) instead of all 9")
```

In `main()`, replace `for name in STAGE_ORDER:` with:
```python
    stage_list = [args.only] if args.only else STAGE_ORDER
    for name in stage_list:
        _run_one(args, name, run_root, paper_id)
```

In `_run_one()` for `s09_render`, expand the formats resolution to honor `--retry-failed`:
```python
    elif name == "s09_render":
        formats = _resolve_formats_for_s09(args, out)
        _s09.run(
            compose_dir=stage_dir(run_root, paper_id, "s08_section_compose"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            out_dir=out,
            paper_title=args.paper_id or Path(args.pdf).stem,
            lang=args.lang,
            formats=formats,
            pptx_bullets=args.pptx_bullets,
        )
```

Add helper at module scope (next to `_parse_formats`):
```python
def _resolve_formats_for_s09(args, out: Path) -> list[str] | None:
    if args.retry_failed:
        done_path = out / "done.yaml"
        if done_path.exists():
            import yaml as _y
            done = _y.safe_load(done_path.read_text(encoding="utf-8")) or {}
            failed = [k for k, v in (done.get("formats") or {}).items()
                      if isinstance(v, dict) and "error" in v]
            if failed:
                return failed
    return _parse_formats(args.formats)
```

Also remove the `is_done()` skip when `--retry-failed` is set, so the s09 stage actually re-runs even though done.yaml exists. In `_run_one()` near the top:
```python
    if is_done(out) and not args.force and not getattr(args, "retry_failed", False):
        print(f"[skip] {name} (already done)")
        return
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_cli_retry_failed.py -v`
Expected: PASSED.

- [ ] **Step 4: Ensure prior cli tests still pass**

Run: `pytest tests/test_cli.py tests/test_cli_retry_failed.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli_retry_failed.py
git commit -m "feat(cli): --only and --retry-failed honor done.yaml.formats[*].error"
```

### Task M5.7 — Full suite pass + tag M5

- [ ] **Step 1: Run everything**

Run: `cd /Users/zhangjiedong/codeFiles/article/paper2md && pytest -q`
Expected: all green (previous count + ~30 new tests added across milestones).

- [ ] **Step 2: Run a real smoke render against the hu2025 fixture (optional but recommended)**

Run:
```bash
uv run python -c "
from pathlib import Path
from stages.s09_render.runner import run
result = run(
    compose_dir=Path('runs/hu2025/s08_section_compose'),
    fig_notes_dir=Path('runs/hu2025/s07_figure_analyze'),
    out_dir=Path('/tmp/p2m_smoke'),
    paper_title='Hu 2025 smoke',
    lang='en',
    formats=['docx', 'pdf', 'html'],   # pptx skipped to avoid live LLM
)
print(result)
"
ls -la /tmp/p2m_smoke/
```
Expected: `/tmp/p2m_smoke/preview.docx`, `preview.pdf`, `preview.html`, `mypaper_bundle/`, `done.yaml` all exist; `done.yaml.partial=false`.

- [ ] **Step 3: Tag**

```bash
git tag m5-complete
```

- [ ] **Step 4: Push the branch**

```bash
git push -u origin main
git push --tags
```

---

## Plan self-review checklist (already applied)

- **Spec coverage:** Every section of the spec (1–14) maps to one or more tasks: §3 architecture → M2.4 + M3.2 + M4.4; §4 model → M2.2; §5 classes → M2.3, M2.5, M3.3, M3.4, M4.2, M4.3, M4.4; §6 CLI → M5.3, M5.6; §7 errors → M5.1; §8 deps → M3.1, M4.1, M5.4; §9 _common → M1.1–M1.5; §10 tests → covered per-task + M5.7; §11 back-compat → guaranteed by `stages/_common/__init__.py` re-exports + default `formats=["docx"]` in M2 and `("docx","pdf","html")` in M4.5; §12 milestones → mirrored 1:1.
- **No placeholders:** Every code block is complete; no "TODO/TBD/fill in".
- **Type consistency:** `DocumentBuilder.build()` always takes `(chapters_md: dict[str, str], fig_notes: list[dict])` — same in test stubs and impl. `PptxSummarizer.summarize()` returns `dict | None` everywhere. `RENDERERS` is `dict[str, type[Renderer]]` consistent across all renderer modules.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-render-redesign-implementation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for this plan because milestones are well-isolated.

2. **Inline Execution** — I execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
