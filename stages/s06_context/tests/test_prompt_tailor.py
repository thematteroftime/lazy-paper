"""Tests for prompt_tailor — LLM mocked."""
from __future__ import annotations

import json
from pathlib import Path


def test_generate_prompt_augment_happy_path(tmp_path):
    """Mocked LLM returns valid JSON; function returns parsed dict + adds metadata."""
    from stages.s06_context.prompt_tailor import generate_prompt_augment

    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text(
        "Intro text about NBST ceramics. Jiang et al. reported W_rec=2.94 J/cm³."
    )

    context = {
        "title": "Demo paper", "system": "NBST-BMZ", "abbreviations": [],
        "keywords": [], "key_terms": [], "headline_metrics": {},
    }
    valid_response = json.dumps({
        "domain_framing": "lead-free relaxor antiferroelectric ceramics",
        "terminology": [{"term": "W_rec", "note": "energy density J/cm³"}],
        "metric_patterns": [{"kind": "energy", "regex": "\\d+\\.\\d+\\s*J/cm³"}],
        "comparator_style": {
            "format": "<Author> et al. reported <metric>=<value>",
            "example_from_paper": "Jiang et al. reported W_rec=2.94 J/cm³",
        },
    })
    out = generate_prompt_augment(
        context=context, chapters_dir=chapters_dir,
        llm_chat=lambda **_: valid_response,
    )
    assert out["domain_framing"].startswith("lead-free")
    assert out["terminology"][0]["term"] == "W_rec"
    assert "generated_by" in out and out["generated_by"].startswith("prompt_tailor_v")
    assert "generated_at" in out


def test_generate_prompt_augment_malformed_json_raises(tmp_path):
    """LLM returns non-JSON → function raises so caller can soft-degrade."""
    from stages.s06_context.prompt_tailor import (
        generate_prompt_augment,
        PromptTailorError,
    )
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text("intro")

    context = {"title": "x"}
    import pytest
    with pytest.raises(PromptTailorError):
        generate_prompt_augment(
            context=context, chapters_dir=chapters_dir,
            llm_chat=lambda **_: "this is not json",
        )


def test_generate_prompt_augment_missing_required_keys_raises(tmp_path):
    """LLM JSON missing one of the 4 required keys → PromptTailorError."""
    from stages.s06_context.prompt_tailor import (
        generate_prompt_augment,
        PromptTailorError,
    )
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_001_INTRODUCTION.md").write_text("intro")

    incomplete = json.dumps({"domain_framing": "x", "terminology": []})
    import pytest
    with pytest.raises(PromptTailorError):
        generate_prompt_augment(
            context={"title": "x"}, chapters_dir=chapters_dir,
            llm_chat=lambda **_: incomplete,
        )


def test_generate_prompt_augment_no_intro_chapter_uses_empty_intro(tmp_path):
    """If chapter_001_INTRODUCTION.md doesn't exist, pass empty intro and still call LLM."""
    from stages.s06_context.prompt_tailor import generate_prompt_augment

    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    # No intro file written.

    received_user = {}

    def capture_chat(**kw):
        received_user["user"] = kw.get("user", "")
        return json.dumps({
            "domain_framing": "", "terminology": [],
            "metric_patterns": [],
            "comparator_style": {"format": "", "example_from_paper": ""},
        })

    generate_prompt_augment(
        context={"title": "x"}, chapters_dir=chapters_dir,
        llm_chat=capture_chat,
    )
    # The INTRO block in the user prompt should be empty but the marker present.
    assert "<<<INTRO>>>" in received_user["user"]
