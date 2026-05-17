# paper2md Stage-Based Restructure & LLM-Driven Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `paper2md` from a flat `paper2md_*.py` layout into a folder-per-stage pipeline (`stages/01_ocr/` … `stages/09_render/`), add LLM-driven figure analysis and template-driven section composition (Qwen-VL for vision, DeepSeek for text via OpenAI-compatible APIs), and produce mypaper-compatible chapter bundles plus a self-rendered preview docx for any (paper PDF, template DOCX) input pair.

**Architecture:** Each pipeline stage lives in its own folder under `stages/<NN>_<name>/` (runner.py + tests/ + optional prompts/). Stages read prior-stage artifacts from `runs/<paper_id>/<NN>_<name>/` and write their own outputs there, using YAML for structured data and Markdown/PNG/DOCX for content. The `cli.py` orchestrator wires stages, skips already-completed ones (idempotency), and emits a `meta.yaml` with run provenance. LLM calls go through a single `llm/client.py` (OpenAI-compatible, vision+text roles) that records every prompt and response in the run directory for traceability.

**Tech Stack:** Python 3.10+, uv-managed venv, `openai` Python SDK (with `base_url` override for DeepSeek/Qwen DashScope), `pyyaml`, `python-docx`, `pdfplumber`, `pypdfium2`, `python-dotenv`, `pytest`. Existing PaddleOCR-VL cloud API for the PDF→markdown call.

---

## File Structure (target)

```
paper2md/
├── pyproject.toml                  # MODIFY: add openai, pyyaml, python-dotenv
├── cli.py                          # CREATE: single entry "python -m cli run <pdf> --template <docx>"
├── .env                            # EXISTS: PADDLEOCR_TOKEN + LLM_VISION_* + LLM_TEXT_*
├── .gitignore                      # EXISTS
│
├── llm/
│   ├── __init__.py                 # CREATE: empty
│   ├── client.py                   # CREATE: LLM(role) → chat(system, user, images=[]) → str
│   ├── models.yaml                 # CREATE: role → {base_url, model, env_key} mapping
│   └── prompts/
│       ├── paper_context.md        # CREATE: system + user prompt template for stage 06
│       ├── figure_analyze.md       # CREATE: prompt template for stage 07
│       └── section_compose.md      # CREATE: prompt template for stage 08
│
├── stages/
│   ├── __init__.py                 # CREATE: empty
│   ├── _common.py                  # CREATE: load_yaml/dump_yaml/run_dir helpers
│   ├── 01_ocr/
│   │   ├── __init__.py             # CREATE: empty
│   │   ├── runner.py               # CREATE: PDF + token → doc_*.md + imgs/
│   │   └── tests/test_runner.py    # CREATE: mocked-API test
│   ├── 02_clean/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: port from old paper2md_clean.py
│   │   └── tests/test_runner.py    # CREATE: 7 tests ported
│   ├── 03_chapter/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: port chapter splitter (science_paper mode default)
│   │   └── tests/test_runner.py    # CREATE: anchor test ported
│   ├── 04_figures/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: figures.yaml + tables.yaml + mentions.yaml
│   │   └── tests/test_runner.py    # CREATE: 2 tests ported
│   ├── 05_template/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: parse template.docx → template.yaml
│   │   └── tests/test_runner.py    # CREATE: AFE template fixture test
│   ├── 06_context/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: LLM extract paper_context.yaml
│   │   └── tests/test_runner.py    # CREATE: mocked-LLM test
│   ├── 07_figure_analyze/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: LLM vision per-figure → fig_notes.yaml
│   │   └── tests/test_runner.py    # CREATE: mocked-LLM test
│   ├── 08_section_compose/
│   │   ├── __init__.py
│   │   ├── runner.py               # CREATE: LLM text per-section → chapters/*.md
│   │   └── tests/test_runner.py    # CREATE: mocked-LLM test
│   └── 09_render/
│       ├── __init__.py
│       ├── runner.py               # CREATE: bundle + preview docx
│       └── tests/test_runner.py    # CREATE: smoke test
│
├── runs/                           # CREATE empty; populated at runtime
│
├── tests/
│   └── conftest.py                 # CREATE: shared fixtures (sample paper docs)
│
└── docs/superpowers/plans/         # EXISTS: plan file
```

**DELETED at end of plan:**
- `paper2md.py`
- `paper2md_clean.py`
- `paper2md_chapter.py`
- `paper2md_patterns.py`
- `paper2md_figures.py`
- `paper2md_mapping.py`
- `paper2md_analyze.py`
- `tests/test_clean.py`
- `tests/test_chapter_science.py`
- `tests/test_figures.py`
- `tests/test_analyze.py`
- `make_summary.py` (one-off, no longer needed)
- `参考文献/弛豫反铁电/he2023_out/compose_v2.py` (one-off; v2 docx kept as golden reference)

**PRESERVED as golden reference:**
- `参考文献/弛豫反铁电/Summary_He_2023_ANT-CAFE_深度分析_v2.docx`
- `参考文献/弛豫反铁电/he2023_out/imgs/` (used as Phase B fixture)

---

## Conventions

**Run directory:** `runs/<paper_id>/`. The `paper_id` is derived from the PDF filename (slugified, max 50 chars). The CLI accepts `--paper-id <slug>` to override.

**YAML over JSON:** All intermediate structured data (figures.yaml, fig_notes.yaml, template.yaml, context.yaml, meta.yaml, chapter_index.yaml). Prompts use Markdown (`.md`).

**LLM call audit:** Each LLM invocation writes two files into the calling stage's run dir:
- `<basename>.prompt.md` — the exact prompt that was sent (system + user + image manifest)
- `<basename>.response.json` — `{model, latency_ms, usage, content}`

**Stage idempotency:** `runner.run(paper_id, run_root)` checks for a `done.yaml` marker in its own output dir. If present and `--force` not given, it returns the existing artifacts.

**git:** This repo is not a git repository (per Task 1.8 of the previous plan). No `git commit` steps; if `git init` is later desired ask the user.

---

## Phase A — Foundation

### Task A.1: Add LLM dependencies via uv

**Files:**
- Modify: `/Users/zhangjiedong/codeFiles/article/paper2md/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Replace the `[project]` `dependencies` block with:

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
]

[project.optional-dependencies]
dev = ["pytest>=8"]
```

- [ ] **Step 2: Install**

Run from `/Users/zhangjiedong/codeFiles/article/paper2md`:
```
uv pip install -e '.[dev]' --python .venv/bin/python
```
Expected: "Installed N packages" with no errors.

- [ ] **Step 3: Smoke-test all imports**

Run:
```
.venv/bin/python -c "import openai, yaml, dotenv, docx, pdfplumber, pypdfium2, pytest; print('ok')"
```
Expected: `ok`.

### Task A.2: Create folder skeleton

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/__init__.py` (empty)
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/_common.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/__init__.py` (empty)
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/prompts/.gitkeep` (touch)
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/runs/.gitkeep` (touch)
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/tests/conftest.py`
- Create: empty `__init__.py` in each of `stages/01_ocr`, `02_clean`, `03_chapter`, `04_figures`, `05_template`, `06_context`, `07_figure_analyze`, `08_section_compose`, `09_render`, and a `tests/__init__.py` in each.

- [ ] **Step 1: Create directory tree**

Run:
```
cd /Users/zhangjiedong/codeFiles/article/paper2md
mkdir -p stages/{01_ocr,02_clean,03_chapter,04_figures,05_template,06_context,07_figure_analyze,08_section_compose,09_render}/tests
mkdir -p llm/prompts runs
touch stages/__init__.py llm/__init__.py llm/prompts/.gitkeep runs/.gitkeep
for d in stages/0[1-9]_*; do touch "$d/__init__.py" "$d/tests/__init__.py"; done
```

- [ ] **Step 2: Create `stages/_common.py`**

```python
"""Shared stage helpers: run-dir layout, YAML I/O, slug, done-marker."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import yaml


def slugify(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "_", text.strip(), flags=re.UNICODE)
    s = s.strip("_")
    return s[:maxlen] if s else "untitled"


def stage_dir(run_root: Path, paper_id: str, stage_name: str) -> Path:
    d = Path(run_root) / paper_id / stage_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, obj: Any) -> None:
    path.write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def mark_done(stage_path: Path, extra: dict[str, Any] | None = None) -> None:
    dump_yaml(stage_path / "done.yaml", {"finished_at": time.time(), **(extra or {})})


def is_done(stage_path: Path) -> bool:
    return (stage_path / "done.yaml").exists()
```

- [ ] **Step 3: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures across stage tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
```

- [ ] **Step 4: Verify import**

Run:
```
.venv/bin/python -c "from stages._common import slugify, dump_yaml; print(slugify('Hello World'))"
```
Expected: `Hello_World`

### Task A.3: LLM client + models.yaml

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/models.yaml`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/client.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_llm_client.py`

- [ ] **Step 1: Create `llm/models.yaml`**

```yaml
# Role-based LLM configuration. Each role resolves env vars:
#   <ROLE>_BASE_URL  -> base_url for openai client
#   <ROLE>_API_KEY   -> api_key
#   <ROLE>_MODEL     -> model name
# Defaults are sensible if env vars not set; CLI uses them directly.
vision:
  env_prefix: LLM_VISION
  default_base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  default_model: qwen-vl-max-latest
  supports_images: true
text:
  env_prefix: LLM_TEXT
  default_base_url: https://api.deepseek.com/v1
  default_model: deepseek-chat
  supports_images: false
```

- [ ] **Step 2: Write failing test `tests/test_llm_client.py`**

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm.client import LLM, image_to_data_url


def test_image_to_data_url(tmp_path: Path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")  # minimal JPEG magic
    url = image_to_data_url(img)
    assert url.startswith("data:image/jpeg;base64,")
    assert "/9j" not in url[:23]  # base64 body comes after prefix


def test_llm_text_role_chat(monkeypatch):
    monkeypatch.setenv("LLM_TEXT_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_TEXT_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_TEXT_MODEL", "test-model")

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="hello"))]
    fake_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    with patch("llm.client.OpenAI") as oai_cls:
        oai_cls.return_value.chat.completions.create.return_value = fake_resp
        llm = LLM(role="text")
        out = llm.chat(system="be concise", user="hi")
    assert out.content == "hello"
    assert out.usage["total_tokens"] == 15
    assert out.model == "test-model"


def test_llm_vision_role_includes_images(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_VISION_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_VISION_BASE_URL", "https://x.example.com/v1")
    monkeypatch.setenv("LLM_VISION_MODEL", "qwen-vl")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="saw img"))]
    fake_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    with patch("llm.client.OpenAI") as oai_cls:
        oai_cls.return_value.chat.completions.create.return_value = fake_resp
        llm = LLM(role="vision")
        out = llm.chat(system="describe", user="what is this", images=[img])

    call_kwargs = oai_cls.return_value.chat.completions.create.call_args.kwargs
    user_msg = call_kwargs["messages"][1]
    # user content must be a list with text + image_url parts when images present
    assert isinstance(user_msg["content"], list)
    types = [p["type"] for p in user_msg["content"]]
    assert "text" in types and "image_url" in types
    assert out.content == "saw img"


def test_llm_vision_role_rejects_images_if_unsupported(monkeypatch):
    monkeypatch.setenv("LLM_TEXT_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_TEXT_MODEL", "deepseek-chat")
    llm = LLM(role="text")
    with pytest.raises(ValueError, match="does not support images"):
        llm.chat(system="x", user="y", images=[Path("/tmp/whatever.jpg")])
```

- [ ] **Step 3: Run test, verify ImportError**

Run: `.venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: `ModuleNotFoundError: No module named 'llm.client'`

- [ ] **Step 4: Implement `llm/client.py`**

```python
"""OpenAI-compatible client for vision (Qwen-VL) and text (DeepSeek) roles."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

