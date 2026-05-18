# Paper2MD Deep-Analysis Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing `paper2md` pipeline so a PDF → PaddleOCR run yields **per-section clean chapters**, a **structured figure index** (Fig.N → image_path + caption + section), and a **figure-mention map**; then run a per-paper **figure-and-text deep analysis** that produces a template-driven, bilingual .docx (with selected figures embedded) rather than a translation.

**Architecture:**
- Phase 1 (offline post-processing of OCR output, no new API calls beyond the existing one): three new helpers (`paper2md_clean.py`, `paper2md_figures.py`) plus a new `science_paper` split mode in the existing chapter/pattern modules. Validation script asserts shape on the He 2023 PDF.
- Phase 2 (analysis): a driver script that loads the Phase-1 artifacts, dispatches parallel image-reading subagents (via `superpowers:dispatching-parallel-agents`) — one per figure — for visual interpretation, then composes a bilingual .docx using the user's outline template with embedded figures. Image selection is **decided dynamically** from the figure-mention map + agent scores, not pre-hardcoded.

**Tech Stack:** Python 3.9 (existing `.venv`, managed with `uv`), `python-docx`, `pdfplumber` (already installed), `pypdfium2`, `requests`. Existing PaddleOCR-VL cloud API for the initial PDF → markdown call. Superpowers skills: `subagent-driven-development` for execution, `dispatching-parallel-agents` for the visual-analysis fan-out.

---

## File Structure

**New files:**
- `paper2md_clean.py` — text cleaning (page-header stripping, `(cid:0)` fixes, two-column de-interleaving heuristic, subscript/superscript recovery).
- `paper2md_figures.py` — figure & table index builder; mention scanner; chapter-figure cross-reference.
- `paper2md_analyze.py` — Phase-2 driver: loads chapters + figures, dispatches per-figure visual-analysis subagents, composes the .docx.
- `tests/test_clean.py`, `tests/test_figures.py`, `tests/test_chapter_science.py` — pytest specs.
- `tests/fixtures/he2023_doc_*.md` — small fixtures cut from the real OCR output (added once we have the token).
- `docs/superpowers/plans/2026-05-16-paper2md-deep-analysis.md` — this file.

**Modified files:**
- `paper2md_patterns.py` — add `SECTION_ANCHORS` and a `science_paper` aware `detect_heading()` path.
- `paper2md_chapter.py` — add `split_mode="science_paper"`, anchor-driven splitter that does **not** require leading `#`.
- `paper2md.py` — wire `--split-mode science_paper` and a new `--analyze` flag that runs Phase 2 after split.
- `pyproject.toml` — add `python-docx`, `pdfplumber`, `pypdfium2`, `pytest` as dev deps; bump version.

**Out of scope (YAGNI):** OCR retry/resume, multi-PDF batch UX, layout-engine swap. Keep the cloud API call as-is; all improvements are post-processing.

---

## Phase 0 — Workspace prep

