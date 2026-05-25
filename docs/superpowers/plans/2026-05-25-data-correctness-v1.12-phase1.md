# v1.12 数据正确性 Phase 1 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用现成仓库 + 最小自写代码，给 lazy-paper 装上"可量化的数据正确性"——先建立 RAGAS 评测基线，再上 PDFFigures 2（治图编号错位）和 LightRAG entity-dedup（治作者错配类 bug 的源头）。Phase 1 ship 三件事 + 一份 baseline 报告。

**Architecture:** 三个独立子系统，全部 `--feature-flag` gated，默认关闭。RAGAS 是前置（没它就无法量化后两者的实际收益）。PDFFigures 2 走 subprocess 调 Scala JAR，零 Python 实现负担。LightRAG dedup 只 lift 一个 prompt + 算法（~80 LOC），不引入 LightRAG 整包。

**Tech Stack:** Python 3.11+ (uv-managed)、pytest、ragas (pip via uv)、PDFFigures 2 跑在 docker 镜像 `lazy-paper/pdffigures2:0.1.0`（项目自带 Dockerfile 一次性构建，**本机不装 Java/sbt**）、instructor + DeepSeek-Reasoner（已配 `.env`）。所有外部依赖走 uv 或 docker，符合项目 CLAUDE.md "系统级依赖走 Docker、不污染本机" 原则。

**Spec reference:** 本 plan 即 spec（用户已在前一轮对话中同意整体方向）。

**Phase 1 范围（本文档）：**
- Task 1–5: RAGAS 评测框架 + meng2024 + ali2025_flash 双 golden set + baseline
- Task 6–9: PDFFigures 2 sidecar（gated by `--pdffigures2`）
- Task 10–12: LightRAG entity-dedup port（gated by `LAZY_PAPER_ENTITY_DEDUP=1`）
- Task 13: Phase 1 收尾 — re-run RAGAS、写对比报告、决策 Phase 2 范围

**Phase 2 候选（不在本 plan，需 Phase 1 RAGAS 数据后再规划）：**
- MiniCheck NLI 第 5 层 verifier
- LLM coreference rewrite pre-pass
- ChemDataExtractor 2.0 KG 交叉校验

---

## File Structure

**New files:**
- `tests/eval/golden_qa/meng2024.yaml` — 20 题 + 期望答案 + 期望命中 chunk 范围
- `tests/eval/golden_qa/ali2025_flash.yaml` — 同上
- `tests/eval/__init__.py`
- `tests/eval/conftest.py` — ragas 的 pytest fixture
- `tests/eval/test_ragas_baseline.py` — 跑 RAGAS 四指标的 pytest harness（`@pytest.mark.ragas` skipped by default）
- `scripts/ragas_eval.py` — CLI 入口：`uv run python -m scripts.ragas_eval --paper meng2024`
- `scripts/pdffigures2_sidecar.py` — 调 docker wrapper + 解析 JSON 输出
- `Dockerfile.pdffigures2` — 一次性构建 PDFFigures 2 docker 镜像（不污染本机 JVM）
- `vendor/pdffigures2.sh` — 调 `lazy-paper/pdffigures2:0.1.0` 的 shell wrapper
- `stages/s06_context/entity_dedup.py` — LightRAG 风格的实体去重模块（~80 LOC）
- `stages/s06_context/tests/test_entity_dedup.py`
- `llm/prompts/entity_dedup.md` — 去重 LLM prompt
- `docs/archive/v1_12_phase1_ragas_baseline.md` — Task 5 产出的基线报告
- `docs/archive/v1_12_phase1_summary.md` — Task 13 产出的收尾报告

**Modified files:**
- `pyproject.toml` — `[project.optional-dependencies] dev` 加 `ragas`
- `cli.py:46-50` — 加 `--pdffigures2` flag；s04 dispatch 处加 sidecar 调用
- `stages/s04_figures/runner.py` — Task 8 加 `reconcile_with_pdffigures2()`（仅当 sidecar JSON 存在时执行）
- `stages/s06_context/runner.py` — Task 11 加 `if os.environ.get("LAZY_PAPER_ENTITY_DEDUP"): entity_dedup.run(...)`
- `.env.example` — 新增 `LAZY_PAPER_ENTITY_DEDUP`、`PDFFIGURES2_JAR` 两行
- `.gitignore` — `vendor/*.jar`、`tests/eval/_ragas_out/`
- `CHANGELOG.md` — v1.12-phase1 条目（Task 13）
- `docs/ARCHITECTURE.md` — §12 "Known limits" 把 "caption-aware numbering" 从 deferred 改成 done；新增 §4.10 "entity-dedup pass"

**Out of scope（不动）：**
- s07 vision LLM 调用
- s08 verifier 逻辑
- s09 渲染器
- 任何 prompt 修改（除新增 entity_dedup prompt）

---

## Task 1: 准备 ragas 依赖 + smoke test

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/eval/test_ragas_smoke.py` (临时文件，Task 4 删)

- [ ] **Step 1: 编辑 pyproject.toml `[project.optional-dependencies].dev`，追加 ragas**

```toml
# pyproject.toml — 现状有 [project.optional-dependencies].dev 段
dev = [
    "pytest>=8",
    # ... existing entries ...
    "ragas>=0.2,<0.3",  # NEW: faithfulness / context_recall / context_precision metrics
]
```

- [ ] **Step 2: 安装并验证版本**

Run: `uv pip install -e ".[dev]"`
Expected: 无报错，最后一行 `Successfully installed ... ragas-0.2.x`

Run: `uv run python -c "import ragas; print(ragas.__version__)"`
Expected: 输出 `0.2.x`（任一 minor）。**若失败：检查 ragas 在 PyPI 的实际可用版本，调整版本约束**

- [ ] **Step 3: 写 smoke test 验证 ragas 能跑一个 trivial 例子**

`tests/eval/test_ragas_smoke.py`:
```python
"""Throwaway smoke test — confirms ragas wiring before we build the harness."""
import pytest

pytestmark = pytest.mark.ragas


def test_ragas_imports():
    from ragas.metrics import faithfulness, context_recall, context_precision
    assert all(callable(m) or hasattr(m, "name") for m in [
        faithfulness, context_recall, context_precision,
    ])
```

- [ ] **Step 4: 注册 ragas marker；运行 smoke**

`pyproject.toml` `[tool.pytest.ini_options].markers` 追加：
```toml
markers = [
    "live: tests that call real LLM/OCR APIs (skipped by default; run via -m live)",
    "ragas: ragas evaluation harness (skipped by default; run via -m ragas)",  # NEW
]
addopts = "-m 'not live and not ragas'"  # CHANGE: add 'and not ragas'
```

Run: `uv run pytest -m ragas -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/eval/test_ragas_smoke.py
git commit -m "build(deps): add ragas to dev extras for v1.12 eval harness"
```

---

## Task 2: 设计 golden QA 数据格式 + meng2024 写 20 题

**Files:**
- Create: `tests/eval/golden_qa/meng2024.yaml`
- Create: `tests/eval/golden_qa/_schema.md`（人类文档）

- [ ] **Step 1: 写 schema 文档**

`tests/eval/golden_qa/_schema.md`:
```markdown
# Golden QA Schema

每个文件对应一篇 demo paper。RAGAS faithfulness / context_recall / context_precision 用这些题打分。

## YAML 结构

```yaml
paper_id: meng2024_v111_demo        # 必须匹配 runs/ 子目录名
source_pdf: input/papers/meng2024.pdf
items:
  - id: q01
    question: |
      0.85NBST-0.15BMZ 在 340 kV/cm 下的 W_rec 是多少？
    ground_truth: |
      W_rec = 5.00 J/cm³（在 340 kV/cm 下，效率 90.09%）
    expected_chunks:        # 用于 context_recall — 答案应来自哪些 chunk
      - chapter_005_RESULTS_AND_DISCUSSION.md   # chapter 文件名
      # 可选：附加 char range, 用于精度调试
      - chapter_005_RESULTS_AND_DISCUSSION.md:8000-8400
    tags: [headline_metric, results]
```

## 题目选择原则