_MODELS_YAML = Path(__file__).resolve().parent / "models.yaml"


def _load_roles() -> dict:
    return yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))


def image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict
    latency_ms: float


class LLM:
    def __init__(self, role: str, dotenv_path: Path | None = None):
        load_dotenv(dotenv_path or Path.cwd() / ".env", override=False)
        roles = _load_roles()
        if role not in roles:
            raise ValueError(f"unknown role {role!r}; expected one of {list(roles)}")
        cfg = roles[role]
        prefix = cfg["env_prefix"]
        api_key = os.environ.get(f"{prefix}_API_KEY")
        if not api_key:
            raise RuntimeError(f"missing env var {prefix}_API_KEY")
        base_url = os.environ.get(f"{prefix}_BASE_URL", cfg["default_base_url"])
        self.model = os.environ.get(f"{prefix}_MODEL", cfg["default_model"])
        self.supports_images = bool(cfg.get("supports_images", False))
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        *,
        system: str,
        user: str,
        images: list[Path] = (),
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        if images and not self.supports_images:
            raise ValueError(f"role/model {self.model} does not support images")
        messages = [{"role": "system", "content": system}]
        if images:
            user_parts: list[dict] = [{"type": "text", "text": user}]
            for img in images:
                user_parts.append(
                    {"type": "image_url", "image_url": {"url": image_to_data_url(Path(img))}}
                )
            messages.append({"role": "user", "content": user_parts})
        else:
            messages.append({"role": "user", "content": user})

        t0 = time.time()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency_ms = (time.time() - t0) * 1000
        u = getattr(resp, "usage", None)
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", None),
            "completion_tokens": getattr(u, "completion_tokens", None),
            "total_tokens": getattr(u, "total_tokens", None),
        }
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=self.model,
            usage=usage,
            latency_ms=latency_ms,
        )
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: 4 passed.

### Task A.4: Live LLM smoke test

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_llm_smoke.py`

- [ ] **Step 1: Write live smoke test (marked `live`, skippable)**

```python
"""Live smoke tests. Require .env with real keys. Run explicitly:

    .venv/bin/python -m pytest tests/test_llm_smoke.py -v -m live
"""
import os
import pytest
from pathlib import Path

from llm.client import LLM

pytestmark = pytest.mark.live


def _have_keys() -> bool:
    return bool(os.environ.get("LLM_VISION_API_KEY")) and bool(os.environ.get("LLM_TEXT_API_KEY"))


@pytest.mark.skipif(not _have_keys(), reason="LLM keys not set")
def test_text_llm_returns_nonempty():
    llm = LLM(role="text")
    out = llm.chat(system="Reply with one word: ok", user="say ok", max_tokens=10)
    assert out.content.strip(), "empty content"
    assert out.usage["total_tokens"] is not None


@pytest.mark.skipif(not _have_keys(), reason="LLM keys not set")
def test_vision_llm_describes_image(tmp_path: Path):
    from PIL import Image
    img = tmp_path / "red.png"
    Image.new("RGB", (32, 32), "red").save(img)
    llm = LLM(role="vision")
    out = llm.chat(
        system="Describe the dominant color of the image in one English word.",
        user="What color?",
        images=[img],
        max_tokens=20,
    )
    assert "red" in out.content.lower(), f"unexpected response: {out.content!r}"
```

- [ ] **Step 2: Mark `live` in pyproject (so default `pytest` skips it)**

Append to `pyproject.toml` (after `[project.optional-dependencies]`):
```toml
[tool.pytest.ini_options]
markers = [
    "live: tests that call real LLM/OCR APIs (skipped by default; run via -m live)",
]
addopts = "-m 'not live'"
```

- [ ] **Step 3: Run live tests using env from .env**

```
set -a; source .env; set +a; .venv/bin/python -m pytest tests/test_llm_smoke.py -v -m live
```
Expected: 2 passed. Total latency may take 5–20 s.

If either fails with auth error, surface error and BLOCK; do not silently retry.

- [ ] **Step 4: Run default suite (should skip live)**

Run: `.venv/bin/python -m pytest -v`
Expected: previous tests (`test_llm_client.py`) pass; live tests skipped with "deselecting due to live marker".

---

## Phase B — Migrate existing stages 01–04

### Task B.1: stage 01 OCR runner

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/01_ocr/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/01_ocr/tests/test_runner.py`

This stage POSTs the PDF to PaddleOCR-VL, polls until done, and writes raw `doc_*.md` files plus `imgs/` into the stage dir. We do NOT live-call PaddleOCR in unit tests; we mock the HTTP layer.

- [ ] **Step 1: Write the failing test**

```python
# stages/01_ocr/tests/test_runner.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stages._common import is_done
from stages._01_ocr_runner import run as run_ocr  # we re-export below


def test_ocr_runner_writes_docs_and_images(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    # Mock the cloud API: POST returns jobId; GET poll returns done with resultUrl
    job_response = {"data": {"jobId": "job-xyz"}}
    done_state = {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://x/result.json"}}}
    result_text = json.dumps({
        "result": {
            "layoutParsingResults": [
                {
                    "markdown": {
                        "text": '# page 1\n<img src="imgs/img_a.jpg">\n',
                        "images": {"imgs/img_a.jpg": "https://x/img_a.jpg"},
                    },
                    "outputImages": {},
                }
            ]
        }
    })

    def fake_post(url, **kwargs):
        r = MagicMock(); r.ok = True; r.json.return_value = job_response
        return r

    def fake_get(url, **kwargs):
        r = MagicMock(); r.ok = True
        if url.endswith("/job-xyz"):
            r.json.return_value = done_state
        elif url.endswith("result.json"):
            r.text = result_text
        else:
            r.content = b"\xff\xd8\xff\xe0FAKE-JPEG"
        return r

    with patch("stages._01_ocr_runner.requests.Session") as sess_cls:
        sess = sess_cls.return_value
        sess.post.side_effect = fake_post
        sess.get.side_effect = fake_get
        run_dir = tmp_path / "runs" / "paper" / "01_ocr"
        run_ocr(pdf=pdf, out_dir=run_dir, token="t")

    assert (run_dir / "doc_0.md").exists()
    assert (run_dir / "imgs" / "img_a.jpg").exists()
    assert is_done(run_dir)
```

Note the import alias `stages._01_ocr_runner`: Python identifiers can't start with a digit, so we'll expose the runner via the package mechanism (`stages/01_ocr/runner.py` imported by the stage shim).

Actually, simpler: create the runner at `stages/01_ocr/runner.py` and import it via `importlib`. We'll set up an `__init__.py` re-export.

Update `stages/01_ocr/__init__.py` (already empty) to:
```python
from .runner import run  # re-export
```
and the test imports `from stages._common import is_done` + `from stages.01_ocr.runner import run`.

But again: digit-first package names. The Python-clean way: rename the folders to use a stage_NN prefix that's valid, e.g., `s01_ocr`. Or use a non-package layout and load via `importlib`. The cleanest is to rename:

- `stages/s01_ocr/`, `stages/s02_clean/` etc.

Update File Structure & test imports accordingly.

**Revised name:** use `s01_ocr`, `s02_clean`, … `s09_render` so they are valid Python identifiers.

Re-do test:
```python
# stages/s01_ocr/tests/test_runner.py
from stages.s01_ocr.runner import run as run_ocr
```

- [ ] **Step 2: Run test to verify failure**

First, rename the folders:
```
cd /Users/zhangjiedong/codeFiles/article/paper2md/stages
for d in 0?_*; do mv "$d" "s${d}"; done
```
Result: `s01_ocr`, `s02_clean`, …

Now run:
```
.venv/bin/python -m pytest stages/s01_ocr/tests/test_runner.py -v
```
Expected: ImportError on `stages.s01_ocr.runner`.

- [ ] **Step 3: Implement `stages/s01_ocr/runner.py`**

```python
"""Stage 01: PDF -> PaddleOCR-VL -> doc_*.md + imgs/."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

from stages._common import mark_done

API = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
MODEL = "PaddleOCR-VL-1.5"
OPT = {k: False for k in ("useDocOrientationClassify", "useDocUnwarping", "useChartRecognition")}


def run(*, pdf: Path, out_dir: Path, token: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    h = {"Authorization": f"bearer {token}"}
    with pdf.open("rb") as f:
        r = s.post(API, headers=h,
                   data={"model": MODEL, "optionalPayload": json.dumps(OPT)},
                   files={"file": f}, timeout=600)
    if not r.ok:
        raise SystemExit(r.text)
    job_id = r.json()["data"]["jobId"]
    poll_url = f"{API}/{job_id}"
    while True:
        j = s.get(poll_url, headers=h, timeout=60).json()["data"]
        if j["state"] == "done":
            text = s.get(j["resultUrl"]["jsonUrl"], timeout=120).text
            break
        if j["state"] == "failed":
            raise SystemExit(j.get("errorMsg", j))
        print(j["state"], file=sys.stderr)
        time.sleep(5)
    n = 0
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        for res in json.loads(line)["result"]["layoutParsingResults"]:
            (out_dir / f"doc_{n}.md").write_text(res["markdown"]["text"], encoding="utf-8")
            for rel, url in res["markdown"]["images"].items():
                q = out_dir / rel
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(s.get(url, timeout=120).content)
            n += 1
    mark_done(out_dir, {"docs": n})
    return {"docs": n}
```