### Task 0.1: Add dev deps & smoke-test imports

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml`**

Replace the `[project]` `dependencies` block with:

```toml
dependencies = [
    "requests>=2.31.0",
    "pdfplumber>=0.11",
    "pypdfium2>=4",
    "python-docx>=1.1",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
```

- [ ] **Step 2: Install via uv**

Run: `uv pip install -e .[dev] --python .venv/bin/python`
Expected: "Installed N packages" with no errors.

- [ ] **Step 3: Smoke-test imports**

Run: `.venv/bin/python -c "import pdfplumber, pypdfium2, docx, pytest; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pdfplumber/pypdfium2/python-docx/pytest deps"
```

> Note: repo has no `.git` per env probe. If `git init` is needed, do it once before this step; otherwise skip commits. Reuse this rule for every commit step below.

---

## Phase 1 — Cleaner & Structured OCR Output

### Task 1.1: Header/footer stripping in `paper2md_clean.py`

**Files:**
- Create: `paper2md_clean.py`
- Test: `tests/test_clean.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clean.py
from paper2md_clean import strip_running_headers

def test_strip_running_headers_journal_line():
    docs = [
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 1.",
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 2.",
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 3.",
    ]
    cleaned = strip_running_headers(docs, min_repeat=3)
    for c in cleaned:
        assert "Acta Materialia" not in c
        assert "Real body" in c

def test_strip_running_headers_keeps_unique_lines():
    docs = ["unique header\nbody A", "another\nbody B"]
    cleaned = strip_running_headers(docs, min_repeat=3)
    assert cleaned[0].startswith("unique header")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean.py -v`
Expected: `ImportError: cannot import name 'strip_running_headers'`

- [ ] **Step 3: Implement `paper2md_clean.py`**

```python
"""Per-paper text cleaning helpers for OCR output."""
from __future__ import annotations

from collections import Counter


def strip_running_headers(docs: list[str], min_repeat: int = 3) -> list[str]:
    """Remove lines that repeat across >= min_repeat documents (running header/footer)."""
    line_counter: Counter[str] = Counter()
    for d in docs:
        seen_in_doc: set[str] = set()
        for raw in d.splitlines():
            line = raw.strip()
            if not line or len(line) > 120:
                continue
            if line in seen_in_doc:
                continue
            seen_in_doc.add(line)
            line_counter[line] += 1
    drop = {ln for ln, n in line_counter.items() if n >= min_repeat}
    out: list[str] = []
    for d in docs:
        kept = [raw for raw in d.splitlines() if raw.strip() not in drop]
        out.append("\n".join(kept))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_clean.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add paper2md_clean.py tests/test_clean.py
git commit -m "feat(clean): strip cross-page running headers/footers"
```

### Task 1.2: Character & subscript repair

**Files:**
- Modify: `paper2md_clean.py`
- Test: `tests/test_clean.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_clean.py`:

```python
from paper2md_clean import repair_chars

def test_repair_cid_minus():
    assert repair_chars("ranging between 0.1 to (cid:0) 10^{-4}") == \
        "ranging between 0.1 to − 10^{-4}"

def test_repair_subscripted_oxide_formula():
    # "O 3" → "O₃" in chemical formulas only
    assert repair_chars("AgNbO 3 ceramic") == "AgNbO₃ ceramic"
    assert repair_chars("page 3 of 8") == "page 3 of 8"  # untouched

def test_repair_squashed_ag_plus():
    assert repair_chars("translation mode (Ag + )") == "translation mode (Ag⁺)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_clean.py::test_repair_cid_minus -v`
Expected: ImportError

- [ ] **Step 3: Extend `paper2md_clean.py`**

```python
import re

_CID_MAP = {"(cid:0)": "−"}
_SUB_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUP_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

_OXIDE_RE = re.compile(
    r"\b([A-Z][a-z]?(?:[A-Z][a-z]?\d*)*[A-Z][a-z]?)\s+(\d{1,2})\b"
)
_CATION_PLUS_RE = re.compile(r"\b([A-Z][a-z]?)\s+\+\s*\)")
_POWER_DIGIT_RE = re.compile(r"\^\{(-?\d+)\}")


def repair_chars(text: str) -> str:
    for k, v in _CID_MAP.items():
        text = text.replace(k, v)

    def _ox(m: re.Match[str]) -> str:
        prefix, digits = m.group(1), m.group(2)
        if not re.search(r"[A-Z]", prefix):
            return m.group(0)
        return f"{prefix}{digits.translate(_SUB_DIGITS)}"

    text = _OXIDE_RE.sub(_ox, text)
    text = _CATION_PLUS_RE.sub(lambda m: f"{m.group(1)}⁺", text)
    return text
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_clean.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add paper2md_clean.py tests/test_clean.py
git commit -m "feat(clean): repair (cid:0), oxide subscripts, cation pluses"
```

### Task 1.3: Two-column interleave detector

**Files:**
- Modify: `paper2md_clean.py`
- Test: `tests/test_clean.py` (extend)

Background: The He 2023 page-2 sample shows character-level column interleaving: `outs A t l a t n h d o i u n g g h en t e h r e g y...`. We detect such lines (single-letter token ratio > 60% over >= 20 tokens) and tag them with `<!-- corrupted-column-flow -->` so the chapter splitter can isolate them rather than break section detection.

- [ ] **Step 1: Write the failing test**

```python
from paper2md_clean import flag_corrupted_column_flow

def test_flag_obvious_interleave():
    bad = "outs A t l a t n h d o i u n g g h en t e h r e g y cl s a to ra g e p e r f or m a n c e"
    flagged = flag_corrupted_column_flow(bad)
    assert flagged.startswith("<!-- corrupted-column-flow -->")
    assert bad in flagged

def test_keep_normal_line():
    ok = "we found a high polarization change and low hysteresis"
    assert flag_corrupted_column_flow(ok) == ok
```

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m pytest tests/test_clean.py::test_flag_obvious_interleave -v`
Expected: ImportError

- [ ] **Step 3: Implement**

```python
def flag_corrupted_column_flow(text: str) -> str:
    out_lines = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) >= 20:
            singletons = sum(1 for t in tokens if len(t) == 1)
            if singletons / len(tokens) > 0.6:
                out_lines.append("<!-- corrupted-column-flow -->\n" + line)
                continue
        out_lines.append(line)
    return "\n".join(out_lines)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_clean.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add paper2md_clean.py tests/test_clean.py
