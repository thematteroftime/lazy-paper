import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from stages.s09_render.runner import run


def _seed(compose: Path, fig_dir: Path):
    (compose / "chapters").mkdir(parents=True)
    (compose / "chapters" / "01.md").write_text(
        "# Intro\n\nfirst para\n\nsecond para\n", encoding="utf-8")
    fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text("[]", encoding="utf-8")


def test_second_run_with_same_input_makes_zero_llm_calls(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content=json.dumps({"bullets": ["a", "b"], "figure_one_liners": {}}),
        model="fake", usage={}, latency_ms=1.0,
    )

    with patch("llm.client.LLM", return_value=fake_llm):
        run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en", formats=["pptx"], pptx_bullets="llm")
        first_calls = fake_llm.chat.call_count
        assert first_calls >= 1

        run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en", formats=["pptx"], pptx_bullets="llm")
        second_calls = fake_llm.chat.call_count
        assert second_calls == first_calls, \
            f"cache should have prevented new LLM calls (first={first_calls}, second={second_calls})"