- [ ] **Step 4: Run test, expect pass**

Run: `.venv/bin/python -m pytest stages/s01_ocr/tests/test_runner.py -v`
Expected: 1 passed.

### Task B.2: stage 02 clean runner

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s02_clean/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s02_clean/tests/test_runner.py`

Port the three cleaners (`strip_running_headers`, `repair_chars`, `flag_corrupted_column_flow`) verbatim from `paper2md_clean.py` into the new runner, plus a `run(in_dir, out_dir)` wrapper.

- [ ] **Step 1: Write failing tests**

```python
# stages/s02_clean/tests/test_runner.py
from pathlib import Path

from stages.s02_clean.runner import (
    strip_running_headers,
    repair_chars,
    flag_corrupted_column_flow,
    run,
)


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


def test_repair_cid_minus():
    assert repair_chars("ranging between 0.1 to (cid:0) 10^{-4}") == \
        "ranging between 0.1 to − 10^{-4}"


def test_repair_subscripted_oxide_formula():
    assert repair_chars("AgNbO 3 ceramic") == "AgNbO₃ ceramic"
    assert repair_chars("page 3 of 8") == "page 3 of 8"


def test_repair_squashed_ag_plus():
    assert repair_chars("translation mode (Ag + )") == "translation mode (Ag⁺)"


def test_flag_obvious_interleave():
    bad = "outs A t l a t n h d o i u n g g h en t e h r e g y cl s a to ra g e p e r f or m a n c e"
    flagged = flag_corrupted_column_flow(bad)
    assert flagged.startswith("<!-- corrupted-column-flow -->")
    assert bad in flagged


def test_keep_normal_line():
    ok = "we found a high polarization change and low hysteresis"
    assert flag_corrupted_column_flow(ok) == ok


def test_run_clean_pipeline(tmp_path: Path):
    in_dir = tmp_path / "in"; in_dir.mkdir()
    out_dir = tmp_path / "out"
    (in_dir / "doc_0.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nAgNbO 3 sample.",
        encoding="utf-8",
    )
    (in_dir / "doc_1.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nSecond page.",
        encoding="utf-8",
    )
    (in_dir / "doc_2.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nThird page.",
        encoding="utf-8",
    )
    run(in_dir=in_dir, out_dir=out_dir)
    out0 = (out_dir / "doc_0.md").read_text(encoding="utf-8")
    assert "Acta Materialia" not in out0
    assert "AgNbO₃" in out0
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s02_clean/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stages/s02_clean/runner.py`**

```python
"""Stage 02: clean OCR doc_*.md (header strip, char repair, column-flow flag)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from stages._common import mark_done


def strip_running_headers(docs: list[str], min_repeat: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for d in docs:
        seen: set[str] = set()
        for raw in d.splitlines():
            line = raw.strip()
            if not line or len(line) > 120 or line in seen:
                continue
            seen.add(line)
            counter[line] += 1
    drop = {ln for ln, n in counter.items() if n >= min_repeat}
    return ["\n".join(raw for raw in d.splitlines() if raw.strip() not in drop) for d in docs]


_CID_MAP = {"(cid:0)": "−"}
_SUB_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_OXIDE_RE = re.compile(r"\b([A-Z][a-z]?(?:[A-Z][a-z]?\d*)*[A-Z][a-z]?)\s+(\d{1,2})\b")
_CATION_PLUS_RE = re.compile(r"\b([A-Z][a-z]?)\s+\+\s*\)")


def repair_chars(text: str) -> str:
    for k, v in _CID_MAP.items():
        text = text.replace(k, v)

    def _ox(m: re.Match[str]) -> str:
        prefix, digits = m.group(1), m.group(2)
        if not re.search(r"[A-Z]", prefix):
            return m.group(0)
        return f"{prefix}{digits.translate(_SUB_DIGITS)}"

    text = _OXIDE_RE.sub(_ox, text)
    text = _CATION_PLUS_RE.sub(lambda m: f"{m.group(1)}⁺)", text)
    return text


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


def run(*, in_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = sorted(in_dir.glob("doc_*.md"))
    if not docs:
        raise FileNotFoundError(f"no doc_*.md in {in_dir}")
    texts = [p.read_text(encoding="utf-8") for p in docs]
    texts = strip_running_headers(texts, min_repeat=3)
    for src, txt in zip(docs, texts):
        cleaned = flag_corrupted_column_flow(repair_chars(txt))
        (out_dir / src.name).write_text(cleaned, encoding="utf-8")
    # also copy imgs/ if present so downstream stages still find images relative to out_dir
    imgs = in_dir / "imgs"
    if imgs.exists():
        dst = out_dir / "imgs"
        dst.mkdir(exist_ok=True)
        for p in imgs.iterdir():
            (dst / p.name).write_bytes(p.read_bytes())
    mark_done(out_dir, {"docs": len(docs)})
    return {"docs": len(docs)}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest stages/s02_clean/tests/test_runner.py -v`
Expected: 8 passed.

### Task B.3: stage 03 chapter runner

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s03_chapter/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s03_chapter/tests/test_runner.py`

Port `paper2md_patterns.py` + `paper2md_chapter.py::split_by_chapters` (science_paper mode as default) into one runner. Add `chapter_index.yaml` output (replacing JSON).

- [ ] **Step 1: Write failing tests**

```python
# stages/s03_chapter/tests/test_runner.py
from pathlib import Path

import yaml

from stages.s03_chapter.runner import run, detect_science_anchor


def test_detect_anchor_named_section():
    assert detect_science_anchor("References") == "References"
    assert detect_science_anchor("## Introduction") == "Introduction"
    assert detect_science_anchor("Random body text that doesn't anchor") is None


def test_detect_anchor_numbered_subsection():
    assert detect_science_anchor("2.1. Sample preparation").startswith("2.1")


def test_run_splits_imrad(tmp_path: Path):
    in_dir = tmp_path / "in"; in_dir.mkdir()
    (in_dir / "doc_0.md").write_text(
        "## Abstract\nWe report...\n\n"
        "1. Introduction\nIntro body.\n\n"
        "2. Experimental\nMethod body.\n\n"
        "3. Results and discussion\nResults body.\n\n"
        "4. Conclusion\nConcl body.\n\n"
        "References\n[1] foo.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    summary = run(in_dir=in_dir, out_dir=out_dir, min_chars=1)
    idx = yaml.safe_load((out_dir / "chapter_index.yaml").read_text(encoding="utf-8"))
    titles = [c["title"] for c in idx]
    assert any("Introduction" in t for t in titles)
    assert any("Experimental" in t for t in titles)
    assert any("Results" in t for t in titles)
    assert any("Conclusion" in t for t in titles)
    assert any("References" in t for t in titles)
    assert summary["count"] == len(titles)
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s03_chapter/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stages/s03_chapter/runner.py`**

```python
"""Stage 03: split cleaned doc_*.md into chapters using IMRaD section anchors."""
from __future__ import annotations

import re
from pathlib import Path

from stages._common import dump_yaml, mark_done, slugify

SECTION_ANCHORS = {
    "abstract", "introduction", "experimental", "experiments",
    "materials and methods", "methods", "methodology",
    "results", "results and discussion", "discussion",
    "conclusion", "conclusions", "summary",
    "acknowledgements", "acknowledgments",
    "references", "supplementary", "appendix",
}

_ANCHOR_LINE_RE = re.compile(
    r"^\s*(#{0,4}\s*)?(\d+(?:\.\d+){0,2}\.?\s+)?(?P<title>[A-Z][A-Za-z &/-]{2,60})\s*$"
)


def detect_science_anchor(line: str) -> str | None:
    m = _ANCHOR_LINE_RE.match(line.strip())
    if not m:
        return None
    title = m.group("title").strip()
    if title.lower() in SECTION_ANCHORS:
        return title
    if m.group(2) and 4 <= len(title) <= 60:
        return f"{m.group(2).strip()} {title}".strip()
    return None


def _clean_len(lines: list[str]) -> int:
    text = re.sub(r"<[^>]+>", "", "\n".join(lines))
    return len(re.sub(r"\s+", "", text))


def run(*, in_dir: Path, out_dir: Path, min_chars: int = 1) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir = out_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    for stale in chapters_dir.glob("chapter_*.md"):
        stale.unlink()

    docs = sorted(in_dir.glob("doc_*.md"))
    if not docs:
        raise FileNotFoundError(f"no doc_*.md in {in_dir}")

    chapter_no = 0
    current_title = "Preface"
    current_lines: list[str] = []
    current_sources: list[str] = []
    chapter_index: list[dict] = []

    def flush() -> None:
        nonlocal chapter_no, current_lines, current_sources, current_title
        body = "\n".join(current_lines).strip()
        if not body:
            return
        fname = f"chapter_{chapter_no:03d}_{slugify(current_title)}.md"
        (chapters_dir / fname).write_text(
            f"<!-- sources: {', '.join(current_sources)} -->\n\n{body}\n",
            encoding="utf-8",
        )
        chapter_index.append({
            "chapter_no": chapter_no,
            "title": current_title,
            "file": fname,
            "sources": current_sources[:],
            "chars": _clean_len(current_lines),
        })
        chapter_no += 1
        current_lines = []
        current_sources = []

    for doc in docs:
        for line in doc.read_text(encoding="utf-8").splitlines():
            heading = detect_science_anchor(line)
            if heading and _clean_len(current_lines) >= min_chars:
                flush()
                current_title = heading
            current_lines.append(line)
        current_sources.append(doc.name)
        current_lines.append("")
    flush()

    dump_yaml(out_dir / "chapter_index.yaml", chapter_index)
    mark_done(out_dir, {"count": len(chapter_index)})
    return {"count": len(chapter_index)}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest stages/s03_chapter/tests/test_runner.py -v`
Expected: 3 passed.

### Task B.4: stage 04 figures runner

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s04_figures/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s04_figures/tests/test_runner.py`

Port `paper2md_figures.py`'s three functions. Outputs are YAML now.

- [ ] **Step 1: Write failing tests**

```python
# stages/s04_figures/tests/test_runner.py
from pathlib import Path

import yaml

from stages.s04_figures.runner import run


def test_figures_basic_pairing(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    (src / "imgs").mkdir()
    (src / "imgs" / "img_a.jpg").write_bytes(b"\xff")
    (src / "imgs" / "img_b.jpg").write_bytes(b"\xff")
    (src / "doc_0.md").write_text(
        '<img src="imgs/img_a.jpg">\n\n'
        "Fig. 1. Phase diagram of ANT-xLa ceramics.\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (src / "doc_1.md").write_text(
        '<img src="imgs/img_b.jpg">\n\n'
        "Fig. 2. Weibull distribution.\n",
        encoding="utf-8",
    )

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    (chapters_dir / "chapter_001_Results.md").write_text("see Fig. 1(a) and Fig. 2.", encoding="utf-8")

    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir)
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    by_id = {f["fig_id"]: f for f in figs}
    assert by_id["Fig. 1"]["image_rel_path"].endswith("img_a.jpg")
    assert "Phase diagram" in by_id["Fig. 1"]["caption"]
    mentions = yaml.safe_load((out_dir / "mentions.yaml").read_text(encoding="utf-8"))
    assert mentions["chapter_001_Results.md"] == ["Fig. 1", "Fig. 2"]


def test_figures_div_wrapped_caption(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    (src / "imgs").mkdir()
    (src / "imgs" / "img.jpg").write_bytes(b"\xff")
    (src / "doc_0.md").write_text(
        '<div><img src="imgs/img.jpg"></div>\n\n'
        '<div style="text-align: center;">Fig. 1. Phase diagram of ANT-xLa ceramics.</div>\n',
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir)
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    assert any(f["fig_id"] == "Fig. 1" and "Phase diagram" in f["caption"] for f in figs)
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s04_figures/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stages/s04_figures/runner.py`**

```python
"""Stage 04: figure & table index + chapter mention map."""
from __future__ import annotations

import re
from pathlib import Path

from stages._common import dump_yaml, mark_done

IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)
FIG_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*(Fig(?:ure)?\.?\s*\d+[A-Za-z]?)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
TAB_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*(Table\s*\d+)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
FIG_MENTION_RE = re.compile(r"Fig(?:ure)?\.?\s*(\d+)([a-z])?", re.IGNORECASE)


def _normalize_fig_id(raw: str) -> str:
    m = re.match(r"Fig(?:ure)?\.?\s*(\d+)([A-Za-z]?)", raw, re.IGNORECASE)
    if not m:
        return raw.strip()
    return f"Fig. {m.group(1)}{m.group(2).lower() if m.group(2) else ''}"


def run(*, docs_dir: Path, chapters_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    figures: list[dict] = []
    tables: list[dict] = []
    for doc in sorted(docs_dir.glob("doc_*.md")):
        text = doc.read_text(encoding="utf-8")
        img_positions = [(m.start(), m.group(1)) for m in IMG_RE.finditer(text)]
        cap_positions = [
            (m.start(), _normalize_fig_id(m.group(1)), m.group(2).strip())
            for m in FIG_CAP_RE.finditer(text)
        ]
        used: set[int] = set()
        for img_start, rel in img_positions:
            best, best_dist = None, 10**9
            for ci, (cap_start, _fid, _cap) in enumerate(cap_positions):
                if ci in used:
                    continue
                dist = abs(cap_start - img_start)
                if dist < best_dist:
                    best, best_dist = ci, dist
            fid, caption = None, ""
            if best is not None:
                used.add(best)
                fid, caption = cap_positions[best][1], cap_positions[best][2]
            figures.append({
                "fig_id": fid or f"_unmatched_{Path(rel).stem}",
                "image_rel_path": rel,
                "image_abs_path": str((docs_dir / rel).resolve()),
                "caption": caption,
                "source_doc": doc.name,
            })
        for m in TAB_CAP_RE.finditer(text):
            tables.append({"table_id": m.group(1).strip(), "caption": m.group(2).strip(),
                           "source_doc": doc.name})

    mentions: dict[str, list[str]] = {}
    for ch in sorted(chapters_dir.glob("chapter_*.md")):
        ids = sorted({f"Fig. {m.group(1)}{(m.group(2) or '').lower()}"
                      for m in FIG_MENTION_RE.finditer(ch.read_text(encoding='utf-8'))})
        mentions[ch.name] = ids

    dump_yaml(out_dir / "figures.yaml", figures)
    dump_yaml(out_dir / "tables.yaml", tables)
    dump_yaml(out_dir / "mentions.yaml", mentions)
    mark_done(out_dir, {"figures": len(figures), "tables": len(tables)})
    return {"figures": len(figures), "tables": len(tables)}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest stages/s04_figures/tests/test_runner.py -v`
Expected: 2 passed.

---

## Phase C — New LLM-driven stages 05–09

### Task C.1: stage 05 template parser

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s05_template/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s05_template/tests/test_runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s05_template/tests/fixture_tpl.docx` (built via Python in test)

The template parser reads a .docx outline, walks paragraphs, and produces a tree:
```yaml
- level: 1
  number: "1"
  title: "Introduction"
  guidance: "why the topic is important?…"
  hints: {needs_table: false, needs_figure: false}
  children: []
- level: 1
  number: "2"
  title: "Antiferroelectrics"
  guidance: "Discuss characteristics (structure, P-E, applications etc.)\nRenewed interests..."
  hints: ...
  children: [...]
```

- [ ] **Step 1: Write failing test**

```python
# stages/s05_template/tests/test_runner.py
from pathlib import Path

import yaml
from docx import Document

from stages.s05_template.runner import parse_template, run


def _make_fixture(path: Path) -> None:
    doc = Document()
    doc.add_paragraph("Outline", style="Normal")
    p = doc.add_paragraph("Introduction", style="List Paragraph")
    p = doc.add_paragraph("(why the topic is important?…)", style="Normal")
    p = doc.add_paragraph("Antiferroelectrics", style="List Paragraph")
    p = doc.add_paragraph("Discuss characteristics (structure, P-E, applications etc.)", style="Normal")
    p = doc.add_paragraph("Provide Tables summarizing their compositions.", style="Normal")
    doc.save(path)


def test_parse_template_simple(tmp_path: Path):
    fx = tmp_path / "tpl.docx"
    _make_fixture(fx)
    tree = parse_template(fx)
    titles = [n["title"] for n in tree]
    assert "Introduction" in titles
    assert "Antiferroelectrics" in titles
    afe = next(n for n in tree if n["title"] == "Antiferroelectrics")
    assert "Discuss characteristics" in afe["guidance"]
    assert afe["hints"]["needs_table"] is True


def test_run_writes_yaml(tmp_path: Path):
    fx = tmp_path / "tpl.docx"
    _make_fixture(fx)
    out_dir = tmp_path / "out"
    run(template_docx=fx, out_dir=out_dir)
    data = yaml.safe_load((out_dir / "template.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any(n["title"] == "Introduction" for n in data)
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s05_template/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stages/s05_template/runner.py`**

```python
"""Stage 05: parse a user-provided outline docx into a hierarchical structure."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from stages._common import dump_yaml, mark_done

