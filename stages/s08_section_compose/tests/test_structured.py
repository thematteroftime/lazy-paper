"""Day-1 tests for Strategy J — schema + verifier gate."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stages.s08_section_compose.structured import (
    GroundedClaim,
    SectionDraft,
    RequiredMention,
    build_required_mentions,
    verify_section_draft,
    select_top_required,
)
from llm.paper_kg import Entity, PaperKG
from llm.retriever import Chunk


# ─── schema validation ────────────────────────────────────────────────────────

def _make_chunk(cid: str, text: str, doc="doc_1.md", start=0, end=100) -> Chunk:
    return Chunk(id=cid, text=text, doc_name=doc, char_start=start, char_end=end)


def test_grounded_claim_accepts_known_chunk_ids():
    c = GroundedClaim.model_validate(
        {"text": "A claim that references chunk 0.",
         "cited_chunk_ids": [0],
         "cited_quote": "verbatim text"},
        context={"allowed_chunk_ids": {0, 1, 2}},
    )
    assert c.cited_chunk_ids == [0]


def test_grounded_claim_rejects_unknown_chunk_id():
    with pytest.raises(ValidationError) as exc:
        GroundedClaim.model_validate(
            {"text": "A claim citing a nonexistent chunk.",
             "cited_chunk_ids": [99],
             "cited_quote": "hallucinated"},
            context={"allowed_chunk_ids": {0, 1, 2}},
        )
    assert "not in retrieved set" in str(exc.value)


def test_grounded_claim_no_context_skips_validation():
    """Backward compat: when no allowed_chunk_ids context, any ID accepted."""
    c = GroundedClaim(text="No-context claim", cited_chunk_ids=[42],
                      cited_quote="anything")
    assert c.cited_chunk_ids == [42]


def test_section_draft_min_claims_enforced():
    with pytest.raises(ValidationError):
        SectionDraft(claims=[GroundedClaim(text="just one", cited_chunk_ids=[0])])


# ─── verifier gate ────────────────────────────────────────────────────────────

def test_verifier_accepts_exact_quote():
    chunks = {0: _make_chunk("c0", "The breakdown field E_b reached 348 kV/cm at room temperature.")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="E_b reached 348 kV/cm.",
                      cited_chunk_ids=[0],
                      cited_quote="The breakdown field E_b reached 348 kV/cm"),
        GroundedClaim(text="Another related claim.",
                      cited_chunk_ids=[0],
                      cited_quote="at room temperature"),
        GroundedClaim(text="A third claim.",
                      cited_chunk_ids=[0],
                      cited_quote="The breakdown field"),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 3
    assert rejected == []


def test_verifier_rejects_paraphrased_quote():
    chunks = {0: _make_chunk("c0", "Pure white snow blankets the mountains.")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Some claim", cited_chunk_ids=[0],
                      cited_quote="The breakdown field is high"),  # not in source at all
        GroundedClaim(text="Real claim", cited_chunk_ids=[0],
                      cited_quote="Pure white snow blankets"),     # ≥0.85 fuzzy ratio
        GroundedClaim(text="Another claim", cited_chunk_ids=[0],
                      cited_quote="blankets the mountains"),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 2
    assert len(rejected) == 1
    assert "breakdown field" in rejected[0]["quote"]


def test_verifier_passes_empty_quote_through():
    """Claims with no cited_quote skip verification (no grounding to check)."""
    chunks = {0: _make_chunk("c0", "x")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="A1", cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="A2", cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="A3", cited_chunk_ids=[0], cited_quote=""),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 3
    assert rejected == []


# ─── required-mentions construction ───────────────────────────────────────────

def _kg_with_comparator() -> PaperKG:
    return PaperKG(
        entities=[
            Entity(id="m1", type="material", text="0.85NBST-0.15BMZ",
                   source_span=("doc_1.md", 0, 17)),
            Entity(id="c1", type="comparator",
                   text="Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3-based RFE ceramics",
                   source_span=("doc_1.md", 100, 200)),
            Entity(id="c2", type="comparator",
                   text="La(Mg1/2Zr1/2)O3-modified NBT-based RFE ceramics",
                   source_span=("doc_1.md", 250, 350)),
            Entity(id="v1", type="value", text="2.94",
                   source_span=("doc_1.md", 100, 200)),
        ],
        relations=[],
    )


def test_build_required_mentions_picks_comparators_for_introduction():
    kg = _kg_with_comparator()
    source_text = (
        "                                                                                                    "
        "Jiang et al. reported Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3 with W_rec=2.94 J/cm³ and η=91.04%. "
        "Ma et al. La(Mg1/2Zr1/2)O3-modified NBT-based RFE ceramics achieved superior performance."
    )
    source_docs = {"doc_1.md": source_text}
    chunk0 = Chunk(id="r0", text=source_text[80:240], doc_name="doc_1.md",
                   char_start=80, char_end=240)
    chunk1 = Chunk(id="r1", text=source_text[240:400], doc_name="doc_1.md",
                   char_start=240, char_end=400)
    required = build_required_mentions(
        section_title="Introduction", section_guidance="prior work",
        kg=kg, source_docs=source_docs, retrieved_chunks=[chunk0, chunk1],
    )
    types = {r.entity_type for r in required}
    assert "comparator" in types
    # The two comparator entities should be matched to their chunks
    texts = [r.entity_text for r in required]
    assert any("Ca2+/Nb5+" in t for t in texts)


def test_build_required_skips_non_survey_sections():
    """A 'Synthesis' section should not get comparators as required mentions."""
    kg = _kg_with_comparator()
    chunk0 = Chunk(id="r0", text="x", doc_name="doc_1.md", char_start=0, char_end=1)
    required = build_required_mentions(
        section_title="Synthesis and Preparation", section_guidance="tape-casting",
        kg=kg, source_docs={"doc_1.md": "x"}, retrieved_chunks=[chunk0],
    )
    types = {r.entity_type for r in required}
    assert "comparator" not in types


# ─── top-N selection ──────────────────────────────────────────────────────────

def test_select_top_required_caps_at_5():
    """Per design: cap at top-5 most-distinctive."""
    many = [
        RequiredMention(entity_text=f"x{i}", entity_type="comparator",
                        evidence_chunk_id=0, evidence_quote="q",
                        linked_values=[])
        for i in range(10)
    ]
    capped = select_top_required(many, cap=5)
    assert len(capped) == 5


def test_select_top_required_prefers_distinctive_text():
    """A 50-char chemical formula ranks higher than a short generic name."""
    short = RequiredMention(entity_text="short", entity_type="comparator",
                            evidence_chunk_id=0, evidence_quote="q",
                            linked_values=[])
    long_chem = RequiredMention(
        entity_text="0.6[(Bi0.5Na0.4K0.1)1-1.5xLax]TiO3-0.4[2/3SrTiO3-1/3Bi(Mg2/3Ni1/3)O3]",
        entity_type="comparator",
        evidence_chunk_id=0, evidence_quote="q", linked_values=[])
    capped = select_top_required([short, long_chem], cap=1)
    assert capped[0] is long_chem
