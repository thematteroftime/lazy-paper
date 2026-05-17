from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s06_context.runner import run


def test_run_writes_context_yaml(tmp_path: Path):
    chapters = tmp_path / "ch"; chapters.mkdir()
    (chapters / "chapter_000_Preface.md").write_text(
        "Abstract\nWe study ANT-xLa.\n", encoding="utf-8"
    )
    (chapters / "chapter_001_Introduction.md").write_text(
        "1. Introduction\nThis paper is about ANT-xLa, a relaxor antiferroelectric.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content="title: ANT-xLa\nsystem: Ag(1-3x)LaxNb(0.9)Ta(0.1)O3\nabbreviations:\n  - {abbr: ANT, expansion: AgNbTaO3}\nkey_terms: [CAFE]\nkeywords: [antiferroelectric, lead-free]\ncritical_questions: [What is CAFE?]\n",
        usage={"total_tokens": 100},
        model="deepseek-chat",
        latency_ms=500.0,
    )
    with patch("stages.s06_context.runner.LLM", return_value=fake_llm):
        run(chapters_dir=chapters, out_dir=out_dir)

    data = yaml.safe_load((out_dir / "context.yaml").read_text(encoding="utf-8"))
    assert data["title"] == "ANT-xLa"
    assert data["system"].startswith("Ag")
    # Prompt + response are persisted for audit
    assert (out_dir / "paper_context.prompt.md").exists()
    assert (out_dir / "paper_context.response.json").exists()
