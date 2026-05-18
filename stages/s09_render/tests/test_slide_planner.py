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


def test_planner_emits_one_content_slide_per_figure_block():
    """v6: when chapter has bullets+figure, planner emits 'combined' not 'figure'.
    When chapter has only a figure (no bullets), it emits 'figure'.
    In either case there should be exactly one content slide per figure block.
    """
    # Case 1: chapter has paragraphs + figure → combined slide
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=True)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    combined_slides = [s for s in deck.slides if s.kind == "combined"]
    figure_slides = [s for s in deck.slides if s.kind == "figure"]
    # With 2 paragraphs + 1 figure → 1 combined slide
    assert len(combined_slides) + len(figure_slides) == 1
    if combined_slides:
        assert combined_slides[0].caption == "caption 0"
        assert "deep obs 0" in combined_slides[0].deep_observation
    else:
        assert figure_slides[0].caption == "caption 0"
        assert "deep obs 0" in figure_slides[0].deep_observation

    # Case 2: figure-only chapter (no paragraphs) → figure slide
    doc_fig_only = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="FigOnly", level=1, blocks=(
            FigureBlock(
                fig_id="Fig. 1", label="Fig. 1",
                image_paths=(Path("/tmp/img.jpg"),),
                caption="solo caption", deep_observation="solo obs",
            ),
        )),
    ))
    deck2 = SlidePlanner(lang="en").plan(doc_fig_only, summaries=None)
    fig_slides2 = [s for s in deck2.slides if s.kind == "figure"]
    assert len(fig_slides2) == 1
    assert fig_slides2[0].caption == "solo caption"


def test_planner_combined_when_chapter_has_bullets_and_figures():
    """v6: chapter with both paragraphs and figures → combined slides, no separate bullets or figure slides."""
    doc = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Mixed", level=1, blocks=(
            Paragraph(text="First para."),
            Paragraph(text="Second para."),
            FigureBlock(
                fig_id="Fig. 1", label="Fig. 1",
                image_paths=(Path("/tmp/img1.jpg"),),
                caption="fig caption", deep_observation="fig obs",
            ),
        )),
    ))
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    combined = [s for s in deck.slides if s.kind == "combined"]
    bullets_slides = [s for s in deck.slides if s.kind == "bullets"]
    figure_slides = [s for s in deck.slides if s.kind == "figure"]

    assert len(combined) == 1, "Expected exactly 1 combined slide"
    assert len(bullets_slides) == 0, "No separate bullets slide expected"
    assert len(figure_slides) == 0, "No separate figure slide expected"
    assert combined[0].bullets, "Combined slide should have bullets"
    assert combined[0].image_paths, "Combined slide should have image paths"
    assert combined[0].caption == "fig caption"
    assert "fig obs" in combined[0].deep_observation


def test_planner_combined_distributes_bullets_across_multiple_figures():
    """v6: chapter with 6 bullets and 2 figures → 2 combined slides with distributed bullets."""
    doc = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Multi", level=1, blocks=(
            *(Paragraph(text=f"Sentence {i}.") for i in range(6)),
            FigureBlock(
                fig_id="Fig. 1", label="Fig. 1",
                image_paths=(Path("/tmp/img1.jpg"),),
                caption="cap1", deep_observation="obs1",
            ),
            FigureBlock(
                fig_id="Fig. 2", label="Fig. 2",
                image_paths=(Path("/tmp/img2.jpg"),),
                caption="cap2", deep_observation="obs2",
            ),
        )),
    ))
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    combined = [s for s in deck.slides if s.kind == "combined"]
    assert len(combined) == 2
    # First combined: Fig. 1
    assert combined[0].caption == "cap1"
    # Second combined: Fig. 2
    assert combined[1].caption == "cap2"
    # Each combined slide has some bullets
    assert all(len(s.bullets) > 0 for s in combined)


def test_planner_bullets_capped_at_max_per_slide():
    doc = Document(paper_title="P", lang="en", chapters=(
        Chapter(heading="Long", level=1, blocks=tuple(
            Paragraph(text=f"sentence {i}.") for i in range(20)
        )),
    ))
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    # In v6 with no figures, these become pure bullets slides
    bullet_slides = [s for s in deck.slides if s.kind == "bullets"]
    assert all(len(s.bullets) <= SlidePlanner.MAX_BULLETS_PER_SLIDE for s in bullet_slides)


def test_planner_uses_summaries_when_provided():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=True)
    summaries = {
        "Ch1": {
            "bullets": ["llm bullet a", "llm bullet b"],
            "figure_one_liners": {"Fig. 1": "one-liner from LLM"},
        }
    }
    deck = SlidePlanner(lang="en").plan(doc, summaries=summaries)
    # In v6, bullets+figure → combined slide
    combined = [s for s in deck.slides if s.kind == "combined"]
    bullets_slides = [s for s in deck.slides if s.kind == "bullets"]

    if combined:
        # bullets come from LLM summary
        assert "llm bullet a" in combined[0].bullets
        assert "one-liner from LLM" in combined[0].deep_observation
    else:
        # fallback: separate slides
        bs = next(s for s in bullets_slides)
        assert "llm bullet a" in bs.bullets
        fig_slide = next(s for s in deck.slides if s.kind == "figure")
        assert "one-liner from LLM" in fig_slide.deep_observation


def test_planner_attaches_paragraph_text_to_speaker_notes():
    doc = _doc(blocks_per_chapter=2, n_chapters=1, with_figure=False)
    deck = SlidePlanner(lang="en").plan(doc, summaries=None)
    bullets_slide = next(s for s in deck.slides if s.kind == "bullets")
    # Original paragraph text is preserved in notes for the speaker.
    assert "Para 0 of chapter 0." in bullets_slide.notes