_NEEDS_TABLE_RE = re.compile(r"\b(?:provide|include|tabulate|tables?)\b.*\btable", re.IGNORECASE)
_NEEDS_FIGURE_RE = re.compile(r"\b(?:figure|illustration|diagram|chart)\b", re.IGNORECASE)
_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\s+(.+?)\s*$")


def _hints(text: str) -> dict:
    return {
        "needs_table": bool(_NEEDS_TABLE_RE.search(text)),
        "needs_figure": bool(_NEEDS_FIGURE_RE.search(text)),
    }


def parse_template(template_docx: Path) -> list[dict]:
    doc = Document(template_docx)
    nodes: list[dict] = []
    current: dict | None = None
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        is_heading = style == "List Paragraph" or bool(_NUMBERED_RE.match(text))
        if is_heading:
            m = _NUMBERED_RE.match(text)
            if m:
                number, title = m.group(1), m.group(2)
                level = number.count(".") + 1
            else:
                number, title, level = "", text, 1
            current = {
                "level": level,
                "number": number,
                "title": title,
                "guidance": "",
                "hints": {"needs_table": False, "needs_figure": False},
                "children": [],
            }
            nodes.append(current)
        else:
            if current is None:
                continue
            current["guidance"] = (current["guidance"] + "\n" + text).strip()
            h = _hints(current["guidance"])
            current["hints"] = h
    return nodes