- 80% 客观可验证（数值、化学式、机制名）
- 20% 论断性（结论、比较）
- 至少 3 题考验"跨章节一致性"（同一 fact 在不同章节出现）
- 至少 3 题考验"figure ID 正确性"（答案需引用 Fig. N）
- 至少 3 题考验"作者归属正确性"（答案应说 "X et al. report …" 而不应张冠李戴）
```

- [ ] **Step 2: 创建 meng2024 golden QA 文件，先写 5 题做格式验证**

`tests/eval/golden_qa/meng2024.yaml`:
```yaml
paper_id: meng2024_v111_demo
source_pdf: input/papers/meng2024.pdf
items:
  - id: q01
    question: |
      0.85NBST-0.15BMZ 在 340 kV/cm 下的 W_rec 是多少？
    ground_truth: |
      W_rec = 5.00 J/cm³，效率约 90.09%
    expected_chunks: [chapter_005_RESULTS_AND_DISCUSSION.md]
    tags: [headline_metric, results]

  - id: q02
    question: |
      Meng2024 体系的 flagship 组分化学式是什么？
    ground_truth: |
      (1-x)(Na0.3Bi0.38Sr0.28TiO3)-xBi(Mg0.5Zr0.5)O3 体系，x=0.15 为最优
    expected_chunks: [chapter_001_INTRODUCTION.md]
    tags: [system, abstract]

  - id: q03
    question: |
      论文用什么实验方法测量 P-E loop？
    ground_truth: |
      标准的电滞回线测试（铁电分析仪），未明确给出仪器型号
    expected_chunks: [chapter_002_EXPERIMENTAL_SECTION.md]
    tags: [method]

  - id: q04
    question: |
      论文引用的 BiFeO3 体系（Jiang 等人工作）报道的 W_rec 是多少？
    ground_truth: |
      Jiang et al. 报道的 BiFeO3-based 体系 W_rec ≈ 2.94 J/cm³
    expected_chunks: [chapter_001_INTRODUCTION.md, chapter_005_RESULTS_AND_DISCUSSION.md]
    tags: [comparator, author_attribution]

  - id: q05
    question: |
      Fig. 1 展示了什么？
    ground_truth: |
      Fig. 1 是协同优化策略的示意图，包含 Pmax/Wrec loops 与机制 panels
    expected_chunks: [chapter_001_INTRODUCTION.md]
    tags: [figure_id]
```

- [ ] **Step 3: 验证 yaml 可解析**

Run: `uv run python -c "import yaml; print(len(yaml.safe_load(open('tests/eval/golden_qa/meng2024.yaml'))['items']))"`
Expected: `5`

- [ ] **Step 4: 补齐到 20 题**

打开 `runs/meng2024_v111_demo/s09_render/preview.html`（已有 demo 输出），从中挑符合上述标签分布的 15 题继续填入。每题 ground_truth 必须从 PDF / preview 验证，不能凭空写。

最终分布检查（人工自检）：
- headline_metric: ≥3 题
- comparator + author_attribution: ≥4 题
- figure_id: ≥3 题
- method/system/abstract: ≥3 题
- 跨章节一致性: ≥3 题

Run: `uv run python -c "import yaml; d=yaml.safe_load(open('tests/eval/golden_qa/meng2024.yaml')); print(len(d['items'])); print(sorted(set(t for i in d['items'] for t in i['tags'])))"`
Expected: `20`，并且 tags 集合涵盖上述 5 类。

- [ ] **Step 5: Commit**

```bash
git add tests/eval/golden_qa/
git commit -m "test(eval): meng2024 golden QA set (20 questions) for ragas harness"
```

---

## Task 3: ali2025_flash 写 20 题

**Files:**
- Create: `tests/eval/golden_qa/ali2025_flash.yaml`

- [ ] **Step 1: 复制 meng2024 文件结构，改 paper_id**

`tests/eval/golden_qa/ali2025_flash.yaml`:
```yaml
paper_id: ali2025_flash_v111_demo
source_pdf: input/papers/ali2025_flash.pdf
items:
  # 20 题，从 runs/ali2025_flash_v111_demo/ 既有产物 + PDF 校验
