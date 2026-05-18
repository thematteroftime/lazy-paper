"""Render a SlideDeck to .pptx — poster-inspired design.

Design: warm cream bg (#FAF6EE), serif titles (#2A2520), sans-serif body,
white card containers on cream, large gray numerical accents, section accent
color rotation, 16:9 widescreen (13.333 × 7.5 in).
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
    """Design token namespace."""
    W, H         = Inches(13.333), Inches(7.5)
    BG_CREAM     = RGBColor(0xFA, 0xF6, 0xEE)
    CARD_WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
    CARD_BORDER  = RGBColor(0xE5, 0xDF, 0xD3)
    TEXT_DARK    = RGBColor(0x2A, 0x25, 0x20)
    TEXT_NAVY    = RGBColor(0x3D, 0x50, 0x60)
    TEXT_GRAY    = RGBColor(0xA8, 0xA1, 0x9A)
    NUM_ACCENT   = RGBColor(0xD8, 0xCF, 0xC0)
    WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
    ACCENTS = [
        RGBColor(0x7B, 0xA6, 0x7A),   # sage green
        RGBColor(0xD4, 0x9F, 0x5A),   # warm amber
        RGBColor(0xA8, 0x7C, 0x5A),   # terracotta
        RGBColor(0x5B, 0x7A, 0x99),   # slate blue
    ]
    EA_SERIF = "Source Han Serif SC"
    EA_SANS  = "PingFang SC"
    LAT_SERIF = "Cambria"
    LAT_SANS  = "Calibri"


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
        # Reposition & style the title placeholder (keeps shapes.title for tests)
        ph = s.shapes.title
        if ph is not None:
            ph.left, ph.top, ph.width, ph.height = (
                Inches(1.0), Inches(2.5), Inches(8.5), Inches(2.2))
            ph.text_frame.word_wrap = True
            ph.text_frame.text = slide.title
            p = ph.text_frame.paragraphs[0]
            if p.runs:
                _run_style(p.runs[0], Pt(36), True, T.TEXT_DARK, T.LAT_SERIF, T.EA_SERIF)
            p.alignment = 1
        # Remove subtitle placeholder
        for ph2 in list(s.placeholders):
            if ph2.placeholder_format.idx == 1:
                ph2._element.getparent().remove(ph2._element); break
        # Decorative lines
        _line(s, Inches(1.0), Inches(2.35), Inches(9.5), Inches(2.35), T.TEXT_GRAY, Pt(0.75))
        _line(s, Inches(1.0), Inches(4.9),  Inches(9.5), Inches(4.9),  T.TEXT_GRAY, Pt(0.75))
        # Eyebrow
        _tb1(s, "MOMENT  ·  论文摘要分析",
             Inches(1.0), Inches(1.8), Inches(8.5), Inches(0.45),
             Pt(11), T.TEXT_GRAY, T.LAT_SANS, T.EA_SANS, align=1)
        # Sub-label
        kws = getattr(doc, "keywords", None) or []
        sub = "  ·  ".join(([kws[0]] if kws else []) + [doc.lang.upper()])
        _tb1(s, sub, Inches(1.0), Inches(5.0), Inches(8.5), Inches(0.4),
             Pt(12), T.TEXT_GRAY, T.LAT_SANS, T.EA_SANS, align=1, italic=True)
        # Issue card
        today = datetime.date.today()
        pid = _pid(doc.paper_title)
        _card(s, Inches(10.0), Inches(1.0), Inches(2.9), Inches(1.65),
              ["ISSUE 01", f"{today.year}·{today.month:02d}·{today.day:02d}", f"{total} SLIDES"],
              Pt(11), T.TEXT_NAVY, align=1)
        _footer(s, pid, idx, total)
        _notes(s, slide.notes)

    def _outline(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        _num_accent(s, "00", Inches(0.4), Inches(0.3), Pt(72))
        _tb1(s, "目  录  ·  CONTENTS",
             Inches(1.5), Inches(0.55), Inches(10.0), Inches(0.7),
             Pt(28), T.TEXT_NAVY, T.LAT_SERIF, T.EA_SERIF, bold=True)
        _line(s, Inches(1.5), Inches(1.35), Inches(12.0), Inches(1.35), T.CARD_BORDER, Pt(1))
        row_h = Inches(0.6)
        for i, bul in enumerate(slide.bullets):
            y = Inches(1.5) + i * row_h
            _tb1(s, f"{i+1:02d}", Inches(1.5), y, Inches(0.6), row_h,
                 Pt(14), T.ACCENTS[i % 4], T.LAT_SERIF, T.EA_SERIF, bold=True)
            _tb1(s, bul, Inches(2.2), y, Inches(9.5), row_h,
                 Pt(16), T.TEXT_DARK, T.LAT_SANS, T.EA_SANS, wrap=True)
            if i < len(slide.bullets) - 1:
                _line(s, Inches(1.5), y + row_h - Inches(0.05),
                      Inches(11.8), y + row_h - Inches(0.05), T.CARD_BORDER, Pt(0.5))
        _footer(s, _pid(doc.paper_title), idx, total)
        _notes(s, slide.notes)

    def _divider(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        acc = T.ACCENTS[self._ch % 4]
        num = f"{self._ch+1:02d}"
        _num_accent(s, num, Inches(0.5), Inches(0.4), Pt(96))
        # Card
        cx, cy, cw, ch = Inches(3.5), Inches(2.3), Inches(6.5), Inches(2.8)
        _rrect(s, cx, cy, cw, ch, T.CARD_WHITE, T.CARD_BORDER, 0.05)
        _tb1(s, slide.title, cx + Inches(0.4), cy + Inches(0.35),
             cw - Inches(0.8), Inches(1.0),
             Pt(30), T.TEXT_DARK, T.LAT_SERIF, T.EA_SERIF, bold=True, align=1)
        ly = cy + Inches(1.5)
        _line(s, cx + Inches(0.4), ly, cx + cw - Inches(0.4), ly, acc, Pt(2))
        _tb1(s, f"CHAPTER {num}", cx + Inches(0.4), ly + Inches(0.15),
             cw - Inches(0.8), Inches(0.6),
             Pt(11), T.TEXT_GRAY, T.LAT_SANS, T.EA_SANS, align=1)
        _footer(s, _pid(doc.paper_title), idx, total)
        _notes(s, slide.notes)

    def _bullets(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        chi = max(self._ch, 0)
        acc = T.ACCENTS[chi % 4]
        _section_bar(s, chi, slide.title, acc)
        title = "总结 · CONCLUSION" if slide.kind == "closing" else slide.title
        _tb1(s, title, Inches(1.0), Inches(1.3), Inches(11.0), Inches(0.75),
             Pt(22), T.TEXT_DARK, T.LAT_SERIF, T.EA_SERIF, bold=True, wrap=True)
        if slide.bullets:
            cx, cy, cw, row_h = Inches(0.8), Inches(2.15), Inches(11.7), Inches(0.6)
            ch = Inches(0.35) + len(slide.bullets) * row_h + Inches(0.25)
            _rrect(s, cx, cy, cw, ch, T.CARD_WHITE, T.CARD_BORDER, 0.03)
            for i, bul in enumerate(slide.bullets):
                by = cy + Inches(0.3) + i * row_h
                _tb1(s, "▸", cx + Inches(0.25), by, Inches(0.35), row_h,
                     Pt(14), acc, T.LAT_SANS, T.EA_SANS)
                _tb1(s, bul, cx + Inches(0.65), by, cw - Inches(0.9), row_h,
                     Pt(16), T.TEXT_DARK, T.LAT_SANS, T.EA_SANS, wrap=True)
        _footer(s, _pid(doc.paper_title), idx, total)
        _notes(s, slide.notes)

    def _figure(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        chi = max(self._ch, 0)
        acc = T.ACCENTS[chi % 4]
        _section_bar(s, chi, slide.title, acc)
        _num_accent(s, f"{chi+1:02d}", Inches(0.4), Inches(0.3), Pt(72))
        _tb1(s, slide.title, Inches(1.0), Inches(1.2), Inches(11.5), Inches(0.6),
             Pt(16), T.TEXT_DARK, T.LAT_SERIF, T.EA_SERIF, bold=True, wrap=True)
        img_max_h = Inches(4.2)
        for ip in slide.image_paths:
            if not ip.exists(): continue
            pic = s.shapes.add_picture(str(ip), Inches(0.9), Inches(1.95), Inches(11.5))
            if pic.height > img_max_h:
                r = img_max_h / pic.height
                pic.height, pic.width = img_max_h, int(pic.width * r)
            pic.left = int((T.W - pic.width) / 2)
            break
        if slide.deep_observation:
            oy, oh = Inches(6.3), Inches(0.9)
            _rrect(s, Inches(0.8), oy, Inches(11.7), oh, T.CARD_WHITE, T.CARD_BORDER, 0.03)
            tb = s.shapes.add_textbox(Inches(1.1), oy + Inches(0.12),
                                      Inches(11.1), oh - Inches(0.2))
            tf = tb.text_frame; tf.word_wrap = True
            p = tf.paragraphs[0]
            r1 = p.add_run(); r1.text = "深度观察 · "
            _run_style(r1, Pt(10), True, acc, T.LAT_SANS, T.EA_SANS)
            r2 = p.add_run(); r2.text = slide.deep_observation
            _run_style(r2, Pt(12), False, T.TEXT_DARK, T.LAT_SANS, T.EA_SANS, italic=True)
        _footer(s, _pid(doc.paper_title), idx, total)
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
    bg.fill.solid(); bg.fill.fore_color.rgb = _T.BG_CREAM
    bg.line.fill.background()
    tree = s.shapes._spTree; el = bg._element
    tree.remove(el); tree.insert(2, el)


def _rrect(s, left, top, w, h, fill, border, adj=0.04):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, w, h)
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = border; sh.line.width = Pt(1)
    sh.adjustments[0] = adj


def _line(s, x1, y1, x2, y2, color, width):
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    ln.line.color.rgb = color; ln.line.width = width


def _num_accent(s, num, left, top, size=Pt(96)):
    tb = s.shapes.add_textbox(left, top, Inches(2.5), Inches(1.8))
    p = tb.text_frame.paragraphs[0]; r = p.add_run(); r.text = num
    _run_style(r, size, False, _T.NUM_ACCENT, _T.LAT_SERIF, _T.EA_SERIF)


def _section_bar(s, ch_idx, heading, accent):
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                             Inches(0), Inches(0), Inches(13.333), Inches(0.55))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
    _tb1(s, f"{ch_idx+1:02d}  ·  {heading.upper()}",
         Inches(0.4), Inches(0.08), Inches(12.0), Inches(0.4),
         Pt(11), _T.WHITE, _T.LAT_SANS, _T.EA_SANS, bold=True)


def _card(s, left, top, w, h, lines, fsize, fcolor, align=1):
    _rrect(s, left, top, w, h, _T.CARD_WHITE, _T.CARD_BORDER, 0.04)
    rh = h / max(len(lines), 1)
    for i, txt in enumerate(lines):
        _tb1(s, txt, left + Inches(0.15), top + i * rh + Inches(0.05),
             w - Inches(0.3), rh, fsize, fcolor, _T.LAT_SANS, _T.EA_SANS, align=align)


def _footer(s, paper_id, slide_idx, total):
    _tb1(s, f"PAPER2MD  ·  {paper_id}",
         Inches(0.4), Inches(7.1), Inches(6.0), Inches(0.3),
         Pt(9), _T.TEXT_GRAY, _T.LAT_SANS, _T.EA_SANS)
    _tb1(s, f"{slide_idx} / {total}",
         Inches(11.5), Inches(7.1), Inches(1.5), Inches(0.3),
         Pt(9), _T.TEXT_GRAY, _T.LAT_SANS, _T.EA_SANS)


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