def run(*, template_docx: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tree = parse_template(template_docx)
    dump_yaml(out_dir / "template.yaml", tree)
    mark_done(out_dir, {"top_level_nodes": len(tree)})
    return {"top_level_nodes": len(tree)}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest stages/s05_template/tests/test_runner.py -v`
Expected: 2 passed.

### Task C.2: stage 06 paper context extraction

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s06_context/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s06_context/tests/test_runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/prompts/paper_context.md`

This stage calls the **text** LLM once with the paper's abstract + intro to extract:
- title
- system / material composition
- key abbreviations and definitions
- 5–10 paper-specific keywords (used downstream to find caption-relevant chapters and to ground figure analysis)

- [ ] **Step 1: Write prompt template `llm/prompts/paper_context.md`**

```
SYSTEM:
You are a careful materials-science research assistant. Read a paper's abstract and introduction and return STRICT YAML (no markdown fence) describing the paper. Output ONLY the YAML; no preamble.

USER:
Abstract and introduction of the paper follow between <<< >>> markers.

<<<
{paper_text}
>>>

Return YAML with this exact schema:
title: <one-line English title>
system: <chemical formula or short system descriptor, e.g. "Ag(1-3x)La(x)Nb(0.9)Ta(0.1)O3 ceramics">
abbreviations:
  - {abbr: <abbr>, expansion: <full term>}
key_terms:
  - <term>
keywords:
  - <keyword>
critical_questions:
  - <one open question raised by the paper>
```

- [ ] **Step 2: Write failing test (mocked LLM)**

```python
# stages/s06_context/tests/test_runner.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s06_context.runner import run


def test_run_writes_context_yaml(tmp_path: Path):
    chapters = tmp_path / "ch"; chapters.mkdir()
    (chapters / "chapter_000_Preface.md").write_text(
        "Abstract\nWe study ANT-xLa.\n", encoding="utf-8"
    )
    (chapters / "chapter_001_Introduction.md").write_text(
        "1. Introduction\nThis paper is about ANT-xLa, a relaxor antiferroelectric.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content="title: ANT-xLa\nsystem: Ag(1-3x)LaxNb(0.9)Ta(0.1)O3\nabbreviations:\n  - {abbr: ANT, expansion: AgNbTaO3}\nkey_terms: [CAFE]\nkeywords: [antiferroelectric, lead-free]\ncritical_questions: [What is CAFE?]\n",
        usage={"total_tokens": 100},
        model="deepseek-chat",
        latency_ms=500.0,
    )
    with patch("stages.s06_context.runner.LLM", return_value=fake_llm):
        run(chapters_dir=chapters, out_dir=out_dir)

    data = yaml.safe_load((out_dir / "context.yaml").read_text(encoding="utf-8"))
    assert data["title"] == "ANT-xLa"
    assert data["system"].startswith("Ag")
    # Prompt + response are persisted for audit
    assert (out_dir / "paper_context.prompt.md").exists()
    assert (out_dir / "paper_context.response.json").exists()
```

- [ ] **Step 3: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s06_context/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `stages/s06_context/runner.py`**

```python
"""Stage 06: extract paper context (system, abbreviations, keywords) via text LLM."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from llm.client import LLM
from stages._common import dump_yaml, mark_done

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "paper_context.md"


def _gather_paper_text(chapters_dir: Path) -> str:
    pieces: list[str] = []
    for name in ("chapter_000_Preface.md", "chapter_001_Introduction.md"):
        p = chapters_dir / name
        if p.exists():
            pieces.append(p.read_text(encoding="utf-8"))
    if not pieces:
        for p in sorted(chapters_dir.glob("chapter_*.md"))[:2]:
            pieces.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(pieces)[:20000]


def _split_prompt(template_text: str, paper_text: str) -> tuple[str, str]:
    system_marker = "SYSTEM:"
    user_marker = "USER:"
    sys_idx = template_text.index(system_marker) + len(system_marker)
    user_idx = template_text.index(user_marker)
    system = template_text[sys_idx:user_idx].strip()
    user = template_text[user_idx + len(user_marker):].strip().replace("{paper_text}", paper_text)
    return system, user


def run(*, chapters_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paper_text = _gather_paper_text(chapters_dir)
    template_text = PROMPT_PATH.read_text(encoding="utf-8")
    system, user = _split_prompt(template_text, paper_text)

    (out_dir / "paper_context.prompt.md").write_text(
        f"# SYSTEM\n{system}\n\n# USER\n{user}", encoding="utf-8"
    )

    llm = LLM(role="text")
    response = llm.chat(system=system, user=user, max_tokens=1500)
    (out_dir / "paper_context.response.json").write_text(
        json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                    "usage": response.usage, "content": response.content},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    data = yaml.safe_load(response.content) if response.content.strip() else {}
    dump_yaml(out_dir / "context.yaml", data)
    mark_done(out_dir, {"tokens": response.usage.get("total_tokens")})
    return data
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest stages/s06_context/tests/test_runner.py -v`
Expected: 1 passed.

### Task C.3: stage 07 per-figure vision analysis

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s07_figure_analyze/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s07_figure_analyze/tests/test_runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/prompts/figure_analyze.md`

For each `Fig. N` in `figures.yaml`:
1. Find chapters that mention it (from `mentions.yaml`), extract ±2 paragraph windows
2. Build a prompt: paper context + caption + chapter excerpts
3. Call vision LLM with the image
4. Parse YAML response into `fig_notes.yaml`
5. Persist `<fig_id>.prompt.md` and `<fig_id>.response.json`

- [ ] **Step 1: Write prompt template `llm/prompts/figure_analyze.md`**

```
SYSTEM:
You are an expert reviewer analyzing one figure of a peer-reviewed paper. You must visually examine the image (it is provided as an inline image) and return STRICT YAML (no markdown fence) with critical insight, not just a translation of the caption.

USER:
Paper context:
{paper_context}

Figure id: {fig_id}
Caption (from OCR):
{caption}

Surrounding-text excerpts:
{chapter_excerpts}

Tasks:
1) Visually describe the panels, axes, units, value ranges, and visible trends.
2) For each surrounding-text claim about THIS figure, classify as supported / exaggerated / unsupported, with a 1-sentence reason.
3) Write a Chinese paragraph (100-220 characters) of deep critical observation — NOT a translation but an insight (a non-obvious visual feature, a methodological caveat, a missing comparison, or an internal inconsistency).
4) Same insight in 80-150-character English.
5) Suggest a Chinese caption (14-40 characters).

Return YAML with this exact schema:
fig_id: {fig_id}
visual_summary: <text>
text_claim_check:
  - claim: <text>
    verdict: supported | exaggerated | unsupported
    note: <text>
deep_observation_cn: <text>
deep_observation_en: <text>
caption_cn: <text>
```

- [ ] **Step 2: Write failing test**

```python
# stages/s07_figure_analyze/tests/test_runner.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s07_figure_analyze.runner import run


def test_run_per_figure_writes_notes(tmp_path: Path):
    # Synthetic inputs
    figs_dir = tmp_path / "figs"; figs_dir.mkdir()
    (figs_dir / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 1", "image_rel_path": "imgs/a.jpg",
         "image_abs_path": str(figs_dir / "a.jpg"), "caption": "phase diagram",
         "source_doc": "doc_0.md"},
    ], allow_unicode=True), encoding="utf-8")
    (figs_dir / "mentions.yaml").write_text(yaml.safe_dump({
        "chapter_003_Results.md": ["Fig. 1"],
    }, allow_unicode=True), encoding="utf-8")
    (figs_dir / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    (chapters_dir / "chapter_003_Results.md").write_text(
        "Fig. 1 shows the phase diagram.\n", encoding="utf-8"
    )

    context_dir = tmp_path / "ctx"; context_dir.mkdir()
    (context_dir / "context.yaml").write_text(
        "title: test\nsystem: X\nkey_terms: [a]\n", encoding="utf-8"
    )

    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content=(
            "fig_id: Fig. 1\n"
            "visual_summary: bar chart\n"
            "text_claim_check:\n"
            "  - {claim: x, verdict: supported, note: ok}\n"
            "deep_observation_cn: 深度观察\n"
            "deep_observation_en: deep observation\n"
            "caption_cn: 图1\n"
        ),
        usage={"total_tokens": 200},
        model="qwen-vl",
        latency_ms=1000.0,
    )
    with patch("stages.s07_figure_analyze.runner.LLM", return_value=fake_llm):
        run(figures_dir=figs_dir, chapters_dir=chapters_dir,
            context_dir=context_dir, out_dir=out_dir)

    notes = yaml.safe_load((out_dir / "fig_notes.yaml").read_text(encoding="utf-8"))
    assert notes[0]["fig_id"] == "Fig. 1"
    assert notes[0]["caption_cn"] == "图1"
    assert (out_dir / "Fig_1.prompt.md").exists()
    assert (out_dir / "Fig_1.response.json").exists()
