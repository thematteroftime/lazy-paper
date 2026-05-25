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


def test_verifier_rejects_empty_quote_with_author_anchor(monkeypatch):
    """v1.12 phase 2: claim names 'Jiang et al.' but cited_quote empty → REJECT."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "1")  # default; explicit for clarity
    chunks = {0: _make_chunk("c0", "Jiang et al. reported W_rec = 2.94 J/cm³.")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang et al. reported a moderate W_rec.",
                      cited_chunk_ids=[0], cited_quote=""),  # anchored but empty quote
        GroundedClaim(text="The system maintains stability.",
                      cited_chunk_ids=[0], cited_quote=""),  # no anchors — should pass
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 1
    assert accepted[0].text == "The system maintains stability."
    assert any(r["reason"] == "anchored_claim_no_quote" for r in rejected)


def test_verifier_rejects_empty_quote_with_value_anchor(monkeypatch):
    """v1.12 phase 2: claim names 'W_rec = 5.00 J/cm³' but cited_quote empty → REJECT."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "1")
    chunks = {0: _make_chunk("c0", "A large W_rec of 5.00 J/cm³ was achieved.")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="The flagship achieves W_rec = 5.00 J/cm³ at 340 kV/cm.",
                      cited_chunk_ids=[0], cited_quote=""),  # value anchor, no quote → REJECT
        GroundedClaim(text="The material was synthesized conventionally.",
                      cited_chunk_ids=[0], cited_quote=""),  # no anchors → ACCEPT
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 1
    assert accepted[0].text == "The material was synthesized conventionally."
    assert any(r["reason"] == "anchored_claim_no_quote" for r in rejected)


def test_verifier_opt_out_via_env_restores_old_behavior(monkeypatch):
    """LAZY_PAPER_ANCHORED_QUOTE=0 restores pre-v1.12 'blanket accept empty quote'."""
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")
    chunks = {0: _make_chunk("c0", "Jiang et al. reported W_rec.")}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Jiang et al. reported a moderate W_rec.",
                      cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="The ceramic was sintered at 1100 °C.",
                      cited_chunk_ids=[0], cited_quote=""),
    ])
    accepted, rejected = verify_section_draft(draft, chunks)
    assert len(accepted) == 2, "opt-out env should accept anchored empty-quote claims"


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


