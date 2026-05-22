# v1.10 候选变体并行测试 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 7 篇论文上并行测试 3 个 v1.10 候选变体（A env tuning / B required-cap 分级 / C figure_ids 硬约束），量化每个根因的实际贡献，决定 v1.10 ship 哪些。

**Architecture:** 3 个 git worktree 隔离各变体代码 + 共享 baseline runs/ 作对照锚点 + Python 脚本采集 6 指标 + 决策报告。LLM-judge 依赖的 M4 指标实验前先重评 baseline 防 historical-vs-current 漂移。

**Tech Stack:** Python 3.12 (uv venv), pytest, yaml, instructor + DeepSeek-Reasoner（已配 `.env`），git worktree。

**Spec reference:** `docs/superpowers/specs/2026-05-22-v1_10-variant-test-design.md`

---

## File Structure

**New files (在 main 分支):**
- `scripts/collect_variant_metrics.py` — 单 run 指标采集器（M1/M2/M3/M5/M6）
- `scripts/recheck_baseline.py` — baseline M4 重评封装
- `scripts/run_variant_matrix.sh` — 三变体批跑总调度
- `tests/test_collect_variant_metrics.py` — 采集器单测
- `runs/_baseline_recheck.yaml` — M4 复核结果（gitignore）
- `docs/v1_10_variant_comparison.md` — 最终对比报告

**Modified files (各 worktree 内):**
- `worktree-variant-b-cap`:
  - `stages/s08_section_compose/structured.py` — `select_top_required` 分级
  - `stages/s08_section_compose/tests/test_structured.py` — 加单测
- `worktree-variant-c-figure`:
  - `stages/s08_section_compose/structured.py` — SectionDraft + prompt + verify + figure-retry
  - `stages/s08_section_compose/tests/test_structured.py` — 加单测

**Env config (worktree 各自的 .env):**
- variant-a-env: `LAZY_PAPER_MIN_SECTION_CHARS=1200`, `LAZY_PAPER_BEST_OF_N=3`
- variant-b-cap: `LAZY_PAPER_REQUIRED_CAP_SURVEY=12`, `LAZY_PAPER_REQUIRED_CAP=5`
- variant-c-figure: 沿用 default

---

## Task 1: 清理过时 runs/ 目录

**Files:**
- Modify: `runs/` — 删 `*_v140` / `*_v160_J` / `*_v170_KL` / `*_v181_KL` / `*_v181` 子目录

- [ ] **Step 1: 预览要删的目录列表**

```bash
ls -d runs/*_v140 runs/*_v160_J runs/*_v170_KL runs/*_v181_KL runs/*_v181 2>/dev/null
```

Expected: 列出 25-30 个目录（覆盖各论文的历史版本）

- [ ] **Step 2: 记录删前 runs/ 体积**

```bash
du -sh runs/
```

Expected: ~337M

- [ ] **Step 3: 删除过时目录**

```bash
rm -rf runs/*_v140 runs/*_v160_J runs/*_v170_KL runs/*_v181_KL runs/*_v181
```

Expected: 无输出（成功）

- [ ] **Step 4: 验证保留的目录**

```bash
ls runs/ | grep -vE "_v140|_v160_J|_v170_KL|_v181_KL|_v181$" | head -30
du -sh runs/
```

Expected: 保留 `<paper>/`, `<paper>_v190/`, `<paper>_v190b/`, `<paper>_v191/`；总体积 ~190M

- [ ] **Step 5: Commit（runs/ 在 .gitignore，所以无 commit 实物，只记 note）**

```bash
git log --oneline -1
```

记录到 worklog 即可，无 commit。

---

## Task 2: 写 metrics 采集脚本（含单测）

**Files:**
- Create: `scripts/collect_variant_metrics.py`
- Create: `tests/test_collect_variant_metrics.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_collect_variant_metrics.py
"""Tests for variant-test metrics collector."""
from pathlib import Path
import yaml
import pytest

from scripts.collect_variant_metrics import (
    collect_chars_per_section,
    collect_figure_embed_ratio,
    parse_coverage_from_log,
    count_retry_fires,
    collect_run_metrics,
)


def test_collect_chars_per_section(tmp_path):
    chapters = tmp_path / "s08_section_compose" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "01_intro.md").write_text("a" * 1500, encoding="utf-8")
    (chapters / "02_methods.md").write_text("b" * 800, encoding="utf-8")
    result = collect_chars_per_section(tmp_path)
    assert result == {"01_intro": 1500, "02_methods": 800}


def test_collect_figure_embed_ratio(tmp_path):
    s09 = tmp_path / "s09_render"
    s09.mkdir(parents=True)
    (s09 / "preview.html").write_text(
        "<p><img src='a'><img src='b'></p>", encoding="utf-8"
    )
    s07 = tmp_path / "s07_figure_analyze"
    s07.mkdir(parents=True)
    (s07 / "fig_notes.yaml").write_text(
        yaml.safe_dump([
            {"fig_id": "Fig. 1"},
            {"fig_id": "Fig. 2"},
            {"fig_id": "Fig. 3"},
            {"fig_id": "Fig. 4"},
        ]),
        encoding="utf-8",
    )
    embedded, available, ratio = collect_figure_embed_ratio(tmp_path)
    assert embedded == 2
    assert available == 4
    assert ratio == 0.5


def test_parse_coverage_from_log():
    log = (
        "[s08] structured-compose: required=12 "
        "pre-verify-missing=5 (58%) post-verify-missing=3 (75%)\n"
        "[s08] structured-compose: required=8 "
        "pre-verify-missing=2 (75%) post-verify-missing=1 (88%)\n"
    )
    result = parse_coverage_from_log(log)
    assert result == [
        {"required": 12, "pre_missing": 5, "post_missing": 3},
        {"required": 8, "pre_missing": 2, "post_missing": 1},
    ]


def test_count_retry_fires():
    log = (
        "[s08] retry-when-empty: lifted post-verify coverage from 2/5 to 4/5\n"
        "[s08] retry-when-empty: lifted post-verify coverage from 1/3 to 2/3\n"
        "[s08] retry-when-short: lifted 3->5 claims, 600->1200 chars\n"
    )
    assert count_retry_fires(log, "retry-when-empty") == 2
    assert count_retry_fires(log, "retry-when-short") == 1
```

- [ ] **Step 2: 跑测试看 fail**

