"""Render a SlideDeck to .pptx — academic defense style (v3).

Design: monochrome cream bg (#FBFAF7), near-black text, no accent colors,
formal graduation-defense aesthetic, compact layout, no brand tag.
Template-swap: caller may supply a .pptx master via `template_path`.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import ClassVar

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.slide_planner import Slide, SlideDeck, SlidePlanner


class _T:
    """Design token namespace — monochrome academic palette."""
    W, H         = Inches(13.333), Inches(7.5)
    BG           = RGBColor(0xFB, 0xFA, 0xF7)   # very light cream
    TEXT         = RGBColor(0x1A, 0x1A, 0x1A)   # near-black body
    TEXT_DIM     = RGBColor(0x66, 0x66, 0x66)   # subtitle / metadata
    TEXT_FAINT   = RGBColor(0xA8, 0xA8, 0xA8)   # footer / fine rules
    RULE         = RGBColor(0xD0, 0xD0, 0xD0)   # thin separator lines
    EA_SERIF     = "Source Han Serif SC"
    EA_SANS      = "PingFang SC"
    LAT_SERIF    = "Cambria"
    LAT_SANS     = "Calibri"


_IDX_TITLE = 0   # "Title Slide" layout — has shapes.title placeholder
_IDX_BLANK = 6   # "Blank" layout — full canvas


class PptxRenderer(Renderer):
    extension: ClassVar[str] = "pptx"

    def __init__(self, summaries: dict | None = None,
                 template_path: Path | None = None):
        self.summaries = summaries
        self.template_path = template_path
        self._ch: int = -1   # chapter index, incremented on each divider

    def render(self, doc: Document, out_path: Path) -> None:
        deck = SlidePlanner(lang=doc.lang).plan(doc, self.summaries)
        if self.template_path is not None:
            prs = Presentation(str(self.template_path))
        else:
            prs = Presentation()
            prs.slide_width, prs.slide_height = _T.W, _T.H
        total = len(deck.slides)
        self._ch = -1
        for idx, slide in enumerate(deck.slides, 1):
            self._dispatch(prs, slide, idx, total, doc)
        prs.save(str(out_path))

    def _dispatch(self, prs, slide, idx, total, doc):
        kw = dict(idx=idx, total=total, doc=doc)
        if   slide.kind == "title":   self._title(prs, slide, **kw)
        elif slide.kind == "outline": self._outline(prs, slide, **kw)
        elif slide.kind == "divider": self._ch += 1; self._divider(prs, slide, **kw)
        elif slide.kind == "figure":  self._figure(prs, slide, **kw)
        else:                         self._bullets(prs, slide, **kw)

    # ── slide builders ─────────────────────────────────────────────────────────

    def _title(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_TITLE))
        _bg(s)
        T = _T
        # Academic-style font sizing: more conservative than magazine
        title_len = len(slide.title)
        title_pt = 30 if title_len < 60 else (26 if title_len < 100 else 22)
        # Reposition & style the title placeholder (keeps shapes.title for tests)
        ph = s.shapes.title
        if ph is not None:
            ph.left, ph.top, ph.width, ph.height = (
                Inches(1.2), Inches(1.6), Inches(10.9), Inches(3.2))
            ph.text_frame.word_wrap = True
            ph.text_frame.text = slide.title
            p = ph.text_frame.paragraphs[0]
            if p.runs:
                _run_style(p.runs[0], Pt(title_pt), True, T.TEXT, T.LAT_SERIF, T.EA_SERIF)
            p.alignment = 1
        # Remove subtitle placeholder
        for ph2 in list(s.placeholders):
            if ph2.placeholder_format.idx == 1:
                ph2._element.getparent().remove(ph2._element); break
        # Thin decorative rule below title area
        _line(s, Inches(1.5), Inches(4.95), Inches(11.8), Inches(4.95), T.RULE, Pt(0.75))
        # Subtitle metadata line (formal info, not slogan)
        n_ch = len(doc.chapters)
        n_bl = sum(len(c.blocks) for c in doc.chapters)
        sub = f"{doc.lang.upper()}  ·  {n_ch} chapters  ·  {n_bl} blocks"
        _tb1(s, sub,
             Inches(1.5), Inches(5.1), Inches(9.0), Inches(0.5),
             Pt(13), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True, align=1)
        # Bottom-right metadata line
        today = datetime.date.today()
        pid = _pid(doc.paper_title)
        meta = f"{pid}  ·  {today.year}-{today.month:02d}-{today.day:02d}"
        _tb1(s, meta,
             Inches(7.5), Inches(6.9), Inches(5.5), Inches(0.35),
             Pt(10), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS, align=2)
        _footer(s, idx, total)
        _notes(s, slide.notes)

    def _outline(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        # Header
        _tb1(s, "目  录  ·  Contents",
             Inches(0.8), Inches(0.45), Inches(11.7), Inches(0.65),
             Pt(24), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True)
        _line(s, Inches(0.8), Inches(1.1), Inches(12.5), Inches(1.1), T.RULE, Pt(1))
        # Compact row spacing — more information per slide
        row_h = Inches(0.4)
        n = len(slide.bullets)
        if n > 12:
            # Two-column layout for large chapter counts
            half = (n + 1) // 2
            for i, bul in enumerate(slide.bullets):
                col = i // half
                row = i % half
                x_num = Inches(0.8) + col * Inches(6.3)
                x_txt = Inches(1.55) + col * Inches(6.3)
                txt_w = Inches(5.2)
                y = Inches(1.2) + row * row_h
                _tb1(s, f"{i+1:02d}", x_num, y, Inches(0.65), row_h,
                     Pt(13), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, bold=True)
                _tb1(s, bul, x_txt, y, txt_w, row_h,
                     Pt(14), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
                _line(s, x_num, y + row_h - Inches(0.03),
                      x_num + Inches(5.8), y + row_h - Inches(0.03), T.RULE, Pt(0.4))
        else:
            for i, bul in enumerate(slide.bullets):
                y = Inches(1.2) + i * row_h
                _tb1(s, f"{i+1:02d}", Inches(0.8), y, Inches(0.65), row_h,
                     Pt(14), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, bold=True)
                _tb1(s, bul, Inches(1.55), y, Inches(10.8), row_h,
                     Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
                if i < n - 1:
                    _line(s, Inches(0.8), y + row_h - Inches(0.03),
                          Inches(12.5), y + row_h - Inches(0.03), T.RULE, Pt(0.4))
        _footer(s, idx, total)
        _notes(s, slide.notes)

    def _divider(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        num = f"§{self._ch+1}"
        # Section number — small, centered, gray
        _tb1(s, num,
             Inches(0), Inches(2.2), Inches(13.333), Inches(0.55),
             Pt(18), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, align=1)
        # Chapter title — large serif bold, centered
        _tb1(s, slide.title,
             Inches(1.5), Inches(2.85), Inches(10.333), Inches(1.3),
             Pt(32), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True, align=1, wrap=True)
        # Thin rule — narrow, centered
        _line(s, Inches(4.5), Inches(4.25), Inches(8.833), Inches(4.25), T.RULE, Pt(1))
        # Localized subtitle
        subtitle = f"引言 / {slide.title}" if slide.title and slide.title != "Introduction" else slide.title
        _tb1(s, subtitle,
             Inches(1.5), Inches(4.4), Inches(10.333), Inches(0.5),
             Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True, align=1)
        _footer(s, idx, total)
        _notes(s, slide.notes)

    def _bullets(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        chi = max(self._ch, 0)
        is_closing = slide.kind == "closing"
        # Section header text
        sec_label = "总结 · Conclusion" if is_closing else f"§{chi+1}  ·  {slide.title}"
        _tb1(s, sec_label,
             Inches(0.7), Inches(0.4), Inches(12.0), Inches(0.45),
             Pt(14), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, wrap=True)
        _line(s, Inches(0.7), Inches(0.88), Inches(12.6), Inches(0.88), T.RULE, Pt(0.75))
        # Slide title (only when not closing, to avoid repetition)
        if not is_closing:
            _tb1(s, slide.title,
                 Inches(0.7), Inches(1.0), Inches(12.0), Inches(0.7),
                 Pt(22), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True, wrap=True)
        # Bullet markers (Unicode numbered dingbats for up to 5; else ▸)
        MARKERS = ["❶", "❷", "❸", "❹", "❺", "❻", "❼", "❽", "❾", "❿"]
        if slide.bullets:
            body_top = Inches(1.8) if not is_closing else Inches(1.1)
            row_h = Inches(0.62)
            for i, bul in enumerate(slide.bullets):
                by = body_top + i * row_h
                marker = MARKERS[i] if i < len(MARKERS) else "▸"
                _tb1(s, marker, Inches(0.7), by, Inches(0.45), row_h,
                     Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS)
                _tb1(s, bul, Inches(1.2), by, Inches(11.6), row_h,
                     Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
        # Key takeaway from summaries (italic, centered, below bullets)
        heading = slide.title
        summ = (self.summaries or {}).get(heading, {})
        takeaway = summ.get("key_takeaway", "")
        if takeaway:
            n_b = len(slide.bullets)
            body_top = Inches(1.8) if not is_closing else Inches(1.1)
            ty = body_top + n_b * Inches(0.62) + Inches(0.2)
            _tb1(s, f"Key takeaway: {takeaway}",
                 Inches(0.7), ty, Inches(12.0), Inches(0.5),
                 Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True, align=1)
        _footer(s, idx, total)
        _notes(s, slide.notes)

    def _figure(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        chi = max(self._ch, 0)
        # Section header
        _tb1(s, f"§{chi+1}  ·  Fig.",
             Inches(0.7), Inches(0.4), Inches(12.0), Inches(0.45),
             Pt(14), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF)
        _line(s, Inches(0.7), Inches(0.88), Inches(12.6), Inches(0.88), T.RULE, Pt(0.75))
        # Caption above image
        _tb1(s, slide.title,
             Inches(0.7), Inches(1.0), Inches(12.0), Inches(0.55),
             Pt(16), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True, wrap=True)
        # Image — larger, centered
        img_top = Inches(1.65)
        img_max_h = Inches(5.0)
        img_max_w = Inches(10.5)
        for ip in slide.image_paths:
            if not ip.exists(): continue
            pic = s.shapes.add_picture(str(ip), Inches(0.9), img_top, img_max_w)
            if pic.height > img_max_h:
                r = img_max_h / pic.height
                pic.height, pic.width = img_max_h, int(pic.width * r)
            if pic.width > img_max_w:
                r = img_max_w / pic.width
                pic.width, pic.height = img_max_w, int(pic.height * r)
            pic.left = int((_T.W - pic.width) / 2)
            break
        # Deep observation below image — italic, narrow
        if slide.deep_observation:
            _tb1(s, f"深度观察  ·  {slide.deep_observation}",
                 Inches(0.7), Inches(6.75), Inches(12.0), Inches(0.5),
                 Pt(12), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True)
        _footer(s, idx, total)
        _notes(s, slide.notes)

    @staticmethod
    def _lay(prs, idx):
        return PptxRenderer._layout(prs, idx)

    @staticmethod
    def _layout(prs, idx):
        """Return layout at *idx*, falling back to layout[0] if out of range."""
        lays = prs.slide_layouts
        return lays[idx] if idx < len(lays) else lays[0]

    @staticmethod
    def _attach_notes(s, notes):   # kept for compat
        _notes(s, notes)


# ── design primitives ──────────────────────────────────────────────────────────

def _bg(s) -> None:
    """Cream full-slide rectangle pushed to back of z-order."""
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), _T.W, _T.H)
    bg.fill.solid(); bg.fill.fore_color.rgb = _T.BG
    bg.line.fill.background()
    tree = s.shapes._spTree; el = bg._element
    tree.remove(el); tree.insert(2, el)


def _line(s, x1, y1, x2, y2, color, width):
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    ln.line.color.rgb = color; ln.line.width = width


def _footer(s, slide_idx, total):
    """Page number only — bottom-right, formal 'N of N' wording."""
    _tb1(s, f"{slide_idx} / {total}",
         Inches(11.5), Inches(7.1), Inches(1.5), Inches(0.3),
         Pt(10), _T.TEXT_FAINT, _T.LAT_SANS, _T.EA_SANS)


def _notes(s, text):
    if text:
        s.notes_slide.notes_text_frame.text = text


def _tb1(s, text, left, top, w, h, fsize, fcolor, lat_font, ea_font,
         bold=False, italic=False, wrap=False, align=None):
    """Add a single-paragraph textbox."""
    tb = s.shapes.add_textbox(left, top, w, h)
    tf = tb.text_frame
    if wrap: tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = text
    _run_style(r, fsize, bold, fcolor, lat_font, ea_font, italic=italic)
    if align is not None: p.alignment = align


def _run_style(r, size, bold, color, lat_font, ea_font, italic=False):
    r.font.size = size; r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = color; r.font.name = lat_font
    _ea(r, ea_font)


def _ea(run, font_name):
    """Inject <a:ea typeface="..."/> for CJK rendering."""
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rPr, qn("a:ea"))
    ea.set("typeface", font_name)


def _pid(title):
    words = title.split()[:3]
    return "-".join(w.lower().strip(".,;:()[]") for w in words if w)[:20]


RENDERERS["pptx"] = PptxRenderer