def test_compose_structured_no_retry_when_required_mostly_covered(monkeypatch):
    """Retry-when-empty does NOT fire when post-verify coverage > 50%.

    With 3 required and 2 mentioned (67%), the post-verify coverage is
    above threshold so no retry call is made — keeping the cost ceiling
    fixed when the initial draft is good enough.
    """
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()
    chunks = [_make_chunk("r0", "alpha beta gamma", "doc_1.md", 0, 16),
              _make_chunk("r1", "Other content", "doc_1.md", 100, 113)]
    required = [
        RequiredMention(entity_text="alpha", entity_type="comparator",
                        evidence_chunk_id=0, evidence_quote="q", linked_values=[]),
        RequiredMention(entity_text="beta", entity_type="comparator",
                        evidence_chunk_id=0, evidence_quote="q", linked_values=[]),
        RequiredMention(entity_text="gamma", entity_type="comparator",
                        evidence_chunk_id=0, evidence_quote="q", linked_values=[]),
    ]
    # Mentions 2 of 3 distinctive tokens → ~67% coverage, above 50%.
    partial = SectionDraft(claims=[
        GroundedClaim(text="Discusses alpha and beta in detail.",
                      cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Other content paragraph.",
                      cited_chunk_ids=[1], cited_quote=""),
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
    # Disable the length-based retry — this test is about coverage retry only.
    monkeypatch.setenv("LAZY_PAPER_MIN_SECTION_CHARS", "0")

    compose_structured(
        mock_llm, section_title="Introduction", section_guidance="x",
        lang_instruction="Chinese", chunks=chunks, required=required,
    )
    assert call_count["n"] == 1


def test_compose_structured_retries_when_section_too_short(monkeypatch):
    """retry-when-short fires when verified draft is below min-chars/claims.

    Coverage is fine (no required mentions), but the draft has only 2
    short claims totalling ~60 chars — under the default thresholds, so
    a second LLM call should fire.
    """
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()
    chunks = [_make_chunk("r0", "x" * 200, "doc_1.md", 0, 200)]
    required: list = []  # no required mentions — coverage retry won't fire
    short = SectionDraft(claims=[
        GroundedClaim(text="Short claim one.", cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Short claim two.", cited_chunk_ids=[0], cited_quote=""),
    ])
    longer = SectionDraft(claims=[
        GroundedClaim(text="A much longer claim that covers " + ("x" * 150),
                      cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Another substantive claim " + ("y" * 150),
                      cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Third detailed claim " + ("z" * 150),
                      cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Fourth claim " + ("w" * 150),
                      cited_chunk_ids=[0], cited_quote=""),
    ])
    drafts = [short, longer]
    call_count = {"n": 0}

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
        mock_llm, section_title="Section", section_guidance="x",
        lang_instruction="Chinese", chunks=chunks, required=required,
    )
    assert call_count["n"] == 2, "second call (retry-when-short) should fire"
    # The longer draft should win because it's longer + has more claims
    assert len(verified.claims) >= 3


def test_compose_structured_no_short_retry_when_disabled(monkeypatch):
    """LAZY_PAPER_MIN_SECTION_CHARS=0 disables length-based retry."""
    from unittest.mock import MagicMock
    from stages.s08_section_compose.structured import compose_structured

    mock_llm = MagicMock()
    mock_llm.model = "deepseek-chat"
    mock_llm._client = MagicMock()
    chunks = [_make_chunk("r0", "x" * 200, "doc_1.md", 0, 200)]
    short = SectionDraft(claims=[
        GroundedClaim(text="Short.", cited_chunk_ids=[0], cited_quote=""),
        GroundedClaim(text="Also short.", cited_chunk_ids=[0], cited_quote=""),
    ])
    call_count = {"n": 0}

    class _FakeCompletions:
        def create(self, **kwargs):
            call_count["n"] += 1
            return short
    class _FakeChat:
        completions = _FakeCompletions()
    class _FakeClient:
        chat = _FakeChat()
    monkeypatch.setattr("instructor.from_openai",
                        lambda client, mode=None: _FakeClient())
    monkeypatch.setenv("LAZY_PAPER_MIN_SECTION_CHARS", "0")

    compose_structured(
        mock_llm, section_title="Section", section_guidance="x",
        lang_instruction="Chinese", chunks=chunks, required=[],
    )
    assert call_count["n"] == 1


def test_figure_relevance_picks_topically_close_figures():
    from stages.s08_section_compose.structured import _figure_relevance

    fig_notes = [
        {"fig_id": "Fig.1", "caption": "SEM microstructure of NBST-BMZ ceramics",
         "deep_observation": "Grain size decreases with BMZ content"},
        {"fig_id": "Fig.5", "caption": "P-E loops at varying electric field",
         "deep_observation": "Pinched double loops characteristic of AFE"},
        {"fig_id": "Fig.8", "caption": "Frequency-dependent dielectric constant",
         "deep_observation": "Broad relaxor peak around 200°C"},
    ]
    # Section about P-E loops — should rank Fig.5 highest
    top = _figure_relevance(
        section_title="Polarization Behaviour",
        section_guidance="P-E hysteresis loops and pinched response",
        fig_notes=fig_notes, top_k=2,
    )
    assert len(top) >= 1
    assert top[0]["fig_id"] == "Fig.5"


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


# v1.11 Tier 1 — Meta-Auditor M1+M2 confirmed user-visible bug fixes

def test_figure_ids_pydantic_max_length():
    """M2 #2: schema must hard-cap figure_ids at 3 per claim
    (ali2025_flash ch11 hit 62 refs/chapter before this cap)."""
    import pytest
    from pydantic import ValidationError
    from stages.s08_section_compose.structured import GroundedClaim
    # 3 figs OK
    c = GroundedClaim(
        text="As shown in Fig. 1, Fig. 2, Fig. 3 the trend holds.",
        cited_chunk_ids=[0], cited_quote="content",
        figure_ids=["Fig. 1", "Fig. 2", "Fig. 3"],
    )
    assert len(c.figure_ids) == 3
    # 4 figs rejected
    with pytest.raises(ValidationError):
        GroundedClaim(
            text="x", cited_chunk_ids=[0], cited_quote="",
            figure_ids=["Fig. 1", "Fig. 2", "Fig. 3", "Fig. 4"],
        )


def test_verify_rejects_schema_prefix_leak():
    """M2 #3: claim.text starting with 'GroundedClaim:' / 'Claim:' is
    schema noise leaking through; must be rejected before reaching prose."""
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
    )
    from llm.retriever import Chunk
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="GroundedClaim: Kerr et al. demonstrated 5 J/cm³.",
            cited_chunk_ids=[0], cited_quote="content",
        ),
        GroundedClaim(
            text="Claim: Jiang et al. reported 2.94 J/cm³.",
            cited_chunk_ids=[0], cited_quote="content here",
        ),
        GroundedClaim(
            text="This is a normal claim.",
            cited_chunk_ids=[0], cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here",
                              doc_name="d", char_start=0, char_end=12)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=0.85,
    )
    leak_rejects = [r for r in rejected
                    if r.get("reason") == "schema_prefix_leak"]
    assert len(leak_rejects) == 2  # both prefixed claims rejected
    accepted_texts = [c.text for c in accepted]
    assert "This is a normal claim." in accepted_texts
    assert not any(t.startswith("GroundedClaim:") for t in accepted_texts)
    assert not any(t.startswith("Claim:") for t in accepted_texts)


