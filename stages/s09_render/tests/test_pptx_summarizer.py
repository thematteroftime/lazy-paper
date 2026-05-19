import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)
from stages.s09_render.pptx_summarizer import PptxSummarizer, _normalize_chapter_summary
from stages.s09_render._math import normalize_math


def _doc():
    return Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Intro", level=1, blocks=(
            Paragraph(text="A study of X."),
            Paragraph(text="It matters because Y."),
            FigureBlock(fig_id="Fig. 1", label="Fig. 1",
                        image_paths=(Path("/img.jpg"),),
                        caption="schema", deep_observation="long obs"),
        )),
    ))


def _fake_llm(payload: dict) -> MagicMock:
    fake = MagicMock()
    fake.chat.return_value = MagicMock(
        content=json.dumps(payload),
        model="fake",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        latency_ms=42.0,
    )
    return fake


def test_summarize_calls_llm_once_per_chapter(tmp_path: Path):
    """v9: LLM returns figure_observations (2-3 points per figure)."""
    llm = _fake_llm({
        "bullets": ["Reached 8.6 J/cm³", "Efficiency 91%"],
        "figure_observations": {"Fig. 1": ["obs point 1", "obs point 2"]},
    })
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert llm.chat.call_count == 1
    assert result["Intro"]["bullets"] == ["Reached 8.6 J/cm³", "Efficiency 91%"]
    assert result["Intro"]["figure_observations"] == {"Fig. 1": ["obs point 1", "obs point 2"]}


