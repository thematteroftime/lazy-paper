"""Tests for variant C — figure_ids hard constraint."""
import pytest

from stages.s08_section_compose.structured import GroundedClaim, SectionDraft


def test_grounded_claim_has_figure_ids_default_empty():
    c = GroundedClaim(text="xx", cited_chunk_ids=[0], cited_quote="q")
    assert c.figure_ids == []


def test_grounded_claim_accepts_figure_ids():
    c = GroundedClaim(
        text="As shown in Fig. 3 …",
        cited_chunk_ids=[0],
        cited_quote="q",
        figure_ids=["Fig. 3"],
    )
    assert c.figure_ids == ["Fig. 3"]


def test_verify_flags_missing_figure_mention():
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="Some claim without figure literal",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 5"],
        ),
        GroundedClaim(
            text="Another supporting claim here.",
            cited_chunk_ids=[0],
            cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here", doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id, ratio_threshold=0.85)
    # advisory: claim still accepted
    assert len(accepted) == 2
    # but rejected log should record the figure_hint_unmet
    has_fig_advisory = any(
        isinstance(r, dict) and r.get("reason") == "figure_hint_unmet"
        for r in rejected
    )
    assert has_fig_advisory, f"expected figure_hint_unmet advisory; got {rejected}"


def test_verify_accepts_when_figure_mentioned():
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="As shown in Fig. 5, the trend is clear.",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 5"],
        ),
        GroundedClaim(
            text="Another supporting claim here.",
            cited_chunk_ids=[0],
            cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here", doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id, ratio_threshold=0.85)
    assert len(accepted) == 2
    no_fig_advisory = not any(
        isinstance(r, dict) and r.get("reason") == "figure_hint_unmet"
        for r in rejected
    )
    assert no_fig_advisory