def test_claim_dedup_collapses_chinese_english_rephrase():
    """M2 #1: same fact written in English + 中文 must collapse via
    distinctive-token tier, even when anchor regex misses."""
    from stages.s08_section_compose.structured import _claim_dedup_key
    # No author / no SI-unit value → falls past anchor tier, but distinctive
    # chemical tokens (bi0, na0, tio3, codoped) should collapse.
    en = ("Researchers achieved 8.3 J/cm3 in Ca2+/Nb5+-codoped "
          "Bi0.5Na0.5TiO3-based ceramics through defect-dipole design.")
    zh = ("通过缺陷偶极子设计，研究者在Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3 "
          "陶瓷上获得了 8.3 J/cm3。")
    k_en = _claim_dedup_key(en)
    k_zh = _claim_dedup_key(zh)
    # Both should be anchor-based ("8.3" matches the value regex) OR
    # distinct-token based — either way the key must match.
    assert k_en == k_zh, f"expected dedup; got {k_en!r} vs {k_zh!r}"


def test_anchor_value_regex_expanded_units():
    """M2: value-anchor regex was missing common units (mC/cm², GPa,
    bare J/cm) → claims fell to prefix-key per language and didn't dedup."""
    from stages.s08_section_compose.structured import _claim_anchors
    # bare J/cm (no superscript) was previously missed
    assert "8.3" in _claim_anchors("Tang et al. reported 8.3 J/cm.")
    # mC/cm² was missed
    assert "12.5" in _claim_anchors("Zhang et al. showed 12.5 mC/cm²")
    # GPa was missed
    assert "5" in _claim_anchors("Li 等人 测得 5 GPa")


def test_anchor_author_loose_whitespace():
    """M2: Chinese 'Tang等人' (no space) was missed; loosened to \\s*."""
    from stages.s08_section_compose.structured import _claim_anchors
    assert "Tang" in _claim_anchors("Tang等人提出了一种新材料")
    assert "Tang" in _claim_anchors("Tang 等人提出了一种新材料")
    assert "Tang" in _claim_anchors("Tang et al. proposed")


def test_author_chunk_advisory_default(monkeypatch):
    """v1.11.1 Bug #3: by default, a claim attributing work to an author
    whose surname doesn't appear in any cited chunk is recorded as advisory
    (kept in accepted) — captures the meng2024 ch13 'Cao 等人' case for
    review without dropping content."""
    monkeypatch.delenv("LAZY_PAPER_AUTHOR_HARDREJECT", raising=False)
    chunks = {0: Chunk(id="c0", text="Ma et al. reported W_rec=7.5 J/cm³",
                       doc_name="d", char_start=0, char_end=40)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Cao 等人 report W_rec=2.20", cited_chunk_ids=[0],
                      cited_quote="Ma et al. reported"),
        GroundedClaim(text="Ma et al. report W_rec=7.5", cited_chunk_ids=[0],
                      cited_quote="Ma et al. reported"),
    ])
    accepted, rejected = verify_section_draft(draft, chunks, ratio_threshold=0.85)
    advisory = [r for r in rejected
                if r.get("reason") == "author_not_in_chunk_advisory"]
    assert len(advisory) == 1
    assert advisory[0]["missing_authors"] == ["cao"]
    # Both claims remain accepted under advisory mode (telemetry, not block)
    assert len(accepted) == 2


