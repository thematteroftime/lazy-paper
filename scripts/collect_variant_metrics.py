"""Collect 5 metrics (M1/M2/M3/M5/M6) from a single variant run.

Usage:
    python scripts/collect_variant_metrics.py runs/<paper>_<variant>_r<run>/

Writes metrics.yaml in the run directory. M4 (TestCase scores) is
collected separately via scripts/recheck_baseline.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
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
    """Count distinct figures embedded vs available.

    A figure can have multiple panels — HTML renders each panel as a
    separate `<img>` tag, but we want one count per distinct figure.
    `<figure>` wraps the whole multi-panel block, so counting those is
    the right denominator-aware metric.
    """
    html = run_dir / "s09_render" / "preview.html"
    fig_notes = run_dir / "s07_figure_analyze" / "fig_notes.yaml"
    embedded = 0
    available = 0
    if html.exists():
        text = html.read_text(encoding="utf-8")
        embedded = text.count("<figure")
        if embedded == 0:
            # Fallback for templates without <figure> wrapping: count
            # unique alt-text instead (alt="图 N" / "Fig. N")
            alts = re.findall(r'alt="([^"]+)"', text)
            embedded = len(set(alts))
    if fig_notes.exists():
        notes = yaml.safe_load(fig_notes.read_text(encoding="utf-8")) or []
        available = len(notes)
    ratio = embedded / available if available else 0.0
    return embedded, available, ratio


def collect_figure_hallucinations(run_dir: Path) -> tuple[int, list[str]]:
    """Count fig_ids cited in chapter md that don't exist in fig_notes.

    A side-effect probe for variant C — figure_ids hard constraint can
    nudge the LLM to write 'Fig. N' for nonexistent figure numbers,
    which s09 then silently drops.
    """
    chapters_dir = run_dir / "s08_section_compose" / "chapters"
    fig_notes = run_dir / "s07_figure_analyze" / "fig_notes.yaml"
    if not chapters_dir.exists() or not fig_notes.exists():
        return 0, []
    notes = yaml.safe_load(fig_notes.read_text(encoding="utf-8")) or []
    valid_nums: set[str] = set()
    for n in notes:
        fid = n.get("fig_id", "")
        m = re.search(r"(\d+)", fid)
        if m:
            valid_nums.add(m.group(1))
    cited_nums: set[str] = set()
    for md in chapters_dir.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:Fig\.\s*|图\s*)(\d+)", text):
            cited_nums.add(m.group(1))
    hallucinated = sorted(cited_nums - valid_nums, key=int)
    return len(hallucinated), hallucinated


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
    halluc_count, halluc_ids = collect_figure_hallucinations(run_dir)
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
        "M2_figures_hallucinated_count": halluc_count,
        "M2_figures_hallucinated_ids": halluc_ids,
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