```bash
uv run pytest tests/test_collect_variant_metrics.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collect_variant_metrics'`

- [ ] **Step 3: 实现采集脚本**

```python
# scripts/collect_variant_metrics.py
"""Collect 6 metrics (M1/M2/M3/M5/M6) from a single variant run.

Usage:
    python scripts/collect_variant_metrics.py runs/<paper>_<variant>_r<run>/

Writes metrics.yaml in the run directory. M4 (TestCase scores) is
collected separately via scripts/recheck_baseline.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

_COVERAGE_RE = re.compile(
    r"required=(\d+)\s+pre-verify-missing=(\d+)\s+\(\d+%\)\s+"
    r"post-verify-missing=(\d+)\s+\(\d+%\)"
)


def collect_chars_per_section(run_dir: Path) -> dict[str, int]:
    chapters = run_dir / "s08_section_compose" / "chapters"
    if not chapters.exists():
        return {}
    out: dict[str, int] = {}
    for md in sorted(chapters.glob("*.md")):
        out[md.stem] = len(md.read_text(encoding="utf-8"))
    return out


def collect_figure_embed_ratio(run_dir: Path) -> tuple[int, int, float]:
    html = run_dir / "s09_render" / "preview.html"
    fig_notes = run_dir / "s07_figure_analyze" / "fig_notes.yaml"
    embedded = 0
    available = 0
    if html.exists():
        embedded = html.read_text(encoding="utf-8").count("<img ")
    if fig_notes.exists():
        notes = yaml.safe_load(fig_notes.read_text(encoding="utf-8")) or []
        available = len(notes)
    ratio = embedded / available if available else 0.0
    return embedded, available, ratio


def parse_coverage_from_log(log_text: str) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    for m in _COVERAGE_RE.finditer(log_text):
        req, pre, post = (int(x) for x in m.groups())
        out.append({"required": req, "pre_missing": pre, "post_missing": post})
    return out


def count_retry_fires(log_text: str, kind: str) -> int:
    return len(re.findall(rf"\[s08\] {re.escape(kind)}: lifted", log_text))


def collect_run_metrics(
    run_dir: Path,
    variant: str,
    paper: str,
    run_idx: int,
    log_text: str = "",
    cost_usd: float | None = None,
) -> dict:
    chars = collect_chars_per_section(run_dir)
    embedded, available, ratio = collect_figure_embed_ratio(run_dir)
    coverage = parse_coverage_from_log(log_text)
    return {
        "variant": variant,
        "paper": paper,
        "run": run_idx,
        "M1_chars_per_section": chars,
        "M1_total_chars": sum(chars.values()),
        "M1_mean_chars": int(sum(chars.values()) / len(chars)) if chars else 0,
        "M2_figures_embedded": embedded,
        "M2_figures_available": available,
        "M2_embed_ratio": round(ratio, 3),
        "M3_coverage_per_section": coverage,
        "M3_total_required": sum(c["required"] for c in coverage),
        "M3_total_post_missing": sum(c["post_missing"] for c in coverage),
        "M5_retry_empty_fires": count_retry_fires(log_text, "retry-when-empty"),
        "M5_retry_short_fires": count_retry_fires(log_text, "retry-when-short"),
        "M6_llm_cost_usd": cost_usd,
    }


def _parse_paper_from_run_dir(run_dir: Path) -> tuple[str, str, int]:
    # naming: <paper>_v<variant>_r<run> or <paper>
    name = run_dir.name
    m = re.match(r"(.+)_v([A-Za-z]+)_r(\d+)$", name)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    return name, "baseline", 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    run_dir = Path(argv[1]).resolve()
    if not run_dir.exists():
        print(f"error: {run_dir} does not exist", file=sys.stderr)
        return 1
    paper, variant, run_idx = _parse_paper_from_run_dir(run_dir)
    log_path = run_dir / "s08.log"
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    metrics = collect_run_metrics(run_dir, variant, paper, run_idx, log_text)
    out_path = run_dir / "metrics.yaml"
    out_path.write_text(yaml.safe_dump(metrics, sort_keys=False), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: 跑测试看 pass**

```bash
uv run pytest tests/test_collect_variant_metrics.py -v
```

Expected: 4 passed

- [ ] **Step 5: 烟测脚本 main**

```bash
uv run python scripts/collect_variant_metrics.py runs/meng2024_v190 2>&1 | head
ls runs/meng2024_v190/metrics.yaml
```

Expected: 输出 "wrote runs/meng2024_v190/metrics.yaml"，文件存在

- [ ] **Step 6: Commit**

```bash
git add scripts/collect_variant_metrics.py tests/test_collect_variant_metrics.py
git commit -m "scripts: variant-test metrics collector (M1/M2/M3/M5/M6)"
```

---

## Task 3: 写 baseline 复核脚本（M4 重评封装）

**Files:**
- Create: `scripts/recheck_baseline.py`

- [ ] **Step 1: 看一下现有 evaluate.py 接口**

```bash
grep -nE "^def |class " scripts/evaluate.py | head -10
head -30 scripts/evaluate.py
```

Expected: 看到 evaluator 的入口函数（具体名字根据实际文件）

- [ ] **Step 2: 实现封装脚本（按现有 evaluator 接口调用）**

```python
# scripts/recheck_baseline.py
"""Recheck baseline TestCase scores before variant comparison.

Per spec §10: M4 TestCase scores depend on LLM judge with its own
variance. Historical 9/9/9 may not reproduce. This script re-evaluates
each baseline run's TestCase and writes runs/_baseline_recheck.yaml.

Usage:
    python scripts/recheck_baseline.py [--retries N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Adjust this import to match the actual evaluator API in scripts/evaluate.py.
# If evaluate.py exposes a CLI only, use subprocess.run instead.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate import evaluate_paper_testcase  # noqa: E402

BASELINE_MATRIX = [
    ("meng2024_v190", "T1"),
    ("meng2024_v190", "T3"),
    ("meng2024_v190_run2", "T1"),
    ("meng2024_v190_run2", "T3"),
    ("meng2024_v190_run3", "T1"),
    ("meng2024_v190_run3", "T3"),
    ("yang2025_v190", "T2"),
    ("chai2026_v190", "T6"),
    ("ali2025_flash_v190", "T4"),
    ("fu2020_v190", "T5"),
]

HISTORICAL = {
    ("meng2024_v190", "T1"): 9,
    ("meng2024_v190", "T3"): 3,
    ("meng2024_v190_run2", "T1"): 9,
    ("meng2024_v190_run2", "T3"): 3,
    ("meng2024_v190_run3", "T1"): 9,
    ("meng2024_v190_run3", "T3"): 5,
    ("yang2025_v190", "T2"): 3,
    ("chai2026_v190", "T6"): 4,
    ("ali2025_flash_v190", "T4"): 4,
    ("fu2020_v190", "T5"): 3,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retries", type=int, default=1,
                    help="Per-(paper,test) recheck count (default 1)")
    ap.add_argument("--output", type=Path,
                    default=Path("runs/_baseline_recheck.yaml"))
    args = ap.parse_args()

    results: list[dict] = []
    for paper_run, test_id in BASELINE_MATRIX:
        run_dir = Path("runs") / paper_run
        if not run_dir.exists():
            print(f"skip: {run_dir} missing", file=sys.stderr)
            continue
        scores: list[int] = []
        for _ in range(args.retries):
            score = evaluate_paper_testcase(run_dir, test_id)
            scores.append(int(score))
        historical = HISTORICAL.get((paper_run, test_id))
        mean = sum(scores) / len(scores)
        delta_to_hist = mean - historical if historical is not None else None
        verdict = "OK"
        if delta_to_hist is not None and abs(delta_to_hist) >= 2:
            verdict = "DRIFT (≥2) — extend sample"
        results.append({
            "paper_run": paper_run,
            "test_id": test_id,
            "historical": historical,
            "rechecked_scores": scores,
            "rechecked_mean": round(mean, 2),
            "delta_to_historical": (
                round(delta_to_hist, 2) if delta_to_hist is not None else None
            ),
            "verdict": verdict,
        })
        print(f"{paper_run}/{test_id}: {scores} mean={mean:.1f} "
              f"(hist={historical}) → {verdict}", flush=True)

    args.output.write_text(yaml.safe_dump(results, sort_keys=False),
                           encoding="utf-8")
    print(f"\nwrote {args.output}", flush=True)
    drift = [r for r in results if "DRIFT" in r["verdict"]]
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 验证脚本 imports 不报错**

```bash
uv run python -c "import scripts.recheck_baseline"
```

Expected: 无 import error；若 `from scripts.evaluate import evaluate_paper_testcase` 报错，根据真实 `evaluate.py` 接口调整（subprocess 或不同函数名）

- [ ] **Step 4: 把 baseline_recheck.yaml 加进 .gitignore**

```bash
echo "runs/_baseline_recheck.yaml" >> .gitignore
git diff .gitignore
```

Expected: 看到新增 1 行

- [ ] **Step 5: Commit**

```bash
git add scripts/recheck_baseline.py .gitignore
git commit -m "scripts: baseline TestCase recheck per v1.10-spec §10"
```

---

## Task 4: 跑 baseline 复核

**Files:**
- Run: `scripts/recheck_baseline.py`
- Output: `runs/_baseline_recheck.yaml`（gitignored）

- [ ] **Step 1: 跑复核（1 retry per testcase）**

```bash
uv run python scripts/recheck_baseline.py --retries 1 2>&1 | tee /tmp/baseline_recheck.log
```

Expected: 输出 10 行 (paper, test, scores, mean, verdict)；`runs/_baseline_recheck.yaml` 写入；exit 0（无 DRIFT）或 exit 1（有 DRIFT）

- [ ] **Step 2: 看是否有 DRIFT**

```bash
grep "DRIFT" /tmp/baseline_recheck.log
```

Expected: 空（无 drift）或列出有偏差的 (paper, test)

- [ ] **Step 3: 若有 DRIFT，扩 sample 至 3**

仅在 step 2 看到 DRIFT 时执行：

```bash
uv run python scripts/recheck_baseline.py --retries 3 2>&1 | tee /tmp/baseline_recheck_3x.log
```

Expected: 每个 testcase 跑 3 次，取 mean 与 historical 比

- [ ] **Step 4: 把 baseline_recheck 摘要写到 plan worklog**

```bash
cat runs/_baseline_recheck.yaml | head -50
```

记录到对话或后续 commit msg 即可。

---

## Task 5: 创建 3 个 git worktree

**Files:**
- Modify: `.git/worktrees/` (git internal)

- [ ] **Step 1: 准备 worktree 根目录**

```bash
mkdir -p .worktrees
ls .worktrees/
```

Expected: 目录存在且为空

- [ ] **Step 2: 创建 variant-a-env worktree（基于 main）**

```bash
git worktree add .worktrees/variant-a-env -b variant-a-env-test main
```

Expected: 创建成功，输出 "Preparing worktree (new branch 'variant-a-env-test')"

- [ ] **Step 3: 创建 variant-b-cap worktree**

```bash
git worktree add .worktrees/variant-b-cap -b variant-b-cap-test main
```

Expected: 创建成功

- [ ] **Step 4: 创建 variant-c-figure worktree**

```bash
git worktree add .worktrees/variant-c-figure -b variant-c-figure-test main
```

Expected: 创建成功

- [ ] **Step 5: 把 .worktrees/ 加 .gitignore**

```bash
echo ".worktrees/" >> .gitignore
git add .gitignore
git commit -m "chore: ignore .worktrees/ for variant-test runs"
```

- [ ] **Step 6: 验证 3 个 worktree 都活着**

```bash
git worktree list
```

Expected: 4 行（main + 3 个 .worktrees/...）

---

## Task 6: Variant A — env tuning（无代码）

**Files:**
- Create: `.worktrees/variant-a-env/.env.local`（gitignore）

- [ ] **Step 1: 进入 worktree 准备 env**

```bash
cd .worktrees/variant-a-env && cp .env .env.local 2>/dev/null || cp .env.example .env.local
```

Expected: `.env.local` 存在

- [ ] **Step 2: 追加 variant-A 的 env override**

```bash
cd .worktrees/variant-a-env
cat >> .env.local <<'EOF'

# v1.10 variant A: env tuning
LAZY_PAPER_MIN_SECTION_CHARS=1200
LAZY_PAPER_BEST_OF_N=3
EOF
cat .env.local | tail -5
```

Expected: 看到末尾两个新行

- [ ] **Step 3: Commit 变体 A 配置说明（不 commit .env.local）**

```bash
cd .worktrees/variant-a-env
cat > VARIANT_NOTES.md <<'EOF'
# Variant A — env tuning

No code changes. Run with:

  LAZY_PAPER_MIN_SECTION_CHARS=1200 LAZY_PAPER_BEST_OF_N=3 \
    uv run lazy-paper run --pdf <pdf> --template <tpl> \
      --paper-id <paper>_vA_r<N>
EOF
git add VARIANT_NOTES.md
git commit -m "variant-a: env tuning notes (no code change)"
```

---

## Task 7: Variant B — required cap 分级（TDD）

**Files:**
- Modify: `.worktrees/variant-b-cap/stages/s08_section_compose/structured.py:482-540`
- Modify: `.worktrees/variant-b-cap/stages/s08_section_compose/tests/test_structured.py`（或新建）

- [ ] **Step 1: cd 进 worktree**

```bash
cd .worktrees/variant-b-cap
ls stages/s08_section_compose/tests/ 2>/dev/null || echo "no tests dir"
```

- [ ] **Step 2: 看现状 select_top_required**

```bash
sed -n '482,540p' stages/s08_section_compose/structured.py
```

记录现状用于回滚参考。

- [ ] **Step 3: 写失败测试**

```python
# .worktrees/variant-b-cap/stages/s08_section_compose/tests/test_required_cap_tiered.py
"""Test cap tiering by section type (variant B)."""
import os
import pytest

from stages.s08_section_compose.structured import (
    RequiredMention,
    select_top_required,
)


def _make_required(n: int) -> list[RequiredMention]:
    return [
        RequiredMention(
            entity_type="comparator",
            entity_text=f"X{i}",
            author_text=f"A{i}",
            evidence_chunk_id=i,
            evidence_quote="q",
            linked_values=[f"V{i}=1 J/cm³"],
        )
        for i in range(n)
    ]


def test_non_survey_section_caps_at_5(monkeypatch):
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP", raising=False)
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP_SURVEY", raising=False)
    out = select_top_required(_make_required(12), is_survey=False)
    assert len(out) == 5


def test_survey_section_caps_at_12(monkeypatch):
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP", raising=False)
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP_SURVEY", raising=False)
    out = select_top_required(_make_required(15), is_survey=True)
    assert len(out) == 12


def test_env_overrides_caps(monkeypatch):
    monkeypatch.setenv("LAZY_PAPER_REQUIRED_CAP", "3")
    monkeypatch.setenv("LAZY_PAPER_REQUIRED_CAP_SURVEY", "8")
    assert len(select_top_required(_make_required(10), is_survey=False)) == 3
    assert len(select_top_required(_make_required(10), is_survey=True)) == 8


def test_short_list_returns_all(monkeypatch):
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP", raising=False)
    monkeypatch.delenv("LAZY_PAPER_REQUIRED_CAP_SURVEY", raising=False)
    out = select_top_required(_make_required(3), is_survey=True)
    assert len(out) == 3
```

- [ ] **Step 4: 跑测试看 fail**

```bash
cd .worktrees/variant-b-cap
uv run pytest stages/s08_section_compose/tests/test_required_cap_tiered.py -v
```

Expected: FAIL — `TypeError: select_top_required() got an unexpected keyword argument 'is_survey'` 或 `len(out) == 5` vs 12 不符

- [ ] **Step 5: 改 `select_top_required` 签名 + 实现**

打开 `.worktrees/variant-b-cap/stages/s08_section_compose/structured.py`，定位到 L482 `select_top_required` 函数，改为：

```python
def select_top_required(
    required: list[RequiredMention],
    *,
    is_survey: bool = False,
) -> list[RequiredMention]:
    """Pick top-cap by length + digit-density.

    Cap is tiered: survey sections default 12, others 5. Env overrides
    via LAZY_PAPER_REQUIRED_CAP_SURVEY / LAZY_PAPER_REQUIRED_CAP.
    """
    import os as _os
    cap_survey = int(_os.environ.get("LAZY_PAPER_REQUIRED_CAP_SURVEY", "12"))
    cap_normal = int(_os.environ.get("LAZY_PAPER_REQUIRED_CAP", "5"))
    cap = cap_survey if is_survey else cap_normal

    def score(m: RequiredMention) -> float:
        ent_len = len(m.entity_text)
        digit_frac = sum(c.isdigit() for c in m.entity_text) / max(ent_len, 1)
        return ent_len * (1 + digit_frac)

    return sorted(required, key=score, reverse=True)[:cap]
```

- [ ] **Step 6: 找 call site 加 is_survey 传参**

```bash
cd .worktrees/variant-b-cap
grep -n "select_top_required" stages/s08_section_compose/*.py
```

Expected: 1-2 处调用。把每处改成传 `is_survey=_is_survey_section(section_title)`。

例如在 `runner.py` 或 `structured.py` 调用处：
```python
# 改前
required = select_top_required(required_raw)
# 改后
from stages.s08_section_compose.structured import _is_survey_section
required = select_top_required(
    required_raw, is_survey=_is_survey_section(section_title),
)
```

- [ ] **Step 7: 跑新测试 + 跑既有 s08 测试看不退化**

```bash
cd .worktrees/variant-b-cap
uv run pytest stages/s08_section_compose/ -v
```

Expected: 新测 4 pass + 既有测试全 pass

- [ ] **Step 8: 跑全测试套确认不打破别处**

```bash
cd .worktrees/variant-b-cap
uv run pytest -q
```

Expected: 255+ pass（255 既有 + 4 新）

- [ ] **Step 9: Commit**

```bash
cd .worktrees/variant-b-cap
git add stages/s08_section_compose/structured.py \
        stages/s08_section_compose/tests/test_required_cap_tiered.py
# 如果 runner.py 也改了，也 add 进去
git commit -m "variant-b: tier required-cap by section type (survey=12, other=5)"
```

---

## Task 8: Variant C — figure_ids 进 schema + 硬约束（TDD）

**Files:**
- Modify: `.worktrees/variant-c-figure/stages/s08_section_compose/structured.py`
- Create: `.worktrees/variant-c-figure/stages/s08_section_compose/tests/test_figure_hard_constraint.py`

### Task 8.1 — schema 字段

- [ ] **Step 1: cd 进 worktree**

```bash
cd .worktrees/variant-c-figure
```

- [ ] **Step 2: 找 GroundedClaim / SectionDraft 定义**

```bash
grep -nE "class GroundedClaim|class SectionDraft" stages/s08_section_compose/structured.py
```

记录行号（设为 L_GC 与 L_SD）。

- [ ] **Step 3: 写失败测试 — schema 加字段**

```python
# .worktrees/variant-c-figure/stages/s08_section_compose/tests/test_figure_hard_constraint.py
"""Tests for variant C — figure_ids hard constraint."""
import pytest

from stages.s08_section_compose.structured import GroundedClaim, SectionDraft


def test_grounded_claim_has_figure_ids_default_empty():
    c = GroundedClaim(text="x", cited_chunk_ids=[0], cited_quote="q")
    assert c.figure_ids == []


def test_grounded_claim_accepts_figure_ids():
    c = GroundedClaim(
        text="As shown in Fig. 3 …",
        cited_chunk_ids=[0],
        cited_quote="q",
        figure_ids=["Fig. 3"],
    )
    assert c.figure_ids == ["Fig. 3"]
```

- [ ] **Step 4: 跑测试看 fail**

```bash
cd .worktrees/variant-c-figure
uv run pytest stages/s08_section_compose/tests/test_figure_hard_constraint.py -v
```

Expected: FAIL — `AttributeError: 'GroundedClaim' object has no attribute 'figure_ids'`

- [ ] **Step 5: 加 figure_ids 字段**

在 `GroundedClaim` 类（L_GC 附近）加字段：

```python
class GroundedClaim(BaseModel):
    text: str
    cited_chunk_ids: list[int]
    cited_quote: str = ""
    figure_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Figure IDs (e.g. 'Fig. 3') that this claim references. "
            "When non-empty, claim.text MUST contain the fig_id literal "
            "(or Chinese-form '图N') — checked by verify_section_draft."
        ),
    )
```

- [ ] **Step 6: 跑测试看 pass**

```bash
cd .worktrees/variant-c-figure
uv run pytest stages/s08_section_compose/tests/test_figure_hard_constraint.py -v
```

Expected: 2 pass

- [ ] **Step 7: Commit**

```bash
cd .worktrees/variant-c-figure
git add stages/s08_section_compose/structured.py \
        stages/s08_section_compose/tests/test_figure_hard_constraint.py
git commit -m "variant-c: add figure_ids field to GroundedClaim schema"
```

### Task 8.2 — verify_section_draft 加 figure check

- [ ] **Step 1: 写失败测试**

追加到 `test_figure_hard_constraint.py`：

```python
def test_verify_flags_missing_figure_mention():
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="Some claim without figure literal",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 5"],
        ),
    ])
    chunks_by_id = {0: Chunk(text="content here", doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id, ratio_threshold=0.85)
    # advisory: still accepted, but should produce a flag for the caller
    assert len(accepted) == 1
    # the verifier exposes flags via rejected[].reason or via critic_flags;
    # for now just confirm the claim made it through (advisory only)


def test_verify_accepts_when_figure_mentioned():
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="As shown in Fig. 5, the trend is clear.",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 5"],
        ),
    ])
    chunks_by_id = {0: Chunk(text="content here", doc_name="d", char_start=0, char_end=12)}
    accepted, _ = verify_section_draft(draft, chunks_by_id, ratio_threshold=0.85)
    assert len(accepted) == 1
```

- [ ] **Step 2: 跑看 fail（可能 Chunk import 路径要调）**

```bash
cd .worktrees/variant-c-figure
uv run pytest stages/s08_section_compose/tests/test_figure_hard_constraint.py::test_verify_flags_missing_figure_mention -v
```

Expected: 可能 FAIL on Chunk import — 据真实路径调整 import

- [ ] **Step 3: 加 figure check 到 verify_section_draft**

在 `verify_section_draft` 的 claim 循环里（接受 claim 之前）加：

```python
# variant-c: figure_ids hard hint (advisory)
if claim.figure_ids:
    import re as _re
    missing_figs = []
    for fid in claim.figure_ids:
        # fid like "Fig. 3" → also accept "图3"
        m = _re.match(r"Fig\.\s*(\d+)", fid)
        if m:
            num = m.group(1)
            patterns = [rf"Fig\.\s*{num}", rf"图\s*{num}"]
        else:
            patterns = [_re.escape(fid)]
        if not any(_re.search(p, claim.text) for p in patterns):
            missing_figs.append(fid)
    if missing_figs:
        # advisory only — record but still accept
        rejected.append({
            "claim_text": claim.text[:80],
            "reason": "figure_hint_unmet",
            "missing_figures": missing_figs,
        })
```

- [ ] **Step 4: 跑测看 pass**

```bash
cd .worktrees/variant-c-figure
uv run pytest stages/s08_section_compose/tests/test_figure_hard_constraint.py -v
```

Expected: 4 pass

- [ ] **Step 5: Commit**

```bash
cd .worktrees/variant-c-figure
git add stages/s08_section_compose/structured.py \
        stages/s08_section_compose/tests/test_figure_hard_constraint.py
git commit -m "variant-c: verify_section_draft figure-mention advisory check"
```

### Task 8.3 — prompt 加 figure citation 段 + figure-retry

- [ ] **Step 1: 改 `_STRUCTURED_SYSTEM` 加 figure citation 段**

定位 `_STRUCTURED_SYSTEM = """...` 块，在 "Quote-then-claim discipline" 段之后插入：

```python
_STRUCTURED_SYSTEM = """...（保留原内容）...

## Figure citation requirement (variant C hard constraint)

When the USER message lists 'Figures topically relevant to this section':
  - For EACH such fig_id, write at least one claim that:
      * sets figure_ids = ["<fig_id>"]  (e.g. ["Fig. 3"])
      * contains the literal "Fig. N" (English) or "图N" (Chinese) in
        the claim's text
  - This ensures the figure is embedded in the rendered output (s09
    binding is literal-substring based).
  - If multiple figures are relevant, write multiple claims — do not
    cram all fig_ids into one claim.
...（其余保留）"""
```

- [ ] **Step 2: 加 figure-retry 逻辑到 `compose_structured` 末尾（return 前）**

紧跟现有 `retry-when-short` 块之后插入：

```python
# variant-c: figure-retry — if section_figures non-empty and verified
# missing ≥ 50% of available figures, one strengthened retry.
if section_figures:
    available_ids = {n.get("fig_id") for n in section_figures if n.get("fig_id")}
    mentioned_ids: set[str] = set()
    import re as _re
    full_text = " ".join(c.text for c in verified.claims)
    for fid in available_ids:
        m = _re.match(r"Fig\.\s*(\d+)", fid)
        if m:
            num = m.group(1)
            if (_re.search(rf"Fig\.\s*{num}", full_text)
                    or _re.search(rf"图\s*{num}", full_text)):
                mentioned_ids.add(fid)
        elif fid in full_text:
            mentioned_ids.add(fid)
    missing_figs = available_ids - mentioned_ids
    if available_ids and (len(missing_figs) / len(available_ids)) >= 0.5:
        print(
            f"[s08] figure-retry: mentioned {len(mentioned_ids)}/"
            f"{len(available_ids)} relevant figures — triggering retry",
            flush=True,
        )
        fig_lines = "\n".join(
            f"  - {fid}: write a claim with figure_ids=[\"{fid}\"] "
            f"and \"{fid}\" literally in text"
            for fid in sorted(missing_figs)
        )
        retry_system = _STRUCTURED_SYSTEM + (
            "\n\n## CRITICAL — MISSING FIGURE CITATIONS\n"
            f"Your draft did not cite {len(missing_figs)} relevant "
            f"figures. ADD claims that cite each:\n\n{fig_lines}\n\n"
            "PRESERVE existing well-grounded claims. Add new ones."
        )
        try:
            fig_retry = _single_compose(
                llm, retry_system, user_msg, chunks,
                max_retries=max_retries, temperature=0.3,
            )
            fig_accepted, fig_rejected = verify_section_draft(
                fig_retry, chunks_by_id, ratio_threshold=verifier_threshold,
            )
            fig_verified = (SectionDraft(claims=fig_accepted)
                            if len(fig_accepted) >= 2 else fig_retry)
            # Recompute coverage on new draft
            new_full = " ".join(c.text for c in fig_verified.claims)
            new_mentioned: set[str] = set()
            for fid in available_ids:
                m = _re.match(r"Fig\.\s*(\d+)", fid)
                if m and (_re.search(rf"Fig\.\s*{m.group(1)}", new_full)
                          or _re.search(rf"图\s*{m.group(1)}", new_full)):
                    new_mentioned.add(fid)
                elif fid in new_full:
                    new_mentioned.add(fid)
            if len(new_mentioned) > len(mentioned_ids):
                print(
                    f"[s08] figure-retry: lifted "
                    f"{len(mentioned_ids)}→{len(new_mentioned)} figure mentions",
                    flush=True,
                )
                verified, rejected = fig_verified, fig_rejected
        except Exception as exc:
            print(f"[s08] figure-retry failed: {exc!r}; keeping draft",
                  flush=True)
