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
