from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm.paper_kg import Entity, PaperKG


def _kg() -> PaperKG:
    return PaperKG(
        entities=[
            Entity(id="m1", type="material", text="NBT-BMZ",
                   source_span=("doc_1.md", 0, 7)),
        ],
        relations=[],
    )


def _mock_retriever():
    r = MagicMock()
    r.retrieve.return_value = [
        MagicMock(text="evidence chunk", to_dict=lambda: {"id": "c1",
                  "text": "evidence chunk", "doc_name": "doc_1.md",
                  "char_start": 0, "char_end": 14}),
    ]
    r.check_claim.return_value = {"found": True, "span": ("doc_1.md", 0, 14),
                                  "evidence": "evidence"}
    return r


def test_run_section_agent_emits_draft(tmp_path):
    from stages.s08_section_compose.agent import run_section_agent

    with patch("stages.s08_section_compose.agent.Agent") as MockAgent:
        agent = MockAgent.return_value
        agent.run_sync.return_value = MagicMock(
            output="Section draft with [span:doc_1.md:0-14] citation."
        )
        result = run_section_agent(
            section={"title": "Test", "guidance": "Discuss material."},
            kg=_kg(),
            retriever=_mock_retriever(),
            prior_bullet="",
            max_iters=3,
        )
    assert "[span:" in result


def test_emit_section_requires_citation():
    from stages.s08_section_compose.agent import _validate_emit
    with pytest.raises(ValueError):
        _validate_emit("No citation here.")
    # Has a citation:
    assert _validate_emit("Has [span:doc_1.md:0-5] citation.") is None
