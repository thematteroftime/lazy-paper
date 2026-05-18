"""Render a SlideDeck to .pptx via python-pptx.

Layout choices: use built-in Title Slide, Title and Content, and Blank layouts
from the default template (avoids shipping a custom .pptx master)."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pptx import Presentation
from pptx.util import Inches, Pt

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner


class PptxRenderer(Renderer):
    extension: ClassVar[str] = "pptx"

    def __init__(self, summaries: dict | None = None):
        self.summaries = summaries

    def render(self, doc: Document, out_path: Path) -> None:
        deck = SlidePlanner(lang=doc.lang).plan(doc, self.summaries)
        prs = Presentation()
        for slide in deck.slides:
            self._render_slide(prs, slide)
        prs.save(str(out_path))

    # ---------- per-kind layout dispatch ----------

    def _render_slide(self, prs: Presentation, slide: Slide) -> None:
        if slide.kind == "title":
            self._layout_title(prs, slide)
        elif slide.kind == "outline":
            self._layout_bullets(prs, slide)
        elif slide.kind == "divider":
            self._layout_title(prs, slide)
        elif slide.kind == "bullets":
            self._layout_bullets(prs, slide)
        elif slide.kind == "figure":
            self._layout_figure(prs, slide)
        elif slide.kind == "closing":
            self._layout_bullets(prs, slide)
        else:
            self._layout_bullets(prs, slide)

    # ---------- layouts ----------

    def _layout_title(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[0])  # Title Slide
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        self._attach_notes(s, slide.notes)

    def _layout_bullets(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        body = None
        for shape in s.placeholders:
            if shape.placeholder_format.idx == 1:
                body = shape
                break
        if body is not None and slide.bullets:
            tf = body.text_frame
            tf.text = slide.bullets[0]
            for bullet in slide.bullets[1:]:
                p = tf.add_paragraph()
                p.text = bullet
        self._attach_notes(s, slide.notes)

    def _layout_figure(self, prs: Presentation, slide: Slide) -> None:
        s = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
        # Place the first image (multi-panel: just use the first, keeping it simple)
        for img_path in slide.image_paths:
            if not img_path.exists():
                continue
            s.shapes.add_picture(
                str(img_path),
                left=Inches(1.0), top=Inches(1.5),
                width=Inches(8.0),
            )
            break
        if slide.deep_observation:
            tb = s.shapes.add_textbox(
                left=Inches(0.5), top=Inches(6.5),
                width=Inches(9.0), height=Inches(0.7),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            run = tf.paragraphs[0].add_run()
            run.text = slide.deep_observation
            run.font.size = Pt(12)
        self._attach_notes(s, slide.notes)

    @staticmethod
    def _attach_notes(s, notes: str) -> None:
        if not notes:
            return
        s.notes_slide.notes_text_frame.text = notes


RENDERERS["pptx"] = PptxRenderer