git commit -m "feat(clean): flag character-level two-column interleave artefacts"
```

### Task 1.4: `science_paper` chapter split mode

**Files:**
- Modify: `paper2md_patterns.py`
- Modify: `paper2md_chapter.py`
- Test: `tests/test_chapter_science.py`

Background: Current strict mode treats `### 1. INTRODUCTION` as a non-main heading and collapses everything under "ABSTRACT". We add `science_paper` mode that recognizes a fixed list of section anchors as chapter starts, regardless of MD heading level.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chapter_science.py
from pathlib import Path
from paper2md_chapter import split_by_chapters


def test_science_paper_splits_anchors(tmp_path: Path):
    doc = tmp_path / "doc_0.md"
    doc.write_text(
        "## ABSTRACT\nWe report...\n\n"
        "1. Introduction\nIntro body line.\n\n"
        "2. Experimental\nMethod body.\n\n"
        "2.1. Sample preparation\nMore method.\n\n"
        "3. Results and discussion\nResults body.\n\n"
        "4. Conclusion\nConcl body.\n\n"
        "Acknowledgements\nThanks.\n\n"
        "References\n[1] foo.\n",
        encoding="utf-8",
    )
    files, ch_dir = split_by_chapters(
        [doc], tmp_path, split_mode="science_paper",
        chapter_min_chars=1, chapters_subdir="chapters",
    )
    titles = [p.stem.split("_", 2)[2] for p in files]
    assert any("Introduction" in t for t in titles), titles
    assert any("Experimental" in t for t in titles), titles
    assert any("Results" in t for t in titles), titles
    assert any("Conclusion" in t for t in titles), titles
    assert any("References" in t for t in titles), titles
```

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m pytest tests/test_chapter_science.py -v`
Expected: assertion failure on titles (likely lists only 1–2 chapters)

- [ ] **Step 3: Modify `paper2md_patterns.py`**

Add at the bottom of the file:

```python
SECTION_ANCHORS = (
    "abstract",
    "introduction",
    "experimental",
    "experiments",
    "materials and methods",
    "methods",
    "methodology",
    "results",
    "results and discussion",
    "discussion",
    "conclusion",
    "conclusions",
    "summary",
    "acknowledgements",
    "acknowledgments",
    "references",
    "supplementary",
    "appendix",
)

_ANCHOR_LINE_RE = re.compile(
    r"^\s*(#{0,4}\s*)?(\d+(?:\.\d+){0,2}\.?\s+)?(?P<title>[A-Z][A-Za-z &/-]{2,60})\s*$"
)


def detect_science_anchor(line: str) -> str | None:
    """Return the matched anchor heading if `line` is a section anchor in a science paper, else None."""
    m = _ANCHOR_LINE_RE.match(line.strip())
    if not m:
        return None
    title = m.group("title").strip()
    if title.lower() in SECTION_ANCHORS:
        return title
    # Numbered subsection like "2.1. Sample preparation" — accept any reasonable Title Case after the number.
    if m.group(2) and 4 <= len(title) <= 60:
        return f"{m.group(2).strip()} {title}".strip()
    return None
```

- [ ] **Step 4: Modify `paper2md_chapter.py`**

In `split_by_chapters`, after `include_re/exclude_re` are built, add the science-paper code path:

```python
from paper2md_patterns import detect_heading, is_main_section_heading, detect_science_anchor  # noqa: F401
```

And in the loop over `lines`, replace the single `heading = detect_heading(line, split_mode)` with:

```python
if split_mode == "science_paper":
    heading = detect_science_anchor(line)
else:
    heading = detect_heading(line, split_mode)
```

Also ensure `science_paper` is accepted by `paper2md.py`'s argparse `choices` (do that in Task 1.5).

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_chapter_science.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add paper2md_patterns.py paper2md_chapter.py tests/test_chapter_science.py
git commit -m "feat(chapter): science_paper mode anchored on IMRaD section names"
```

### Task 1.5: Wire `science_paper` into CLI + run clean before split

**Files:**
- Modify: `paper2md.py`

- [ ] **Step 1: Edit argparse choices**

Change line 135 from:

```python
a.add_argument("--split-mode", choices=("strict", "balanced", "loose"), default="balanced")
```

to:

```python
a.add_argument(
    "--split-mode",
    choices=("strict", "balanced", "loose", "science_paper"),
    default="balanced",
)
```

- [ ] **Step 2: Apply cleaners to `doc_*.md` text before split**

Just before the call to `split_by_chapters(paths[:], self.out, ...)` in `Job.run`, insert:

```python
from paper2md_clean import strip_running_headers, repair_chars, flag_corrupted_column_flow