```

- [ ] **Step 3: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s07_figure_analyze/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `stages/s07_figure_analyze/runner.py`**

```python
"""Stage 07: per-figure visual analysis using vision LLM. Outputs fig_notes.yaml."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from llm.client import LLM
from stages._common import dump_yaml, mark_done

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "figure_analyze.md"
FIG_NUM_RE = re.compile(r"Fig\.\s*(\d+)([a-z]?)")


def _excerpts(chapters_dir: Path, mentions: dict[str, list[str]], fig_id: str) -> str:
    m = FIG_NUM_RE.match(fig_id)
    if not m:
        return ""
    fig_num = m.group(1)
    pattern = re.compile(rf"\bFig(?:ure)?\.?\s*{fig_num}(?![0-9])", re.IGNORECASE)
    pieces: list[str] = []
    for ch_name, ids in mentions.items():
        if fig_id not in ids:
            continue
        ch_path = chapters_dir / ch_name
        if not ch_path.exists():
            continue
        paragraphs = re.split(r"\n\s*\n", ch_path.read_text(encoding="utf-8"))
        for i, p in enumerate(paragraphs):
            if pattern.search(p):
                start = max(0, i - 1)
                end = min(len(paragraphs), i + 2)
                pieces.append("\n\n".join(paragraphs[start:end]))
    return "\n\n---\n\n".join(pieces)[:6000]


def _split_prompt(template: str) -> tuple[str, str]:
    sys_idx = template.index("SYSTEM:") + len("SYSTEM:")
    usr_idx = template.index("USER:")
    return template[sys_idx:usr_idx].strip(), template[usr_idx + len("USER:"):].strip()


def _fid_to_filename(fig_id: str) -> str:
    return re.sub(r"[^\w-]+", "_", fig_id).strip("_")


def run(*, figures_dir: Path, chapters_dir: Path, context_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = yaml.safe_load((figures_dir / "figures.yaml").read_text(encoding="utf-8"))
    mentions = yaml.safe_load((figures_dir / "mentions.yaml").read_text(encoding="utf-8")) or {}
    context = yaml.safe_load((context_dir / "context.yaml").read_text(encoding="utf-8")) or {}

    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    paper_context_str = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)

    # Deduplicate by fig_id, keeping the first entry (cleanest caption)
    seen: set[str] = set()
    unique_figs: list[dict] = []
    for f in figures:
        if not f["fig_id"].startswith("Fig."):
            continue
        if f["fig_id"] in seen:
            continue
        seen.add(f["fig_id"])
        unique_figs.append(f)

    llm = LLM(role="vision")
    notes: list[dict] = []
    for f in unique_figs:
        fid = f["fig_id"]
        excerpts = _excerpts(chapters_dir, mentions, fid)
        user_msg = (user_tpl
                    .replace("{paper_context}", paper_context_str)
                    .replace("{fig_id}", fid)
                    .replace("{caption}", f.get("caption", ""))
                    .replace("{chapter_excerpts}", excerpts))
        fname = _fid_to_filename(fid)
        (out_dir / f"{fname}.prompt.md").write_text(
            f"# SYSTEM\n{system_tpl}\n\n# USER\n{user_msg}", encoding="utf-8"
        )
        img_path = Path(f["image_abs_path"])
        if not img_path.exists():
            # Try resolving relative to figures_dir
            img_path = figures_dir / f["image_rel_path"]
        response = llm.chat(system=system_tpl, user=user_msg,
                            images=[img_path] if img_path.exists() else [],
                            max_tokens=2000)
        (out_dir / f"{fname}.response.json").write_text(
            json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                        "usage": response.usage, "content": response.content},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            parsed = yaml.safe_load(response.content) or {}
            parsed.setdefault("fig_id", fid)
            parsed["image_abs_path"] = str(img_path)
            notes.append(parsed)
        except yaml.YAMLError as e:
            notes.append({"fig_id": fid, "error": f"yaml-parse: {e}",
                          "image_abs_path": str(img_path),
                          "raw": response.content})

    dump_yaml(out_dir / "fig_notes.yaml", notes)
    mark_done(out_dir, {"figures": len(notes)})
    return {"figures": len(notes)}
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest stages/s07_figure_analyze/tests/test_runner.py -v`
Expected: 1 passed.

### Task C.4: stage 08 per-section composition

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s08_section_compose/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s08_section_compose/tests/test_runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/llm/prompts/section_compose.md`

For each top-level template node:
1. Gather relevant chapter excerpts (by keyword overlap between node title/guidance and chapter content) and relevant figure notes (by caption/fig_id overlap with node guidance)
2. Build prompt with: paper_context + section title + guidance + hints + gathered evidence
3. Call text LLM
4. Save section body as `chapters/<NN>-<slug>.md` (mypaper file-naming convention)

- [ ] **Step 1: Write prompt template `llm/prompts/section_compose.md`**

```
SYSTEM:
You are a critical-review writer for a materials-science journal. Given a paper's content, figure notes, and an outline section's guidance, write the section body in fluent Chinese with embedded English technical terms. Follow these rules:
- Length: 250-500 Chinese characters per top-level section unless the guidance asks otherwise
- Cite figures by short id (e.g., "图3", "Fig. 3") when the figure notes are relevant
- Echo and ground the guidance — do not paraphrase, develop the argument
- If figure_notes contain non-supported text_claim_check verdicts, surface them as critical points
- Return ONLY the body text (no markdown headings; the orchestrator adds the heading)

USER:
Paper context:
{paper_context}

Section to write:
- Number: {number}
- Title (CN): {title_cn}
- Title (EN): {title_en}
- Guidance: {guidance}
- Hints: needs_table={needs_table}; needs_figure={needs_figure}

Relevant paper chapter excerpts:
{chapter_excerpts}

Relevant figure notes (YAML):
{fig_notes_block}

Write the section body now.
```

- [ ] **Step 2: Write failing test**

```python
# stages/s08_section_compose/tests/test_runner.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s08_section_compose.runner import run


def test_run_writes_chapters(tmp_path: Path):
    # Inputs
    tpl_dir = tmp_path / "tpl"; tpl_dir.mkdir()
    (tpl_dir / "template.yaml").write_text(yaml.safe_dump([
        {"level": 1, "number": "1", "title": "Introduction",
         "guidance": "why important", "hints": {"needs_table": False, "needs_figure": False},
         "children": []},
        {"level": 1, "number": "2", "title": "Structures",
         "guidance": "domain structures", "hints": {"needs_table": False, "needs_figure": True},
         "children": []},
    ], allow_unicode=True), encoding="utf-8")

    ctx_dir = tmp_path / "ctx"; ctx_dir.mkdir()
    (ctx_dir / "context.yaml").write_text("title: test\nsystem: X\n", encoding="utf-8")

    ch_dir = tmp_path / "ch"; ch_dir.mkdir()
    (ch_dir / "chapter_003_Results.md").write_text("domain micro-structure stuff", encoding="utf-8")

    fig_dir = tmp_path / "fig"; fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 4", "deep_observation_cn": "畴", "caption_cn": "TEM"},
    ], allow_unicode=True), encoding="utf-8")
    (fig_dir.parent / "figures_stage").mkdir()
    (fig_dir.parent / "figures_stage" / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 4", "caption": "TEM bright field", "image_abs_path": "/tmp/a.jpg"}
    ], allow_unicode=True), encoding="utf-8")

    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content="本节正文 …",
        usage={"total_tokens": 50}, model="deepseek-chat", latency_ms=400.0,
    )
    with patch("stages.s08_section_compose.runner.LLM", return_value=fake_llm):
        run(template_dir=tpl_dir, chapters_dir=ch_dir, context_dir=ctx_dir,
            fig_notes_dir=fig_dir, figures_stage_dir=fig_dir.parent / "figures_stage",
            out_dir=out_dir)

    out_chapters = sorted((out_dir / "chapters").glob("*.md"))
    assert len(out_chapters) == 2
    assert out_chapters[0].read_text(encoding="utf-8").startswith("# 1")
    assert "本节正文" in out_chapters[0].read_text(encoding="utf-8")
```

- [ ] **Step 3: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s08_section_compose/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `stages/s08_section_compose/runner.py`**

```python
"""Stage 08: write per-section Chinese body via text LLM, driven by template."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from llm.client import LLM
from stages._common import dump_yaml, mark_done, slugify

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "section_compose.md"


def _split_prompt(template: str) -> tuple[str, str]:
    sys_idx = template.index("SYSTEM:") + len("SYSTEM:")
    usr_idx = template.index("USER:")
    return template[sys_idx:usr_idx].strip(), template[usr_idx + len("USER:"):].strip()


def _keyword_score(text: str, keywords: list[str]) -> int:
    return sum(text.lower().count(k.lower()) for k in keywords if k)


def _relevant_chapter_excerpts(chapters_dir: Path, keywords: list[str], top_k: int = 2) -> str:
    scored: list[tuple[int, str]] = []
    for p in sorted(chapters_dir.glob("chapter_*.md")):
        text = p.read_text(encoding="utf-8")
        scored.append((_keyword_score(text, keywords), text))
    scored.sort(key=lambda t: -t[0])
    selected = [t for s, t in scored[:top_k] if s > 0]
    if not selected:
        # Fall back: include results chapter or first content chapter
        for p in sorted(chapters_dir.glob("chapter_*.md")):
            if "Results" in p.name or "Introduction" in p.name:
                selected.append(p.read_text(encoding="utf-8"))
                break
    return "\n\n---\n\n".join(selected)[:8000]


def _relevant_fig_notes(fig_notes: list[dict], figures: list[dict], keywords: list[str]) -> str:
    captions_by_fid = {f["fig_id"]: f.get("caption", "") for f in figures}
    scored: list[tuple[int, dict]] = []
    for note in fig_notes:
        fid = note.get("fig_id", "")
        cap = captions_by_fid.get(fid, "")
        score = _keyword_score(cap + " " + note.get("deep_observation_cn", ""), keywords)
        scored.append((score, note))
    scored.sort(key=lambda t: -t[0])
    picked = [n for s, n in scored[:3] if s > 0]
    return yaml.safe_dump(picked, allow_unicode=True, sort_keys=False) if picked else "(none)"


def run(*, template_dir: Path, chapters_dir: Path, context_dir: Path,
        fig_notes_dir: Path, figures_stage_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_chapters = out_dir / "chapters"
    out_chapters.mkdir(exist_ok=True)
    for stale in out_chapters.glob("*.md"):
        stale.unlink()

    template = yaml.safe_load((template_dir / "template.yaml").read_text(encoding="utf-8")) or []
    context = yaml.safe_load((context_dir / "context.yaml").read_text(encoding="utf-8")) or {}
    fig_notes = yaml.safe_load((fig_notes_dir / "fig_notes.yaml").read_text(encoding="utf-8")) or []
    figures = yaml.safe_load((figures_stage_dir / "figures.yaml").read_text(encoding="utf-8")) or []

    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    paper_context_str = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)

    llm = LLM(role="text")
    written: list[str] = []
    for idx, node in enumerate(template):
        title_cn = node["title"]
        title_en = node["title"]
        guidance = node.get("guidance", "")
        hints = node.get("hints", {})
        keywords = re.findall(r"[A-Za-z一-鿿-]{3,}", f"{title_cn} {guidance}")

        excerpts = _relevant_chapter_excerpts(chapters_dir, keywords)
        notes_block = _relevant_fig_notes(fig_notes, figures, keywords)

        user_msg = (user_tpl
                    .replace("{paper_context}", paper_context_str)
                    .replace("{number}", str(node.get("number", idx + 1)))
                    .replace("{title_cn}", title_cn)
                    .replace("{title_en}", title_en)
                    .replace("{guidance}", guidance)
                    .replace("{needs_table}", str(hints.get("needs_table", False)))
                    .replace("{needs_figure}", str(hints.get("needs_figure", False)))
                    .replace("{chapter_excerpts}", excerpts)
                    .replace("{fig_notes_block}", notes_block))

        slug = slugify(title_cn, maxlen=30)
        basename = f"{idx + 1:02d}-{slug}"
        (out_dir / f"{basename}.prompt.md").write_text(
            f"# SYSTEM\n{system_tpl}\n\n# USER\n{user_msg}", encoding="utf-8"
        )
        response = llm.chat(system=system_tpl, user=user_msg, max_tokens=3000)
        (out_dir / f"{basename}.response.json").write_text(
            json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                        "usage": response.usage, "content": response.content},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_file = out_chapters / f"{basename}.md"
        heading = f"# {node.get('number', idx + 1)} {title_cn}\n\n"
        md_file.write_text(heading + response.content.strip() + "\n", encoding="utf-8")
        written.append(md_file.name)

    dump_yaml(out_dir / "written.yaml", written)
    mark_done(out_dir, {"sections": len(written)})
    return {"sections": len(written)}
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest stages/s08_section_compose/tests/test_runner.py -v`
Expected: 1 passed.

### Task C.5: stage 09 render (mypaper bundle + preview docx)

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s09_render/runner.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/stages/s09_render/tests/test_runner.py`

