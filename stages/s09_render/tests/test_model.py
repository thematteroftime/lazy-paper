from pathlib import Path

import pytest

from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock,
)


def test_paragraph_is_frozen():
    p = Paragraph(text="hello")
    with pytest.raises(Exception):  # FrozenInstanceError
        p.text = "world"  # type: ignore[misc]


def test_figure_block_is_frozen_and_holds_image_paths():
    fb = FigureBlock(
        fig_id="Fig. 1", label="图 1",
        image_paths=(Path("/a/b.jpg"),),
        caption="cap", deep_observation="obs",
    )
    assert fb.fig_id == "Fig. 1"
    assert fb.label == "图 1"
    assert fb.image_paths == (Path("/a/b.jpg"),)
    with pytest.raises(Exception):
        fb.caption = "new"  # type: ignore[misc]


def test_chapter_groups_blocks_in_order():
    p = Paragraph(text="intro text")
    fb = FigureBlock(fig_id="Fig. 1", label="Fig. 1",
                     image_paths=(), caption="", deep_observation="")
    ch = Chapter(heading="Introduction", level=1, blocks=(p, fb))
    assert ch.blocks[0] is p
    assert ch.blocks[1] is fb


def test_document_holds_chapters_and_metadata():
    doc = Document(paper_title="My Paper", lang="zh", chapters=())
    assert doc.paper_title == "My Paper"
    assert doc.lang == "zh"
    assert doc.chapters == ()