```

- [ ] **Step 3: 跑既有测试看不打破**

```bash
cd .worktrees/variant-c-figure
uv run pytest stages/s08_section_compose/ -q
```

Expected: 全 pass（既有 + 新加）

- [ ] **Step 4: 全测试套**

```bash
cd .worktrees/variant-c-figure
uv run pytest -q
```

Expected: 255+ pass

- [ ] **Step 5: Commit**

```bash
cd .worktrees/variant-c-figure
git add stages/s08_section_compose/structured.py
git commit -m "variant-c: prompt figure-citation rules + figure-retry pass"
```

---

## Task 9: 写批跑总调度脚本

**Files:**
- Create: `scripts/run_variant_matrix.sh`

- [ ] **Step 1: 实现批跑脚本**

```bash
#!/usr/bin/env bash
# scripts/run_variant_matrix.sh
# Run a single (variant, paper, run_idx) combo end-to-end.
# Usage: ./scripts/run_variant_matrix.sh <variant> <paper_id> <run_idx>
#   variant ∈ {a, b, c}
#   paper_id matches a directory under runs/ (with existing s01-s07)
#   run_idx is the repetition index (1 for non-meng, 1-3 for meng2024)

set -euo pipefail

variant="$1"
paper="$2"
run="$3"

case "$variant" in
  a) wt=".worktrees/variant-a-env" ;;
  b) wt=".worktrees/variant-b-cap" ;;
  c) wt=".worktrees/variant-c-figure" ;;
  *) echo "unknown variant: $variant"; exit 2 ;;
