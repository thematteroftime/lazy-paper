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

    # v11 two-pass: call order is outline FIRST, then chapter bullets, then paper summary.
    # Each must return a valid payload so the result is cached and the second run
    # makes zero additional LLM calls.
    outline_payload = json.dumps({
        "groups": [{"name": "All", "chapter_headings": ["Intro"], "takeaway": "Context."}]
    })
    chapter_payload = json.dumps({"bullets": ["a", "b"], "figure_one_liners": {}})
    paper_payload = json.dumps({
        "bullets": ["Key finding 1", "Key finding 2"],
        "takeaway": "Important work.",
    })

    _responses = iter([outline_payload, chapter_payload, paper_payload])

    def _next_response(*args, **kwargs):
        try:
            content = next(_responses)
        except StopIteration:
            # Fallback: return outline payload (shouldn't happen in a properly cached run)
            content = outline_payload
        return MagicMock(content=content, model="fake", usage={}, latency_ms=1.0)

    fake_llm = MagicMock()
    fake_llm.chat.side_effect = _next_response

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
