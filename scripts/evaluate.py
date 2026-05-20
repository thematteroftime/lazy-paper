#!/usr/bin/env python3
"""Strategy evaluation harness — score generated chapters on explicit
quality / faithfulness / citation criteria across multiple test cases.

Usage:
    uv run python scripts/evaluate.py <run_dir> [<run_dir> ...]
    uv run python scripts/evaluate.py --all-recent
    uv run python scripts/evaluate.py --paper meng2024 <run_dir>

Each run_dir is a `runs/<paper_id>/` path. The harness:
  1. Loads each chapter + (optionally) the structured.json + retrieval.parquet
  2. Runs a fixed set of scorers per test case
  3. Emits a JSON report to stdout + a Markdown table to stderr

Scorers are deterministic and language-aware. New test cases get added
to TESTS at the bottom of this file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"


# ─── scoring primitives ──────────────────────────────────────────────────────

@dataclass
class PatternHit:
    name: str
    pattern: str
    matched: bool
    sample: str = ""


@dataclass
class TestResult:
    test_name: str
    chapter_path: str
    chapter_size: int
    hits: list[PatternHit] = field(default_factory=list)
    forbidden_hits: list[PatternHit] = field(default_factory=list)
    language_zh_ratio: float = 0.0
    score: int = 0
    max_score: int = 0
    flags: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.test_name:<35} {self.score:>3}/{self.max_score:<3} "
                f"size={self.chapter_size:<5} zh={self.language_zh_ratio:.0%} "
                f"{'⚠ ' + '; '.join(self.flags) if self.flags else ''}")


def _zh_ratio(text: str) -> float:
    body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    body = "".join(body.split())
    if not body:
        return 0.0
    zh = sum(1 for c in body if "一" <= c <= "鿿")
    return zh / len(body)


# ─── test-case schema ────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """One scoring test against one chapter of one paper.

    `required` — pattern groups that contribute to the score (one point
    per matched pattern). `forbidden` — patterns that should NOT appear
    (each occurrence counts as a flag, deducts from score with a cap).
    `min_chars` — chapter must exceed this to score full marks on depth.
    `lang_zh_min_ratio` — if set and < this, flag language regression.
    """
    name: str
    paper_id: str
    section: str          # e.g. "01-Introduction"
    required: dict[str, list[str]] = field(default_factory=dict)
    forbidden: list[str] = field(default_factory=list)
    min_chars: int = 0
    lang_zh_min_ratio: float = 0.0
    max_score: int = 0

    def __post_init__(self):
        if not self.max_score:
            self.max_score = sum(len(v) for v in self.required.values())
            if self.min_chars:
                self.max_score += 1
            if self.lang_zh_min_ratio:
                self.max_score += 1

    def score_against(self, run_dir: Path) -> Optional[TestResult]:
        ch_dir = run_dir / "s08_section_compose" / "chapters"
        matches = list(ch_dir.glob(f"{self.section}*.md"))
        if not matches:
            return None
        chapter = matches[0]
        text = chapter.read_text(encoding="utf-8")
        try:
            rel = chapter.resolve().relative_to(REPO_ROOT)
            chapter_path_str = str(rel)
        except ValueError:
            chapter_path_str = str(chapter)
        result = TestResult(
            test_name=self.name,
            chapter_path=chapter_path_str,
            chapter_size=chapter.stat().st_size,
            max_score=self.max_score,
        )
        # Required hits
        for group, pats in self.required.items():
            for pat in pats:
                m = re.search(pat, text)
                hit = PatternHit(
                    name=f"{group}:{pat}",
                    pattern=pat,
                    matched=bool(m),
                    sample=m.group(0) if m else "",
                )
                result.hits.append(hit)
                if hit.matched:
                    result.score += 1
        # Forbidden
        for pat in self.forbidden:
            m = re.search(pat, text)
            hit = PatternHit(name=f"forbidden:{pat}", pattern=pat,
                              matched=bool(m), sample=m.group(0) if m else "")
            result.forbidden_hits.append(hit)
            if hit.matched:
                result.flags.append(f"forbidden pattern matched: {pat}")
        # Size threshold
        if self.min_chars:
            if result.chapter_size >= self.min_chars:
                result.score += 1
            else:
                result.flags.append(
                    f"size {result.chapter_size} < threshold {self.min_chars}"
                )
        # Language ratio
        if self.lang_zh_min_ratio:
            result.language_zh_ratio = _zh_ratio(text)
            if result.language_zh_ratio >= self.lang_zh_min_ratio:
                result.score += 1
            else:
                result.flags.append(
                    f"zh ratio {result.language_zh_ratio:.0%} < "
                    f"{self.lang_zh_min_ratio:.0%}"
                )
        else:
            result.language_zh_ratio = _zh_ratio(text)
        return result


# ─── citation-correctness scorer (uses structured.json) ──────────────────────

def score_citation_accuracy(run_dir: Path, section: str) -> dict:
    """Validate that each GroundedClaim's cited_quote appears (fuzzy-matched)
    in its declared chunk. Skipped if the run wasn't from Strategy J (no
    structured.json files written)."""
    s_path = run_dir / "s08_section_compose" / f"{section}.structured.json"
    r_path = run_dir / "s08_section_compose" / "retrieval.parquet"
    if not s_path.exists() or not r_path.exists():
        return {"applicable": False}
    import pyarrow.parquet as pq
    from difflib import SequenceMatcher
    chunks = {row["id"]: row for row in pq.read_table(r_path).to_pylist()}
    # chunk IDs are like "c0001" but structured.json uses 0-based indices
    # into the retrieved (non-parent) list. We approximate by ordering
    # children by id and using positional index.
    children = sorted([c for c in chunks.values() if not c.get("is_parent", False)],
                      key=lambda c: c["id"])
    chunks_by_idx = {i: c for i, c in enumerate(children)}

    # Source normalization for fair fuzzy match (mirror what reviewer.py
    # does for regex critic): collapse OCR digit-spaces and strip LaTeX
    # math escapes like \\mathrm{} and trailing $-delimiters.
    _OCR_DIGIT_SPACE = re.compile(r"(?<=[\d.])\s+(?=[\d.])")
    _LATEX_CMD = re.compile(r"\\(?:mathrm|text|mbox|operatorname)\{([^}]*)\}")
    _LATEX_NOISE = re.compile(r"\\(?=[%$&_^{}])|[$_^]")

    def _norm(text: str) -> str:
        prev = None
        cur = text
        while prev != cur:
            prev, cur = cur, _OCR_DIGIT_SPACE.sub("", cur)
        cur = _LATEX_CMD.sub(r"\1", cur)
        cur = _LATEX_NOISE.sub("", cur)
        return cur

    draft = json.loads(s_path.read_text())
    total_claims = len(draft["claims"])
    quote_present = 0
    quote_verified = 0
    fabricated = []
    for c in draft["claims"]:
        q = c.get("cited_quote", "").strip()
        if not q:
            continue
        quote_present += 1
        verified = False
        q_norm = _norm(q)
        for cid in c.get("cited_chunk_ids", []):
            ch = chunks_by_idx.get(cid)
            if not ch:
                continue
            chunk_text = _norm(ch["text"])
            if q_norm in chunk_text or q_norm.lower() in chunk_text.lower():
                verified = True
                break
            # longest contiguous match coverage (mirror structured.py logic)
            m = SequenceMatcher(None, q_norm, chunk_text)
            longest = m.find_longest_match(0, len(q_norm), 0, len(chunk_text))
            coverage = longest.size / max(1, len(q_norm))
            if coverage >= 0.85:
                verified = True
                break
        if verified:
            quote_verified += 1
        else:
            fabricated.append({"quote": q[:80], "cited_chunk_ids": c.get("cited_chunk_ids")})
    rate = quote_verified / max(1, quote_present)
    return {
        "applicable": True,
        "total_claims": total_claims,
        "claims_with_quote": quote_present,
        "verified_quotes": quote_verified,
        "verified_ratio": round(rate, 3),
        "fabricated_quote_count": len(fabricated),
        "fabricated_sample": fabricated[:3],
    }


# ─── benchmark suite definition ──────────────────────────────────────────────

TESTS: list[TestCase] = [
    # ────────────────────────────────────────────────────────────────────────
    # T1. meng2024 introduction must recover 4 cited literature benchmarks
    #    (Jiang et al. W_rec=2.94 J/cm³ η=91.04%; Ma et al. 7.5 J/cm³ / 90.5%;
    #     Zhang et al. 8.58 J/cm³ / 94.5%; Tang et al. 8.3 J/cm³ / 80%).
    # ────────────────────────────────────────────────────────────────────────
    TestCase(
        name="meng2024:ch01_benchmark_recovery",
        paper_id="meng2024",
        section="01-Introduction",
        required={
            # Authors — match Chinese 'X等' / 'X 等人' / English 'X et al.'
            "authors":  [r"Jiang(?:\s*等|\s*et\s*al\.)",
                         r"Ma(?:\s*等|\s*et\s*al\.)",
                         r"Zhang(?:\s*等|\s*et\s*al\.)",
                         r"Tang(?:\s*等|\s*et\s*al\.)"],
            "values":   [r"2\.94", r"7\.5\s*J", r"8\.58", r"8\.3\s*J",
                         r"91\.04", r"90\.5", r"94\.5", r"80\s*%"],
            "formulas": [r"Ca²?⁺?[\s/]?Nb", r"La\(Mg", r"K[0₀]\.?[1₁]", r"0\.8Bi"],
        },
        lang_zh_min_ratio=0.30,
    ),

    # ────────────────────────────────────────────────────────────────────────
    # T2. yang2025 introduction must NOT fabricate energy-storage numbers
    #    (the paper is about neuromorphic computing; has zero W_rec data).
    # ────────────────────────────────────────────────────────────────────────
    TestCase(
        name="yang2025:ch01_no_fabrication",
        paper_id="yang2025",
        section="01-Introduction",
        forbidden=[r"8\.6\s*J/cm", r"η\s*=\s*85", r"Wrec\s*=\s*\d"],
        required={
            "on_topic": [r"CBPS|CuBiP|铜铋|relaxor|弛豫", r"突触|synap|neuromorphic"],
        },
        lang_zh_min_ratio=0.30,
    ),

    # ────────────────────────────────────────────────────────────────────────
    # T3. meng2024 synthesis chapter must mention tape-casting + grain data
    # ────────────────────────────────────────────────────────────────────────
    TestCase(
        name="meng2024:ch10_synthesis_specificity",
        paper_id="meng2024",
        section="10-Synthesis_and_Preparation",
        required={
            "method":      [r"tape[‑\-]?casting", r"流延"],
            "grain_data":  [r"\d+\.\d+\s*μm", r"Bi₂?Ti₂?O₇?|pyrochlore|焦绿石"],
        },
        min_chars=500,
    ),

    # ────────────────────────────────────────────────────────────────────────
    # T4. ali2025_flash ch14 (Comparison with Prior Work) must be substantial,
    #    not a stub, and must include at least 2 quantitative competitor data
    #    points (e.g. temperature shifts, strain values).
    # ────────────────────────────────────────────────────────────────────────
    TestCase(
        name="ali2025_flash:ch14_depth",
        paper_id="ali2025_flash",
        section="14-Comparison_with_Prior_Work",
        required={
            "quant_anchors": [r"\d+\s*K(?![A-Za-z])", r"\d+(\.\d+)?\s*%",
                              r"\d+\s*°C", r"\d+\s*kV"],
        },
        min_chars=1000,
    ),

    # ────────────────────────────────────────────────────────────────────────
    # Generic generalization tests — apply to any clean corpus paper.
    # T5+T6 verify the strategy doesn't break sane defaults on papers
    # without specific known defects.
    # ────────────────────────────────────────────────────────────────────────
    TestCase(
        name="fu2020:ch01_basic",
        paper_id="fu2020",
        section="01-Introduction",
        required={
            # Fu et al. 2020 paper title — should be present in any intro
            "on_topic": [r"PbZrO|铅锆|antiferroelectric|反铁电",
                         r"ferrielectric|铁电体性|亚铁电"],
        },
        forbidden=[r"η\s*=\s*85%", r"Wrec\s*=\s*8\.6"],  # template-fab signals
        min_chars=600,
        lang_zh_min_ratio=0.30,
    ),
    TestCase(
        name="chai2026:ch01_basic",
        paper_id="chai2026",
        section="01-Introduction",
        required={
            "on_topic": [r"K[0₀]\.?5Na[0₀]\.?5NbO[3₃]|KNN|铌酸",
                         r"energy storage|储能"],
        },
        forbidden=[r"η\s*=\s*85%", r"Wrec\s*=\s*8\.6"],
        min_chars=600,
        lang_zh_min_ratio=0.30,
    ),
]


# ─── runner ──────────────────────────────────────────────────────────────────

def evaluate_run(run_dir: Path) -> dict:
    """Run every applicable test against this run_dir; return dict report."""
    # Determine the underlying paper by trimming any trailing _vXXX_Y suffix.
    paper_id = run_dir.name
    # Strip any trailing "_v<digits>_..." suffix (one regex covers all
    # variants: _v140, _v140_baseline, _v170_KL, _v170_KL_run2, _v160_J1, ...)
    m = re.match(r"^(.+?)_v\d+(?:_[A-Za-z0-9]+)*$", paper_id)
    if m:
        paper_id = m.group(1)
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
            "chapter_size": r.chapter_size,
            "zh_ratio": round(r.language_zh_ratio, 3),
            "flags": r.flags,
            "missed_patterns": [h.name for h in r.hits if not h.matched],
            "forbidden_hits": [h.name for h in r.forbidden_hits if h.matched],
        })
        # Citation accuracy from structured.json (if present)
        cit = score_citation_accuracy(run_dir, r.test_name.split(":")[1].split("_")[0]
                                       if ":" in r.test_name else "01-Introduction")
        # Actually, derive section name from the TestCase
        for tc2 in TESTS:
            if tc2.name == r.test_name:
                cit = score_citation_accuracy(run_dir, tc2.section)
                break
        if cit.get("applicable"):
            results[-1]["citation_accuracy"] = cit
    try:
        run_name = str(run_dir.resolve().relative_to(REPO_ROOT))
    except ValueError:
        run_name = str(run_dir)
    return {
        "run": run_name,
        "paper_id": paper_id,
        "results": results,
    }


def print_markdown_table(reports: list[dict]) -> None:
    if not reports:
        print("(no scorable runs)", file=sys.stderr)
        return
    # Collect every test that appeared
    test_names = sorted({r["test"] for rep in reports for r in rep["results"]})
    headers = ["run"] + test_names
    print(" | ".join(headers), file=sys.stderr)
    print(" | ".join("-" * max(3, len(h)) for h in headers), file=sys.stderr)
    for rep in reports:
        row = [rep["run"].replace("runs/", "")]
        score_by_test = {r["test"]: r for r in rep["results"]}
        for t in test_names:
            r = score_by_test.get(t)
            if not r:
                row.append("—")
            else:
                cell = f"{r['score']}/{r['max_score']}"
                if r.get("flags"):
                    cell += " ⚠"
                row.append(cell)
        print(" | ".join(row), file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="*", type=Path)
    ap.add_argument("--all-recent", action="store_true",
                    help="Score every runs/*_v1[6-7]_* directory")
    args = ap.parse_args()

    run_dirs: list[Path] = []
    if args.all_recent:
        for p in sorted(RUNS_DIR.glob("*_v1[6-7]*")):
            if p.is_dir():
                run_dirs.append(p)
    run_dirs.extend(args.run_dirs)
    if not run_dirs:
        ap.error("provide run directories or --all-recent")

    reports = []
    for d in run_dirs:
        if not d.exists():
            print(f"  WARN: {d} missing", file=sys.stderr)
            continue
        rep = evaluate_run(d)
        if rep["results"]:
            reports.append(rep)
    print_markdown_table(reports)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
