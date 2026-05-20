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