Produces TWO artifacts:
- `mypaper_bundle/chapters/*.md` + `mypaper_bundle/figures/*.jpg` (copied from s07 image_abs_path) + `mypaper_bundle/README.md` (drop-in instructions for mypaper)
- `preview.docx` self-rendered with python-docx, embedding the section text and figures

- [ ] **Step 1: Write failing test**

```python
# stages/s09_render/tests/test_runner.py
from pathlib import Path

import yaml
from docx import Document
from PIL import Image

from stages.s09_render.runner import run


def test_run_produces_bundle_and_preview(tmp_path: Path):
    compose_dir = tmp_path / "compose"; compose_dir.mkdir()
    (compose_dir / "chapters").mkdir()
    (compose_dir / "chapters" / "01-intro.md").write_text(
        "# 1 引言\n\n这是引言。\n", encoding="utf-8"
    )
    (compose_dir / "chapters" / "02-results.md").write_text(
        "# 2 结果\n\n这是结果。\n", encoding="utf-8"
    )

    fig_dir = tmp_path / "fig"; fig_dir.mkdir()
    img_path = tmp_path / "imgs" / "a.jpg"; img_path.parent.mkdir()
    Image.new("RGB", (200, 100), "blue").save(img_path)
    (fig_dir / "fig_notes.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 1", "image_abs_path": str(img_path),
         "caption_cn": "图1: 测试",
         "deep_observation_cn": "观察",
         "text_claim_check": [{"claim": "x", "verdict": "supported", "note": "ok"}]},
    ], allow_unicode=True), encoding="utf-8")

    out_dir = tmp_path / "out"
    run(compose_dir=compose_dir, fig_notes_dir=fig_dir, out_dir=out_dir,
        paper_title="测试论文")

    bundle = out_dir / "mypaper_bundle"
    assert (bundle / "chapters" / "01-intro.md").exists()
    assert (bundle / "chapters" / "02-results.md").exists()
    assert (bundle / "figures" / "a.jpg").exists()
    assert (bundle / "README.md").exists()

    preview = out_dir / "preview.docx"
    assert preview.exists() and preview.stat().st_size > 4000
    d = Document(preview)
    text = "\n".join(p.text for p in d.paragraphs)
    assert "引言" in text and "结果" in text
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest stages/s09_render/tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stages/s09_render/runner.py`**

```python
"""Stage 09: render mypaper-compatible bundle + self-contained preview docx."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from stages._common import dump_yaml, mark_done

BUNDLE_README = """\
# mypaper bundle

Drop this folder's contents into mypaper/ to render the styled thesis:

    cp -r chapters/* /path/to/mypaper/chapters/
    cp -r figures/*  /path/to/mypaper/figures/
    cd /path/to/mypaper && uv run python scripts/build.py

The README of mypaper has the full template-swap instructions.
"""


def _cn_font(run, size=10.5, bold=False, color=None):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.append(rf)
    rf.set(qn("w:eastAsia"), "宋体")
    rf.set(qn("w:ascii"), "Times New Roman")
    rf.set(qn("w:hAnsi"), "Times New Roman")


def _render_preview_docx(*, compose_dir: Path, fig_notes: list[dict],
                         out_path: Path, paper_title: str) -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    sec.left_margin = sec.right_margin = Cm(2.2)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _cn_font(p.add_run(paper_title), size=16, bold=True)

    fig_by_id = {n["fig_id"]: n for n in fig_notes}

    for ch in sorted((compose_dir / "chapters").glob("*.md")):
        text = ch.read_text(encoding="utf-8")
        lines = text.splitlines()
        i = 0
        if lines and lines[0].startswith("# "):
            heading = lines[0][2:].strip()
            p = doc.add_paragraph()
            _cn_font(p.add_run(heading), size=14, bold=True)
            i = 1
        body = "\n".join(lines[i:]).strip()
        for para in body.split("\n\n"):
            if not para.strip():
                continue
            p = doc.add_paragraph()
            p.paragraph_format.first_line_indent = Cm(0.74)
            _cn_font(p.add_run(para.strip()), size=10.5)
        # Inline-embed figures that this section references by Fig.N substring
        for fid, note in fig_by_id.items():
            if fid in body and Path(note["image_abs_path"]).exists():
                ip = doc.add_paragraph(); ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ip.add_run().add_picture(note["image_abs_path"], width=Cm(13))
                cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _cn_font(cap.add_run(note.get("caption_cn", fid)), size=9, bold=True)
                if note.get("deep_observation_cn"):
                    obs = doc.add_paragraph()
                    _cn_font(obs.add_run(f"【深度观察】{note['deep_observation_cn']}"),
                             size=9, color=(0x33, 0x33, 0x66))
    doc.save(out_path)


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / "mypaper_bundle"
    (bundle / "chapters").mkdir(parents=True, exist_ok=True)
    (bundle / "figures").mkdir(exist_ok=True)

    # Copy chapters
    for md in (compose_dir / "chapters").glob("*.md"):
        shutil.copy2(md, bundle / "chapters" / md.name)

    # Copy figures referenced by notes
    fig_notes = yaml.safe_load((fig_notes_dir / "fig_notes.yaml").read_text(encoding="utf-8")) or []
    for note in fig_notes:
        ap = Path(note.get("image_abs_path", ""))
        if ap.exists():
            shutil.copy2(ap, bundle / "figures" / ap.name)

    (bundle / "README.md").write_text(BUNDLE_README, encoding="utf-8")

    preview = out_dir / "preview.docx"
    _render_preview_docx(compose_dir=compose_dir, fig_notes=fig_notes,
                         out_path=preview, paper_title=paper_title)

    mark_done(out_dir, {
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
        "preview_bytes": preview.stat().st_size,
    })
    return {"preview": str(preview), "bundle": str(bundle)}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest stages/s09_render/tests/test_runner.py -v`
Expected: 1 passed.

---

## Phase D — CLI + cleanup + end-to-end

### Task D.1: cli.py orchestrator

**Files:**
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/cli.py`
- Create: `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_cli.py`

The CLI exposes ONE primary command, `run`, that wires all 9 stages:

```
python -m cli run --pdf <path> --template <docx> [--paper-id <slug>] [--runs-dir runs/] [--skip-ocr] [--force]
```

It loads `.env`, decides `paper_id` (slug of PDF name unless overridden), creates `runs/<id>/<NN_name>/` per stage, runs stages in order, and writes a `meta.yaml` summarizing the run.

- [ ] **Step 1: Write failing test (no live calls — stages mocked)**

```python
# tests/test_cli.py
from pathlib import Path
from unittest.mock import patch

import yaml

from cli import main


def test_cli_run_creates_run_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PADDLEOCR_TOKEN", "fake")
    monkeypatch.setenv("LLM_VISION_API_KEY", "fake")
    monkeypatch.setenv("LLM_TEXT_API_KEY", "fake")

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    tpl = tmp_path / "tpl.docx"
    from docx import Document
    d = Document(); d.add_paragraph("Outline"); d.save(tpl)

    runs_dir = tmp_path / "runs"

    # Mock each stage's run() to a no-op that creates the expected output marker
    def mk_runner(name):
        def fake_run(**kwargs):
            outd = kwargs.get("out_dir") or kwargs.get("out_dir") or Path("/tmp")
            outd.mkdir(parents=True, exist_ok=True)
            (outd / "done.yaml").write_text("ok\n", encoding="utf-8")
            return {"name": name}
        return fake_run

    targets = [
        "stages.s01_ocr.runner.run",
        "stages.s02_clean.runner.run",
        "stages.s03_chapter.runner.run",
        "stages.s04_figures.runner.run",
        "stages.s05_template.runner.run",
        "stages.s06_context.runner.run",
        "stages.s07_figure_analyze.runner.run",
        "stages.s08_section_compose.runner.run",
        "stages.s09_render.runner.run",
    ]
    patches = [patch(t, mk_runner(t)) for t in targets]
    for pp in patches:
        pp.start()
    try:
        rc = main([
            "run",
            "--pdf", str(pdf),
            "--template", str(tpl),
            "--runs-dir", str(runs_dir),
            "--paper-id", "paper",
        ])
    finally:
        for pp in patches:
            pp.stop()

    assert rc == 0
    meta = yaml.safe_load((runs_dir / "paper" / "meta.yaml").read_text(encoding="utf-8"))
    assert meta["paper_id"] == "paper"
    assert meta["stages_completed"] == [t.rsplit(".", 2)[0].split(".")[1] for t in targets]