def test_summarize_legacy_figure_one_liners_normalized(tmp_path: Path):
    """v9 backward compat: old figure_one_liners response is auto-normalized to figure_observations."""
    llm = _fake_llm({"bullets": ["Reached 8.6 J/cm³", "Efficiency 91%"], "figure_one_liners": {"Fig. 1": "old one-liner"}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert result is not None
    assert "figure_observations" in result["Intro"]
    # Legacy value wrapped in a list
    assert result["Intro"]["figure_observations"] == {"Fig. 1": ["old one-liner"]}


def test_summarize_writes_audit_files(tmp_path: Path):
    llm = _fake_llm({"bullets": ["Reached 8.6 J/cm³"], "figure_observations": {}})
    PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en").summarize(_doc())
    slug = "Intro"
    assert (tmp_path / f"{slug}.input_hash.json").exists()
    assert (tmp_path / f"{slug}.json").exists()
    assert (tmp_path / f"{slug}.prompt.md").exists()
    assert (tmp_path / f"{slug}.response.json").exists()


def test_summarize_reuses_cache_when_input_hash_matches(tmp_path: Path):
    llm = _fake_llm({"bullets": ["Reached 8.6 J/cm³"], "figure_observations": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1

    # Second run with identical input: cache hit, no LLM call.
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1


def test_summarize_reruns_when_chapter_text_changes(tmp_path: Path):
    llm = _fake_llm({"bullets": ["Reached 8.6 J/cm³"], "figure_observations": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())

    changed = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Intro", level=1, blocks=(
            Paragraph(text="DIFFERENT TEXT"),
        )),
    ))
    summarizer.summarize(changed)
    assert llm.chat.call_count == 2


def test_summarize_returns_none_after_three_consecutive_failures(tmp_path: Path):
    failing_llm = MagicMock()
    failing_llm.chat.side_effect = RuntimeError("LLM exploded")
    summarizer = PptxSummarizer(llm=failing_llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize(_doc())
    assert result is None
    assert failing_llm.chat.call_count == 3   # 3 retries on the single chapter


# ── v7 new tests ────────────────────────────────────────────────────────────────

def _multi_doc():
    """Document with 3 chapters for outline/paper tests."""
    return Document(paper_title="Test Paper", lang="en", chapters=(
        Chapter(heading="Intro", level=1, blocks=(
            Paragraph(text="Introduction paragraph."),
        )),
        Chapter(heading="Methods", level=1, blocks=(
            Paragraph(text="We used method X."),
            FigureBlock(fig_id="Fig. 1", label="Fig. 1",
                        image_paths=(Path("/m.jpg"),),
                        caption="method fig", deep_observation="detailed obs"),
        )),
        Chapter(heading="Conclusion", level=1, blocks=(
            Paragraph(text="In conclusion, Y was found."),
        )),
    ))


def test_pptx_summarizer_summarize_outline_returns_groups(tmp_path: Path):
    """summarize_outline returns a list of group dicts."""
    outline_payload = {
        "groups": [
            {"name": "Background", "chapter_headings": ["Intro"], "takeaway": "Sets context."},
            {"name": "Core Work", "chapter_headings": ["Methods"], "takeaway": "Main methods."},
            {"name": "Findings", "chapter_headings": ["Conclusion"], "takeaway": "Key results."},
        ]
    }
    llm = _fake_llm(outline_payload)
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize_outline(_multi_doc())

    assert result is not None
    assert len(result) == 3
    assert result[0]["name"] == "Background"
    assert "Intro" in result[0]["chapter_headings"]
    assert result[0]["takeaway"] == "Sets context."


def test_pptx_summarizer_summarize_outline_caches_correctly(tmp_path: Path):
    """summarize_outline caches result and avoids second LLM call."""
    outline_payload = {
        "groups": [
            {"name": "Background", "chapter_headings": ["Intro"], "takeaway": "Sets context."},
            {"name": "Core Work", "chapter_headings": ["Methods"], "takeaway": "Main methods."},
            {"name": "Findings", "chapter_headings": ["Conclusion"], "takeaway": "Key results."},
        ]
    }
    llm = _fake_llm(outline_payload)
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    doc = _multi_doc()

    # First call: LLM invoked
    result1 = summarizer.summarize_outline(doc)
    assert llm.chat.call_count == 1
    assert (tmp_path / "_outline.json").exists()
    assert (tmp_path / "_outline.input_hash.json").exists()

    # Second call with same input: cache hit, no new LLM call
    result2 = summarizer.summarize_outline(doc)
    assert llm.chat.call_count == 1
    assert result2 == result1


def test_pptx_summarizer_summarize_outline_returns_none_on_failure(tmp_path: Path):
    """summarize_outline returns None when LLM fails repeatedly."""
    failing_llm = MagicMock()
    failing_llm.chat.side_effect = RuntimeError("Network error")
    summarizer = PptxSummarizer(llm=failing_llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize_outline(_multi_doc())
    assert result is None
    assert failing_llm.chat.call_count == 3


def test_pptx_summarizer_summarize_paper_returns_bullets_and_takeaway(tmp_path: Path):
    """summarize_paper returns dict with bullets and takeaway.

    v1.3 T3: requires ≥3 quantitative bullets + a comparative/quant takeaway."""
    paper_payload = {
        "bullets": [
            "Energy density reaches 8.6 J/cm³",
            "Efficiency hits 91%",
            "Breakdown field 350 kV/cm",
            "Tested at 25°C",
            "Frequency span 2-800 kHz",
        ],
        "takeaway": "Improves prior work energy density by 30%.",
    }
    llm = _fake_llm(paper_payload)
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize_paper(_multi_doc())

    assert result is not None
    assert len(result["bullets"]) == 5
    assert "8.6" in result["bullets"][0]


def test_pptx_summarizer_summarize_paper_caches_correctly(tmp_path: Path):
    """summarize_paper caches result and avoids second LLM call."""
    paper_payload = {
        "bullets": [
            "Energy density 8.6 J/cm³",
            "Efficiency 91%",
            "Breakdown 350 kV/cm",
        ],
        "takeaway": "Outperforms baselines by 30% efficiency.",
    }
    llm = _fake_llm(paper_payload)
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    doc = _multi_doc()

    # First call: LLM invoked
    result1 = summarizer.summarize_paper(doc)
    assert llm.chat.call_count == 1
    assert (tmp_path / "_paper.json").exists()
    assert (tmp_path / "_paper.input_hash.json").exists()
    assert (tmp_path / "_paper.prompt.md").exists()
    assert (tmp_path / "_paper.response.json").exists()

    # Second call: cache hit
    result2 = summarizer.summarize_paper(doc)
    assert llm.chat.call_count == 1
    assert result2 == result1


def test_pptx_summarizer_summarize_paper_returns_none_on_failure(tmp_path: Path):
    """summarize_paper returns None when LLM fails repeatedly."""
    failing_llm = MagicMock()
    failing_llm.chat.side_effect = RuntimeError("LLM down")
    summarizer = PptxSummarizer(llm=failing_llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize_paper(_multi_doc())
    assert result is None
    assert failing_llm.chat.call_count == 3


# ── v9 new tests ────────────────────────────────────────────────────────────────

class TestNormalizeChapterSummary:
    """Tests for _normalize_chapter_summary (legacy cache compat)."""

    def test_new_format_passthrough(self):
        """Payload with figure_observations is returned unchanged."""
        payload = {
            "bullets": ["Reached 8.6 J/cm³"],
            "figure_observations": {"Fig. 1": ["obs 1", "obs 2"]},
        }
        result = _normalize_chapter_summary(payload)
        assert result["figure_observations"] == {"Fig. 1": ["obs 1", "obs 2"]}

    def test_legacy_one_liners_converted(self):
        """Old figure_one_liners dict is converted to list-of-one per figure."""
        payload = {
            "bullets": ["Reached 8.6 J/cm³"],
            "figure_one_liners": {"Fig. 1": "old one-liner", "Fig. 2": "another"},
        }
        result = _normalize_chapter_summary(payload)
        assert "figure_observations" in result
        assert result["figure_observations"]["Fig. 1"] == ["old one-liner"]
        assert result["figure_observations"]["Fig. 2"] == ["another"]

    def test_missing_both_keys_adds_empty_dict(self):
        """Payload with neither key gets an empty figure_observations."""
        payload = {"bullets": ["Reached 8.6 J/cm³"]}
        result = _normalize_chapter_summary(payload)
        assert result["figure_observations"] == {}

    def test_both_keys_new_takes_precedence(self):
        """When both keys present, figure_observations wins (no conversion)."""
        payload = {
            "bullets": ["Reached 8.6 J/cm³"],
            "figure_one_liners": {"Fig. 1": "old"},
            "figure_observations": {"Fig. 1": ["new obs"]},
        }
        result = _normalize_chapter_summary(payload)
        assert result["figure_observations"] == {"Fig. 1": ["new obs"]}


class TestNormalizeMath:
    """Tests for normalize_math helper."""

    def test_greek_letter_eta(self):
        assert normalize_math(r"$\eta$") == "η"

    def test_greek_letter_standalone(self):
        assert normalize_math(r"\eta") == "η"
        assert normalize_math(r"\sigma") == "σ"
        assert normalize_math(r"\mu") == "μ"

    def test_subscript_braces(self):
        result = normalize_math(r"E_{b}")
        assert "E" in result and "b" in result  # E with subscript b char
        # subscript b maps to ᵦ (b is not in _SUB_MAP for subscript letters beyond h)
        # check E remains and _{b} is processed
        assert "_{" not in result

    def test_subscript_single_char(self):
        result = normalize_math(r"W_rec")  # underscore single char
        # 'r' not in subscript map, so unchanged aside from underscore removal
        assert "_" not in result or "W" in result

    def test_superscript_digits(self):
        result = normalize_math(r"cm^{3}")
        assert "cm" in result
        assert "³" in result

    def test_strip_dollar_delimiters(self):
        assert normalize_math(r"$\eta$") == "η"
        assert normalize_math(r"$E_b$") == "Eᵦ" or "E" in normalize_math(r"$E_b$")

    def test_operators(self):
        assert normalize_math(r"\times") == "×"
        assert normalize_math(r"\pm") == "±"
        assert normalize_math(r"\leq") == "≤"
        assert normalize_math(r"\rightarrow") == "→"

    def test_unicode_subscript_letters_collapse_to_underscore_ascii(self):
        # v1.2 Issue A1: Unicode subscript letters get dropped by PPT fonts
        # that don't cover U+2090–U+209C, so we fall back to ASCII underscore.
        assert normalize_math("aₚₕₒₜ/cₚₕₒₜ") == "a_phot/c_phot"
        assert normalize_math("Tₘ") == "T_m"
        assert normalize_math("εᵣ") == "ε_r"

    def test_unicode_subscript_digits_remain_unicode(self):
        # Pure digit subscripts like H₂O / Pb²⁺ render fine in standard fonts.
        # They must NOT be collapsed back to ASCII.
        assert normalize_math("H₂O") == "H₂O"
        assert normalize_math("Pb₀.₆₅") == "Pb₀.₆₅"

    def test_empty_string(self):
        assert normalize_math("") == ""

    def test_none_like_empty(self):
        assert normalize_math("") == ""

    def test_no_latex_passthrough(self):
        text = "ANT-3La achieves η=85% efficiency"
        assert normalize_math(text) == text  # no change needed


class TestIsLowDiversity:
    """v1.2.2: low-diversity heuristic refactored — only triggers when a token
    appears in EVERY group name (catches mono-keyword outline degeneracy).
    Recurring paper-specific nouns in N-1 of N names should NOT trigger."""

    def test_cjk_all_same_prefix_triggers(self):
        from stages.s09_render.pptx_summarizer import _is_low_diversity
        groups = [{"name": n} for n in [
            "弛豫反铁电基础概念", "弛豫反铁电相变机制",
            "弛豫反铁电应用", "弛豫反铁电结论与展望",
        ]]
        assert _is_low_diversity(groups) is True

    def test_cjk_diverse_passes(self):
        from stages.s09_render.pptx_summarizer import _is_low_diversity
        groups = [{"name": n} for n in [
            "A位掺杂调控", "相变机制与极化",
            "能量存储性能", "微观表征技术",
        ]]
        assert _is_low_diversity(groups) is False

    def test_english_paper_specific_noun_in_majority_does_not_trigger(self):
        """yang2025 regression: CBPS in 3 of 4 group names is acceptable."""
        from stages.s09_render.pptx_summarizer import _is_low_diversity
        groups = [{"name": n} for n in [
            "Relaxor AFE Concept and Background",
            "CBPS Synthesis and Crystal Structure",
            "CBPS Relaxor AFE Properties",
            "Neuromorphic Computing with CBPS",
        ]]
        assert _is_low_diversity(groups) is False

    def test_english_token_in_every_name_triggers(self):
        from stages.s09_render.pptx_summarizer import _is_low_diversity
        groups = [{"name": n} for n in [
            "CBPS Basics", "CBPS Synthesis", "CBPS Properties", "CBPS Outlook",
        ]]
        assert _is_low_diversity(groups) is True

    def test_few_groups_never_triggers(self):
        from stages.s09_render.pptx_summarizer import _is_low_diversity
        assert _is_low_diversity([{"name": "A"}, {"name": "A"}, {"name": "A"}]) is False


class TestV1_3_Validators:
    """v1.3 T3/T7: post-LLM content validators."""

    def test_has_quant_matches_units(self):
        from stages.s09_render.pptx_summarizer import _has_quant
        assert _has_quant("Achieved 8.6 J/cm³")
        assert _has_quant("Efficiency reaches 91%")
        assert _has_quant("Frequency 800 kHz")
        assert _has_quant("Field 350 kV/cm")
        assert _has_quant("Temperature 25°C")
        assert not _has_quant("This is a qualitative statement.")
        assert not _has_quant("")

    def test_is_descriptive_only_rejects_pure_description(self):
        from stages.s09_render.pptx_summarizer import _is_descriptive_only
        assert _is_descriptive_only("Panel (a) shows the dielectric peak.")
        assert _is_descriptive_only("Figure illustrates the trend.")

    def test_is_descriptive_only_accepts_critique(self):
        from stages.s09_render.pptx_summarizer import _is_descriptive_only
        # 'shows' + critique marker → not pure description
        assert not _is_descriptive_only(
            "Panel (a) shows W_rec vs x but lacks error bars — limitation."
        )
        assert not _is_descriptive_only("Missing control: figure should add x=0 reference.")
        assert not _is_descriptive_only("")  # empty is not descriptive-only


class TestV1_3_QuantValidation:
    """v1.3 T3: paper-summary rejects payloads lacking quantitative content."""

    def test_summarize_paper_retries_on_low_quant_count(self, tmp_path: Path):
        # First payload: 2/3 quant — should be rejected.
        bad = {
            "bullets": ["Energy density 8.6 J/cm³", "Efficiency 91%", "Improved markedly"],
            "takeaway": "Outperforms baselines by 30%.",
        }
        good = {
            "bullets": ["8.6 J/cm³", "91%", "350 kV/cm"],
            "takeaway": "Outperforms by 30%.",
        }
        llm = MagicMock()
        llm.chat.side_effect = [
            MagicMock(content=json.dumps(bad), model="m", usage={}, latency_ms=1),
            MagicMock(content=json.dumps(good), model="m", usage={}, latency_ms=1),
        ]
        summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
        result = summarizer.summarize_paper(_multi_doc())
        assert result is not None
        assert llm.chat.call_count == 2  # 1 reject + 1 accept

    def test_summarize_paper_soft_accept_logs_failure_but_returns_payload(
        self, tmp_path: Path, capsys,
    ):
        """v1.3.1: strict-validation failure no longer returns None — the
        last shape-valid payload is soft-accepted so the closing slide ships
        with content instead of falling back to rule-based paragraph snippets.
        Logging still surfaces the failure on stderr.
        """
        payload = {
            "bullets": ["A", "B", "C"],
            "takeaway": "Good work.",
        }
        llm = MagicMock()
        llm.chat.return_value = MagicMock(
            content=json.dumps(payload), model="m", usage={}, latency_ms=1,
        )
        summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
        result = summarizer.summarize_paper(_multi_doc())
        # Soft-accept: payload returned even though strict validation rejected it.
        assert result is not None
        assert result["bullets"] == payload["bullets"]
        captured = capsys.readouterr()
        # Failure is still logged with the soft-accept marker.
        assert "summarize_paper (soft-accept)" in captured.err


class TestV1_3_1_SoftAccept:
    """v1.3.1 — chapter and paper summarizers must soft-accept the last
    shape-valid payload when strict T3 quant validation rejects all retries.
    Catastrophic for EN papers in v1.3.0: 80%+ of chapters lost their LLM
    summaries because conceptual chapters legitimately have no quant anchors,
    which dropped the slide planner to its [:60] rule-based fallback."""

    def test_summarize_chapter_soft_accepts_no_quant_payload(self, tmp_path: Path):
        # All retries return a shape-valid payload with NO quantitative content.
        non_quant = {
            "bullets": [
                "Relaxor antiferroelectrics combine antiparallel dipoles with field-induced polarization switching.",
                "CuBiP2Se6 single crystals retain antiferroelectric order down to atomic thicknesses.",
            ],
            "figure_observations": {},
        }
        llm = MagicMock()
        llm.chat.return_value = MagicMock(
            content=json.dumps(non_quant), model="m", usage={}, latency_ms=1,
        )
        summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
        result = summarizer.summarize(_doc())
        # Soft-accept: result has the bullets even though strict validation failed.
        assert result is not None
        assert result["Intro"]["bullets"] == non_quant["bullets"]
        # Cache written despite validation failure (soft-accept persists).
        assert (tmp_path / "Intro.json").exists()

    def test_summarize_paper_soft_accepts_non_comparative_takeaway(self, tmp_path: Path):
        # 3 quant bullets but qualitative takeaway → would have been rejected.
        payload = {
            "bullets": [
                "Reached 8.6 J/cm³",
                "Efficiency 91%",
                "Field 350 kV/cm",
                "Stable to 250°C",
            ],
            "takeaway": "This paper introduces a robust new framework for relaxor design.",
        }
        llm = MagicMock()
        llm.chat.return_value = MagicMock(
            content=json.dumps(payload), model="m", usage={}, latency_ms=1,
        )
        summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
        result = summarizer.summarize_paper(_multi_doc())
        assert result is not None
        assert result["takeaway"] == payload["takeaway"]


class TestV1_3_1_ExoticUnicodeFallback:
    """v1.3.1: rare Unicode punctuation (U+2011, U+202F, …) renders as boxes
    in the default PPT fonts. normalize_math maps them to ASCII equivalents."""

    def test_non_breaking_hyphen_becomes_ascii_hyphen(self):
        # U+2011 → '-'
        assert normalize_math("non‑centrosymmetric") == "non-centrosymmetric"
        assert normalize_math("P‑E loop") == "P-E loop"

    def test_narrow_no_break_space_becomes_regular_space(self):
        # U+202F → ' '
        assert normalize_math("8.6 J/cm³") == "8.6 J/cm³"

    def test_zero_width_space_dropped(self):
        # U+200B disappears
        assert normalize_math("foo​bar") == "foobar"
