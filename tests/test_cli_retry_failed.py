from pathlib import Path
from unittest.mock import patch

import yaml

from cli import main


def test_retry_failed_only_reruns_formats_marked_in_done_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PADDLEOCR_TOKEN", "fake")
    monkeypatch.setenv("LLM_VISION_API_KEY", "fake")
    monkeypatch.setenv("LLM_TEXT_API_KEY", "fake")

    runs = tmp_path / "runs"
    paper_dir = runs / "p" / "s09_render"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("done.yaml").write_text(
        yaml.safe_dump({
            "partial": True,
            "formats": {
                "docx": "/x/preview.docx",
                "pdf":  {"error": "weasyprint failed"},
                "html": "/x/preview.html",
            },
        }), encoding="utf-8",
    )

    pdf = tmp_path / "p.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    tpl = tmp_path / "t.docx"
    from docx import Document as DocxDocument
    DocxDocument().save(tpl)

    captured: dict = {}

    def fake_s09_run(**kwargs):
        captured.update(kwargs)
        (kwargs["out_dir"] / "done.yaml").write_text("ok\n", encoding="utf-8")
        return {}

    with patch("stages.s09_render.runner.run", side_effect=fake_s09_run):
        rc = main([
            "run", "--pdf", str(pdf), "--template", str(tpl),
            "--runs-dir", str(runs), "--paper-id", "p",
            "--only", "s09_render", "--retry-failed",
        ])

    assert rc == 0
    # Only the failed format(s) should have been requested
    assert captured.get("formats") == ["pdf"]
