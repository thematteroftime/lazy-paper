import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)
from stages.s09_render.pptx_summarizer import PptxSummarizer


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
    llm = _fake_llm({"bullets": ["a", "b"], "figure_one_liners": {"Fig. 1": "ok"}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")

    result = summarizer.summarize(_doc())
    assert llm.chat.call_count == 1
    assert result["Intro"]["bullets"] == ["a", "b"]
    assert result["Intro"]["figure_one_liners"] == {"Fig. 1": "ok"}


def test_summarize_writes_audit_files(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
    PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en").summarize(_doc())
    slug = "Intro"
    assert (tmp_path / f"{slug}.input_hash.json").exists()
    assert (tmp_path / f"{slug}.json").exists()
    assert (tmp_path / f"{slug}.prompt.md").exists()
    assert (tmp_path / f"{slug}.response.json").exists()


def test_summarize_reuses_cache_when_input_hash_matches(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
    summarizer = PptxSummarizer(llm=llm, cache_dir=tmp_path, lang="en")
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1

    # Second run with identical input: cache hit, no LLM call.
    summarizer.summarize(_doc())
    assert llm.chat.call_count == 1


def test_summarize_reruns_when_chapter_text_changes(tmp_path: Path):
    llm = _fake_llm({"bullets": ["a"], "figure_one_liners": {}})
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
