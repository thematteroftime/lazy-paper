from pathlib import Path

from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock,
)
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner


def _doc(blocks_per_chapter=2, n_chapters=2, with_figure=True) -> Document:
    chapters = []
    for i in range(n_chapters):
        blocks = [Paragraph(text=f"Para {j} of chapter {i}.") for j in range(blocks_per_chapter)]
        if with_figure:
            blocks.append(FigureBlock(
                fig_id=f"Fig. {i+1}", label=f"Fig. {i+1}",
                image_paths=(Path(f"/tmp/img{i}.jpg"),),
                caption=f"caption {i}", deep_observation=f"deep obs {i}",
            ))
        chapters.append(Chapter(heading=f"Ch{i+1}", level=1, blocks=tuple(blocks)))
    return Document(paper_title="P", lang="en", chapters=tuple(chapters))


def test_planner_starts_with_title_then_outline():
    deck = SlidePlanner(lang="en").plan(_doc(), summaries=None)
    assert deck.slides[0].kind == "title"
    assert deck.slides[0].title == "P"
    assert deck.slides[1].kind == "outline"
    assert "Ch1" in deck.slides[1].bullets
    assert "Ch2" in deck.slides[1].bullets


def test_planner_ends_with_closing_slide():
    deck = SlidePlanner(lang="en").plan(_doc(), summaries=None)
    assert deck.slides[-1].kind == "closing"


def test_planner_inserts_divider_only_when_chapter_has_enough_content():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=False)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    kinds = [s.kind for s in deck.slides]
    assert "divider" in kinds   # 2 paragraphs ≥ threshold

    doc1 = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=False)
    deck1 = SlidePlanner(lang="en").plan(doc1, summaries=None)
    kinds1 = [s.kind for s in deck1.slides]
    assert "divider" not in kinds1


def test_planner_emits_one_figure_slide_per_figure_block():
    doc = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=True)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    fig_slides = [s for s in deck.slides if s.kind == "figure"]
    assert len(fig_slides) == 1
    assert fig_slides[0].caption == "caption 0"
    # Without LLM summaries we fall back to using deep_observation verbatim.
    assert "deep obs 0" in fig_slides[0].deep_observation


def test_planner_bullets_capped_at_max_per_slide():
    doc = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Long", level=1, blocks=tuple(
            Paragraph(text=f"sentence {i}.") for i in range(20)
        )),
    ))
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    bullet_slides = [s for s in deck.slides if s.kind == "bullets"]
    assert all(len(s.bullets) <= SlidePlanner.MAX_BULLETS_PER_SLIDE for s in bullet_slides)


def test_planner_uses_summaries_when_provided():
    doc = _doc(blocks_per_chapter=1, n_chapters=1, with_figure=True)
    summaries = {
        "Ch1": {
            "bullets": ["llm bullet a", "llm bullet b"],
            "figure_one_liners": {"Fig. 1": "one-liner from LLM"},
        }
    }
    deck = SlidePlanner(lang="en").plan(doc, summaries=summaries)
    bullets_slide = next(s for s in deck.slides if s.kind == "bullets")
    assert "llm bullet a" in bullets_slide.bullets
    fig_slide = next(s for s in deck.slides if s.kind == "figure")
    assert "one-liner from LLM" in fig_slide.deep_observation


def test_planner_attaches_paragraph_text_to_speaker_notes():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=False)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    bullets_slide = next(s for s in deck.slides if s.kind == "bullets")
    # Original paragraph text is preserved in notes for the speaker.
    assert "Para 0 of chapter 0." in bullets_slide.notes
