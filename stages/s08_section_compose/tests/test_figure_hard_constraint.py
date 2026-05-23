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


def test_verify_skips_figure_advisory_on_rejected_claim():
    """Regression — figure_ids advisory must only run on accepted claims.

    Before fix: a claim rejected at quote-verify still triggered the
    figure_ids check, double-reporting it in `rejected`. Auditor 3
    caught this on cycle 1.
    """
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="Some claim without figure literal",
            cited_chunk_ids=[0],
            cited_quote="this quote does not match the chunk at all",
            figure_ids=["Fig. 5"],
        ),
        GroundedClaim(
            text="A second claim so accepted >= 2 path differs.",
            cited_chunk_ids=[0],
            cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here",
                              doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=0.85,
    )
    # Claim 0 quote doesn't match → rejected (only as quote miss).
    # Must NOT also have a figure_hint_unmet entry for the same claim.
    fig_advisories = [r for r in rejected
                      if isinstance(r, dict)
                      and r.get("reason") == "figure_hint_unmet"]
    assert fig_advisories == [], (
        f"rejected claim should not produce figure advisory; got {fig_advisories}"
    )


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


def test_figure_id_whitelist_advisory_default(monkeypatch):
    """Default: unknown fig_id flagged in rejected as 'figure_id_unknown'
    but claim is still accepted and figure_ids preserved.
    Per cycle 1+2 evidence (unknown fig_ids are usually s04 numbering
    misalignment, not LLM hallucination), default is advisory not hard.
    """
    monkeypatch.delenv("LAZY_PAPER_FIGURE_ID_WHITELIST", raising=False)
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="As shown in Fig. 9 and Fig. 1, the trend is clear.",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 9", "Fig. 1"],
        ),
        GroundedClaim(
            text="A second supporting claim.",
            cited_chunk_ids=[0],
            cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here",
                              doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=0.85,
        available_fig_ids={"Fig. 1"},
    )
    assert len(accepted) == 2
    # figure_ids preserved (advisory mode)
    assert accepted[0].figure_ids == ["Fig. 9", "Fig. 1"]
    # advisory entry recorded
    unknown_advisories = [r for r in rejected
                          if r.get("reason") == "figure_id_unknown"]
    assert len(unknown_advisories) == 1
    assert unknown_advisories[0]["unknown_figures"] == ["Fig. 9"]


def test_figure_id_whitelist_hard_when_env_set(monkeypatch):
    """Env=1: unknown fig_id stripped from claim.figure_ids; claim
    still accepted (don't drop the prose, just sanitize the binding)."""
    monkeypatch.setenv("LAZY_PAPER_FIGURE_ID_WHITELIST", "1")
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="As shown in Fig. 9 and Fig. 1.",
            cited_chunk_ids=[0],
            cited_quote="content",
            figure_ids=["Fig. 9", "Fig. 1"],
        ),
        GroundedClaim(
            text="A second supporting claim.",
            cited_chunk_ids=[0],
            cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here",
                              doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=0.85,
        available_fig_ids={"Fig. 1"},
    )
    assert len(accepted) == 2
    # unknown stripped, known preserved
    assert accepted[0].figure_ids == ["Fig. 1"]
    # advisory still recorded for audit visibility
    unknown_advisories = [r for r in rejected
                          if r.get("reason") == "figure_id_unknown"]
    assert len(unknown_advisories) == 1