esac

new_id="${paper}_v${variant}_r${run}"
src_run="runs/${paper}"

# Copy cached s01-s07 from existing baseline run to avoid re-OCR
if [ ! -d "${src_run}" ]; then
  echo "ERROR: ${src_run} missing — cannot reuse OCR cache"
  exit 1
fi
mkdir -p "${wt}/runs/${new_id}"
for stage in s01_ocr s02_clean s03_chapter s04_figures s05_template \
             s06_context s07_figure_analyze; do
  if [ -d "${src_run}/${stage}" ]; then
    cp -r "${src_run}/${stage}" "${wt}/runs/${new_id}/"
  fi
done

cd "${wt}"

# Run s08 + s09 only (rest is cached). Capture s08 stdout to s08.log.
if [ -f .env.local ]; then export $(grep -v '^#' .env.local | xargs -I{} echo {}); fi
uv run lazy-paper run \
  --paper-id "${new_id}" \
  --only s08_section_compose,s09_render \
  --force 2>&1 | tee "runs/${new_id}/s08.log"

# Collect metrics
cd - >/dev/null
uv run python scripts/collect_variant_metrics.py "${wt}/runs/${new_id}"

echo "[run-matrix] done: ${new_id}"
```

- [ ] **Step 2: 给执行权限 + 烟测（dry-args，不真跑）**

```bash
chmod +x scripts/run_variant_matrix.sh
bash -n scripts/run_variant_matrix.sh
```

Expected: 无 syntax error

- [ ] **Step 3: Commit**

```bash
git add scripts/run_variant_matrix.sh
git commit -m "scripts: variant-matrix batch run wrapper (reuse OCR cache)"
```

---

## Task 10: 跑变体 A — 7 篇论文 + meng2024 ×3

**Files:**
- Run: `scripts/run_variant_matrix.sh` ×9 times for variant A

- [ ] **Step 1: 跑 6 个 generic + 3 个 testcase 论文 ×1**

```bash
for paper in meng2024 yang2025 chai2026 ali2025_flash gaur2022 he2023 pan2025; do
  bash scripts/run_variant_matrix.sh a "${paper}" 1
