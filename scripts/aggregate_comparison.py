"""Aggregate baseline + variant metrics.yaml into a markdown comparison table.

Reads:
  - runs/<paper>_v190/metrics.yaml          (baseline; collect via collect_variant_metrics.py first)
  - .worktrees/variant-a-env/runs/<paper>_va_r<N>/metrics.yaml
  - .worktrees/variant-b-cap/runs/<paper>_vb_r<N>/metrics.yaml
  - .worktrees/variant-c-figure/runs/<paper>_vc_r<N>/metrics.yaml

Emits a markdown report on stdout grouping by (variant, paper) and showing
M1/M2/M3/M5/M6 means across runs.

Usage:
    uv run python scripts/aggregate_comparison.py > /tmp/variant_comparison_table.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

VARIANT_DIRS: dict[str, Path] = {
    "A": REPO_ROOT / ".worktrees" / "variant-a-env" / "runs",
    "B": REPO_ROOT / ".worktrees" / "variant-b-cap" / "runs",
    "C": REPO_ROOT / ".worktrees" / "variant-c-figure" / "runs",
}

PAPERS = [
    "meng2024", "yang2025", "chai2026", "ali2025_flash",
    "gaur2022", "he2023", "pan2025",
]


def _load_metrics(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"WARN: failed to parse {path}: {exc!r}", file=sys.stderr)
        return None


def collect_all() -> dict[tuple[str, str], list[dict]]:
    """Returns matrix[(variant, paper)] = list of run metrics dicts."""
    matrix: dict[tuple[str, str], list[dict]] = defaultdict(list)

    # Baseline runs: runs/<paper>_v190, _v190_run2, _v190_run3, _v190b
    for paper in PAPERS:
        for suffix in ["_v190", "_v190_run2", "_v190_run3", "_v190b"]:
            p = REPO_ROOT / "runs" / f"{paper}{suffix}" / "metrics.yaml"
            m = _load_metrics(p)
            if m:
                matrix[("baseline", paper)].append(m)

    # Variant runs
    for variant, runs_root in VARIANT_DIRS.items():
        if not runs_root.exists():
            continue
        for run_dir in sorted(runs_root.glob(f"*_v{variant.lower()}_r*")):
            m = _load_metrics(run_dir / "metrics.yaml")
            if m:
                # Extract paper name from run dir name
                # e.g. meng2024_va_r1 -> meng2024
                stem = run_dir.name
                # Cut off `_v<variant>_r<N>` suffix
                idx = stem.rfind(f"_v{variant.lower()}_r")
                paper = stem[:idx] if idx > 0 else stem
                matrix[(variant, paper)].append(m)

    return matrix


def _mean(xs: list[float | int | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def _stdev(xs: list[float | int]) -> float:
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _fmt(v: float | int | None, decimals: int = 0) -> str:
    if v is None:
        return "—"
    if decimals == 0:
        return str(int(round(v)))
    return f"{v:.{decimals}f}"


def render_table(matrix: dict[tuple[str, str], list[dict]]) -> str:
    out: list[str] = []
    out.append(
        "| Variant | Paper | n | M1 chars | M2 embed/avail | M2 halluc | "
        "M3 missing/required | M5 empty/short | M6 cost |"
    )
    out.append(
        "|---|---|---|---|---|---|---|---|---|"
    )
    sort_key = {"baseline": 0, "A": 1, "B": 2, "C": 3}
    rows = sorted(
        matrix.items(),
        key=lambda kv: (sort_key.get(kv[0][0], 9), kv[0][1]),
    )
    for (variant, paper), runs in rows:
        if not runs:
            continue
        n = len(runs)
        m1_mean = _mean([r.get("M1_total_chars") for r in runs])
        m2_embed = _mean([r.get("M2_figures_embedded") for r in runs])
        m2_avail = _mean([r.get("M2_figures_available") for r in runs])
        m2_halluc = _mean([r.get("M2_figures_hallucinated_count") for r in runs])
        m3_required = _mean([r.get("M3_total_required") for r in runs])
        m3_missing = _mean([r.get("M3_total_post_missing") for r in runs])
        m5e = _mean([r.get("M5_retry_empty_fires") for r in runs])
        m5s = _mean([r.get("M5_retry_short_fires") for r in runs])
        m6 = _mean([r.get("M6_llm_cost_usd") for r in runs])
        out.append(
            f"| {variant} | {paper} | {n} | "
            f"{_fmt(m1_mean)} | "
            f"{_fmt(m2_embed)}/{_fmt(m2_avail)} | "
            f"{_fmt(m2_halluc, 1)} | "
            f"{_fmt(m3_missing)}/{_fmt(m3_required)} | "
            f"{_fmt(m5e, 1)}/{_fmt(m5s, 1)} | "
            f"{('$' + _fmt(m6, 2)) if m6 is not None else '—'} |"
        )
    return "\n".join(out)


def render_zero_variance_check(matrix: dict[tuple[str, str], list[dict]]) -> str:
    """Show M1_total_chars stdev for each variant on meng2024 (zero-variance probe)."""
    out: list[str] = []
    out.append("### M1 zero-variance probe — meng2024 across 3 runs\n")
    out.append("| Variant | n | M1 chars (per run) | mean | stdev |")
    out.append("|---|---|---|---|---|")
    for variant in ["baseline", "A", "B", "C"]:
        runs = matrix.get((variant, "meng2024"), [])
        if not runs:
            continue
        chars = [r.get("M1_total_chars", 0) for r in runs]
        m = sum(chars) / len(chars) if chars else 0
        out.append(
            f"| {variant} | {len(runs)} | "
            f"{' / '.join(str(c) for c in chars)} | "
            f"{int(round(m))} | {_fmt(_stdev(chars), 1)} |"
        )
    return "\n".join(out)


def main() -> int:
    matrix = collect_all()
    if not matrix:
        print("ERROR: no metrics.yaml files found", file=sys.stderr)
        return 1
    print("# v1.10 Variant Comparison — Raw Metrics\n")
    print("## All runs aggregated by (variant, paper)\n")
    print(render_table(matrix))
    print()
    print(render_zero_variance_check(matrix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
