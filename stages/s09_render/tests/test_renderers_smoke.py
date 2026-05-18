from pathlib import Path

import pytest
from docx import Document as DocxDocument
from PIL import Image

from stages.s09_render.model import Document, Chapter, Paragraph, FigureBlock
from stages.s09_render.renderers import RENDERERS
import stages.s09_render.renderers.docx  # noqa: F401 — triggers RENDERERS["docx"] registration
import stages.s09_render.renderers.html  # noqa: F401 — triggers RENDERERS["html"] registration


@pytest.fixture
def one_image(tmp_path: Path) -> Path:
    p = tmp_path / "tiny.jpg"
    Image.new("RGB", (100, 50), "red").save(p)
    return p


def _make_doc(one_image: Path) -> Document:
    return Document(
        paper_title="Smoke Test Paper",
        lang="zh",
        chapters=(
            Chapter(heading="引言", level=1, blocks=(
                Paragraph(text="这是引言的第一段。"),
                Paragraph(text="第二段提到 Fig. 1 的内容。"),
                FigureBlock(fig_id="Fig. 1", label="图 1",
                            image_paths=(one_image,),
                            caption="第一张图", deep_observation="观察"),
            )),
        ),
    )


def test_docx_renderer_produces_readable_file(tmp_path: Path, one_image: Path):
    doc = _make_doc(one_image)
    out = tmp_path / "preview.docx"
    RENDERERS["docx"]().render(doc, out)
    assert out.exists() and out.stat().st_size > 4000
    d = DocxDocument(out)
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Smoke Test Paper" in text
    assert "引言" in text
    assert "图 1. 第一张图" in text
    assert len(d.inline_shapes) == 1


def test_html_renderer_self_contained_base64(tmp_path: Path, one_image: Path):
    doc = _make_doc(one_image)
    out = tmp_path / "preview.html"
    RENDERERS["html"]().render(doc, out)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "Smoke Test Paper" in html
    assert "引言" in html
    assert "图 1. 第一张图" in html
    # Base64 embedded image — no external file refs
    assert 'src="data:image/' in html
    assert 'src="/tmp' not in html  # absolute paths must NOT leak