def test_author_chunk_hardreject_when_env_set(monkeypatch):
    """LAZY_PAPER_AUTHOR_HARDREJECT=1 promotes the advisory to a hard
    rejection — claim is dropped from `accepted`."""
    monkeypatch.setenv("LAZY_PAPER_AUTHOR_HARDREJECT", "1")
    chunks = {0: Chunk(id="c0", text="Ma et al. reported W_rec=7.5",
                       doc_name="d", char_start=0, char_end=30)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Cao 等人 report W_rec=2.20", cited_chunk_ids=[0],
                      cited_quote="Ma et al. reported"),
        GroundedClaim(text="Ma et al. report W_rec=7.5", cited_chunk_ids=[0],
                      cited_quote="Ma et al. reported"),
    ])
    accepted, rejected = verify_section_draft(draft, chunks, ratio_threshold=0.85)
    hard = [r for r in rejected if r.get("reason") == "author_not_in_chunk"]
    assert len(hard) == 1
    accepted_texts = [c.text for c in accepted]
    assert "Cao 等人 report W_rec=2.20" not in accepted_texts
    assert "Ma et al. report W_rec=7.5" in accepted_texts


def test_author_chunk_passes_when_surname_in_chunk(monkeypatch):
    """A claim mentioning an author whose name DOES appear in a cited
    chunk must not be flagged — guards against false positives."""
    monkeypatch.delenv("LAZY_PAPER_AUTHOR_HARDREJECT", raising=False)
    chunks = {0: Chunk(id="c0", text="As Smith et al. reported in [12], the W_rec is 5.0",
                       doc_name="d", char_start=0, char_end=60)}
    draft = SectionDraft(claims=[
        GroundedClaim(text="Smith et al. found W_rec=5.0", cited_chunk_ids=[0],
                      cited_quote="Smith et al. reported"),
        GroundedClaim(text="A claim with no author mention.", cited_chunk_ids=[0],
                      cited_quote="reported in"),
    ])
    accepted, rejected = verify_section_draft(draft, chunks, ratio_threshold=0.85)
    assert not any(r.get("reason", "").startswith("author_not_in_chunk")
                   for r in rejected)
    assert len(accepted) == 2


def test_dedup_anchors_unit_aware_no_false_collision():
    """Cycle 5 A3: same author + same number but different unit must
    NOT collide (e.g., 'Li 5 GPa' fracture vs 'Li 5 J/cm³' energy)."""
    from stages.s08_section_compose.structured import _claim_dedup_key
    fracture = "Li et al. achieved 5 GPa fracture toughness in this work."
    energy = "Li et al. demonstrated 5 J/cm³ energy density in BST."
    k1 = _claim_dedup_key(fracture)
    k2 = _claim_dedup_key(energy)
    assert k1 != k2, f"unit-aware dedup failed: both keys = {k1!r}"


def test_claim_anchors_returns_value_only_for_verifier():
    """Verifier checks anchor-in-quote substring. The anchor must be
    the bare value (no unit) — quotes don't always carry unit verbatim."""
    from stages.s08_section_compose.structured import _claim_anchors
    anchors = _claim_anchors("Jiang et al. reported 2.94 J/cm³ value.")
    # bare value, not "2.94J/cm³" — verifier will substring-match "2.94"
    # against quote even when quote lacks the unit.
    assert "2.94" in anchors
    assert "Jiang" in anchors


def test_dedup_anchors_unicode_unit_normalized():
    """Meta-Auditor M1 D3: '5 J/cm³' (Unicode super) and '5 J/cm3' (ASCII)
    must collapse — they're the same fact, just different rendering."""
    from stages.s08_section_compose.structured import _claim_dedup_key
    a = "Tang et al. demonstrated 5 J/cm³ energy density."
    b = "Tang et al. demonstrated 5 J/cm3 energy density."
    assert _claim_dedup_key(a) == _claim_dedup_key(b)