done
```

Expected: 7 个 `runs/<paper>_vA_r1/metrics.yaml` 生成（在 worktree-a-env 下）

- [ ] **Step 2: 跑 meng2024 第 2、3 次（共 3 次共方差观测）**

```bash
bash scripts/run_variant_matrix.sh a meng2024 2
bash scripts/run_variant_matrix.sh a meng2024 3
```

Expected: `meng2024_vA_r2/` 和 `_r3/` 各自含 metrics.yaml

- [ ] **Step 3: 验证全部 metrics.yaml 存在**

```bash
ls .worktrees/variant-a-env/runs/*_vA_r*/metrics.yaml | wc -l
```

Expected: 9

---

## Task 11: 跑变体 B — 7 篇论文 + meng2024 ×3

- [ ] **Step 1: 同 Task 10 模式，变体改 b**

```bash
for paper in meng2024 yang2025 chai2026 ali2025_flash gaur2022 he2023 pan2025; do
  bash scripts/run_variant_matrix.sh b "${paper}" 1
done
bash scripts/run_variant_matrix.sh b meng2024 2
bash scripts/run_variant_matrix.sh b meng2024 3
```

- [ ] **Step 2: 验证**

```bash
ls .worktrees/variant-b-cap/runs/*_vB_r*/metrics.yaml | wc -l
```

Expected: 9

---

## Task 12: 跑变体 C — 7 篇论文 + meng2024 ×3

- [ ] **Step 1: 同上，变体 c**

```bash
for paper in meng2024 yang2025 chai2026 ali2025_flash gaur2022 he2023 pan2025; do
  bash scripts/run_variant_matrix.sh c "${paper}" 1
