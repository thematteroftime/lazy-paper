"""Smoke tests for scripts/evaluate.py — verify the harness scores
correctly on synthetic fixtures + that adding a new TestCase doesn't
crash on missing chapters."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import evaluate  # noqa: E402


def test_test_cases_have_unique_names():
    names = [tc.name for tc in evaluate.TESTS]
    assert len(names) == len(set(names)), f"duplicate test names: {names}"


def test_test_cases_compute_max_score():
    """max_score is auto-derived from required + thresholds."""
    for tc in evaluate.TESTS:
        # Should be at least 1 — otherwise the test is a no-op
        assert tc.max_score >= 1, f"{tc.name} has max_score=0"


def test_score_against_missing_chapter_returns_none(tmp_path):
    tc = evaluate.TESTS[0]
    # No s08 dir → score_against returns None, not crash
    fake_run = tmp_path / "fake_paper_v1.0"
    fake_run.mkdir()
    result = tc.score_against(fake_run)
    assert result is None


def test_score_against_synthetic_perfect_chapter(tmp_path):
    """If a chapter contains every required pattern, it should score max."""
    tc = evaluate.TESTS[0]  # meng2024 ch01 benchmark
    run = tmp_path / f"{tc.paper_id}_v9.0_X"
    ch_dir = run / "s08_section_compose" / "chapters"
    ch_dir.mkdir(parents=True)
    # Build a chapter that hits every required pattern + Chinese ratio
    chapter = ch_dir / f"{tc.section}-fake.md"
    chapter.write_text(
        "# Introduction\n\n"
        "反铁电材料体系中弛豫铁电陶瓷因其优异的储能性能受到广泛关注。"
        "近年来研究者通过多种策略提升能量存储密度与效率，相关代表性工作如下："
        "Jiang等在Ca²⁺/Nb⁵⁺共掺杂体系中实现Wrec达2.94 J/cm³，效率η为91.04%。"
        "Ma等通过La(Mg₁/₂Zr₁/₂)O₃改性获得Wrec为7.5 J/cm³，η达90.5%。"
        "Zhang等在K₀.₁系统中实现Wrec为8.58 J/cm³，η高达94.5%。"
        "Tang等通过0.8Bi₀.₃₉₅基体系获得Wrec为8.3 J/cm³与η约80%。"
        "本工作通过协同优化策略在中等电场下实现了优异的储能性能。",
        encoding="utf-8",
    )
    result = tc.score_against(run)
    assert result is not None
    # All 16 patterns hit + lang ratio = 17/17
    assert result.score == result.max_score, \
        f"expected perfect score, got {result.score}/{result.max_score}; " \
        f"missed: {[h.name for h in result.hits if not h.matched]}"


def test_forbidden_pattern_raises_flag(tmp_path):
    """yang2025 test case forbids '8.6 J/cm³'; a chapter containing it flags."""
    tc = next(t for t in evaluate.TESTS if t.name == "yang2025:ch01_no_fabrication")
    run = tmp_path / "yang2025_v9.0_X"
    ch_dir = run / "s08_section_compose" / "chapters"
    ch_dir.mkdir(parents=True)
    (ch_dir / f"{tc.section}-fake.md").write_text(
        "# Introduction\n\n"
        "CBPS材料展现优异的突触可塑性（synaptic plasticity）。"
        "在测试中观察到Wrec=8.6 J/cm³ at η=85%的储能性能。",
        encoding="utf-8",
    )
    result = tc.score_against(run)
    assert result is not None
    assert any("forbidden" in f for f in result.flags), \
        f"expected forbidden-pattern flag, got {result.flags}"


def test_evaluate_run_detects_paper_id_from_suffix(tmp_path):
    """evaluate_run trims '_v\\d+_*' suffix to recover the base paper id."""
    run = tmp_path / "meng2024_v170_KL_run2"
    (run / "s08_section_compose" / "chapters").mkdir(parents=True)
    rep = evaluate.evaluate_run(run)
    assert rep["paper_id"] == "meng2024"
