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


# ─── Day-2: compose pipeline + missing_required audit ────────────────────────

def test_missing_required_audits_entities_not_in_prose():
    """If a required entity's distinctive text is missing from the draft
    prose, it shows up — even when the entity's evidence chunk WAS cited."""
    from stages.s08_section_compose.structured import missing_required
    required = [
        RequiredMention(
            entity_text="Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3",
            entity_type="comparator", evidence_chunk_id=0,
            evidence_quote="q", linked_values=[], author_text="Jiang",
        ),
        RequiredMention(
            entity_text="some-other-rare-formula-XYZ",
            entity_type="comparator", evidence_chunk_id=1,
            evidence_quote="q", linked_values=[], author_text="Smith",
        ),
    ]
    # Draft cites BOTH chunks but only writes about the first comparator
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="Jiang et al. reported W_rec=2.94 in Ca2+/Nb5+-codoped material.",
            cited_chunk_ids=[0, 1], cited_quote=""),
        GroundedClaim(text="Generic background paragraph.",
                      cited_chunk_ids=[1], cited_quote=""),
    ])
    missing = missing_required(required, draft)
    assert len(missing) == 1, f"expected 1 missing, got {len(missing)}"
    assert missing[0].entity_text == "some-other-rare-formula-XYZ"


def test_render_strips_chunk_leak():
    """LLM sometimes leaks '(chunk 11)' literal references; render() strips."""
    d = SectionDraft(claims=[
        GroundedClaim(text="A claim with leakage (chunk 11).",
                      cited_chunk_ids=[11], cited_quote=""),
        GroundedClaim(text="另一句 [chunk 3, 5] 中文也要处理。",
                      cited_chunk_ids=[3, 5], cited_quote=""),
        GroundedClaim(text="(chunk 1) at start.",
                      cited_chunk_ids=[1], cited_quote=""),
    ])
    out = d.render(mode="REMOVE")
    assert "chunk" not in out.lower()
    assert "A claim with leakage" in out
    assert "另一句" in out and "中文也要处理" in out


def test_compose_structured_retries_when_required_all_missed(monkeypatch):
    """v1.8: when the initial draft cites 0 required entities, a retry call
    with a stronger 'you missed everything' system prompt should fire."""
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()

    chunks = [
        _make_chunk("r0", "Jiang et al. achieved 2.94 J/cm3 in Ca2+/Nb5+ system.",
                    doc="doc_1.md", start=100, end=200),
        _make_chunk("r1", "Generic background paragraph.",
                    doc="doc_1.md", start=300, end=400),
    ]
    required = [
        RequiredMention(
            entity_text="Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3",
            entity_type="comparator", evidence_chunk_id=0,
            evidence_quote="Jiang et al. achieved 2.94 J/cm3",
            linked_values=["W_rec=2.94 J/cm³"], author_text="Jiang",
        ),
        RequiredMention(
            entity_text="La(Mg1/2Zr1/2)O3", entity_type="comparator",
            evidence_chunk_id=0, evidence_quote="Ma et al. 7.5 J/cm3",
            linked_values=["W_rec=7.5 J/cm³"], author_text="Ma",
        ),
    ]
    # First call: returns a draft that ignores the required mention.
    bad_draft = SectionDraft(claims=[
        GroundedClaim(text="Generic intro about AFE materials.",
                      cited_chunk_ids=[1], cited_quote=""),
        GroundedClaim(text="More generic content here.",
                      cited_chunk_ids=[1], cited_quote=""),
    ])
    # Retry call: returns a draft that cites the required mention (chunk 0).
    good_draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang et al. achieved W_rec=2.94 J/cm³ "
                            "in Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3.",
                      cited_chunk_ids=[0],
                      cited_quote="Jiang et al. achieved 2.94 J/cm3"),
        GroundedClaim(text="Generic intro about AFE materials.",
                      cited_chunk_ids=[1], cited_quote=""),
        GroundedClaim(text="More generic content here.",
                      cited_chunk_ids=[1], cited_quote=""),
    ])
    call_count = {"n": 0}
    drafts = [bad_draft, good_draft]

    class _FakeCompletions:
        def create(self, **kwargs):
            d = drafts[call_count["n"]]
            call_count["n"] += 1
            return d
    class _FakeChat:
        completions = _FakeCompletions()
    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr("instructor.from_openai",
                        lambda client, mode=None: _FakeClient())

    verified, _ = compose_structured(
        mock_llm,
        section_title="Introduction",
        section_guidance="prior work",
        lang_instruction="Chinese",
        chunks=chunks,
        required=required,
        prior_findings="",
    )
    # 2 calls expected: initial + retry
    assert call_count["n"] == 2
    # Retry's good_draft should have been used (cites chunk 0)
    assert any(0 in c.cited_chunk_ids for c in verified.claims)