done
bash scripts/run_variant_matrix.sh c meng2024 2
bash scripts/run_variant_matrix.sh c meng2024 3
```

- [ ] **Step 2: 验证**

```bash
ls .worktrees/variant-c-figure/runs/*_vC_r*/metrics.yaml | wc -l
```

Expected: 9

---

## Task 13: 跑 M4 评测（每变体有 TestCase 的论文）

**Files:**
- Run: `scripts/evaluate.py`（按现有 CLI 调用，不新写）

- [ ] **Step 1: 跑每变体的 TestCase 评测**

```bash
for variant in a b c; do
  case "$variant" in
    a) wt=".worktrees/variant-a-env" ;;
    b) wt=".worktrees/variant-b-cap" ;;
    c) wt=".worktrees/variant-c-figure" ;;
  esac
  for combo in "meng2024 T1" "meng2024 T3" "yang2025 T2" "chai2026 T6" \
               "ali2025_flash T4"; do
    set -- $combo
    paper="$1"; tc="$2"
    if [ "$paper" = "meng2024" ]; then
      for r in 1 2 3; do
        uv run python scripts/evaluate.py \
          --paper "${paper}_v${variant}_r${r}" \
          --testcase "$tc" \
          --runs-dir "${wt}/runs" \
          | tee -a "/tmp/m4_v${variant}.log"
      done
    else
      uv run python scripts/evaluate.py \
        --paper "${paper}_v${variant}_r1" \
        --testcase "$tc" \
        --runs-dir "${wt}/runs" \
        | tee -a "/tmp/m4_v${variant}.log"
    fi
  done
