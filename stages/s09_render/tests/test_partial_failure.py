from pathlib import Path
from unittest.mock import patch

import yaml
from PIL import Image

from stages.s09_render.runner import run


def _seed(compose: Path, fig_dir: Path):
    (compose / "chapters").mkdir(parents=True)
    (compose / "chapters" / "01.md").write_text("# C\n\nbody\n", encoding="utf-8")
    fig_dir.mkdir()
    (fig_dir / "fig_notes.yaml").write_text("[]", encoding="utf-8")


def test_one_format_failure_does_not_block_others(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)

    # Make PdfRenderer.render raise, leave docx/html intact.
    with patch("stages.s09_render.renderers.pdf.PdfRenderer.render",
               side_effect=RuntimeError("pdf broken")):
        result = run(
            compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
            paper_title="t", lang="en",
            formats=["docx", "pdf", "html"],
        )

    assert (out_dir / "preview.docx").exists()
    assert (out_dir / "preview.html").exists()
    assert not (out_dir / "preview.pdf").exists()

    done = yaml.safe_load((out_dir / "done.yaml").read_text(encoding="utf-8"))
    assert done["partial"] is True
    assert "error" in done["formats"]["pdf"]
    assert done["formats"]["docx"].endswith("preview.docx")
    assert done["formats"]["html"].endswith("preview.html")
    assert result["partial"] is True


def test_all_formats_succeed_means_partial_is_false(tmp_path: Path):
    compose = tmp_path / "compose"
    fig_dir = tmp_path / "fig"
    out_dir = tmp_path / "out"
    _seed(compose, fig_dir)
    run(compose_dir=compose, fig_notes_dir=fig_dir, out_dir=out_dir,
        paper_title="t", lang="en", formats=["docx", "html"])
    done = yaml.safe_load((out_dir / "done.yaml").read_text(encoding="utf-8"))
    assert done["partial"] is False
