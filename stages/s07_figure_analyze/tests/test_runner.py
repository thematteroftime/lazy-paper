from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from stages.s07_figure_analyze.runner import run


def test_run_per_figure_writes_notes(tmp_path: Path):
    figs_dir = tmp_path / "figs"; figs_dir.mkdir()
    (figs_dir / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 1", "image_rel_path": "imgs/a.jpg",
         "image_abs_path": str(figs_dir / "a.jpg"), "caption": "phase diagram",
         "source_doc": "doc_0.md"},
    ], allow_unicode=True), encoding="utf-8")
    (figs_dir / "mentions.yaml").write_text(yaml.safe_dump({
        "chapter_003_Results.md": ["Fig. 1"],
    }, allow_unicode=True), encoding="utf-8")
    (figs_dir / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    (chapters_dir / "chapter_003_Results.md").write_text(
        "Fig. 1 shows the phase diagram.\n", encoding="utf-8"
    )

    context_dir = tmp_path / "ctx"; context_dir.mkdir()
    (context_dir / "context.yaml").write_text(
        "title: test\nsystem: X\nkey_terms: [a]\n", encoding="utf-8"
    )

    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content=(
            "fig_id: Fig. 1\n"
            "visual_summary: bar chart\n"
            "text_claim_check:\n"
            "  - {claim: x, verdict: supported, note: ok}\n"
            "deep_observation: 深度观察\n"
            "caption: 图1\n"
        ),
        usage={"total_tokens": 200},
        model="qwen-vl",
        latency_ms=1000.0,
    )
    with patch("stages.s07_figure_analyze.runner.LLM", return_value=fake_llm):
        run(figures_dir=figs_dir, chapters_dir=chapters_dir,
            context_dir=context_dir, out_dir=out_dir)

    notes = yaml.safe_load((out_dir / "fig_notes.yaml").read_text(encoding="utf-8"))
    assert notes[0]["fig_id"] == "Fig. 1"
    assert notes[0]["caption"] == "图1"
    assert (out_dir / "Fig_1.prompt.md").exists()
    assert (out_dir / "Fig_1.response.json").exists()


def test_run_multi_panel_grouping(tmp_path: Path):
    """Two figures.yaml entries with the same fig_id are sent in one LLM call."""
    figs_dir = tmp_path / "figs"; figs_dir.mkdir()
    panel_a = figs_dir / "a.jpg"; panel_a.write_bytes(b"\xff\xd8\xff\xe0")
    panel_b = figs_dir / "b.jpg"; panel_b.write_bytes(b"\xff\xd8\xff\xe0")
    import yaml
    (figs_dir / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 1", "image_rel_path": "a.jpg",
         "image_abs_path": str(panel_a), "caption": "phase diagram",
         "source_doc": "doc_0.md"},
        {"fig_id": "Fig. 1", "image_rel_path": "b.jpg",
         "image_abs_path": str(panel_b), "caption": "phase diagram",
         "source_doc": "doc_0.md"},
    ], allow_unicode=True), encoding="utf-8")
    (figs_dir / "mentions.yaml").write_text(yaml.safe_dump({}, allow_unicode=True), encoding="utf-8")

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    context_dir = tmp_path / "ctx"; context_dir.mkdir()
    (context_dir / "context.yaml").write_text("title: test\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content=(
            "fig_id: Fig. 1\n"
            "visual_summary: combined view\n"
            "text_claim_check: []\n"
            "deep_observation: ok\n"
            "caption: 图1\n"
        ),
        usage={"total_tokens": 100}, model="qwen-vl", latency_ms=200.0,
    )
    with patch("stages.s07_figure_analyze.runner.LLM", return_value=fake_llm):
        run(figures_dir=figs_dir, chapters_dir=chapters_dir,
            context_dir=context_dir, out_dir=out_dir)
    # Verify LLM was called with BOTH images
    chat_kwargs = fake_llm.chat.call_args.kwargs
    assert len(chat_kwargs["images"]) == 2, chat_kwargs
    # fig_notes contains one entry with both image_paths
    import yaml
    notes = yaml.safe_load((out_dir / "fig_notes.yaml").read_text(encoding="utf-8"))
    assert len(notes) == 1
    assert len(notes[0]["image_paths"]) == 2


def test_generation_prompt_caption_skips_llm(tmp_path: Path):
    """v1.11.1 Bug #4 Layer B: figures.yaml entries with CLIP-style
    captions (e.g. hif_2 Fig. 43 dog photo) bypass the vision LLM
    so they don't reach s08 prompts and pollute the chapters."""
    figs_dir = tmp_path / "figs"; figs_dir.mkdir()
    real = figs_dir / "real.jpg"; real.write_bytes(b"\xff\xd8\xff\xe0")
    stub = figs_dir / "stub.jpg"; stub.write_bytes(b"\xff\xd8\xff\xe0")
    (figs_dir / "figures.yaml").write_text(yaml.safe_dump([
        {"fig_id": "Fig. 1", "image_rel_path": "real.jpg",
         "image_abs_path": str(real), "caption": "P-E hysteresis loops",
         "source_doc": "doc_0.md"},
        {"fig_id": "Fig. 43", "image_rel_path": "stub.jpg",
         "image_abs_path": str(stub),
         "caption": "(a) A high quality photo of a dog playing in a green field.",
         "source_doc": "doc_0.md"},
    ], allow_unicode=True), encoding="utf-8")
    (figs_dir / "mentions.yaml").write_text(yaml.safe_dump({}, allow_unicode=True), encoding="utf-8")
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    context_dir = tmp_path / "ctx"; context_dir.mkdir()
    (context_dir / "context.yaml").write_text("title: t\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    fake_llm = MagicMock()
    fake_llm.chat.return_value = MagicMock(
        content="fig_id: Fig. 1\nvisual_summary: x\ntext_claim_check: []\ndeep_observation: x\ncaption: x\n",
        usage={"total_tokens": 50}, model="qwen-vl", latency_ms=10.0,
    )
    with patch("stages.s07_figure_analyze.runner.LLM", return_value=fake_llm):
        run(figures_dir=figs_dir, chapters_dir=chapters_dir,
            context_dir=context_dir, out_dir=out_dir)

    assert fake_llm.chat.call_count == 1, "Fig. 43 must skip the LLM"
    notes = yaml.safe_load((out_dir / "fig_notes.yaml").read_text(encoding="utf-8"))
    fids = {n.get("fig_id") for n in notes}
    assert "Fig. 1" in fids
    assert "Fig. 43" not in fids, f"generation-prompt fig must be skipped; got {fids}"