def test_verify_truncates_oos_claims_chapter_level(monkeypatch):
    """Parallel B v1.11: chapter-level OOS cap. ANY claim firing OOS
    opener triggers truncation of WHOLE chapter to first 3 claims,
    even if subsequent claims don't match opener regex (real hif_2
    ch04 had 1 opener + 11 off-topic descriptive claims). Claim-
    level cap would only catch the 1 opener; chapter-level catches all."""
    # v1.12 phase 2: this test predates anchored-quote enforcement. Its OOS
    # claim fixtures happen to contain value anchors (e.g. "48.9%") which
    # would now be rejected by the empty-quote anchor check, masking the
    # OOS-overflow behaviour this test actually exercises. Opt out of the
    # phase-2 reject so the original OOS-overflow assertion remains valid.
    monkeypatch.setenv("LAZY_PAPER_ANCHORED_QUOTE", "0")
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
    )
    from llm.retriever import Chunk
    claims = [
        # 1 OOS opener
        GroundedClaim(
            text="源论文未涉及弛豫反铁电体，专注于 unCLIP 模型。",
            cited_chunk_ids=[0], cited_quote="",
        ),
        # 4 off-topic descriptive (NOT matching opener regex)
        GroundedClaim(
            text="unCLIP 由先验网络和解码器网络组成。",
            cited_chunk_ids=[0], cited_quote="",
        ),
        GroundedClaim(
            text="扩散先验在光真实感上达到 48.9%。",
            cited_chunk_ids=[0], cited_quote="",
        ),
        GroundedClaim(
            text="自回归先验对应值为 47.1%。",
            cited_chunk_ids=[0], cited_quote="",
        ),
        GroundedClaim(
            text="多样性指标 70.5% 远高于 GLIDE。",
            cited_chunk_ids=[0], cited_quote="",
        ),
    ]
    draft = SectionDraft(claims=claims)
    chunks_by_id = {0: Chunk(id="c0", text="dummy",
                              doc_name="d", char_start=0, char_end=5)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id)
    assert len(accepted) == 3  # capped chapter-wide
    overflow_rejects = [r for r in rejected
                        if r.get("reason") == "oos_chapter_overflow"]
    assert len(overflow_rejects) == 2


def test_oos_cap_not_triggered_for_normal_chapter():
    """Negative: no OOS opener → no truncation."""
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
    )
    from llm.retriever import Chunk
    claims = [
        GroundedClaim(text=f"Normal claim {i}.",
                       cited_chunk_ids=[0], cited_quote="")
        for i in range(5)
    ]
    draft = SectionDraft(claims=claims)
    chunks_by_id = {0: Chunk(id="c0", text="dummy",
                              doc_name="d", char_start=0, char_end=5)}
    accepted, rejected = verify_section_draft(draft, chunks_by_id)
    assert len(accepted) == 5
    overflow_rejects = [r for r in rejected
                        if r.get("reason") == "oos_chapter_overflow"]
    assert overflow_rejects == []


def test_format_section_figures_block_includes_deep_obs():
    """Parallel C v1.11 fix: figures block must pass visual_summary +
    deep_observation to LLM, not just caption[:140]. Was the v1.6
    silent regression that left figure-content in YAML 'sleeping'."""
    from stages.s08_section_compose.structured import _format_section_figures_block
    notes = [{
        "fig_id": "Fig. 3",
        "caption": "P-E loops at 25 °C, 100 °C and 200 °C.",
        "visual_summary": "Three nested loops in red/green/blue; vertical axis P (μC/cm²) -60 to 60; horizontal axis E (kV/cm) -200 to 200. All loops slim with low remnant polarization.",
        "deep_observation": "The temperature stability is demonstrated; W_rec degradation is 8% from 25 °C to 200 °C, suggesting PNR-pinning effect.",
    }]
    out = _format_section_figures_block(notes)
    assert "visual:" in out
    assert "observation:" in out
    assert "PNR" in out
    assert "W_rec" in out