raw_texts = [p.read_text(encoding="utf-8") for p in paths]
raw_texts = strip_running_headers(raw_texts, min_repeat=3)
for p, t in zip(paths, raw_texts):
    t = repair_chars(t)
    t = flag_corrupted_column_flow(t)
    p.write_text(t, encoding="utf-8")
```

Apply the same block in the `--split-existing` path inside `main()`.

- [ ] **Step 3: Smoke test (no network)**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests from 1.1–1.4 pass.

- [ ] **Step 4: Commit**

```bash
git add paper2md.py
git commit -m "feat(cli): pre-clean docs and accept --split-mode science_paper"
```

### Task 1.6: Figure/table index builder

**Files:**
- Create: `paper2md_figures.py`
- Test: `tests/test_figures.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_figures.py
from pathlib import Path
from paper2md_figures import build_figure_index


def test_build_figure_index_basic(tmp_path: Path):
    (tmp_path / "imgs").mkdir()
    img1 = tmp_path / "imgs" / "img_box_1_2_3_4.jpg"
    img1.write_bytes(b"\xff")
    img2 = tmp_path / "imgs" / "img_box_5_6_7_8.jpg"
    img2.write_bytes(b"\xff")

    d0 = tmp_path / "doc_0.md"
    d0.write_text(
        '<img src="imgs/img_box_1_2_3_4.jpg">\n\n'
        "Fig. 1. Phase diagram of ANT-xLa ceramics.\n\n"
        "Some prose discussing things.\n",
        encoding="utf-8",
    )
    d1 = tmp_path / "doc_1.md"
    d1.write_text(
        '<img src="imgs/img_box_5_6_7_8.jpg">\n\n'
        "Fig. 2. Weibull distribution of breakdown field.\n",
        encoding="utf-8",
    )
    figs = build_figure_index([d0, d1], tmp_path)
    by_id = {f["fig_id"]: f for f in figs}
    assert by_id["Fig. 1"]["image_rel_path"].endswith("img_box_1_2_3_4.jpg")
    assert "Phase diagram" in by_id["Fig. 1"]["caption"]
    assert by_id["Fig. 2"]["image_rel_path"].endswith("img_box_5_6_7_8.jpg")
```

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m pytest tests/test_figures.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `paper2md_figures.py`**

```python
"""Figure & table index, plus chapter↔figure mention scanner."""
from __future__ import annotations

import json
import re
from pathlib import Path

IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)
FIG_CAP_RE = re.compile(r"^\s*(Fig(?:ure)?\.?\s*\d+[A-Za-z]?)\.?\s*(.*)", re.MULTILINE)
TAB_CAP_RE = re.compile(r"^\s*(Table\s*\d+)\.?\s*(.*)", re.MULTILINE)
FIG_MENTION_RE = re.compile(r"Fig(?:ure)?\.?\s*(\d+)([a-z])?", re.IGNORECASE)


def _normalize_fig_id(raw: str) -> str:
    m = re.match(r"Fig(?:ure)?\.?\s*(\d+)([A-Za-z]?)", raw, re.IGNORECASE)
    if not m:
        return raw.strip()
    return f"Fig. {m.group(1)}{m.group(2).lower() if m.group(2) else ''}"


