"""Render a SlideDeck to .pptx via python-pptx.

Design principles:
- Typography: Calibri (Latin) + Microsoft YaHei (CJK) cascade.
- Color palette: deep-navy titles (#1F3A5F), neutral-gray footer (#888888),
  dark-gray captions (#444444); body text uses template default.
- No background images, no shadows, no decorative shapes except the single
  horizontal rule on divider slides.
- Template-swap: caller may supply a .pptx as a slide-master base via
  `template_path`.  A _layout() fallback guards against templates with
  fewer than the expected 11 layouts.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import ClassVar

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner

# ── color constants ────────────────────────────────────────────────────────────
_NAVY = RGBColor(0x1F, 0x3A, 0x5F)
_GRAY = RGBColor(0x88, 0x88, 0x88)
_DARK_GRAY = RGBColor(0x44, 0x44, 0x44)

# ── layout index constants ─────────────────────────────────────────────────────
_IDX_TITLE_SLIDE = 0       # "Title Slide" (title + subtitle)
_IDX_TITLE_CONTENT = 1     # "Title and Content"
_IDX_TITLE_ONLY = 5        # "Title Only"

_SLIDE_W = Inches(10.0)    # default widescreen width
_SLIDE_H = Inches(7.5)     # default widescreen height


class PptxRenderer(Renderer):
    extension: ClassVar[str] = "pptx"

    def __init__(self, summaries: dict | None = None,
                 template_path: Path | None = None):
        self.summaries = summaries
        self.template_path = template_path

    # ── public entry point ─────────────────────────────────────────────────────

    def render(self, doc: Document, out_path: Path) -> None:
        deck = SlidePlanner(lang=doc.lang).plan(doc, self.summaries)
        if self.template_path is not None:
            prs = Presentation(str(self.template_path))
        else:
            prs = Presentation()

        total = len(deck.slides)
        for slide_idx, slide in enumerate(deck.slides, start=1):
            self._render_slide(prs, slide, slide_idx=slide_idx, total=total,
                               doc=doc)
        prs.save(str(out_path))

    # ── per-kind dispatch ──────────────────────────────────────────────────────

    def _render_slide(self, prs: Presentation, slide: Slide, *,
                      slide_idx: int, total: int, doc: Document) -> None:
        kw = dict(slide_idx=slide_idx, total=total, doc=doc)
        if slide.kind == "title":
            self._layout_title(prs, slide, **kw)
        elif slide.kind == "outline":
            self._layout_outline(prs, slide, **kw)
        elif slide.kind == "divider":
            self._layout_divider(prs, slide, **kw)
        elif slide.kind == "bullets":
            self._layout_bullets(prs, slide, **kw)
        elif slide.kind == "figure":
            self._layout_figure(prs, slide, **kw)
        elif slide.kind == "closing":
            self._layout_bullets(prs, slide, **kw)
        else:
            self._layout_bullets(prs, slide, **kw)

    # ── layout helpers ─────────────────────────────────────────────────────────

    def _layout_title(self, prs: Presentation, slide: Slide, *,
                      slide_idx: int, total: int, doc: Document) -> None:
        s = prs.slides.add_slide(self._layout(prs, _IDX_TITLE_SLIDE))

        # Title
        if s.shapes.title is not None:
            tf = s.shapes.title.text_frame
            tf.text = slide.title
            p = tf.paragraphs[0]
            if p.runs:
                r = p.runs[0]
                r.font.size = Pt(36)
                r.font.bold = True
                r.font.color.rgb = _NAVY
                r.font.name = "Calibri"
                _set_ea_font(r, "Microsoft YaHei")

        # Subtitle: "ZH · N slides · YYYY-MM-DD"
        today = datetime.date.today().isoformat()
        subtitle_text = f"{doc.lang.upper()} · {total} slides · {today}"
        # Find the subtitle placeholder (idx == 1)
        sub_ph = None
        for ph in s.placeholders:
            if ph.placeholder_format.idx == 1:
                sub_ph = ph
                break
        if sub_ph is not None:
            tf2 = sub_ph.text_frame
            tf2.text = subtitle_text
            if tf2.paragraphs and tf2.paragraphs[0].runs:
                r2 = tf2.paragraphs[0].runs[0]
                r2.font.size = Pt(14)
                r2.font.bold = False
                r2.font.color.rgb = _GRAY
                r2.font.name = "Calibri"

        self._attach_notes(s, slide.notes)

    def _layout_outline(self, prs: Presentation, slide: Slide, *,
                        slide_idx: int, total: int, doc: Document) -> None:
        s = prs.slides.add_slide(self._layout(prs, _IDX_TITLE_CONTENT))

        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
            _style_title_shape(s.shapes.title, size=Pt(24))

        body = _get_body_placeholder(s)
        if body is not None and slide.bullets:
            tf = body.text_frame
            tf.text = slide.bullets[0]
            _style_run(tf.paragraphs[0], size=Pt(18), line_spacing=1.15)
            for bullet in slide.bullets[1:]:
                p = tf.add_paragraph()
                p.text = bullet
                _style_run(p, size=Pt(18), line_spacing=1.15)

        self._add_header(s, doc.paper_title)
        self._add_footer(s, slide_idx, total)
        self._attach_notes(s, slide.notes)

    def _layout_divider(self, prs: Presentation, slide: Slide, *,
                        slide_idx: int, total: int, doc: Document) -> None:
        # Use Title Only layout; we'll center the text manually
        s = prs.slides.add_slide(self._layout(prs, _IDX_TITLE_ONLY))

        if s.shapes.title is not None:
            title_shape = s.shapes.title
            tf = title_shape.text_frame
            tf.text = slide.title
            if tf.paragraphs and tf.paragraphs[0].runs:
                r = tf.paragraphs[0].runs[0]
                r.font.size = Pt(32)
                r.font.bold = True
                r.font.color.rgb = _NAVY
                r.font.name = "Calibri"
                _set_ea_font(r, "Microsoft YaHei")

        # Thin horizontal rule below title (~at 2.8 inches from top)
        line = s.shapes.add_connector(
            1,  # MSO_CONNECTOR_TYPE.STRAIGHT == 1
            Inches(2.0), Inches(2.8),   # x1, y1
            Inches(8.0), Inches(2.8),   # x2, y2
        )
        line.line.color.rgb = _GRAY
        line.line.width = Pt(1)

        self._add_header(s, doc.paper_title)
        self._add_footer(s, slide_idx, total)
        self._attach_notes(s, slide.notes)

    def _layout_bullets(self, prs: Presentation, slide: Slide, *,
                        slide_idx: int, total: int, doc: Document) -> None:
        s = prs.slides.add_slide(self._layout(prs, _IDX_TITLE_CONTENT))

        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
            _style_title_shape(s.shapes.title, size=Pt(20))

        body = _get_body_placeholder(s)
        if body is not None and slide.bullets:
            tf = body.text_frame
            tf.text = slide.bullets[0]
            _style_run(tf.paragraphs[0], size=Pt(18), line_spacing=1.15)
            for bullet in slide.bullets[1:]:
                p = tf.add_paragraph()
                p.text = bullet
                _style_run(p, size=Pt(18), line_spacing=1.15)

        self._add_header(s, doc.paper_title)
        self._add_footer(s, slide_idx, total)
        self._attach_notes(s, slide.notes)

    def _layout_figure(self, prs: Presentation, slide: Slide, *,
                       slide_idx: int, total: int, doc: Document) -> None:
        s = prs.slides.add_slide(self._layout(prs, _IDX_TITLE_ONLY))

        if s.shapes.title is not None:
            s.shapes.title.text = slide.title
            _style_title_shape(s.shapes.title, size=Pt(18))

        # Image — first available path
        for img_path in slide.image_paths:
            if not img_path.exists():
                continue
            s.shapes.add_picture(
                str(img_path),
                left=Inches(1.0), top=Inches(1.5),
                width=Inches(8.0),
            )
            break

        # Deep observation caption below image
        if slide.deep_observation:
            tb = s.shapes.add_textbox(
                left=Inches(0.5), top=Inches(6.2),
                width=Inches(9.0), height=Inches(0.8),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = slide.deep_observation
            run.font.size = Pt(11)
            run.font.italic = True
            run.font.color.rgb = _DARK_GRAY
            run.font.name = "Calibri"
            _set_ea_font(run, "Microsoft YaHei")

        self._add_header(s, doc.paper_title)
        self._add_footer(s, slide_idx, total)
        self._attach_notes(s, slide.notes)

    # ── header / footer ────────────────────────────────────────────────────────

    def _add_header(self, s, paper_title: str) -> None:
        """Top-right textbox: paper title truncated to 50 chars, 9pt gray."""
        label = paper_title[:50]
        tb = s.shapes.add_textbox(
            left=Inches(5.5), top=Inches(0.2),
            width=Inches(4.0), height=Inches(0.3),
        )
        tf = tb.text_frame
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = label
        run.font.size = Pt(9)
        run.font.color.rgb = _GRAY
        run.font.name = "Calibri"

    def _add_footer(self, s, slide_idx: int, total: int) -> None:
        """Bottom-right textbox: 'N / total', 10pt gray."""
        tb = s.shapes.add_textbox(
            left=Inches(8.5), top=Inches(7.0),
            width=Inches(1.0), height=Inches(0.3),
        )
        tf = tb.text_frame
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = f"{slide_idx} / {total}"
        run.font.size = Pt(10)
        run.font.color.rgb = _GRAY
        run.font.name = "Calibri"

    # ── static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _layout(prs: Presentation, idx: int):
        """Return layout at *idx*, falling back to layout[0] if out of range."""
        layouts = prs.slide_layouts
        if idx < len(layouts):
            return layouts[idx]
        return layouts[0]

    @staticmethod
    def _attach_notes(s, notes: str) -> None:
        if not notes:
            return
        s.notes_slide.notes_text_frame.text = notes


# ── module-level typography helpers ───────────────────────────────────────────

def _set_ea_font(run, font_name: str = "Microsoft YaHei") -> None:
    """Inject <a:ea typeface="..."/> into the run's rPr for CJK font cascade."""
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rPr, qn("a:ea"))
    ea.set("typeface", font_name)


