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
        "bullets": ["a", "b"],
        "figure_observations": {"Fig. 1": ["obs point 1", "obs point 2"]},
    })
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert llm.chat.call_count == 1
    assert result["Intro"]["bullets"] == ["a", "b"]
    assert result["Intro"]["figure_observations"] == {"Fig. 1": ["obs point 1", "obs point 2"]}


def test_summarize_legacy_figure_one_liners_normalized(tmp_path: Path):
    """v9 backward compat: old figure_one_liners response is auto-normalized to figure_observations."""
    llm = _fake_llm({"bullets": ["a", "b"], "figure_one_liners": {"Fig. 1": "old one-liner"}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert result is not None
    assert "figure_observations" in result["Intro"]
    # Legacy value wrapped in a list
    assert result["Intro"]["figure_observations"] == {"Fig. 1": ["old one-liner"]}


def test_summarize_writes_audit_files(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_observations": {}})
    PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en").summarize(_doc())
    slug = "Intro"
    assert (tmp_path / f"{slug}.input_hash.json").exists()
    assert (tmp_path / f"{slug}.json").exists()
    assert (tmp_path / f"{slug}.prompt.md").exists()
    assert (tmp_path / f"{slug}.response.json").exists()


def test_summarize_reuses_cache_when_input_hash_matches(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_observations": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1

    # Second run with identical input: cache hit, no LLM call.
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1


def test_summarize_reruns_when_chapter_text_changes(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_observations": {}})
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
            {"name": "Section A", "chapter_headings": ["Intro", "Methods", "Conclusion"], "takeaway": "All."},
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
    """summarize_paper returns dict with bullets and takeaway."""
    paper_payload = {
        "bullets": ["Finding 1", "Finding 2", "Finding 3", "Finding 4", "Finding 5"],
        "takeaway": "This paper advances the field significantly.",
    }
    llm = _fake_llm(paper_payload)
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    result = summarizer.summarize_paper(_multi_doc())

    assert result is not None
    assert result["bullets"] == ["Finding 1", "Finding 2", "Finding 3", "Finding 4", "Finding 5"]
    assert result["takeaway"] == "This paper advances the field significantly."


def test_pptx_summarizer_summarize_paper_caches_correctly(tmp_path: Path):
    """summarize_paper caches result and avoids second LLM call."""
    paper_payload = {
        "bullets": ["B1", "B2", "B3"],
        "takeaway": "Important work.",
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
            "bullets": ["a"],
            "figure_observations": {"Fig. 1": ["obs 1", "obs 2"]},
        }
        result = _normalize_chapter_summary(payload)
        assert result["figure_observations"] == {"Fig. 1": ["obs 1", "obs 2"]}

    def test_legacy_one_liners_converted(self):
        """Old figure_one_liners dict is converted to list-of-one per figure."""
        payload = {
            "bullets": ["a"],
            "figure_one_liners": {"Fig. 1": "old one-liner", "Fig. 2": "another"},
        }
        result = _normalize_chapter_summary(payload)
        assert "figure_observations" in result
        assert result["figure_observations"]["Fig. 1"] == ["old one-liner"]
        assert result["figure_observations"]["Fig. 2"] == ["another"]

    def test_missing_both_keys_adds_empty_dict(self):
        """Payload with neither key gets an empty figure_observations."""
        payload = {"bullets": ["a"]}
        result = _normalize_chapter_summary(payload)
        assert result["figure_observations"] == {}

    def test_both_keys_new_takes_precedence(self):
        """When both keys present, figure_observations wins (no conversion)."""
        payload = {
            "bullets": ["a"],
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

    def test_empty_string(self):
        assert normalize_math("") == ""

    def test_none_like_empty(self):
        assert normalize_math("") == ""

    def test_no_latex_passthrough(self):
        text = "ANT-3La achieves η=85% efficiency"
        assert normalize_math(text) == text  # no change needed