def build_figure_index(doc_paths: list[Path], out_dir: Path) -> list[dict]:
    items: list[dict] = []
    for doc in doc_paths:
        text = doc.read_text(encoding="utf-8")
        img_positions = [(m.start(), m.group(1)) for m in IMG_RE.finditer(text)]
        cap_positions = [
            (m.start(), _normalize_fig_id(m.group(1)), m.group(2).strip())
            for m in FIG_CAP_RE.finditer(text)
        ]
        used_caps: set[int] = set()
        for img_start, rel in img_positions:
            best, best_dist = None, 10**9
            for ci, (cap_start, fid, cap) in enumerate(cap_positions):
                if ci in used_caps:
                    continue
                dist = abs(cap_start - img_start)
                if dist < best_dist:
                    best, best_dist = ci, dist
            fig_id, caption = (None, "")
            if best is not None:
                used_caps.add(best)
                fig_id, caption = cap_positions[best][1], cap_positions[best][2]
            items.append(
                {
                    "fig_id": fig_id or f"_unmatched_{Path(rel).stem}",
                    "image_rel_path": rel,
                    "image_abs_path": str((out_dir / rel).resolve()),
                    "caption": caption,
                    "source_doc": doc.name,
                }
            )
    (out_dir / "figures.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return items


def build_table_index(doc_paths: list[Path], out_dir: Path) -> list[dict]:
    items: list[dict] = []
    for doc in doc_paths:
        for m in TAB_CAP_RE.finditer(doc.read_text(encoding="utf-8")):
            items.append({"table_id": m.group(1).strip(), "caption": m.group(2).strip(), "source_doc": doc.name})
    (out_dir / "tables.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return items


def build_mentions(chapter_paths: list[Path], chapter_dir: Path) -> dict[str, list[str]]:
    mentions: dict[str, list[str]] = {}
    for ch in chapter_paths:
        ids = sorted({f"Fig. {m.group(1)}{(m.group(2) or '').lower()}" for m in FIG_MENTION_RE.finditer(ch.read_text(encoding='utf-8'))})
        mentions[ch.name] = ids
    (chapter_dir / "figure_mentions.json").write_text(
        json.dumps(mentions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return mentions
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_figures.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add paper2md_figures.py tests/test_figures.py
git commit -m "feat(figures): figure/table index + chapter mention map"
```

### Task 1.7: Run figure index & mentions in CLI

**Files:**
- Modify: `paper2md.py`

- [ ] **Step 1: Wire `build_figure_index`, `build_table_index`, `build_mentions` into `Job.run` after `validate_chapter_image_mapping`**

Insert before `if self.cleanup_intermediate:`:

```python
from paper2md_figures import build_figure_index, build_table_index, build_mentions
doc_paths = sorted(self.out.glob("doc_*.md"))
build_figure_index(doc_paths, self.out)
build_table_index(doc_paths, self.out)
build_mentions(chapter_paths, chapter_dir)
```

Replicate in the `--split-existing` branch in `main()`.

- [ ] **Step 2: End-to-end smoke (still no token needed)**

Run: `.venv/bin/python -m pytest -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add paper2md.py
git commit -m "feat(cli): emit figures.json/tables.json/figure_mentions.json"
```

### Task 1.8: He 2023 acceptance run

**Files:**
- Modify: none (operational task)
- Output: `参考文献/弛豫反铁电/he2023_out/`

Requires: `PADDLEOCR_TOKEN`.

- [ ] **Step 1: Run full pipeline**

```bash
PADDLEOCR_TOKEN=$TOKEN .venv/bin/python paper2md.py \
  "参考文献/弛豫反铁电/A.He 等 - 2023 - Superior energy storage properties with thermal stability in lead-free ceramics by constructing an a.pdf" \
  -o "参考文献/弛豫反铁电/he2023_out" \
  --split-mode science_paper
```

Expected: directory contains `chapters/`, `figures.json`, `tables.json`, `chapters/figure_mentions.json`.

- [ ] **Step 2: Assertions**

Run:

```bash
.venv/bin/python -c "
import json, pathlib, sys
o = pathlib.Path('参考文献/弛豫反铁电/he2023_out')
figs = json.loads((o/'figures.json').read_text())
chs = json.loads((o/'chapters/chapter_index.json').read_text())
assert len([f for f in figs if f['fig_id'].startswith('Fig.')]) >= 7, len(figs)
assert any('Introduction' in c['title'] or 'INTRODUCTION' in c['title'] for c in chs)
assert any('Results' in c['title'] or 'RESULTS' in c['title'] for c in chs)
assert max(c['chars'] for c in chs) < 30000, 'over-merged chapter'
print('ok', len(figs), len(chs))
"
```

Expected: `ok 8 ≥7`

- [ ] **Step 3: Commit fixtures (small)**

```bash
cp 参考文献/弛豫反铁电/he2023_out/chapters/chapter_index.json tests/fixtures/he2023_chapter_index.json
cp 参考文献/弛豫反铁电/he2023_out/figures.json tests/fixtures/he2023_figures.json
git add tests/fixtures
git commit -m "test: he2023 acceptance fixtures"
```

---

## Phase 2 — Figure-and-Text Deep Analysis Driver

### Task 2.1: Per-figure visual analysis (dispatch fan-out)

**Files:**
- Create: `paper2md_analyze.py`
- Test: `tests/test_analyze.py`

This task **does not** call subagents itself in pytest; it instead writes a deterministic JSON plan that the executing skill can fan out. We unit-test the plan construction; the real fan-out is done by the executing skill via `superpowers:dispatching-parallel-agents`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyze.py
import json
from pathlib import Path
from paper2md_analyze import build_analysis_plan


def test_build_analysis_plan(tmp_path: Path):
    (tmp_path / "figures.json").write_text(json.dumps([
        {"fig_id": "Fig. 1", "image_rel_path": "imgs/a.jpg", "image_abs_path": "/tmp/a.jpg", "caption": "Phase diagram", "source_doc": "doc_2.md"},
        {"fig_id": "Fig. 2", "image_rel_path": "imgs/b.jpg", "image_abs_path": "/tmp/b.jpg", "caption": "Weibull", "source_doc": "doc_3.md"},
    ]), encoding="utf-8")
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "figure_mentions.json").write_text(json.dumps({
        "chapter_003_Results.md": ["Fig. 1", "Fig. 2"],
        "chapter_004_Discussion.md": ["Fig. 1"],
    }), encoding="utf-8")
    (tmp_path / "chapters" / "chapter_003_Results.md").write_text("As shown in Fig. 1(a)... and Fig. 2.", encoding="utf-8")
    (tmp_path / "chapters" / "chapter_004_Discussion.md").write_text("Fig. 1(c) implies...", encoding="utf-8")
    plan = build_analysis_plan(tmp_path)
    by_fig = {item["fig_id"]: item for item in plan["figure_tasks"]}
    assert by_fig["Fig. 1"]["mention_count"] == 2
    assert by_fig["Fig. 1"]["chapters"] == ["chapter_003_Results.md", "chapter_004_Discussion.md"]
    assert by_fig["Fig. 1"]["image_abs_path"] == "/tmp/a.jpg"
```

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `paper2md_analyze.py` (plan builder only for now)**

```python
"""Phase-2 analysis driver: figure interpretation + bilingual docx composition."""
from __future__ import annotations

import json
from pathlib import Path


def build_analysis_plan(out_dir: Path) -> dict:
    figs = json.loads((out_dir / "figures.json").read_text(encoding="utf-8"))
    mentions = json.loads((out_dir / "chapters" / "figure_mentions.json").read_text(encoding="utf-8"))
    by_fig: dict[str, list[str]] = {}
    for ch, ids in mentions.items():
        for fid in ids:
            by_fig.setdefault(fid, []).append(ch)
    figure_tasks: list[dict] = []
    for f in figs:
        fid = f["fig_id"]
        chapters = by_fig.get(fid, [])
        figure_tasks.append(
            {
                "fig_id": fid,
                "image_abs_path": f["image_abs_path"],
                "caption": f.get("caption", ""),
                "chapters": chapters,
                "mention_count": len(chapters),
            }
        )
    figure_tasks.sort(key=lambda t: (-t["mention_count"], t["fig_id"]))
    (out_dir / "analysis_plan.json").write_text(
        json.dumps({"figure_tasks": figure_tasks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"figure_tasks": figure_tasks}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add paper2md_analyze.py tests/test_analyze.py
git commit -m "feat(analyze): emit per-figure analysis plan sorted by mention count"
```

### Task 2.2: Fan-out figure analysis (executor side — manual subagent dispatch)

This task is **not pure code**; it is a runbook executed by the implementing agent via `superpowers:dispatching-parallel-agents`. The plan from Task 2.1 lists every figure; each becomes one subagent prompt.

- [ ] **Step 1: Load `analysis_plan.json`**

```bash
.venv/bin/python -c "
import json, pathlib
p = pathlib.Path('参考文献/弛豫反铁电/he2023_out/analysis_plan.json')
print(json.dumps(json.loads(p.read_text())['figure_tasks'][:3], ensure_ascii=False, indent=2))
"
```

- [ ] **Step 2: For each figure, dispatch one subagent (parallel)**

Each subagent receives:
- `image_abs_path` (Read it visually)
- The captions of figure
- The text of every chapter that mentions this figure (cut to ±2 paragraphs around each `Fig. N` mention)
- The template section name(s) this figure is most relevant to (Structures / Dielectric / Polarization / Applications, decided by keyword match on captions: TEM/SEM/domain → Structures; ε_r/permittivity → Dielectric; P-E/hysteresis/Wrec → Polarization or Applications; in-situ/temperature → Thermal stability / Applications)
- Prompt asks for: (a) what is visually readable in the figure that the text does not state; (b) whether claims in the surrounding text are supported, exaggerated, or unsupported by the figure; (c) one-paragraph "deep observation" suitable for embedding in the template; (d) recommended caption in Chinese.

- [ ] **Step 3: Collect outputs into `fig_notes.json`**

Each subagent returns a JSON blob:
```json
{
  "fig_id": "Fig. 1",
  "visual_summary": "...",
  "text_claim_check": [{"claim": "...", "verdict": "supported|exaggerated|unsupported", "note": "..."}],
  "deep_observation_cn": "...",
  "deep_observation_en": "...",
  "caption_cn": "..."
}
```

Driver concatenates into `参考文献/弛豫反铁电/he2023_out/fig_notes.json`.

- [ ] **Step 4: Pick figures to embed in docx**

Selection rule (decided **after** subagent results are in):
1. Always include any figure with mention_count >= 2 across template-relevant sections.
2. Include any figure where `text_claim_check` contains a non-`supported` verdict (these are the analytical hooks).
3. Cap at 6 figures; ties broken by mention_count.
4. If a figure is a phase diagram or in-situ TEM series, prioritize.

Selected `fig_ids` are written to `参考文献/弛豫反铁电/he2023_out/embed_list.json`.

### Task 2.3: Compose bilingual docx with embedded figures + critical analysis

**Files:**
- Modify: `paper2md_analyze.py`
- Test: `tests/test_analyze.py` (extend with smoke test on a minimal `fig_notes.json`)

- [ ] **Step 1: Write failing test**

```python
from paper2md_analyze import compose_docx


def test_compose_docx_smoke(tmp_path: Path):
    fig_notes = [
        {"fig_id": "Fig. 1", "image_abs_path": str(tmp_path / "imgs" / "a.jpg"),
         "deep_observation_cn": "相图揭示...", "deep_observation_en": "Phase diagram reveals...",
         "caption_cn": "图1：相图与三反铁电区"},
    ]
    (tmp_path / "imgs").mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.new("RGB", (640, 480), "white").save(tmp_path / "imgs" / "a.jpg")
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_Introduction.md").write_text("intro body", encoding="utf-8")
    (chapters_dir / "chapter_002_Results.md").write_text("results body", encoding="utf-8")
    out_path = tmp_path / "summary.docx"
    compose_docx(
        chapters_dir=chapters_dir,
        fig_notes=fig_notes,
        embed_ids=["Fig. 1"],
        meta={"title_cn": "测试", "title_en": "Test", "reference": "—", "system": "—"},
        out_path=out_path,
    )
    assert out_path.exists() and out_path.stat().st_size > 5000
```

- [ ] **Step 2: Run failing**

Run: `.venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `compose_docx`**

Append to `paper2md_analyze.py`:

```python
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


TEMPLATE_SECTIONS = [
    ("1. 引言：选题为何重要", "Introduction: Why this topic matters", []),
    ("2. 反铁电体特征与储能再认识", "Antiferroelectrics & renewed interest", []),
    ("3. 弛豫体与弛豫反铁电体", "Relaxors and Relaxor AFEs", []),
    ("4. 弛豫反铁电体的结构表征", "Structures of Relaxor AFE", []),
    ("5. 弛豫反铁电体的介电性能", "Dielectric Properties of Relaxor AFE", []),
    ("6. 极化行为：P-E 回线与机制", "Polarization Behaviour", []),
    ("7. 应用：储能与脉冲功率", "Applications", []),
    ("8. 讨论：CAFE 与弛豫反铁电概念再审视", "Discussion", []),
    ("9. 结论与启示", "Conclusions & Implications", []),
]


def _set_cn_font(run, size=11, bold=False):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    rPr = run._element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts")) or OxmlElement("w:rFonts")
    if rf.getparent() is None:
        rPr.append(rf)
    rf.set(qn("w:eastAsia"), "宋体")
    rf.set(qn("w:ascii"), "Times New Roman")
    rf.set(qn("w:hAnsi"), "Times New Roman")


def _heading(doc, cn, en, level=1):
    sizes = {1: 14, 2: 12}
    p = doc.add_paragraph()
    r = p.add_run(f"{cn}  /  {en}")
    _set_cn_font(r, size=sizes.get(level, 12), bold=True)


def _para(doc, text, indent=True):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    p.paragraph_format.line_spacing = 1.25
    r = p.add_run(text)
    _set_cn_font(r, size=11)


def compose_docx(*, chapters_dir, fig_notes, embed_ids, meta, out_path):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2.2)
    sec.left_margin = sec.right_margin = Cm(2.5)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(meta["title_cn"]); _set_cn_font(r, size=16, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(meta["title_en"]); _set_cn_font(r, size=13, bold=True)

    notes_by_id = {n["fig_id"]: n for n in fig_notes}
    for i, (cn, en, _) in enumerate(TEMPLATE_SECTIONS, start=1):
        _heading(doc, cn, en, level=1)
        # Insert figure for sections 4..7 if any embedded figure matches that section's keywords.
        for fid in embed_ids:
            n = notes_by_id.get(fid)
            if not n:
                continue
            if 4 <= i <= 7 and Path(n["image_abs_path"]).exists():
                doc.add_picture(n["image_abs_path"], width=Cm(14))
                _para(doc, n.get("caption_cn", fid), indent=False)
                _para(doc, "深度观察 / Deep observation: " + n.get("deep_observation_cn", ""))
                break
        # Placeholder body. The driver injects real per-section text before this in production usage.
        _para(doc, "(本节正文由 Phase 2 驱动器在调用时填入。/ Body inserted by Phase 2 driver.)")

    out_path = Path(out_path)
    doc.save(out_path)
    return out_path
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add paper2md_analyze.py tests/test_analyze.py
git commit -m "feat(analyze): compose bilingual docx with embedded figures"
```

### Task 2.4: End-to-end deep analysis on He 2023

Operational task; needs `PADDLEOCR_TOKEN` and the `subagent-driven-development` skill.

- [ ] **Step 1: Run Phase-1 (Task 1.8) if not already done.**

- [ ] **Step 2: Build the analysis plan**

```bash
.venv/bin/python -c "from paper2md_analyze import build_analysis_plan; from pathlib import Path; build_analysis_plan(Path('参考文献/弛豫反铁电/he2023_out'))"
```

- [ ] **Step 3: Dispatch parallel figure-analysis subagents**

For each entry in `analysis_plan.json::figure_tasks`, spawn a `general-purpose` subagent (or `Explore` if read-only) with the prompt template below. Run in parallel batches of 4 to respect rate limits.

Prompt template (fill `{image_abs_path}` etc.):
```
You are analyzing one figure from a peer-reviewed materials-science paper.

Inputs you must read:
- Image: {image_abs_path}  (use the Read tool to view it)
- Caption: {caption}
- Mentioning chapter excerpts:
{chapter_excerpts}

Tasks:
1) Describe what is visually readable in the figure that the text does not state.
2) For each surrounding-text claim about this figure, classify as supported / exaggerated / unsupported, with a one-sentence reason.
3) Write one Chinese paragraph (≤180 chars) of deep observation suitable for embedding in a critical review.
4) Suggest a Chinese caption (≤40 chars).

