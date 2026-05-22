"""Run scripts/evaluate.py on every variant run dir + collect into yaml.

Each run dir has the chapter outputs; evaluate_run() picks TestCases
that match the run's paper_id (stripped of variant suffix).
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import re
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.evaluate import TESTS, evaluate_run  # noqa: E402


_VARIANT_SUFFIX = re.compile(r"_v[abc]_r\d+$")


def _paper_id_of(run_dir: Path) -> str:
    """Strip variant suffix (_v[abc]_r\\d+) to get base paper_id."""
    return _VARIANT_SUFFIX.sub("", run_dir.name)


def _eval_against_paper(run_dir: Path, paper_id: str) -> dict:
    """Run all TestCases whose paper_id matches; return same shape as evaluate_run."""
    results = []
    for tc in TESTS:
        if tc.paper_id != paper_id:
            continue
        r = tc.score_against(run_dir)
        if r is None:
            continue
        results.append({
            "test": r.test_name,
            "score": r.score,
            "max_score": r.max_score,
        })
    return {"paper_id": paper_id, "results": results}


def main() -> int:
    results: dict[str, dict] = {}
    # Variant runs — use explicit paper_id strip + manual TestCase match
    for wt in ["variant-a-env", "variant-b-cap", "variant-c-figure"]:
        runs_dir = REPO_ROOT / ".worktrees" / wt / "runs"
        if not runs_dir.exists():
            continue
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            paper_id = _paper_id_of(run_dir)
            rep = _eval_against_paper(run_dir, paper_id)
            if rep["results"]:
                results[run_dir.name] = {
                    "paper_id": paper_id,
                    "tests": [
                        {"test": r["test"], "score": r["score"], "max": r["max_score"]}
                        for r in rep["results"]
                    ],
                }

    # Baseline runs too (for reference)
    for run_dir in sorted((REPO_ROOT / "runs").iterdir()):
        if not run_dir.is_dir() or run_dir.name.startswith("_"):
            continue
        if "_v190" not in run_dir.name:
            continue
        try:
            rep = evaluate_run(run_dir)
        except Exception:
            continue
        if rep.get("results"):
            results[run_dir.name] = {
                "paper_id": rep["paper_id"],
                "tests": [
                    {"test": r["test"], "score": r["score"], "max": r["max_score"]}
                    for r in rep["results"]
                ],
            }

    out_path = REPO_ROOT / "runs" / "_m4_results.yaml"
    out_path.write_text(yaml.safe_dump(results, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path} ({len(results)} runs)")

    # Print summary table
    print("\n## M4 TestCase scores (variant vs baseline)\n")
    by_test: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for run_name, info in results.items():
        for t in info["tests"]:
            by_test[t["test"]].append((run_name, t["score"], t["max"]))
    for test_name in sorted(by_test):
        print(f"\n### {test_name}\n")
        for run_name, score, mx in sorted(by_test[test_name]):
            print(f"  {run_name}: {score}/{mx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