def _style_title_shape(title_shape, size: Emu = None) -> None:
    """Apply navy + bold to a title placeholder's first run."""
    tf = title_shape.text_frame
    if not tf.paragraphs:
        return
    p = tf.paragraphs[0]
    if not p.runs:
        return
    r = p.runs[0]
    if size is not None:
        r.font.size = size
    r.font.bold = True
    r.font.color.rgb = _NAVY
    r.font.name = "Calibri"
    _set_ea_font(r, "Microsoft YaHei")


def _style_run(para, size: Emu = None, bold: bool = False,
               line_spacing: float | None = None) -> None:
    """Style all existing runs in *para* and set paragraph line spacing."""
    from pptx.util import Pt as _Pt
    from pptx.oxml.ns import qn as _qn

    if line_spacing is not None:
        # Set line spacing via paragraph XML
        pPr = para._p.get_or_add_pPr()
        lnSpc = pPr.find(_qn("a:lnSpc"))
        if lnSpc is None:
            lnSpc = etree.SubElement(pPr, _qn("a:lnSpc"))
        spcPct = lnSpc.find(_qn("a:spcPct"))
        if spcPct is None:
            spcPct = etree.SubElement(lnSpc, _qn("a:spcPct"))
        spcPct.set("val", str(int(line_spacing * 100000)))

    for r in para.runs:
        if size is not None:
            r.font.size = size
        if bold:
            r.font.bold = True
        r.font.name = "Calibri"
        _set_ea_font(r, "Microsoft YaHei")


def _get_body_placeholder(s):
    """Return the content placeholder (idx==1) or None."""
    for shape in s.placeholders:
        if shape.placeholder_format.idx == 1:
            return shape
    return None


RENDERERS["pptx"] = PptxRenderer
