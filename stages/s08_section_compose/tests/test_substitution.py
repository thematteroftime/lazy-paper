"""Tests for {paper.X} placeholder substitution logic in s08_section_compose."""
from __future__ import annotations

import pytest

from stages.s08_section_compose.runner import (
    _build_paper_data,
    substitute_placeholders,
)


# ---------------------------------------------------------------------------
# substitute_placeholders unit tests
# ---------------------------------------------------------------------------


def test_substitute_system():
    text = "研究体系：{paper.system} 的合成路径。"
    data = {"system": "ANT-3La ceramics"}
    result = substitute_placeholders(text, data)
    assert "ANT-3La ceramics" in result
    assert "{paper.system}" not in result


def test_substitute_multiple_keys():
    text = "{paper.title} — 体系 {paper.system} — 关键词 {paper.keywords}"
    data = {
        "title": "Superior energy storage",
        "system": "ANT-xLa",
        "keywords": "energy storage; thermal stability",
    }
    result = substitute_placeholders(text, data)
    assert "Superior energy storage" in result
    assert "ANT-xLa" in result
    assert "energy storage; thermal stability" in result
    assert "{paper." not in result


def test_substitute_unknown_key_left_verbatim():
    """Unknown placeholders must NOT be silently dropped — they stay as-is."""
    text = "ref: {paper.unknown_field} end"
    data = {"system": "X"}
    result = substitute_placeholders(text, data)
    assert "{paper.unknown_field}" in result


def test_substitute_figures_multiline():
    """Multi-line figure string is inserted verbatim."""
    text = "可参考论文图：{paper.figures}。"
    data = {"figures": "Fig.1: XRD patterns\nFig.2: P-E loops"}
    result = substitute_placeholders(text, data)
    assert "Fig.1: XRD patterns" in result
    assert "Fig.2: P-E loops" in result


def test_substitute_empty_text():
    result = substitute_placeholders("", {"system": "X"})
    assert result == ""


def test_substitute_no_placeholders():
    text = "This text has no placeholders."
    result = substitute_placeholders(text, {"system": "X"})
    assert result == text


# ---------------------------------------------------------------------------
# _build_paper_data unit tests
# ---------------------------------------------------------------------------


_SAMPLE_CONTEXT = {
    "title": "Superior energy storage properties in lead-free ceramics",
    "system": "lead-free ceramics (ANT-xLa)",
    "abbreviations": [
        {"abbr": "AFE", "expansion": "antiferroelectric"},
        {"abbr": "RAFE", "expansion": "relaxor-antiferroelectric"},
    ],
    "key_terms": ["energy storage", "thermal stability", "CAFE crossover"],
    "keywords": ["energy storage", "thermal stability", "lead-free", "antiferroelectric", "relaxor"],
}

_SAMPLE_FIGURES = [
    {"fig_id": "Fig. 1", "caption": "Temperature dependence of dielectric permittivity of ANT-xLa ceramics."},
    {"fig_id": "Fig. 2", "caption": "Weibull distribution of breakdown electric field."},
]

_SAMPLE_FIG_NOTES = [
    {
        "fig_id": "Fig. 1",
        "deep_observation": "ANT-3La exhibits intermediate delta_g between NAFE and RAFE, supports CAFE hypothesis.",
    },
    {
        "fig_id": "Fig. 2",
        "deep_observation": "Weibull data lacks error bars; confidence intervals not reported.",
    },
]


def test_build_paper_data_basic_fields():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], _SAMPLE_FIG_NOTES)
    assert data["title"] == _SAMPLE_CONTEXT["title"]
    assert data["system"] == _SAMPLE_CONTEXT["system"]
    assert "AFE = antiferroelectric" in data["abbreviations"]
    assert "RAFE = relaxor-antiferroelectric" in data["abbreviations"]


def test_build_paper_data_keywords_top5():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], [])
    kw = data["keywords"]
    # All 5 keywords should be joined with '; '
    assert "energy storage" in kw
    assert "relaxor" in kw
    assert kw.count(";") == 4  # 5 items -> 4 separators


def test_build_paper_data_key_terms():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], [])
    kt = data["key_terms"]
    assert "energy storage" in kt
    assert "CAFE crossover" in kt


def test_build_paper_data_figures_formatted():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], [])
    figs = data["figures"]
    assert "Fig. 1:" in figs
    assert "Fig. 2:" in figs
    # Captions included
    assert "dielectric permittivity" in figs


def test_build_paper_data_empty_tables_fallback():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], [])
    # Empty tables should produce localized fallback
    assert "未检出" in data["tables"] or "No standalone" in data["tables"]


def test_build_paper_data_tables_present():
    tables = [{"table_id": "Table 1", "caption": "Composition vs properties comparison."}]
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, tables, [])
    assert "Table 1" in data["tables"]
    assert "Composition vs properties" in data["tables"]


def test_build_paper_data_fig_observations_brief():
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], _SAMPLE_FIG_NOTES)
    obs = data["fig_observations_brief"]
    assert "Fig. 1" in obs
    assert "Fig. 2" in obs
    # Each observation should be truncated to ~100 chars
    for line in obs.split("\n"):
        if " — " in line:
            obs_part = line.split(" — ", 1)[1]
            assert len(obs_part) <= 103  # 100 + "..."


def test_build_paper_data_missing_context_fields():
    """Empty context should produce localized fallback strings, not crash."""
    data = _build_paper_data({}, [], [], [])
    assert data["title"]  # not empty string
    assert data["system"]
    assert "未检出" in data["abbreviations"] or "No abbreviation" in data["abbreviations"]
    assert "未检出" in data["keywords"] or "No keywords" in data["keywords"]


def test_full_roundtrip():
    """Build data and substitute into a realistic guidance string."""
    data = _build_paper_data(_SAMPLE_CONTEXT, _SAMPLE_FIGURES, [], _SAMPLE_FIG_NOTES)
    guidance = (
        "列出本论文 {paper.system} 涉及的物理理论。"
        "关键术语：{paper.key_terms}；缩写：{paper.abbreviations}。"
        "图：{paper.figures}。图注：{paper.fig_observations_brief}。"
        "关键词：{paper.keywords}。标题：{paper.title}。"
    )
    result = substitute_placeholders(guidance, data)
    assert "{paper." not in result
    assert "lead-free ceramics (ANT-xLa)" in result
    assert "AFE = antiferroelectric" in result
    assert "Fig. 1:" in result