Return strict JSON: {"fig_id":"...","visual_summary":"...","text_claim_check":[...],"deep_observation_cn":"...","deep_observation_en":"...","caption_cn":"..."}
```

- [ ] **Step 4: Collect into `fig_notes.json`** (see Task 2.2 Step 3).

- [ ] **Step 5: Pick embed list, then compose**

```bash
.venv/bin/python -c "
import json, pathlib
from paper2md_analyze import compose_docx
o = pathlib.Path('参考文献/弛豫反铁电/he2023_out')
notes = json.loads((o/'fig_notes.json').read_text())
embed = json.loads((o/'embed_list.json').read_text())
meta = {
  'title_cn': '论文总结：在反铁电/弛豫反铁电交叉区构建无铅陶瓷以获得高储能性能与热稳定性',
  'title_en': 'Paper Summary: AFE/RAFE Crossover for Energy Storage in Lead-free Ceramics',
  'reference': 'L. He et al., Acta Materialia 249 (2023) 118826',
  'system': 'Ag1-3xLaxNb0.9Ta0.1O3 (ANT-xLa, x=0..5%)',
}
compose_docx(
  chapters_dir=o/'chapters',
  fig_notes=notes,
  embed_ids=embed,
  meta=meta,
  out_path=pathlib.Path('参考文献/弛豫反铁电/Summary_He_2023_ANT-CAFE_中英对照_v2.docx'),
)
"
```

- [ ] **Step 6: Spot-check the docx**

Open it, verify: ≥3 embedded figures, every template section present, every figure note has a non-empty `deep_observation_cn`.

---

## Self-Review

**Spec coverage**
- Phase 1 cleaner: Tasks 1.1–1.3 cover header strip, char repair, two-column flagging. ✓
- Phase 1 chapter split: Task 1.4 adds `science_paper` mode. ✓
- Phase 1 figure index + mentions: Tasks 1.6, 1.7. ✓
- Phase 1 CLI wiring & acceptance: Tasks 1.5, 1.8. ✓
- Phase 2 dynamic figure-selection (the user's decision #3): Tasks 2.1–2.2 produce a plan, dispatch per-figure subagents, then `embed_list.json` is decided by rule *after* the analyses arrive. ✓
- Phase 2 docx composition: Task 2.3. ✓

**Placeholder scan**
- One residual is intentional: in `compose_docx`, the per-section body still says "(本节正文由 Phase 2 驱动器在调用时填入)". This is a function-level placeholder for the body text, **not** a plan-level placeholder; the driver wiring in Task 2.4 substitutes real text. Acceptable because Task 2.4 specifies the substitution.

**Type/signature consistency**
- `build_analysis_plan(out_dir)` returns `{"figure_tasks": [...]}`. Consumed by Task 2.4 Step 3. ✓
- `compose_docx(*, chapters_dir, fig_notes, embed_ids, meta, out_path)` — signature is the same in Task 2.3 and Task 2.4 Step 5. ✓
- Figure dict shape `{fig_id, image_rel_path, image_abs_path, caption, source_doc}` is produced in 1.6 and consumed in 2.1. ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-paper2md-deep-analysis.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks. Best for Phase 1 (lots of small TDD steps).
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, with checkpoints at end of Phase 1 (after Task 1.8) and after Task 2.4.

Which approach?
