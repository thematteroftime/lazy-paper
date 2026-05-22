# scripts/recheck_baseline.py
"""Recheck baseline TestCase scores before variant comparison.

The evaluator (scripts/evaluate.py) is fully deterministic (regex +
size + zh-ratio + fuzzy substring). This script confirms baseline
scores haven't drifted due to evaluator code changes — it does NOT
require LLM calls.

Usage:
    uv run python scripts/recheck_baseline.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from scripts.evaluate import evaluate_run  # noqa: E402

HISTORICAL = {
    # (run_dir_name, test_id): expected_score
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


def _test_id(test_name: str) -> str:
    """'T1: meng2024 ch01-...' -> 'T1'"""
    return test_name.split(":", 1)[0].strip()


def recheck_one(run_dir: Path) -> list[dict]:
    """Score one run dir and pair against historical."""
    report = evaluate_run(run_dir)
    actual = {_test_id(r["test"]): r["score"] for r in report["results"]}
    out: list[dict] = []
    for (paper_run, test_id), historical in HISTORICAL.items():
        if paper_run != run_dir.name:
            continue
        score = actual.get(test_id)
        if score is None:
            print(f"no result for {paper_run}/{test_id}", file=sys.stderr)
            out.append({
                "paper_run": paper_run, "test_id": test_id,
                "historical": historical, "current": None,
                "delta": None, "verdict": "DRIFT — test not found",
            })
            continue
        delta = score - historical
        verdict = "OK" if delta == 0 else f"DRIFT (Δ={delta:+d})"
        out.append({
            "paper_run": paper_run, "test_id": test_id,
            "historical": historical, "current": score,
            "delta": delta, "verdict": verdict,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recheck baseline TestCase scores (deterministic evaluator)."
    )
    ap.add_argument(
        "--output", type=Path, default=Path("runs/_baseline_recheck.yaml"),
        help="Output YAML path (default: runs/_baseline_recheck.yaml)",
    )
    args = ap.parse_args()

    # Collect unique run dirs from HISTORICAL
    run_names = sorted({pr for pr, _ in HISTORICAL.keys()})
    all_results: list[dict] = []
    for run_name in run_names:
        run_dir = REPO_ROOT / "runs" / run_name
        if not run_dir.exists():
            print(f"skip: {run_dir} missing", file=sys.stderr)
            continue
        results = recheck_one(run_dir)
        for r in results:
            print(
                f"{r['paper_run']}/{r['test_id']}: "
                f"hist={r['historical']} current={r['current']} "
                f"→ {r['verdict']}",
                flush=True,
            )
        all_results.extend(results)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(all_results, sort_keys=False), encoding="utf-8")
    print(f"\nwrote {args.output}", flush=True)

    drift = [r for r in all_results if "DRIFT" in r["verdict"]]
    if drift:
        print(
            f"\n{len(drift)} DRIFT entries — investigate evaluator changes",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