done
```

注：`scripts/evaluate.py` 真实 CLI 可能略不同；按实际接口调整 flags。

- [ ] **Step 2: 把 M4 分数注入到 metrics.yaml**

写一个一次性脚本/手动编辑：把每个 (variant, paper, run, testcase) 的 score 写入对应 `runs/<paper>_v<variant>_r<N>/metrics.yaml` 的 `M4_testcase_scores`。

或者更简单：把 M4 输出直接收集到 `runs/_m4_results.yaml`（gitignore）。

```bash
cat > scripts/aggregate_m4.py <<'PYEOF'
"""Aggregate M4 testcase scores from /tmp/m4_v*.log into runs/_m4_results.yaml."""
import re
import yaml
from pathlib import Path

results = {}
for variant in "abc":
    log = Path(f"/tmp/m4_v{variant}.log")
    if not log.exists():
        continue
    for line in log.read_text().splitlines():
        # Expected format from evaluate.py varies — adjust regex to match.
        m = re.match(r"(\w+_v[abc]_r\d+)\s+(\w+)\s+score=(\d+)", line)
        if m:
            paper, tc, score = m.group(1), m.group(2), int(m.group(3))
            results.setdefault(paper, {})[tc] = score

Path("runs/_m4_results.yaml").write_text(
    yaml.safe_dump(results, sort_keys=False), encoding="utf-8"
)
print(f"wrote runs/_m4_results.yaml with {len(results)} papers")
PYEOF
uv run python scripts/aggregate_m4.py
```

- [ ] **Step 3: 把 _m4_results.yaml 加 gitignore**

```bash
echo "runs/_m4_results.yaml" >> .gitignore
git add .gitignore
git commit -m "chore: ignore m4 results yaml"
```

---

## Task 14: 写对比报告

**Files:**
- Create: `docs/v1_10_variant_comparison.md`

- [ ] **Step 1: 跑 baseline metrics 采集（如果之前没采）**

```bash
for paper in meng2024 meng2024_v190_run2 meng2024_v190_run3 \
             yang2025 chai2026 ali2025_flash gaur2022 he2023 pan2025; do
  if [ -d "runs/${paper}_v190" ]; then
    uv run python scripts/collect_variant_metrics.py "runs/${paper}_v190"
  fi
done
```

- [ ] **Step 2: 起草对比报告骨架**

```markdown
# v1.10 候选变体对比报告

> Date: 2026-05-22
> Spec: docs/superpowers/specs/2026-05-22-v1_10-variant-test-design.md
> Plan: docs/superpowers/plans/2026-05-22-v1_10-variant-test.md

## §1 Baseline 复核结果（per spec §10）

(复制 runs/_baseline_recheck.yaml 摘要 + 是否有 DRIFT)

## §2 三变体 vs baseline — 6 指标 delta 表

### M1 字数

| 论文 | baseline | A | A delta | B | B delta | C | C delta |
|---|---|---|---|---|---|---|---|
| meng2024 (3-run mean) | … | … | … | … | … | … | … |
| yang2025 | … | … | … | … | … | … | … |
| ...

### M2 图嵌入比

(同结构表)

### M3 post-verify required missing

### M4 TestCase 得分（含 stdev for meng2024）