def test_verify_results_section_thin_numerics_advisory():
    """Cycle 6 P0: results-class section with no numeric anchors flagged
    (advisory only — claims still accepted). meng2024 ch07 / ali2025 ch07
    were missing main metrics like 'W_rec=5.00 J/cm³'."""
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
    )
    from llm.retriever import Chunk
    # 3 claims, no numeric anchors — advisory should fire
    claims = [
        GroundedClaim(text=f"Generic application claim {i} without metrics.",
                       cited_chunk_ids=[0], cited_quote="")
        for i in range(3)
    ]
    draft = SectionDraft(claims=claims)
    chunks_by_id = {0: Chunk(id="c0", text="dummy",
                              doc_name="d", char_start=0, char_end=5)}
    accepted, rejected = verify_section_draft(
        draft, chunks_by_id, section_title="07-Applications_of_Relaxor_AFEs",
    )
    assert len(accepted) == 3  # all kept
    thin_advisories = [r for r in rejected
                       if r.get("reason") == "results_section_thin_numerics"]
    assert len(thin_advisories) == 1


def test_verify_non_results_section_skips_numerics_advisory():
    """Non-results section title should NOT trigger thin-numerics advisory."""
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
    )
    from llm.retriever import Chunk
    claims = [
        GroundedClaim(text=f"Introduction claim {i}.",
                       cited_chunk_ids=[0], cited_quote="")
        for i in range(3)
    ]
    draft = SectionDraft(claims=claims)
    chunks_by_id = {0: Chunk(id="c0", text="dummy",
                              doc_name="d", char_start=0, char_end=5)}
    _, rejected = verify_section_draft(
        draft, chunks_by_id, section_title="01-Introduction",
    )
    thin_advisories = [r for r in rejected
                       if r.get("reason") == "results_section_thin_numerics"]
    assert thin_advisories == []


# v1.11 architecture-review CUT: cross-citation reject + helper deleted
# (40 LOC defensive code for 1 paper's case; defer to v1.12 with proper
# reference-list orthogonal check). Tests removed accordingly.


def test_oos_regex_matches_chinese_本论文_variant():
    """Bug B (Cycle 10): _OOS_CLAIM_RE was missing 本论文/本研究 + 并非
    variants. hif_2 ch04 opener '本论文并非研究弛豫反铁电体' was missed
    → 48 chapters had unbounded OOS overflow."""
    from stages.s08_section_compose.structured import _OOS_CLAIM_RE
    assert _OOS_CLAIM_RE.search("本论文并非研究弛豫反铁电体")
    assert _OOS_CLAIM_RE.search("本研究并不涉及材料学")
    assert _OOS_CLAIM_RE.search("该研究并未涵盖该课题")
    # existing variants still work
    assert _OOS_CLAIM_RE.search("源论文未涉及该主题")
    assert _OOS_CLAIM_RE.search("the source paper does not cover")
    # normal claim not matched
    assert not _OOS_CLAIM_RE.search("Tang et al. demonstrated 8.3 J/cm³.")


def test_unknown_figure_label_lang_aware(monkeypatch):
    """Hardcode #4 (Cycle 10): 'verifier replacement text is now
    lang-aware via LOCALES, no Chinese leak in --lang en runs."""
    from stages.s08_section_compose.structured import (
        verify_section_draft, GroundedClaim, SectionDraft,
        UNKNOWN_FIGURE_LABEL,
    )
    from llm.retriever import Chunk
    monkeypatch.delenv("LAZY_PAPER_FIGURE_ID_WHITELIST", raising=False)
    draft = SectionDraft(claims=[
        GroundedClaim(
            text="As shown in Fig. 9 the result holds.",
            cited_chunk_ids=[0], cited_quote="content",
            figure_ids=["Fig. 9"],
        ),
        GroundedClaim(
            text="Another supporting claim.",
            cited_chunk_ids=[0], cited_quote="content here",
        ),
    ])
    chunks_by_id = {0: Chunk(id="c0", text="content here",
                              doc_name="d", char_start=0, char_end=12)}
    # English run: substitution text must be the EN locale string
    accepted, _ = verify_section_draft(
        draft, chunks_by_id, ratio_threshold=0.85,
        available_fig_ids={"Fig. 1"}, lang="en",
    )
    assert UNKNOWN_FIGURE_LABEL["en"] in accepted[0].text
    assert "源论文相关图示" not in accepted[0].text
