from pathlib import Path
from unittest.mock import patch

import pytest

from llm.template_author import prescan_run, prescan_pdf
from stages._common import dump_yaml


def _make_run(tmp_path: Path) -> Path:
    run = tmp_path / "runs" / "demo-paper"
    (run / "s02_clean").mkdir(parents=True)
    (run / "s02_clean" / "doc_0.md").write_text(
        "Adaptive Energy Regularization\n\nAbstract — We propose an adaptive "
        "energy term E_t that scales with velocity.", encoding="utf-8")
    (run / "s03_chapter").mkdir()
    dump_yaml(run / "s03_chapter" / "chapter_index.yaml",
              {"chapters": [{"num": 0, "slug": "intro", "title": "INTRODUCTION"},
                            {"num": 1, "slug": "method", "title": "ENERGY REGULARIZATION"}]})
    (run / "s04_figures").mkdir()
    dump_yaml(run / "s04_figures" / "figures.yaml",
              [{"fig_id": "Fig. 1", "caption": "Gait transition vs commanded velocity."}])
    (run / "s06_context").mkdir()
    dump_yaml(run / "s06_context" / "context.yaml",
              {"title": "Adaptive Energy Regularization",
               "keywords": ["energy", "gait"],
               "critical_questions": ["How does E_t scale?"]})
    return run


def test_prescan_run_includes_all_sources(tmp_path: Path):
    run = _make_run(tmp_path)
    digest = prescan_run(run)
    assert "Adaptive Energy Regularization" in digest      # context title
    assert "ENERGY REGULARIZATION" in digest               # chapter title
    assert "Gait transition vs commanded velocity" in digest  # caption
    assert "adaptive" in digest or "Abstract" in digest    # s02 head text


def test_prescan_run_partial_artifacts(tmp_path: Path):
    run = tmp_path / "runs" / "bare"
    (run / "s02_clean").mkdir(parents=True)
    (run / "s02_clean" / "doc_0.md").write_text("Only OCR text here.", encoding="utf-8")
    digest = prescan_run(run)
    assert "Only OCR text here." in digest


def test_prescan_run_nothing_usable(tmp_path: Path):
    run = tmp_path / "runs" / "empty"
    run.mkdir(parents=True)
    with pytest.raises(SystemExit, match="prescan"):
        prescan_run(run)


def test_prescan_pdf_reads_first_pages(tmp_path: Path):
    class FakePage:
        def __init__(self, text): self._t = text
        def extract_text(self): return self._t

    class FakePDF:
        pages = [FakePage("Page one title"), FakePage("Page two"), FakePage(None)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("pdfplumber.open", return_value=FakePDF()):
        digest = prescan_pdf(Path("whatever.pdf"))
    assert "Page one title" in digest and "Page two" in digest
