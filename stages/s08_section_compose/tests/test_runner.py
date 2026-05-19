from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s08_section_compose.runner import run


def test_run_writes_chapters(tmp_path: Path):
    tpl_dir = tmp_path / "tpl"; tpl_dir.mkdir()
    (tpl_dir / "template.yaml").write_text(yaml.safe_dump([
        {"level": 1, "number": "1", "title": "Introduction",
         "guidance": "why important", "hints": {"needs_table": False, "needs_figure": False},
         "children": []},
        {"level": 1, "number": "2", "title": "Structures",
         "guidance": "domain structures", "hints": {"needs_table": False, "needs_figure": True},
         "children": []},
    ], allow_unicode=True), encoding="utf-8")

    ctx_dir = tmp_path / "ctx"; ctx_dir.mkdir()
    (ctx_dir / "context.yaml").write_text("title: test\nsystem: X\n", encoding="utf-8")

    ch_dir = tmp_path / "ch"; ch_dir.mkdir()
    (ch_dir / "chapter_003_Results.md").write_text("domain micro-structure stuff", encoding="utf-8")

    fig_dir = tmp_path / "fig"; fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 4", "deep_observation": "畴", "caption": "TEM"},
    ], allow_unicode=True), encoding="utf-8")
    (fig_dir.parent / "figures_stage").mkdir()
    (fig_dir.parent / "figures_stage" / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 4", "caption": "TEM bright field", "image_abs_path": str(tmp_path / "a.jpg")}
    ], allow_unicode=True), encoding="utf-8")

    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content="本节正文 …",
        usage={"total_tokens": 50}, model="deepseek-chat", latency_ms=400.0,
    )
    with patch("stages.s08_section_compose.runner.LLM", return_value=fake_llm):
        run(template_dir=tpl_dir, chapters_dir=ch_dir, context_dir=ctx_dir,
            fig_notes_dir=fig_dir, figures_stage_dir=fig_dir.parent / "figures_stage",
            out_dir=out_dir)

    out_chapters = sorted((out_dir / "chapters").glob("*.md"))
    assert len(out_chapters) == 2
    assert out_chapters[0].read_text(encoding="utf-8").startswith("# Introduction")
    assert "本节正文" in out_chapters[0].read_text(encoding="utf-8")