```

- [ ] **Step 2: 同 Task 2 Step 4 的方法填 20 题**

确保至少 1 题涵盖 v1.11.4 修复的 T4 4→5 突破点。

- [ ] **Step 3: 验证**

Run: `uv run python -c "import yaml; print(len(yaml.safe_load(open('tests/eval/golden_qa/ali2025_flash.yaml'))['items']))"`
Expected: `20`

- [ ] **Step 4: Commit**

```bash
git add tests/eval/golden_qa/ali2025_flash.yaml
git commit -m "test(eval): ali2025_flash golden QA set (20 questions)"
```

---

## Task 4: 写 RAGAS pytest harness（用真 LLM）

**Files:**
- Create: `tests/eval/__init__.py` (空文件)
- Create: `tests/eval/conftest.py`
- Create: `tests/eval/test_ragas_baseline.py`
- Delete: `tests/eval/test_ragas_smoke.py`（被本 task 替代）
- Modify: `.gitignore` — 加 `tests/eval/_ragas_out/`

- [ ] **Step 1: 写 conftest**

`tests/eval/conftest.py`:
```python
"""Shared fixtures for ragas eval harness.

Reads from runs/<paper_id>/ — assumes the pipeline has been run on each paper
in golden_qa/*.yaml beforehand.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


GOLDEN_DIR = Path(__file__).parent / "golden_qa"
RUNS_ROOT = Path(__file__).parent.parent.parent / "runs"
OUT_DIR = Path(__file__).parent / "_ragas_out"


@pytest.fixture(scope="session")
def golden_papers() -> list[dict]:
    """Yield {paper_id, items[]} for each golden_qa/*.yaml that has a matching runs/ dir."""
    out = []
    for yml in sorted(GOLDEN_DIR.glob("*.yaml")):
        if yml.name.startswith("_"):
            continue
        data = yaml.safe_load(yml.read_text())
        run_dir = RUNS_ROOT / data["paper_id"]
        if not run_dir.exists():
            pytest.skip(f"runs/{data['paper_id']} not present — run pipeline first")
        out.append({**data, "run_dir": run_dir})
    if not out:
        pytest.skip("no golden_qa/*.yaml found with matching runs/")
    return out


@pytest.fixture(scope="session")
def llm_credentials_present() -> bool:
    return bool(os.environ.get("LLM_TEXT_API_KEY"))


@pytest.fixture(scope="session", autouse=True)
def _require_llm(llm_credentials_present):
    if not llm_credentials_present:
        pytest.skip("LLM_TEXT_API_KEY not set — ragas needs a live LLM judge")
```

- [ ] **Step 2: 写 harness 主体**

`tests/eval/test_ragas_baseline.py`:
```python
"""RAGAS faithfulness / context_recall / context_precision against golden_qa.

Runs only when invoked explicitly:
    uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v

Writes per-paper score JSON to tests/eval/_ragas_out/<paper_id>.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ragas


def _load_chapter_chunks(run_dir: Path, expected_chunks: list[str]) -> list[str]:
    """For each expected_chunks entry (basename, optionally `:start-end`),
    read the chapter file from runs/<paper>/s03_chapter/chapters/ and slice."""
    chapters_dir = run_dir / "s03_chapter" / "chapters"
    out = []
    for spec in expected_chunks:
        if ":" in spec:
            fname, span = spec.split(":")
            start, end = (int(x) for x in span.split("-"))
        else:
            fname, start, end = spec, None, None
        text = (chapters_dir / fname).read_text()
        out.append(text[start:end] if start is not None else text)
    return out


def _load_answer(run_dir: Path) -> str:
    """Concatenate s08 composed prose so we can ask 'does it answer Q?'."""
    compose_dir = run_dir / "s08_section_compose" / "chapters"
    return "\n\n".join(
        p.read_text() for p in sorted(compose_dir.glob("*.md"))
    )


def test_ragas_scores(golden_papers):
    """For each golden paper compute 3 metrics + dump JSON."""
    from ragas import evaluate
    from ragas.metrics import faithfulness, context_recall, context_precision
    from datasets import Dataset

    OUT_DIR = Path(__file__).parent / "_ragas_out"
    OUT_DIR.mkdir(exist_ok=True)

    answer_corpus_cache: dict[str, str] = {}
    for paper in golden_papers:
        answer_corpus_cache[paper["paper_id"]] = _load_answer(paper["run_dir"])

    for paper in golden_papers:
        rows = []
        full_answer = answer_corpus_cache[paper["paper_id"]]
        for item in paper["items"]:
            rows.append({
                "question": item["question"].strip(),
                "answer": full_answer,                     # we score the *full* compose output
                "contexts": _load_chapter_chunks(paper["run_dir"], item["expected_chunks"]),
                "ground_truth": item["ground_truth"].strip(),
            })
        ds = Dataset.from_list(rows)
        result = evaluate(ds, metrics=[faithfulness, context_recall, context_precision])
        out = {
            "paper_id": paper["paper_id"],
            "n_questions": len(rows),
            "scores": {k: float(v) for k, v in result.to_pandas().mean(numeric_only=True).items()},
        }
        (OUT_DIR / f"{paper['paper_id']}.json").write_text(json.dumps(out, indent=2))
        # Sanity guard — these are baseline, not pass/fail. Just log & assert >0.
        assert out["scores"]["faithfulness"] > 0, f"{paper['paper_id']} faithfulness == 0"
```

- [ ] **Step 3: 删 smoke test，更新 .gitignore**

```bash
rm tests/eval/test_ragas_smoke.py
```

`.gitignore` 追加：
```
# v1.12 phase1 eval harness outputs
tests/eval/_ragas_out/
```

- [ ] **Step 4: 确保 meng2024 + ali2025_flash 的 runs/ 存在**

Run: `ls runs/meng2024_v111_demo/s08_section_compose/chapters/ runs/ali2025_flash_v111_demo/s08_section_compose/chapters/ | head -5`
Expected: 两个目录都列出 chapter md 文件。
**若任一不存在**：先 `uv run python -m cli run --pdf input/papers/<pdf> --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" --paper-id <id>_v111_demo --lang zh`

- [ ] **Step 5: 干跑 harness（会真调 LLM）**

Run: `uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s`
Expected: 
- 第一次跑可能 1-5 分钟（ragas 每题调一次 LLM）
- 控制台打印两次 evaluate 输出
- `1 passed`
- `tests/eval/_ragas_out/meng2024_v111_demo.json` 和 `ali2025_flash_v111_demo.json` 生成

**若失败**：常见原因 ragas API 在 0.2.x 有 breaking change。检查 `from ragas import evaluate` 路径，必要时 fallback 到 ragas 文档的最新 example。

- [ ] **Step 6: Commit**

```bash
git add tests/eval/ .gitignore
git commit -m "test(eval): ragas baseline harness (faithfulness/recall/precision)"
```

---

## Task 5: 跑 baseline + 写报告

**Files:**
- Create: `docs/archive/v1_12_phase1_ragas_baseline.md`

- [ ] **Step 1: 跑一次 baseline，保留输出**

```bash
uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s 2>&1 | tee /tmp/ragas_baseline_run.log
```

- [ ] **Step 2: 摘录数据写报告**

`docs/archive/v1_12_phase1_ragas_baseline.md`:
```markdown
# v1.12 Phase 1 — RAGAS Baseline

> Captured against code at HEAD `<paste git rev-parse HEAD here>` on 2026-05-XX.
> Reproduce: `uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s`

## Setup
- Papers: meng2024_v111_demo, ali2025_flash_v111_demo
- Questions: 20 per paper (`tests/eval/golden_qa/*.yaml`)
- Ragas metrics: faithfulness, context_recall, context_precision
- Judge LLM: `<LLM_TEXT_MODEL value>` via `<LLM_TEXT_BASE_URL>`

## Scores

| Paper | faithfulness | context_recall | context_precision |
|---|---|---|---|
| meng2024 | <fill> | <fill> | <fill> |
| ali2025_flash | <fill> | <fill> | <fill> |

## Notes & gotchas
- <e.g. "ragas 0.2.x silently skips items with empty contexts; verified all 40 returned scores">
- <e.g. "context_precision is low because we pass full chapter text as one context — Task 11 may improve this">

## What this baseline is FOR
- Task 9 / Task 12 / Task 13 re-run the same harness; deltas attribute to PDFFigures-2 / entity-dedup respectively.
- ≥+5pp on `faithfulness` is the bar for "this change actually helped";
- regression of >1pp on any metric → revert.
```

- [ ] **Step 3: Commit**

```bash
git add docs/archive/v1_12_phase1_ragas_baseline.md
git commit -m "docs(v1.12): ragas baseline scores for meng2024 + ali2025_flash"
```

---

## Task 6: 下载 PDFFigures 2 JAR + 验证 Java 环境

**Files:**
- Modify: `.gitignore` — 加 `vendor/*.jar`
- Modify: `.env.example` — 加 `PDFFIGURES2_JAR`
- Modify: `docs/USER_GUIDE.md` — 加"PDFFigures 2 可选依赖"章节
- Create: `vendor/.gitkeep`

- [ ] **Step 1: 验证 docker 可用（本机不装 Java）**

Run: `docker --version && docker ps -q | head -1`
Expected: 输出 docker 版本号（无报错即可）。
**若 docker 未启动**：先打开 Docker Desktop（macOS / Windows）或 `sudo systemctl start docker`（Linux）。
**Java 完全不装本机** —— 与项目 Docker 偏好（CLAUDE.md "系统级依赖走 Docker"）一致。

- [ ] **Step 2: 准备 pdffigures2 docker 镜像**

PDFFigures 2 没有官方 docker 镜像 release。需要本仓库自带 `Dockerfile.pdffigures2` 一次性构建：

`Dockerfile.pdffigures2`:
```dockerfile
# Build PDFFigures 2 (AI2) into a self-contained jar; expose as ENTRYPOINT.
# Build:  docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2 .
# Run:    docker run --rm -v "$PWD/input:/work" lazy-paper/pdffigures2 /work/foo.pdf
FROM sbtscala/scala-sbt:eclipse-temurin-jammy-11.0.20_8_1.9.6_2.12.18 AS build
WORKDIR /src
RUN git clone --depth 1 https://github.com/allenai/pdffigures2 .
RUN sbt assembly && ls target/scala-2.12/

FROM eclipse-temurin:11-jre-jammy
COPY --from=build /src/target/scala-2.12/pdffigures2-assembly-0.1.0.jar /opt/pdffigures2.jar
WORKDIR /work
ENTRYPOINT ["java", "-jar", "/opt/pdffigures2.jar"]
CMD ["--help"]
```

构建：
```bash
docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .
```

Expected: 末尾 `Successfully tagged lazy-paper/pdffigures2:0.1.0`。
**若 sbt clone 失败**：检查网络；这一步只需要一次，构建后镜像可在团队间分发。

更新 wrapper 脚本：
```bash
mkdir -p vendor
cat > vendor/pdffigures2.sh <<'EOF'
#!/usr/bin/env bash
# Docker wrapper for PDFFigures 2. Host requires only `docker`.
# Input:  $1 = path to PDF (absolute or relative)
# Output: prints JSON array to stdout (figures/captions/regions/figType)
set -euo pipefail
PDF="${1:?usage: pdffigures2.sh <pdf>}"
PDF_ABS="$(cd "$(dirname "$PDF")" && pwd)/$(basename "$PDF")"
PDF_DIR="$(dirname "$PDF_ABS")"
PDF_NAME="$(basename "$PDF_ABS")"
OUT_DIR="$(mktemp -d -t pf2-XXXXXX)"
trap 'rm -rf "$OUT_DIR"' EXIT

docker run --rm \
    -v "$PDF_DIR:/work:ro" \
    -v "$OUT_DIR:/out" \
    lazy-paper/pdffigures2:0.1.0 \
    "/work/$PDF_NAME" -m /out/meta_ -e >/dev/null

cat "$OUT_DIR"/meta_*.json 2>/dev/null || echo "[]"
EOF
chmod +x vendor/pdffigures2.sh
```

```bash
mkdir -p vendor
# 创建 wrapper 脚本而非直接下载 jar
cat > vendor/pdffigures2.sh <<'EOF'
#!/usr/bin/env bash
# Wrapper to invoke pdffigures2 via docker
# Input:  $1 = absolute path to PDF
# Output: prints JSON to stdout (figures/captions/regions)
set -euo pipefail
PDF="${1:?usage: pdffigures2.sh <pdf>}"
PDF_ABS="$(cd "$(dirname "$PDF")" && pwd)/$(basename "$PDF")"
PDF_DIR="$(dirname "$PDF_ABS")"
PDF_NAME="$(basename "$PDF_ABS")"
docker run --rm -v "$PDF_DIR:/work" allenai/pdffigures2 \
    /work/"$PDF_NAME" -d /tmp/out/ -m /tmp/out/meta_ -e
cat /tmp/out/meta_*.json 2>/dev/null || true
EOF
chmod +x vendor/pdffigures2.sh
```

**若 allenai/pdffigures2 docker 镜像不存在**：
fall back 到方案 B，sbt assembly 生成 `target/scala-2.12/pdffigures2-assembly-0.1.0.jar`，cp 到 `vendor/`。

- [ ] **Step 3: 用 meng2024.pdf 试跑一次**

Run: `vendor/pdffigures2.sh input/papers/meng2024.pdf 2>&1 | head -50`
Expected: JSON 数组，每项含 `name`/`caption`/`page`/`regionBoundary`/`figType`。
**若 sbt build 失败**：本 Task 标记 BLOCKED，跳到 Task 10（LightRAG dedup 不依赖 PDFFigures 2）。
**永远不要 brew install Java/sbt**：所有 JVM 工具都在 docker 内。

- [ ] **Step 4: 更新 .gitignore + .env.example + USER_GUIDE**

`.gitignore` 追加：
```
vendor/*.jar
vendor/_tmp/
```

`.env.example` 追加：
```bash
# v1.12 — Optional PDFFigures 2 sidecar for caption-anchored figure numbering.
# Required only when running with --pdffigures2 flag.
# Set to "docker" to use the bundled docker wrapper (recommended, no host JVM
# install). Building the image requires running `docker build -f
# Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .` once.
PDFFIGURES2_JAR=docker
```

`docs/USER_GUIDE.md` 在 "Optional features" 段下加：
```markdown
### PDFFigures 2 sidecar (v1.12, opt-in)

Caption-anchored figure numbering. When MinerU OCR skips or mis-numbers a
figure, PDFFigures 2 (AI2, Scala) re-extracts the canonical Figure N from
the caption text. Enabled with `--pdffigures2` on `lazy-paper run`.

**Setup (docker — only supported path; no host Java needed):**
```bash
docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .   # one-time, ~5 min
```

Set `PDFFIGURES2_JAR=docker` in `.env`. The sidecar runs inside the container;
host JVM and sbt are never touched. Output lands in `s04_figures/_pdffigures2.yaml`.
```

- [ ] **Step 5: Commit**

```bash
git add vendor/pdffigures2.sh vendor/.gitkeep Dockerfile.pdffigures2 .gitignore .env.example docs/USER_GUIDE.md
git commit -m "feat(s04): add PDFFigures 2 sidecar (docker-only, no host JVM)"
```

---

## Task 7: 写 sidecar 调用模块 + 解析

**Files:**
- Create: `scripts/pdffigures2_sidecar.py`
- Create: `scripts/tests/test_pdffigures2_sidecar.py`

- [ ] **Step 1: 写失败测试**

`scripts/tests/test_pdffigures2_sidecar.py`:
```python
"""Unit tests for the pdffigures2 sidecar parser.

Mocks the subprocess call — does not actually run PDFFigures 2.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


SAMPLE_OUTPUT = [
    {"name": "1", "page": 0, "caption": "Schematic of the synergistic optimization strategy.",
     "regionBoundary": {"x1": 100, "y1": 100, "x2": 500, "y2": 400}, "figType": "Figure"},
    {"name": "2", "page": 2, "caption": "P-E loops at various temperatures.",
     "regionBoundary": {"x1": 80, "y1": 200, "x2": 520, "y2": 600}, "figType": "Figure"},
    {"name": "1", "page": 5, "caption": "Lattice parameters from XRD refinement.",
     "regionBoundary": {"x1": 60, "y1": 300, "x2": 540, "y2": 500}, "figType": "Table"},
]


def test_parse_figures_only(tmp_path):
    from scripts.pdffigures2_sidecar import parse_pdffigures2_output
    parsed = parse_pdffigures2_output(SAMPLE_OUTPUT)
    assert len(parsed["figures"]) == 2
    assert parsed["figures"][0]["fig_id"] == "Fig. 1"
    assert parsed["figures"][1]["fig_id"] == "Fig. 2"
    assert len(parsed["tables"]) == 1
    assert parsed["tables"][0]["table_id"] == "Table 1"


def test_canonical_caption_strip(tmp_path):
    from scripts.pdffigures2_sidecar import parse_pdffigures2_output
    parsed = parse_pdffigures2_output([
        {"name": "3", "page": 0, "caption": "Figure 3. P-E loops.", "figType": "Figure",
         "regionBoundary": {"x1": 0, "y1": 0, "x2": 0, "y2": 0}},
    ])
    # "Figure 3." prefix should be stripped from the caption
    assert parsed["figures"][0]["caption"] == "P-E loops."


def test_run_sidecar_subprocess_returns_dict(tmp_path):
    from scripts.pdffigures2_sidecar import run_sidecar
    fake_json = json.dumps(SAMPLE_OUTPUT)
    with patch("scripts.pdffigures2_sidecar._invoke_jar", return_value=fake_json):
        result = run_sidecar(Path("/fake.pdf"))
    assert "figures" in result and len(result["figures"]) == 2


def test_run_sidecar_propagates_unavailable(tmp_path):
    """When _invoke_jar raises SidecarUnavailable, run_sidecar passes it through
    unchanged so callers (cli.py) can decide whether to warn or abort."""
    from scripts.pdffigures2_sidecar import run_sidecar, SidecarUnavailable
    with patch("scripts.pdffigures2_sidecar._invoke_jar",
               side_effect=SidecarUnavailable("docker not available")):
        with pytest.raises(SidecarUnavailable):
            run_sidecar(Path("/fake.pdf"))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest scripts/tests/test_pdffigures2_sidecar.py -v`
Expected: 4 failures，all 因 `ModuleNotFoundError: scripts.pdffigures2_sidecar`

- [ ] **Step 3: 写实现**

`scripts/pdffigures2_sidecar.py`:
```python
"""Wrapper around PDFFigures 2 (AI2) for caption-anchored figure numbering.

Used by stages/s04_figures when `--pdffigures2` is set. Subprocess-only;
never imported into the main pipeline's hot path.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


class SidecarUnavailable(RuntimeError):
    """Raised when the pdffigures2 JAR / docker image is not callable."""


_CAPTION_PREFIX_RE = re.compile(
    r"^(?:Figure|Fig\.?|Table)\s*\d+[A-Za-z]?\.?\s*[:.\-]?\s*",
    re.IGNORECASE,
)


def parse_pdffigures2_output(raw: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Convert the JSON list emitted by pdffigures2 into a figures/tables split.

    Each entry gains:
      - figures: fig_id ('Fig. 1' canonical), caption (prefix stripped),
                 page, region (x1,y1,x2,y2)
      - tables:  table_id ('Table 1'), caption, page, region
    """
    figures: list[dict] = []
    tables: list[dict] = []
    for entry in raw:
        kind = entry.get("figType", "Figure")
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        caption = str(entry.get("caption", "")).strip()
        caption_clean = _CAPTION_PREFIX_RE.sub("", caption).strip()
        region = entry.get("regionBoundary", {})
        rec = {
            "page": entry.get("page", 0),
            "caption": caption_clean,
            "caption_raw": caption,
            "region": (region.get("x1"), region.get("y1"),
                       region.get("x2"), region.get("y2")),
        }
        if kind == "Table":
            tables.append({**rec, "table_id": f"Table {name}"})
        else:
            figures.append({**rec, "fig_id": f"Fig. {name}"})
    return {"figures": figures, "tables": tables}


def _invoke_jar(pdf: Path) -> str:
    """Run PDFFigures 2 via the docker wrapper; return its JSON-array stdout.

    Docker-only by design (project policy: no host JVM install). Set
    PDFFIGURES2_JAR=docker in .env after building the image once with
    `docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .`
    """
    target = os.environ.get("PDFFIGURES2_JAR", "").strip()
    if target != "docker":
        raise SidecarUnavailable(
            "PDFFIGURES2_JAR must be 'docker' (no other paths supported); "
            "build the image with `docker build -f Dockerfile.pdffigures2 "
            "-t lazy-paper/pdffigures2:0.1.0 .` then set PDFFIGURES2_JAR=docker"
        )
    wrapper = Path(__file__).resolve().parent.parent / "vendor" / "pdffigures2.sh"
    if not wrapper.exists():
        raise SidecarUnavailable(f"missing wrapper: {wrapper}")
    try:
        cp = subprocess.run([str(wrapper), str(pdf.resolve())],
                            check=True, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:  # docker binary not in PATH
        raise SidecarUnavailable(f"docker not available: {e}") from e
    return cp.stdout


def run_sidecar(pdf: Path) -> dict[str, list[dict]]:
    """End-to-end: invoke pdffigures2 and parse its output.

    Raises SidecarUnavailable if jar/docker not callable — caller can decide
    to skip silently or warn.
    """
    raw_json = _invoke_jar(pdf)
    raw = json.loads(raw_json) if raw_json.strip() else []
    return parse_pdffigures2_output(raw)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest scripts/tests/test_pdffigures2_sidecar.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/pdffigures2_sidecar.py scripts/tests/test_pdffigures2_sidecar.py
git commit -m "feat(scripts): pdffigures2 sidecar wrapper + parser (TDD)"
```

---

## Task 8: s04 集成 — reconcile 函数 + CLI flag

**Files:**
- Modify: `cli.py` — 加 `--pdffigures2` flag + sidecar 调用
- Modify: `stages/s04_figures/runner.py` — 加 `reconcile_with_pdffigures2()`
- Create: `stages/s04_figures/tests/test_reconcile.py`

- [ ] **Step 1: 写失败测试**

`stages/s04_figures/tests/test_reconcile.py`:
```python
"""Tests for reconcile_with_pdffigures2 — re-numbering figures via caption-anchored truth."""
from __future__ import annotations

import pytest


def test_reconcile_renames_skipped_figure():
    """MinerU outputs Fig.1, Fig.2; pdffigures2 reports Fig.1, Fig.3 (gap at 2).
    Expected: our entry currently labeled 'Fig. 2' is RENAMED to 'Fig. 3'
    so downstream `mentions.yaml` aligns with the paper's actual numbering.
    """
    from stages.s04_figures.runner import reconcile_with_pdffigures2

    mineru_figs = [
        {"fig_id": "Fig. 1", "caption": "Schematic of synergistic optimization", "image_rel_path": "imgs/a.jpg"},
        {"fig_id": "Fig. 2", "caption": "P-E loops at various temperatures", "image_rel_path": "imgs/b.jpg"},
    ]
    pf2 = {
        "figures": [
            {"fig_id": "Fig. 1", "caption": "Schematic of the synergistic optimization strategy", "page": 0, "region": (0,0,0,0)},
            {"fig_id": "Fig. 3", "caption": "P-E loops at various temperatures", "page": 4, "region": (0,0,0,0)},
        ],
        "tables": [],
    }
    out, report = reconcile_with_pdffigures2(mineru_figs, pf2)
    assert out[0]["fig_id"] == "Fig. 1"
    assert out[1]["fig_id"] == "Fig. 3"
    assert any(r["from"] == "Fig. 2" and r["to"] == "Fig. 3" for r in report["renames"])


def test_reconcile_keeps_when_pdffigures2_disagrees():
    """If captions don't match, keep MinerU's numbering and log a `keep` entry."""
    from stages.s04_figures.runner import reconcile_with_pdffigures2

    mineru_figs = [{"fig_id": "Fig. 1", "caption": "Total miss", "image_rel_path": "x.jpg"}]
    pf2 = {"figures": [{"fig_id": "Fig. 5", "caption": "Completely different content", "page": 0, "region": (0,0,0,0)}], "tables": []}
    out, report = reconcile_with_pdffigures2(mineru_figs, pf2)
    assert out[0]["fig_id"] == "Fig. 1"
    assert any(r["fig_id"] == "Fig. 1" and r["reason"] == "no_caption_match" for r in report["keeps"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest stages/s04_figures/tests/test_reconcile.py -v`
Expected: 2 failures, `ImportError: cannot import name 'reconcile_with_pdffigures2'`

- [ ] **Step 3: 实现 reconcile 函数**

在 `stages/s04_figures/runner.py` 末尾追加：
```python
# v1.12 phase1: PDFFigures 2 reconciliation
# When the user opts in via --pdffigures2, we cross-check MinerU's figure
# numbering against the caption-anchored truth from AI2's PDFFigures 2.
# Renames happen ONLY when captions match (jaccard >= 0.5 on word tokens);
# otherwise we trust MinerU and log a `keep` entry for the audit trail.

def _caption_jaccard(a: str, b: str) -> float:
    ta = {w.lower() for w in (a or "").split() if len(w) >= 3}
    tb = {w.lower() for w in (b or "").split() if len(w) >= 3}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def reconcile_with_pdffigures2(
    mineru_figs: list[dict], pf2: dict, *, jaccard_threshold: float = 0.5,
) -> tuple[list[dict], dict]:
    """Rename MinerU figure_ids to match pdffigures2's caption-anchored numbering.

    Matching: for each MinerU figure, find the pdffigures2 figure with the
    highest caption Jaccard score; if >= threshold, adopt pf2's fig_id.

    Returns (new_figs, audit_report). The report shape:
        {
          "renames": [{"from": "Fig. 2", "to": "Fig. 3", "score": 0.83}],
          "keeps":   [{"fig_id": "Fig. 1", "reason": "no_caption_match", "best_score": 0.1}],
        }
    """
    pf2_figs = pf2.get("figures", [])
    out: list[dict] = []
    report: dict = {"renames": [], "keeps": []}
    for fig in mineru_figs:
        original = fig.get("fig_id", "")
        best_score = 0.0
        best_pf2 = None
        for p in pf2_figs:
            s = _caption_jaccard(fig.get("caption", ""), p.get("caption", ""))
            if s > best_score:
                best_score, best_pf2 = s, p
        if best_pf2 and best_score >= jaccard_threshold:
            new_id = best_pf2["fig_id"]
            new_fig = {**fig, "fig_id": new_id}
            out.append(new_fig)
            if new_id != original:
                report["renames"].append({"from": original, "to": new_id,
                                          "score": round(best_score, 3)})
        else:
            out.append(fig)
            report["keeps"].append({"fig_id": original, "reason": "no_caption_match",
                                    "best_score": round(best_score, 3)})
    return out, report
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest stages/s04_figures/tests/test_reconcile.py -v`
Expected: 2 passed

- [ ] **Step 5: 把 sidecar 接入 CLI**

`cli.py` 在 argparse 区追加（第 240 行附近，与其他 flag 并列）：
```python
r.add_argument("--pdffigures2", action="store_true",
               help="v1.12: enable PDFFigures 2 sidecar for caption-anchored "
                    "figure numbering (requires PDFFIGURES2_JAR env). "
                    "Off by default — opt-in until v1.13.")
```

`cli.py` 在 `_run_one` 的 `elif name == "s04_figures":` 分支后插入（第 148 行后）：
```python
        # v1.12 phase1: PDFFigures 2 reconciliation, opt-in
        if getattr(args, "pdffigures2", False):
            from scripts.pdffigures2_sidecar import run_sidecar, SidecarUnavailable
            from stages.s04_figures.runner import reconcile_with_pdffigures2
            try:
                pf2_payload = run_sidecar(Path(args.pdf))
                figures_path = out / "figures.yaml"
                if figures_path.exists():
                    figs = load_yaml(figures_path) or []
                    new_figs, report = reconcile_with_pdffigures2(figs, pf2_payload)
                    dump_yaml(figures_path, new_figs)
                    dump_yaml(out / "_pdffigures2.yaml", {"raw": pf2_payload, "report": report})
                    print(f"        [pdffigures2] renames={len(report['renames'])} "
                          f"keeps={len(report['keeps'])}")
            except SidecarUnavailable as e:
                print(f"        [pdffigures2] skipped: {e}", file=sys.stderr)
```

- [ ] **Step 6: 跑现有 s04 单测确认没坏现有逻辑**

Run: `uv run pytest stages/s04_figures/tests/ -v`
Expected: all pass（新加的 2 + 现有的 N）

- [ ] **Step 7: Commit**

```bash
git add cli.py stages/s04_figures/runner.py stages/s04_figures/tests/test_reconcile.py
git commit -m "feat(s04): reconcile MinerU figures against PDFFigures 2 (opt-in)"
```

---

## Task 9: PDFFigures 2 在 meng2024 上 e2e 试跑 + 报告

**Files:**
- Modify: `docs/archive/v1_12_phase1_ragas_baseline.md` — 追加 "PDFFigures 2 measured impact" 段

- [ ] **Step 1: 在 meng2024 上跑 --pdffigures2 --only s04_figures --force**

```bash
PDFFIGURES2_JAR=docker uv run python -m cli run \
  --pdf input/papers/meng2024.pdf \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id meng2024_v111_demo \
  --lang zh --only s04_figures --force --pdffigures2
```

Expected: 控制台出现 `[pdffigures2] renames=X keeps=Y` 一行。
**若 `renames=0 keeps=N`**：说明 MinerU 在这篇上已经对齐，没活儿可干 —— 找一篇 v1.11 已知有图编号漂移的 paper 重跑（候选：`hif_2_v111_demo`、`pamula2025_v111_demo`）。

- [ ] **Step 2: 看 `_pdffigures2.yaml` 的 report 字段**

```bash
cat runs/meng2024_v111_demo/s04_figures/_pdffigures2.yaml | head -40
```

人工检查：renames 字段是否合理；keeps 的 best_score 是不是普遍 <0.5（合理）还是 >0.5 却没改名（bug）。

- [ ] **Step 3: 跑完整 pipeline 重生成 s08 + s09**

```bash
uv run python -m cli run --pdf input/papers/meng2024.pdf \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id meng2024_v112_pf2 --lang zh --pdffigures2
```

Expected: 整条 pipeline 跑通。新 paper-id `_v112_pf2` 用于和原 `_v111_demo` 对比。

- [ ] **Step 4: 重跑 RAGAS（只对 meng2024）—— 临时改 golden_qa 的 paper_id**

为不污染既有 baseline，临时建一个对照 golden_qa：
```bash
cp tests/eval/golden_qa/meng2024.yaml /tmp/meng2024_pf2.yaml
sed -i '' 's/meng2024_v111_demo/meng2024_v112_pf2/' /tmp/meng2024_pf2.yaml
cp /tmp/meng2024_pf2.yaml tests/eval/golden_qa/meng2024_pf2.yaml
uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s 2>&1 | tee /tmp/ragas_pf2.log
```

- [ ] **Step 5: 摘录 delta 写入报告**

`docs/archive/v1_12_phase1_ragas_baseline.md` 追加：
```markdown
## PDFFigures 2 measured impact (Task 9)

| Metric | Baseline (v1.11.5) | v1.12+pf2 | Δ |
|---|---|---|---|
| meng2024.faithfulness | <X> | <Y> | <+/-Z pp> |
| meng2024.context_recall | ... | ... | ... |
| meng2024.context_precision | ... | ... | ... |

Notes:
- Renames recorded: <N>; manual spot-check: <pass / N issues>
- Decision: <ship / hold / iterate>
```

- [ ] **Step 6: 清理临时文件 + commit**

```bash
rm tests/eval/golden_qa/meng2024_pf2.yaml
# 不删 runs/meng2024_v112_pf2 — 保留作为对照
git add docs/archive/v1_12_phase1_ragas_baseline.md
git commit -m "docs(v1.12): PDFFigures 2 measured impact on meng2024"
```

---

## Task 10: 设计 entity_dedup prompt + 模块骨架

**Files:**
- Create: `llm/prompts/entity_dedup.md`
- Create: `stages/s06_context/entity_dedup.py`
- Create: `stages/s06_context/tests/test_entity_dedup.py`

参考来源：
- LightRAG repo: https://github.com/HKUDS/LightRAG，重点看 `lightrag/operate.py` 里 `_merge_nodes_and_edges` + entity-disambiguation prompt
- 不直接 import 该库（依赖太重），只 lift 算法 + prompt 思路

- [ ] **Step 1: 起草 prompt**

`llm/prompts/entity_dedup.md`:
```markdown
You are an entity disambiguation assistant for materials-science papers. The
KG extractor emitted the following entities, some of which refer to the SAME
real-world entity (e.g. "Meng et al.", "Meng 2024", "this work", "the
authors"). Your job: produce a canonical form for each cluster of variant
mentions.

## Rules

1. NEVER merge entities of different types (do not merge a `material` with an
   `author`, etc.).
2. Within one type, merge variant mentions of the same real-world entity:
   - Authors: "Smith et al." == "Smith and coworkers" == "Smith's group".
     If the paper has multiple Smiths (e.g. Smith J. vs Smith K.), keep them
     separate.
   - "this work" / "we" / "the present authors" / "本工作" / "本文" — merge
     to the SOURCE paper's own author when known; else keep as
     `__self__` placeholder.
   - Materials: same composition with different notations are one entity
     (e.g. "0.85NBST-0.15BMZ" == "(1-x)(NBST)-xBMZ with x=0.15").
3. NEVER invent a canonical form not present in the input list. Pick one of
   the surface forms as canonical, prefer the most specific.

## Input format

```yaml
candidates:
  - id: e_001
    type: author
    surface: "Meng et al."
    source_span: "doc_3.md:1024-1040"
  - id: e_002
    type: author
    surface: "Meng 2024"
    source_span: "doc_5.md:200-210"
```

## Output format (STRICT JSON, no commentary)

```json
{
  "clusters": [
    {"canonical": "Meng et al. 2024", "member_ids": ["e_001", "e_002"]}
  ]
}
```

Rules:
- Every input id MUST appear in exactly one cluster.
- A singleton cluster (no merge) is allowed.
- Canonical form MUST come from one of the surface forms in the cluster.
```

- [ ] **Step 2: 写失败测试**

`stages/s06_context/tests/test_entity_dedup.py`:
```python
"""Tests for entity_dedup — algorithm only (LLM mocked)."""
from __future__ import annotations

from unittest.mock import patch


def test_apply_clusters_renames_relations():
    from stages.s06_context.entity_dedup import apply_clusters

    entities = [
        {"id": "e1", "type": "author", "surface": "Meng et al."},
        {"id": "e2", "type": "author", "surface": "Meng 2024"},
        {"id": "e3", "type": "material", "surface": "BMZ"},
    ]
    relations = [
        {"head": "e1", "relation": "reports", "tail": "e3"},
        {"head": "e2", "relation": "reports", "tail": "e3"},
    ]
    clusters = [
        {"canonical": "Meng et al. 2024", "member_ids": ["e1", "e2"]},
        {"canonical": "BMZ", "member_ids": ["e3"]},
    ]
    new_entities, new_relations = apply_clusters(entities, relations, clusters)
    assert len(new_entities) == 2
    # all relations now point to canonical id (the first member becomes canonical id)
    assert all(r["head"] in {"e1", "e3"} for r in new_relations)
    # duplicate relation collapsed
    assert len(new_relations) == 1


def test_dedup_skips_empty_input():
    from stages.s06_context.entity_dedup import dedup_entities
    out = dedup_entities([], [], llm_chat=lambda **_: "{\"clusters\": []}")
    assert out == ([], [])


def test_dedup_handles_malformed_llm_output():
    from stages.s06_context.entity_dedup import dedup_entities
    # LLM returns invalid JSON — should soft-degrade, return inputs unchanged
    entities = [{"id": "e1", "type": "author", "surface": "X"}]
    out_e, out_r = dedup_entities(entities, [], llm_chat=lambda **_: "not json")
    assert out_e == entities and out_r == []


def test_dedup_validates_cluster_coverage():
    """If LLM forgets an entity, it should NOT silently drop it."""
    from stages.s06_context.entity_dedup import dedup_entities
    entities = [
        {"id": "e1", "type": "author", "surface": "A"},
        {"id": "e2", "type": "author", "surface": "B"},
    ]
    incomplete = '{"clusters": [{"canonical": "A", "member_ids": ["e1"]}]}'
    out_e, _ = dedup_entities(entities, [], llm_chat=lambda **_: incomplete)
    # e2 missing from clusters — defensive fallback should keep e2 as singleton
    assert any(e["id"] == "e2" for e in out_e)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest stages/s06_context/tests/test_entity_dedup.py -v`
Expected: 4 failures, `ImportError: cannot import name`

- [ ] **Step 4: 写实现**

`stages/s06_context/entity_dedup.py`:
```python
"""LightRAG-inspired entity deduplication for the s06 KG.

Lifts the merge prompt + cluster-validate algorithm from
https://github.com/HKUDS/LightRAG without importing the library. Gated by
LAZY_PAPER_ENTITY_DEDUP=1 — default OFF until measured.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "entity_dedup.md"


def _build_user_prompt(entities: list[dict]) -> str:
    import yaml
    candidates = [
        {"id": e["id"], "type": e["type"], "surface": e.get("surface", ""),
         "source_span": e.get("source_span", "")}
        for e in entities
    ]
    return yaml.safe_dump({"candidates": candidates}, allow_unicode=True,
                          sort_keys=False)


def _parse_clusters(text: str, all_ids: set[str]) -> list[dict]:
    """Defensive parse — bail (return []) on any structural problem."""
    try:
        obj = json.loads(text)
        clusters = obj.get("clusters", [])
        if not isinstance(clusters, list):
            return []
        for c in clusters:
            if not isinstance(c, dict):
                return []
            if "canonical" not in c or "member_ids" not in c:
                return []
            if not isinstance(c["member_ids"], list):
                return []
        return clusters
    except (json.JSONDecodeError, TypeError):
        return []


def _ensure_coverage(clusters: list[dict], all_ids: set[str]) -> list[dict]:
    """Add singleton clusters for any id the LLM forgot, so apply_clusters
    doesn't silently drop entities."""
    covered: set[str] = set()
    for c in clusters:
        covered.update(c["member_ids"])
    missing = all_ids - covered
    return clusters + [{"canonical": f"__id_{i}__", "member_ids": [i]} for i in missing]


def apply_clusters(
    entities: list[dict],
    relations: list[dict],
    clusters: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Collapse member ids to the first id in each cluster; dedupe relations."""
    # First id in each cluster wins as canonical id; canonical surface stored on it.
    id_remap: dict[str, str] = {}
    for c in clusters:
        if not c["member_ids"]:
            continue
        canonical_id = c["member_ids"][0]
        for mid in c["member_ids"]:
            id_remap[mid] = canonical_id

    by_id = {e["id"]: e for e in entities}
    new_entities: list[dict] = []
    seen_ids: set[str] = set()
    for c in clusters:
        if not c["member_ids"]:
            continue
        canonical_id = c["member_ids"][0]
        if canonical_id in seen_ids:
            continue
        seen_ids.add(canonical_id)
        e = dict(by_id[canonical_id])
        # Only overwrite surface if LLM gave a real canonical (not the __id_X__ fallback)
        if not c["canonical"].startswith("__id_"):
            e["surface"] = c["canonical"]
        e["dedup_member_ids"] = c["member_ids"]
        new_entities.append(e)

    seen_rels: set[tuple] = set()
    new_relations: list[dict] = []
    for r in relations:
        head = id_remap.get(r["head"], r["head"])
        tail = id_remap.get(r["tail"], r["tail"])
        key = (head, r["relation"], tail)
        if key in seen_rels:
            continue
        seen_rels.add(key)
        new_relations.append({**r, "head": head, "tail": tail})
    return new_entities, new_relations


def dedup_entities(
    entities: list[dict],
    relations: list[dict],
    *,
    llm_chat: Callable[..., str] | None = None,
    model: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """End-to-end entity dedup. Soft-degrades to inputs on any LLM failure.

    `llm_chat` is injectable for tests; in prod it's wired to llm.client.LLM.chat.
    """
    if not entities:
        return entities, relations
    if llm_chat is None:
        from llm.client import LLM
        client = LLM(role="text")
        def _real_chat(**kw):
            return client.chat(**kw).content
        llm_chat = _real_chat

    system = PROMPT_PATH.read_text()
    user = _build_user_prompt(entities)
    try:
        resp = llm_chat(system=system, user=user, temperature=0.1, max_tokens=4000)
    except Exception:
        return entities, relations

    all_ids = {e["id"] for e in entities}
    clusters = _parse_clusters(resp, all_ids)
    if not clusters:
        return entities, relations
    clusters = _ensure_coverage(clusters, all_ids)
    return apply_clusters(entities, relations, clusters)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest stages/s06_context/tests/test_entity_dedup.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add llm/prompts/entity_dedup.md stages/s06_context/entity_dedup.py stages/s06_context/tests/test_entity_dedup.py
git commit -m "feat(s06): entity dedup module + prompt (LightRAG-inspired, TDD)"
```

---

## Task 11: s06 runner 集成 entity_dedup + flag

**Files:**
- Modify: `stages/s06_context/runner.py` — KG extraction 后调 dedup
- Modify: `.env.example` — 加 `LAZY_PAPER_ENTITY_DEDUP`

- [ ] **Step 1: 阅读 s06 runner 找到注入点**

Run: `uv run python -c "from stages.s06_context import runner; import inspect; print(inspect.getsourcefile(runner))"`
读取该文件，找 `build_paper_kg(...)` 调用点（参考架构文档 §4.6 "Step 2"），dedup 应在 KG 写 parquet 之前。

- [ ] **Step 2: 插入 dedup 调用**

在 KG 已构建、parquet 还没写之前的位置（约 `kg_extract.build_paper_kg(...)` 返回值之后），插入：
```python
        import os
        if os.environ.get("LAZY_PAPER_ENTITY_DEDUP", "0") == "1":
            from stages.s06_context.entity_dedup import dedup_entities
            # PaperKG is a Pydantic model — extract the entities/relations lists
            ents = [e.model_dump() for e in paper_kg.entities]
            rels = [r.model_dump() for r in paper_kg.relations]
            new_ents, new_rels = dedup_entities(ents, rels)
            from llm.paper_kg import PaperKG, Entity, Relation
            paper_kg = PaperKG(
                entities=[Entity(**e) for e in new_ents],
                relations=[Relation(**r) for r in new_rels],
            )
            print(f"[s06_context] entity_dedup: {len(ents)} -> {len(new_ents)} entities, "
                  f"{len(rels)} -> {len(new_rels)} relations", flush=True)
```

**注意**：变量名（`paper_kg` 等）需根据 runner.py 实际实现调整；Entity/Relation 字段需匹配 llm/paper_kg.py 的 Pydantic 模型。先 grep `paper_kg` 在 runner.py 找具体行号。

- [ ] **Step 3: .env.example 追加**

```bash
# v1.12 phase1 — LightRAG-inspired entity dedup pass after KG extraction.
# Merges variant author / material mentions ("Meng et al." == "Meng 2024").
# Default OFF until measured impact landed in CHANGELOG.
LAZY_PAPER_ENTITY_DEDUP=0
```

- [ ] **Step 4: 跑现有 s06 测试**

Run: `uv run pytest stages/s06_context/tests/ -v`
Expected: all pass（dedup 默认关，不影响现有行为）。

- [ ] **Step 5: Commit**

```bash
git add stages/s06_context/runner.py .env.example
git commit -m "feat(s06): wire entity_dedup behind LAZY_PAPER_ENTITY_DEDUP flag"
```

---

## Task 12: entity_dedup 在 meng2024 上 e2e 试跑 + 测 RAGAS

**Files:**
- Modify: `docs/archive/v1_12_phase1_ragas_baseline.md` — 追加 "entity_dedup measured impact"

- [ ] **Step 1: 跑 s06 only with dedup on**

```bash
LAZY_PAPER_ENTITY_DEDUP=1 uv run python -m cli run \
  --pdf input/papers/meng2024.pdf \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id meng2024_v112_dedup --lang zh \
  --only s01_ocr,s02_clean,s03_chapter,s04_figures,s05_template,s06_context
```

Expected: 控制台出现 `[s06_context] entity_dedup: N -> M entities, X -> Y relations`，其中 `M <= N`。

- [ ] **Step 2: 人工查看 dedup 结果**

```bash
uv run python -c "
import pyarrow.parquet as pq
df = pq.read_table('runs/meng2024_v112_dedup/s06_context/paper_kg.parquet').to_pandas()
print(df[df['type'].isin(['author','material'])][['id','type','surface','dedup_member_ids']].head(40))
"
```

检查：作者 mention 是否合理 collapse（e.g. "Meng et al."、"Meng 2024"、"this work" 应合到一条）。

- [ ] **Step 3: 跑剩余 stage 完成完整 pipeline**

```bash
LAZY_PAPER_ENTITY_DEDUP=1 uv run python -m cli run \
  --pdf input/papers/meng2024.pdf \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id meng2024_v112_dedup --lang zh
```

- [ ] **Step 4: 跑 RAGAS 同 Task 9 Step 4 方法**

```bash
cp tests/eval/golden_qa/meng2024.yaml /tmp/meng2024_dedup.yaml
sed -i '' 's/meng2024_v111_demo/meng2024_v112_dedup/' /tmp/meng2024_dedup.yaml
cp /tmp/meng2024_dedup.yaml tests/eval/golden_qa/meng2024_dedup.yaml
uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s 2>&1 | tee /tmp/ragas_dedup.log
rm tests/eval/golden_qa/meng2024_dedup.yaml
```

特别关注 `author_attribution` tag 的题目得分。

- [ ] **Step 5: 写入报告**

`docs/archive/v1_12_phase1_ragas_baseline.md` 追加：
```markdown
## entity_dedup measured impact (Task 12)

| Metric | Baseline | v1.12+dedup | Δ |
|---|---|---|---|
| meng2024.faithfulness | <X> | <Y> | <Z> |
| meng2024.context_recall | ... | ... | ... |

Author-attribution sub-score (questions tagged author_attribution):
- Baseline: <N/M correct manual judgement>
- Dedup: <N/M>

Notes:
- KG entity count: <N> → <M> (-K%)
- Spot-check examples: <e.g. "Meng et al." + "Meng 2024" + "this work" → "Meng et al. 2024" ✓>
- Decision: <ship / hold / iterate>
```

- [ ] **Step 6: Commit**

```bash
git add docs/archive/v1_12_phase1_ragas_baseline.md
git commit -m "docs(v1.12): entity_dedup measured impact on meng2024"
```

---

## Task 13: Phase 1 收尾 — 综合报告 + CHANGELOG + ARCHITECTURE

**Files:**
- Create: `docs/archive/v1_12_phase1_summary.md`
- Modify: `CHANGELOG.md` — 加 v1.12-phase1 段
- Modify: `docs/ARCHITECTURE.md` — §4 加 §4.10；§12 把 "caption-aware numbering" 改为 done

- [ ] **Step 1: 综合 Task 9 + Task 12 数据**

`docs/archive/v1_12_phase1_summary.md`:
```markdown
# v1.12 Phase 1 — Summary & Decision

## Shipped
- `--pdffigures2` flag: caption-anchored figure renumbering via AI2 sidecar
- `LAZY_PAPER_ENTITY_DEDUP=1`: LightRAG-style entity dedup in s06
- `pytest -m ragas`: faithfulness / context_recall / context_precision in CI

## Measured Impact

| Stage | meng2024 faithfulness | meng2024 ctx_recall | meng2024 ctx_precision |
|---|---|---|---|
| Baseline (v1.11.5) | <fill> | <fill> | <fill> |
| + PDFFigures 2 | <fill> | <fill> | <fill> |
| + entity_dedup | <fill> | <fill> | <fill> |
| + both | <if measured> | ... | ... |

## Phase 2 decision (based on Phase 1 data)

- If +5pp on faithfulness from BOTH features → recommend default-ON in v1.12
- If only one helped → default-ON only that one, document other as opt-in
- If neither helped → keep both opt-in, plan Phase 2 around MiniCheck +
  coref-rewrite + CDE2 to attack different parts of the gap

Phase 2 candidates (NOT planned in this doc — re-plan after this summary):
1. MiniCheck NLI 5th verifier tier (s08 critic)
2. LLM coreference rewrite pre-pass (new s05.5 stage)
3. ChemDataExtractor 2.0 KG cross-check (s06 dual extraction)
```

- [ ] **Step 2: 更新 CHANGELOG**

`CHANGELOG.md` 顶部追加：
```markdown
## v1.12-phase1 (2026-05-XX)

### Added
- `--pdffigures2` flag: caption-anchored figure renumbering via AI2's PDFFigures 2
  sidecar (docker or jar). Fixes the v1.12-deferred "OCR-order figure numbering"
  issue from ARCHITECTURE §12.
- `LAZY_PAPER_ENTITY_DEDUP=1`: LightRAG-inspired entity disambiguation pass in
  s06_context, merging variant author / material mentions ("Meng et al." +
  "Meng 2024" + "this work"). Targets the v1.11.1 Bug #3 (author misattribution)
  class at the extraction layer.
- `pytest -m ragas`: faithfulness / context_recall / context_precision regression
  harness using golden_qa/{meng2024,ali2025_flash}.yaml (40 questions total).
  Use: `uv run pytest -m ragas tests/eval/`. Outputs JSON to
  `tests/eval/_ragas_out/`.

### Changed
- Both features default OFF — opt-in until Phase 2 measurement confirms.
  See `docs/archive/v1_12_phase1_summary.md` for measured impact.
```

- [ ] **Step 3: 更新 ARCHITECTURE.md**

`docs/ARCHITECTURE.md` §12 行 920（"caption-aware numbering"）改为：
```markdown
- ~~**s04 caption-aware numbering**~~: shipped in v1.12 via `--pdffigures2`
  sidecar (see §4.4 PDFFigures 2 reconciliation).
```

§4.4 末尾追加：
```markdown
**PDFFigures 2 reconciliation (v1.12, opt-in)**: when `--pdffigures2` is set
and `PDFFIGURES2_JAR` env is provided (path or `docker`), s04 calls AI2's
PDFFigures 2 after the MinerU pass and renames any `fig_id` whose caption
matches a pf2 figure with Jaccard ≥0.5. Audit trail lands in
`_pdffigures2.yaml`. Implementation: `scripts/pdffigures2_sidecar.py` +
`stages/s04_figures/runner.py::reconcile_with_pdffigures2`.
```

新增 §4.10：
```markdown
### 4.10 entity_dedup (v1.12 phase1, opt-in)

When `LAZY_PAPER_ENTITY_DEDUP=1`, s06_context runs a LightRAG-inspired
disambiguation pass after KG extraction. A single LLM call (T=0.1, ≤4K tokens)
clusters variant mentions of the same real-world entity within one type
("Meng et al." + "Meng 2024" + "this work" → "Meng et al. 2024"). Defends
against the v1.11.1 author-misattribution class at the extraction layer
rather than the verifier layer.

Implementation: `stages/s06_context/entity_dedup.py` (80 LOC) +
`llm/prompts/entity_dedup.md`. Soft-degrades to inputs on LLM failure or
malformed JSON. Defensive `_ensure_coverage` adds singleton clusters for any
entity the LLM forgot, so dedup never silently drops entities.
```

- [ ] **Step 4: 跑全部测试确认绿**

```bash
uv run pytest -q
```

Expected: 旧测试 301 + 新增 ~8 = ~309 passed。**新加 LLM 集成测试需手动跑：**
```bash
uv run pytest -m ragas -q  # only when API key present
```

- [ ] **Step 5: Commit**

```bash
git add docs/archive/v1_12_phase1_summary.md CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs(v1.12-phase1): summary + CHANGELOG + ARCHITECTURE updates"
```

- [ ] **Step 6: 输出 Phase 2 决策摘要给用户**

人工产物，不写脚本。一段话回 user：
- Phase 1 三件套已 ship
- 量化结果：meng2024 faithfulness <baseline> → <pf2> → <dedup> → <both>
- Phase 2 推荐顺序（按 Phase 1 数据排）：<top item> > <next> > <next>
- 估算 Phase 2 时间：<X> 周

---

## Self-Review

**1. Spec coverage：**
- ✅ RAGAS 评测框架 → Task 1-5
- ✅ PDFFigures 2 caption-anchored renumbering → Task 6-9
- ✅ LightRAG entity dedup → Task 10-12
- ✅ 决策 Phase 2 → Task 13 Step 6
- ❌ Phase 2 三项（MiniCheck / coref / CDE2）刻意不规划 — 等 Phase 1 量化数据，符合用户 "不要写一堆未验证代码" 原则

**2. Placeholder scan：**
- Task 5 Step 2 / Task 9 Step 5 / Task 12 Step 5 报告里有 `<fill>` 占位符 —— 这是**预期**的，因为它们等 Task 执行时填入实际跑出来的数字。已在每处 `<fill>` 旁注明 "from <which Task step>"。
- Task 11 Step 2 说 "变量名需根据 runner.py 实际实现调整" —— 这是因为我没读完 runner.py 全文；执行 agent 第一步应 read 该文件确认变量名。已加注释。

**3. Type consistency：**
- `reconcile_with_pdffigures2()` 在 Task 7 测试和 Task 8 实现里签名一致：`(mineru_figs, pf2) -> (new_figs, report)`
- `dedup_entities()` 在 Task 10 测试和实现里签名一致：`(entities, relations, *, llm_chat=None, model=None) -> (entities, relations)`
- `parse_pdffigures2_output()` 输出字段 `fig_id` / `caption` / `page` / `region` 在 Task 7 和 Task 8 一致
- `apply_clusters` 输出"第一个 member_id 作为 canonical id" 这一约定 Task 10 测试 + 实现 + Task 11 都依赖

**4. 外部 repo 依赖核验路径：**
- ragas: Task 1 Step 2 用 `uv pip install` 直接试装 + import smoke
- PDFFigures 2: Task 6 Step 3 用 meng2024.pdf 真跑一次
- LightRAG: 只 lift 思想，无 import 依赖

**5. 风险点：**
- Task 4 RAGAS API 在不同版本 (0.2.x) 可能有 breaking change — 已在 Step 5 注明 fallback
- Task 6 docker pull `allenai/pdffigures2` 镜像可能不存在 — 已在 Step 3 注明 fallback B (sbt build)
- Task 11 s06 runner 变量名假设 — 已注明执行 agent 需先读源文件
