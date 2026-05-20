from llm.paper_kg import Entity, PaperKG
from stages.s08_section_compose.reviewer import Flag, regex_check


def _kg(*entities: Entity) -> PaperKG:
    return PaperKG(entities=list(entities), relations=[])


def test_numeric_in_source_no_flag():
    draft = "The breakdown field E_b reaches 348 kV/cm."
    source = {"doc_1.md": "E_b = 348 kV/cm in this sample"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    assert flags == []


def test_numeric_drift_flagged():
    draft = "E_b reaches 340 kV/cm."
    source = {"doc_1.md": "E_b = 348 kV/cm"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    assert any(f.problem == "numeric_not_in_source" for f in flags)


def test_unit_mismatch_normalized():
    draft = "Field of 4 MV/cm achieved."
    source = {"doc_1.md": "applied 4000 kV/cm during test"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    # 4 MV/cm == 4000 kV/cm via _units.equal → no flag
    assert flags == []


def test_fig_not_in_yaml():
    draft = "As shown in Fig. 99, the curve rises."
    source = {"doc_1.md": ""}
    flags = regex_check(draft, source, kg=_kg(),
                       fig_yaml=[{"fig_id": "Fig. 1"}, {"fig_id": "Fig. 2"}])
    assert any(f.problem == "fig_not_in_yaml" for f in flags)


def test_fig_in_yaml_no_flag():
    draft = "See Fig. 2 for details."
    source = {"doc_1.md": ""}
    flags = regex_check(draft, source, kg=_kg(),
                       fig_yaml=[{"fig_id": "Fig. 1"}, {"fig_id": "Fig. 2"}])
    assert flags == []


def test_formula_not_in_kg():
    draft = "The Vogel-Fulcher fit gave T_VF = 280 K."
    source = {"doc_1.md": ""}
    # KG has no Vogel-Fulcher entity
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    assert any(f.problem == "formula_not_in_kg" for f in flags)


def test_flag_has_evidence():
    draft = "E_b reaches 340 kV/cm."
    source = {"doc_1.md": "E_b = 348 kV/cm"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    assert flags
    assert flags[0].evidence is not None
    assert "348" in flags[0].evidence


from unittest.mock import MagicMock, patch
from stages.s08_section_compose.reviewer import (
    CritiqueRevision, llm_review, Flag,
)


def test_llm_review_returns_pydantic_object():
    flags = [Flag(span=(0, 10), claim="340 kV/cm", problem="numeric_not_in_source")]
    fake = CritiqueRevision(
        revised_draft="E_b reaches 348 kV/cm (per source).",
        quote_fidelity=4, grounding=4, synthesis_depth=3,
        notes="Corrected drift",
    )
    with patch("stages.s08_section_compose.reviewer._llm_review_call",
               return_value=fake):
        result = llm_review("E_b reaches 340 kV/cm.", flags, evidence="348 kV/cm in source")
    assert result.revised_draft.startswith("E_b reaches 348")
    assert 1 <= result.quote_fidelity <= 4


def test_llm_review_score_validation():
    import pytest
    with pytest.raises(Exception):
        CritiqueRevision(
            revised_draft="x",
            quote_fidelity=5,  # out of range
            grounding=4, synthesis_depth=3, notes="",
        )


# v1.4 live-run hardening: regression tests for false-positive critic flags.

def test_compound_unit_not_flagged_as_bare():
    """1000 °C in draft is OK when source has 1000 °C/s (the rate)."""
    draft = "Heating rate reached 1000 °C/s during flash annealing."
    source = {"doc_1.md": "achieved 1000 °C/s heating rate"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    # neither side should produce a bare "1000 °C" match
    assert all(f.claim != "1000 °C" for f in flags), \
        f"compound unit °C/s should not match bare °C: {flags}"


def test_ocr_spaced_number_matched_in_source():
    """Source has '0 . 0 3 6 %' (OCR artifact); draft has '0.036 %' — must match."""
    draft = "Microscopic strain ε = 0.036 %."
    source = {"doc_1.md": "strain values: $0 . 0 3 6 \\%$ for CA process"}
    flags = regex_check(draft, source, kg=_kg(), fig_yaml=[])
    assert flags == [], f"OCR-spaced source should match: {flags}"
