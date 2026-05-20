"""Tests: citation marker handling in DOCX and HTML renderers."""
from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document as DocxDocument

from llm.citation import CitationMode
from stages.s09_render.model import Chapter, Document, Paragraph
from stages.s09_render.renderers import RENDERERS
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401

MARKER_TEXT = "Some text [span:doc123:10-20] with a citation."
CLEAN_TEXT = "Some text  with a citation."


def _make_doc() -> Document:
    return Document(
        paper_title="Citation Test",
        lang="en",
        chapters=(
            Chapter(heading="Intro", level=1, blocks=(
                Paragraph(text=MARKER_TEXT),
            )),
        ),
    )


def test_docx_remove_strips_markers(tmp_path: Path):
    """Default REMOVE mode: [span:…] markers are absent in the rendered DOCX."""
    doc = _make_doc()
    out = tmp_path / "preview.docx"
    RENDERERS["docx"]().render(doc, out)
    d = DocxDocument(out)
    full_text = "\n".join(p.text for p in d.paragraphs)
    assert "[span:" not in full_text
    assert "Some text" in full_text


def test_docx_keep_preserves_markers(tmp_path: Path):
    """KEEP mode: [span:…] markers are preserved verbatim in the rendered DOCX."""
    doc = _make_doc()
    out = tmp_path / "preview.docx"
    RENDERERS["docx"](citation_mode=CitationMode.KEEP).render(doc, out)
    d = DocxDocument(out)
    full_text = "\n".join(p.text for p in d.paragraphs)
    assert "[span:doc123:10-20]" in full_text


def test_html_remove_strips_markers(tmp_path: Path):
    """Default REMOVE mode: [span:…] markers are absent in the rendered HTML."""
    doc = _make_doc()
    out = tmp_path / "preview.html"
    RENDERERS["html"]().render(doc, out)
    html = out.read_text(encoding="utf-8")
    assert "[span:" not in html
    assert "Some text" in html


def test_html_keep_preserves_markers(tmp_path: Path):
    """KEEP mode: [span:…] markers are preserved verbatim in the rendered HTML."""
    doc = _make_doc()
    out = tmp_path / "preview.html"
    RENDERERS["html"](citation_mode=CitationMode.KEEP).render(doc, out)
    html = out.read_text(encoding="utf-8")
    assert "[span:doc123:10-20]" in html