```

- [ ] **Step 2: Run, expect ImportError**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: ImportError on `cli`.

- [ ] **Step 3: Implement `cli.py`**

```python
"""paper2md CLI: orchestrates the 9 stages over (pdf, template) -> (bundle + preview)."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from stages._common import dump_yaml, slugify, stage_dir, is_done

# Import each stage runner via its package
from stages.s01_ocr.runner import run as s01_run
from stages.s02_clean.runner import run as s02_run
from stages.s03_chapter.runner import run as s03_run
from stages.s04_figures.runner import run as s04_run
from stages.s05_template.runner import run as s05_run
from stages.s06_context.runner import run as s06_run
from stages.s07_figure_analyze.runner import run as s07_run
from stages.s08_section_compose.runner import run as s08_run
from stages.s09_render.runner import run as s09_run

STAGE_ORDER = [
    "s01_ocr", "s02_clean", "s03_chapter", "s04_figures",
    "s05_template", "s06_context", "s07_figure_analyze",
    "s08_section_compose", "s09_render",
]


def _run_one(args, name: str, run_root: Path, paper_id: str) -> None:
    out = stage_dir(run_root, paper_id, name)
    if is_done(out) and not args.force:
        print(f"[skip] {name} (already done)")
        return
    print(f"[run]  {name}")
    if name == "s01_ocr":
        if args.skip_ocr:
            print("        --skip-ocr set; expecting upstream artifacts present")
            return
        s01_run(pdf=Path(args.pdf), out_dir=out, token=os.environ["PADDLEOCR_TOKEN"])
    elif name == "s02_clean":
        s02_run(in_dir=stage_dir(run_root, paper_id, "s01_ocr"), out_dir=out)
    elif name == "s03_chapter":
        s03_run(in_dir=stage_dir(run_root, paper_id, "s02_clean"), out_dir=out, min_chars=1)
    elif name == "s04_figures":
        s04_run(
            docs_dir=stage_dir(run_root, paper_id, "s02_clean"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            out_dir=out,
        )
    elif name == "s05_template":
        s05_run(template_docx=Path(args.template), out_dir=out)
    elif name == "s06_context":
        s06_run(
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            out_dir=out,
        )
    elif name == "s07_figure_analyze":
        s07_run(
            figures_dir=stage_dir(run_root, paper_id, "s04_figures"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            context_dir=stage_dir(run_root, paper_id, "s06_context"),
            out_dir=out,
        )
    elif name == "s08_section_compose":
        s08_run(
            template_dir=stage_dir(run_root, paper_id, "s05_template"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            context_dir=stage_dir(run_root, paper_id, "s06_context"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            figures_stage_dir=stage_dir(run_root, paper_id, "s04_figures"),
            out_dir=out,
        )
    elif name == "s09_render":
        s09_run(
            compose_dir=stage_dir(run_root, paper_id, "s08_section_compose"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            out_dir=out,
            paper_title=args.paper_id or Path(args.pdf).stem,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paper2md")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the full pipeline on one (pdf, template) pair")
    r.add_argument("--pdf", required=True)
    r.add_argument("--template", required=True)
    r.add_argument("--runs-dir", default="runs")
    r.add_argument("--paper-id", default=None)
    r.add_argument("--skip-ocr", action="store_true",
                   help="Assume s01_ocr outputs already exist in the run dir")
    r.add_argument("--force", action="store_true",
                   help="Re-run stages even if done.yaml is present")
    args = ap.parse_args(argv)

    if args.cmd != "run":
        ap.print_help()
        return 1

    load_dotenv(Path.cwd() / ".env", override=False)
    paper_id = args.paper_id or slugify(Path(args.pdf).stem)
    run_root = Path(args.runs_dir)
    run_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    for name in STAGE_ORDER:
        _run_one(args, name, run_root, paper_id)

    meta = {
        "paper_id": paper_id,
        "pdf": str(Path(args.pdf).resolve()),
        "template": str(Path(args.template).resolve()),
        "runs_dir": str(run_root.resolve()),
        "stages_completed": STAGE_ORDER,
        "duration_s": time.time() - t0,
    }
    dump_yaml(run_root / paper_id / "meta.yaml", meta)
    print(f"[done] {paper_id} in {meta['duration_s']:.1f}s → {run_root / paper_id / 's09_render' / 'preview.docx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: 1 passed.

- [ ] **Step 5: Full suite green**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests pass (incl. previous task tests), live tests still skipped.

### Task D.2: Delete legacy files

**Files (DELETE):**
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_clean.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_chapter.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_patterns.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_figures.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_mapping.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/paper2md_analyze.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/make_summary.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_clean.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_chapter_science.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_figures.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/tests/test_analyze.py`
- `/Users/zhangjiedong/codeFiles/article/paper2md/参考文献/弛豫反铁电/he2023_out/compose_v2.py` (no longer needed; v2 docx kept as golden)

**Files (MODIFY):**
- `/Users/zhangjiedong/codeFiles/article/paper2md/pyproject.toml` — update `[tool.setuptools]` `py-modules` list to remove deleted modules

- [ ] **Step 1: Delete all listed files**

```bash
cd /Users/zhangjiedong/codeFiles/article/paper2md
rm paper2md.py paper2md_clean.py paper2md_chapter.py paper2md_patterns.py paper2md_figures.py paper2md_mapping.py paper2md_analyze.py make_summary.py
rm tests/test_clean.py tests/test_chapter_science.py tests/test_figures.py tests/test_analyze.py
rm 参考文献/弛豫反铁电/he2023_out/compose_v2.py
```

- [ ] **Step 2: Update pyproject.toml**

Replace the `[tool.setuptools]` block at the end of `pyproject.toml` with:

```toml
[tool.setuptools]
packages = ["stages", "llm",
            "stages.s01_ocr", "stages.s02_clean", "stages.s03_chapter",
            "stages.s04_figures", "stages.s05_template", "stages.s06_context",
            "stages.s07_figure_analyze", "stages.s08_section_compose", "stages.s09_render",
            "llm.prompts"]
```

Remove the old `[project.scripts]` entry `paper2md = "paper2md:main"` (the module is gone) or replace it with:
```toml
[project.scripts]
paper2md = "cli:main"
```

- [ ] **Step 3: Reinstall + confirm**

```bash
uv pip install -e '.[dev]' --python .venv/bin/python --reinstall
.venv/bin/python -c "import cli; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Run full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: ≥ 20 passed; 2 live tests skipped.

### Task D.3: End-to-end live run on He 2023

**Files:** none modified; this is an operational acceptance run.

Requires: `.env` with `PADDLEOCR_TOKEN`, `LLM_VISION_API_KEY`, `LLM_TEXT_API_KEY`.

- [ ] **Step 1: Use existing He 2023 OCR artifacts**

The previous plan's `参考文献/弛豫反铁电/he2023_out/imgs/` directory contains the extracted images. We need `doc_*.md` too; if cleanup removed them, re-run s01_ocr.

Inspect:
```bash
ls 参考文献/弛豫反铁电/he2023_out/imgs/ | wc -l   # expect 40
ls 参考文献/弛豫反铁电/he2023_out/*.md 2>/dev/null
```

If no `doc_*.md`, we need a fresh OCR run. Otherwise we can pre-stage:
```bash
mkdir -p runs/he2023/s01_ocr/imgs
cp 参考文献/弛豫反铁电/he2023_out/imgs/* runs/he2023/s01_ocr/imgs/ 2>/dev/null
# Without doc_*.md we must re-OCR. Set --skip-ocr only if doc_*.md present.
```

- [ ] **Step 2: Run the pipeline**

```bash
set -a; source .env; set +a
.venv/bin/python -m cli run \
  --pdf "参考文献/弛豫反铁电/A.He 等 - 2023 - Superior energy storage properties with thermal stability in lead-free ceramics by constructing an a.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --runs-dir runs \
  --paper-id he2023
```

Expected: completes in ~3–10 min (OCR + 8 vision + N text calls). Output: `runs/he2023/s09_render/preview.docx` + `runs/he2023/s09_render/mypaper_bundle/`.

- [ ] **Step 3: Acceptance assertions**

```bash
.venv/bin/python -c "
import yaml, pathlib
o = pathlib.Path('runs/he2023')
meta = yaml.safe_load((o / 'meta.yaml').read_text(encoding='utf-8'))
assert meta['paper_id'] == 'he2023'
figs = yaml.safe_load((o / 's04_figures' / 'figures.yaml').read_text())
fig_only = [f for f in figs if f['fig_id'].startswith('Fig.')]
print(f'figures detected: {len(fig_only)}')
notes = yaml.safe_load((o / 's07_figure_analyze' / 'fig_notes.yaml').read_text())
print(f'fig_notes generated: {len(notes)}')
preview = o / 's09_render' / 'preview.docx'
print(f'preview bytes: {preview.stat().st_size}')
bundle = o / 's09_render' / 'mypaper_bundle'
chap_count = len(list((bundle / 'chapters').glob('*.md')))
print(f'bundle chapters: {chap_count}')
assert len(fig_only) >= 6
assert len(notes) >= 6
assert preview.stat().st_size > 50000
assert chap_count >= 3
print('ok')
"
```
Expected: `ok` with figures ≥6, notes ≥6, preview > 50 kB, chapters ≥3.

- [ ] **Step 4: Compare against golden**

Open both:
- `runs/he2023/s09_render/preview.docx`
- `参考文献/弛豫反铁电/Summary_He_2023_ANT-CAFE_深度分析_v2.docx` (golden)

Spot-check: does the new preview cover the same template sections (Introduction / Antiferroelectrics / Structures / Dielectric / Polarization / Applications / Discussion / Conclusions)? Note any deviations.

---

## Self-Review

**1. Spec coverage**

- "Folder-per-stage architecture": Tasks A.2 (skeleton), B.1-B.4 (port stages 01-04), C.1-C.5 (new stages 05-09). ✓
- "YAML for intermediate artifacts": all 9 stages use YAML (figures.yaml, mentions.yaml, template.yaml, context.yaml, fig_notes.yaml, written.yaml, meta.yaml). ✓
- "OpenAI-compatible client with vision + text roles": Task A.3 + A.4 (live smoke). ✓
- "Template extraction (title + guidance + hints)": Task C.1 (`_NEEDS_TABLE_RE`, `_NEEDS_FIGURE_RE`). ✓
- "Per-figure vision analysis driven by template-derived context": Task C.3 (paper_context.yaml injected; chapter excerpts gathered automatically). ✓
- "Per-section text composition": Task C.4. ✓
- "mypaper bundle + preview docx": Task C.5. ✓
- "Stage idempotency / resumability": `is_done()` + `done.yaml` markers + `--force` flag in CLI. ✓
- "LLM call audit (prompt + response per call persisted)": Tasks C.2/C.3/C.4 each write `*.prompt.md` and `*.response.json`. ✓
- "Single CLI entry point": Task D.1. ✓
- "Delete old paper2md_*.py": Task D.2. ✓
- "Live end-to-end test on He 2023": Task D.3. ✓

**2. Placeholder scan**

- No "TBD" / "TODO" / "implement later" — every step has exact code or exact command.
- Test code for every implementation step.
- Tests for stages 06/07/08 use mocked LLMs, so no live keys needed during default test runs.
- D.3 acceptance assertions are concrete (`figures >= 6`, `preview > 50 kB`).
- Note: Task B.1 uses an alias path (`stages.s01_ocr` not `stages.01_ocr`) — addressed by renaming folders to `sNN_*` (valid Python identifiers). The rename is in Task B.1 Step 2.

**3. Type / signature consistency**

- All stages expose `run(*, ...) -> dict`. CLI dispatches by stage name. ✓
- LLM.chat signature: `chat(*, system, user, images=(), temperature=0.2, max_tokens=2000) -> LLMResponse`. Used identically in stages 06/07/08. ✓
- YAML field names consistent across stages: `fig_id`, `image_abs_path`, `caption`, `caption_cn`, `deep_observation_cn`. ✓
- `figures_stage_dir` in stage 08 reads `figures.yaml` from stage 04's output dir — naming makes that explicit. ✓
- `mark_done` / `is_done` from `_common.py` used by every stage. ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-paper2md-stages-restructure.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute tasks in this session using superpowers:executing-plans with checkpoints.

Which approach?