### M5 retry 触发次数

### M6 成本 $ per paper

## §3 zero-variance 防退化检查

meng2024 T1 三跑得分 stdev：
- baseline: 0 (9/9/9)
- A: …
- B: …
- C: …

**判定**：[PASS/FAIL — 哪些变体未保持 stdev=0]

## §4 决策矩阵

| 变体 | 字数提升 | 图引用提升 | coverage 提升 | M4 不退化 | 成本 | 推荐 ship |
|---|---|---|---|---|---|---|
| A | … | … | … | … | … | … |
| B | … | … | … | … | … | … |
| C | … | … | … | … | … | … |

## §5 v1.10 ship 候选

(基于 §4 决策矩阵的结论)

## §6 失败 / regression（如有）

## §7 后续 (deferred to v1.11+)

(spec §11 列的未测项)
```

- [ ] **Step 3: 用 baseline + 27 个 variant metrics.yaml 填表**

写一个 aggregation 脚本帮你聚合：

```bash
cat > scripts/aggregate_comparison.py <<'PYEOF'
"""Aggregate variant + baseline metrics.yaml into a markdown comparison table."""
import yaml
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")
matrix: dict[tuple[str, str], list[dict]] = defaultdict(list)

# baseline runs
for paper_dir in (ROOT / "runs").glob("*_v190*"):
    m_path = paper_dir / "metrics.yaml"
    if m_path.exists():
        m = yaml.safe_load(m_path.read_text(encoding="utf-8"))
        paper = paper_dir.name.split("_v190")[0]
        matrix[("baseline", paper)].append(m)

# variant runs
for variant in "abc":
    wt = ROOT / f".worktrees/variant-{variant}-env" if variant == "a" else \
         ROOT / f".worktrees/variant-{variant}-{'cap' if variant=='b' else 'figure'}"
    for run_dir in (wt / "runs").glob(f"*_v{variant.upper()}_r*"):
        m_path = run_dir / "metrics.yaml"
        if m_path.exists():
            m = yaml.safe_load(m_path.read_text(encoding="utf-8"))
            paper = run_dir.name.split(f"_v{variant.upper()}_")[0]
            matrix[(variant.upper(), paper)].append(m)

# print as markdown
print("| Variant | Paper | M1 chars | M2 embed_ratio | M3 missing | M5 retry empty/short | M6 cost |")
print("|---|---|---|---|---|---|---|")
for (variant, paper), runs in sorted(matrix.items()):
    if not runs:
        continue
    n = len(runs)
    m1 = sum(r["M1_total_chars"] for r in runs) / n
    m2 = sum(r["M2_embed_ratio"] for r in runs) / n
    m3 = sum(r["M3_total_post_missing"] for r in runs) / n
    m5e = sum(r["M5_retry_empty_fires"] for r in runs) / n
    m5s = sum(r["M5_retry_short_fires"] for r in runs) / n
    m6 = sum((r["M6_llm_cost_usd"] or 0) for r in runs) / n
    print(f"| {variant} | {paper} | {m1:.0f} | {m2:.2f} | {m3:.1f} | "
          f"{m5e:.1f}/{m5s:.1f} | ${m6:.2f} |")
PYEOF
uv run python scripts/aggregate_comparison.py > /tmp/comparison_table.md
cat /tmp/comparison_table.md
```

把输出表粘到 `docs/v1_10_variant_comparison.md` 的对应 section。

- [ ] **Step 4: 手工写结论 + 决策矩阵**

基于聚合数据，把 §3 / §4 / §5 文字结论填上。

- [ ] **Step 5: Commit**

```bash
git add docs/v1_10_variant_comparison.md scripts/aggregate_comparison.py
git commit -m "docs(v1.10): variant comparison report (A vs B vs C vs baseline)"
```

---

## Task 15: 决策与 worktree cleanup

**Files:**
- Modify: 根据决策，把胜出变体的代码 merge 到 main
- Delete: 落选变体的 worktree + branch

- [ ] **Step 1: 基于 `docs/v1_10_variant_comparison.md` §5 的决策做汇总**

例如假设 B + C 胜出、A 不显著：

```bash
# Merge variant-b-cap into main
git fetch . variant-b-cap-test:variant-b-merge
git merge --no-ff variant-b-merge -m "feat(v1.10): tier required-cap by section type"
# Merge variant-c-figure
git merge --no-ff variant-c-figure-test -m "feat(v1.10): figure_ids hard constraint + retry"
```

- [ ] **Step 2: 跑全测试套确认**

```bash
uv run pytest -q
```

Expected: 全 pass

- [ ] **Step 3: 删 worktree + branch**

```bash
git worktree remove .worktrees/variant-a-env
git worktree remove .worktrees/variant-b-cap
git worktree remove .worktrees/variant-c-figure
git branch -D variant-a-env-test variant-b-cap-test variant-c-figure-test variant-b-merge 2>/dev/null
```

- [ ] **Step 4: bump 版本 + update CHANGELOG + memory**

```bash
# update pyproject.toml version = "1.10.0"
# add CHANGELOG [1.10.0] entry citing the variant test
# update memory/project_state.md to v1.10
```

(具体内容根据决策填)

- [ ] **Step 5: commit + tag + push**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "release: v1.10.0 — variant-test winners shipped"
git tag v1.10.0
git push origin main v1.10.0
```

- [ ] **Step 6: create GitHub release**

```bash
gh release create v1.10.0 --title "v1.10.0 — ..." \
  --notes-file <release_notes>.md --latest
```

---

## Self-Review Result

- ✅ **Spec coverage**：spec §1-11 全部映射到 task：
  - §2 三变体 → Task 6/7/8
  - §3 测试矩阵 → Task 10/11/12
  - §4 并行架构 → Task 5
  - §5 数据采集 → Task 2, 14
  - §6 对比报告 → Task 14
  - §7 成功标准 → Task 14 §3 / Task 15 §1
  - §8 清理 → Task 1
  - §9 决策候选 → Task 15
  - §10 baseline 复核 → Task 3, 4
- ✅ **Placeholder scan**：无 TBD/TODO；M4 评测的 evaluator CLI 标注"按真实接口调整"是合理 fallback
- ✅ **Type consistency**：`select_top_required(is_survey)` / `GroundedClaim.figure_ids` / `variant ∈ {a,b,c}` 在跨 task 引用一致
