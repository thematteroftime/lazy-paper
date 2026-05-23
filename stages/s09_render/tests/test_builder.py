from pathlib import Path

from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.model import Document, Chapter, Paragraph, FigureBlock


def test_builder_splits_paragraphs_on_double_newline():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    doc = builder.build(chapters_md={"01-intro.md": "# Intro\n\nfirst para\n\nsecond para\n"},
                        fig_notes=[])
    assert len(doc.chapters) == 1
    ch = doc.chapters[0]
    assert ch.heading == "Intro"
    paragraphs = [b for b in ch.blocks if isinstance(b, Paragraph)]
    assert [p.text for p in paragraphs] == ["first para", "second para"]


def test_builder_untitled_fallback_localized():
    """v1.11.1: chapter without a leading `# Title` falls back to a
    language-aware string ('Untitled' for en, '未命名章节' for zh)."""
    builder_zh = DocumentBuilder(lang="zh", paper_title="t")
    doc_zh = builder_zh.build(chapters_md={"01.md": "no heading body\n"}, fig_notes=[])
    assert doc_zh.chapters[0].heading == "未命名章节"

    builder_en = DocumentBuilder(lang="en", paper_title="t")
    doc_en = builder_en.build(chapters_md={"01.md": "no heading body\n"}, fig_notes=[])
    assert doc_en.chapters[0].heading == "Untitled"


def test_builder_attaches_referenced_figures_by_english_id():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# C1\n\nbody mentions Fig. 1 here\n"},
        fig_notes=[{
            "fig_id": "Fig. 1",
            "image_abs_path": "/a/b.jpg",
            "caption": "the caption",
            "deep_observation": "the obs",
        }],
    )
    blocks = doc.chapters[0].blocks
    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert len(figures) == 1
    assert figures[0].fig_id == "Fig. 1"
    assert figures[0].label == "Fig. 1"   # English label unchanged
    assert figures[0].caption == "the caption"
    assert figures[0].image_paths == (Path("/a/b.jpg"),)


def test_builder_localizes_label_to_chinese_when_lang_zh():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# 一\n\n文中提到图1的内容\n"},
        fig_notes=[{"fig_id": "Fig. 1", "image_abs_path": "/a/b.jpg",
                    "caption": "标题", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs[0].label == "图 1"


def test_builder_matches_chinese_reference_with_or_without_space():
    builder = DocumentBuilder(lang="zh", paper_title="t")
    for ref in ("图5", "图 5"):
        doc = builder.build(
            chapters_md={"x.md": f"# X\n\n本段提到{ref}的结果\n"},
            fig_notes=[{"fig_id": "Fig. 5", "image_abs_path": "/p.jpg",
                        "caption": "c", "deep_observation": ""}],
        )
        figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
        assert len(figs) == 1, f"failed for ref={ref!r}"


def test_builder_only_embeds_figure_once_across_chapters():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={
            "01.md": "# A\n\nfirst mention of Fig. 1\n",
            "02.md": "# B\n\nsecond mention of Fig. 1 here too\n",
        },
        fig_notes=[{"fig_id": "Fig. 1", "image_abs_path": "/p.jpg",
                    "caption": "c", "deep_observation": ""}],
    )
    total_figs = sum(
        1 for ch in doc.chapters for b in ch.blocks if isinstance(b, FigureBlock)
    )
    assert total_figs == 1


def test_builder_uses_image_paths_when_present_else_image_abs_path():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# X\n\nFig. 1 multi panel here\n"},
        fig_notes=[{"fig_id": "Fig. 1",
                    "image_paths": ["/a.jpg", "/b.jpg"],
                    "image_abs_path": "/c.jpg",
                    "caption": "x", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs[0].image_paths == (Path("/a.jpg"), Path("/b.jpg"))


def test_builder_drops_figure_with_no_image_paths():
    builder = DocumentBuilder(lang="en", paper_title="t")
    doc = builder.build(
        chapters_md={"01.md": "# X\n\nFig. 99 has no image\n"},
        fig_notes=[{"fig_id": "Fig. 99", "image_paths": [], "image_abs_path": "",
                    "caption": "x", "deep_observation": ""}],
    )
    figs = [b for b in doc.chapters[0].blocks if isinstance(b, FigureBlock)]
    assert figs == []