def test_compose_structured_no_retry_when_required_partially_covered(monkeypatch):
    """Retry-when-empty only fires when ALL required are missed."""
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()
    chunks = [_make_chunk("r0", "Jiang", "doc_1.md", 0, 10),
              _make_chunk("r1", "Other", "doc_1.md", 100, 110)]
    required = [
        RequiredMention(entity_text="x", entity_type="comparator",
                        evidence_chunk_id=0, evidence_quote="q", linked_values=[]),
        RequiredMention(entity_text="y", entity_type="comparator",
                        evidence_chunk_id=1, evidence_quote="q", linked_values=[]),
    ]
    # First (and only — no retry should fire) call cites chunk 0 → 1/2 covered
    partial = SectionDraft(claims=[
        GroundedClaim(text="Cites x", cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Other content", cited_chunk_ids=[1], cited_quote=""),
    ])
    call_count = {"n": 0}

    class _FakeCompletions:
        def create(self, **kwargs):
            call_count["n"] += 1
            return partial
    class _FakeChat:
        completions = _FakeCompletions()
    class _FakeClient:
        chat = _FakeChat()
    monkeypatch.setattr("instructor.from_openai",
                        lambda client, mode=None: _FakeClient())

    compose_structured(
        mock_llm, section_title="Introduction", section_guidance="x",
        lang_instruction="Chinese", chunks=chunks, required=required,
    )
    # 1 call only — partial coverage doesn't trigger retry
    assert call_count["n"] == 1


def test_compose_structured_uses_instructor_and_runs_verifier(monkeypatch):
    """End-to-end mock: instructor returns a SectionDraft, verifier filters,
    we get a verified draft back. No live LLM."""
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()
    chunks = [
        _make_chunk("r0", "Source paragraph one: Ca2+/Nb5+-codoped material achieves 2.94 J/cm3.",
                    doc="doc_1.md", start=0, end=100),
        _make_chunk("r1", "Source paragraph two: synthesis via tape-casting.",
                    doc="doc_1.md", start=100, end=200),
    ]
    fake_draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang reported 2.94 J/cm3.",
                      cited_chunk_ids=[0],
                      cited_quote="Ca2+/Nb5+-codoped material achieves 2.94"),
        GroundedClaim(text="Prepared via tape-casting.",
                      cited_chunk_ids=[1],
                      cited_quote="synthesis via tape-casting"),
        GroundedClaim(text="A fabricated claim.",
                      cited_chunk_ids=[0],
                      cited_quote="This quote is not in source at all"),
    ])

    class _FakeCompletions:
        def create(self, **kwargs):
            return fake_draft
    class _FakeChat:
        completions = _FakeCompletions()
    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr("instructor.from_openai",
                        lambda client, mode=None: _FakeClient())

    verified, rejected = compose_structured(
        mock_llm,
        section_title="Introduction",
        section_guidance="prior work",
        lang_instruction="Chinese",
        chunks=chunks,
        required=[],
        prior_findings="",
    )
    assert len(verified.claims) == 2  # 1 rejected by verifier
    assert len(rejected) == 1
    assert "fabricated" in rejected[0]["text"]
