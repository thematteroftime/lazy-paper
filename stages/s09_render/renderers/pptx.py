"""Render a SlideDeck to .pptx — academic defense style (v4).

Design: monochrome cream bg (#FBFAF7), near-black text, no accent colors,
formal graduation-defense aesthetic, compact layout, no brand tag.
Template-swap: caller may supply a .pptx master via `template_path`.

v4 changes vs v3:
- Title: academic defense pattern (big title centered, rule, subtitle, presenter/affiliation/date box)
- Outline: 2-column for >=5 chapters, smaller font
- Divider: everything fully centered, localized "第N章" subtitle
- Bullets: no duplicate chapter heading, "Key Insights" in header, no takeaway line, proper body clearance
- Figure: side-by-side layout (image left/right alternating), header includes fig number
- Footer: chapter name left + page right, "N of total" format
- Header/body: 0.3" minimum clearance guaranteed
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import ClassVar

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import PP_ALIGN
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

# Chinese number words for divider subtitle
_ZH_NUMS = ["一","二","三","四","五","六","七","八","九","十",
             "十一","十二","十三","十四","十五","十六","十七","十八","十九","二十"]


class PptxRenderer(Renderer):
    extension: ClassVar[str] = "pptx"

    def __init__(self, summaries: dict | None = None,
                 template_path: Path | None = None,
                 presenter: str | None = None,
                 affiliation: str | None = None,
                 subtitle: str | None = None):
        self.summaries = summaries
        self.template_path = template_path
        self.presenter = presenter or "Paper2MD Auto-Analysis"
        self.affiliation = affiliation or "Scientific Paper Deep Analysis"
        self.subtitle = subtitle
        self._ch: int = -1          # chapter index, incremented on each divider
        self._fig_idx: int = 0      # figure counter for alternating layout
        self._cur_chapter: str = "" # current chapter heading for footer

    def render(self, doc: Document, out_path: Path) -> None:
        deck = SlidePlanner(lang=doc.lang).plan(doc, self.summaries)
        if self.template_path is not None:
            prs = Presentation(str(self.template_path))
        else:
            prs = Presentation()
            prs.slide_width, prs.slide_height = _T.W, _T.H
        total = len(deck.slides)
        self._ch = -1
        self._fig_idx = 0
        self._cur_chapter = ""
        # Build heading → 0-based chapter index lookup for §N tracking
        self._ch_idx: dict[str, int] = {
            ch.heading: i for i, ch in enumerate(doc.chapters)
        }
        for idx, slide in enumerate(deck.slides, 1):
            self._dispatch(prs, slide, idx, total, doc)
        prs.save(str(out_path))

    def _dispatch(self, prs, slide, idx, total, doc):
        kw = dict(idx=idx, total=total, doc=doc)
        if   slide.kind == "title":   self._title(prs, slide, **kw)
        elif slide.kind == "outline": self._outline(prs, slide, **kw)
        elif slide.kind == "divider":
            self._ch += 1
            self._cur_chapter = slide.title
            self._divider(prs, slide, **kw)
        elif slide.kind == "figure":
            self._figure(prs, slide, **kw)
            self._fig_idx += 1
        else:
            if slide.kind == "bullets":
                self._cur_chapter = slide.title
            self._bullets(prs, slide, **kw)

    # ── slide builders ─────────────────────────────────────────────────────────

    def _title(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_TITLE))
        _bg(s)
        T = _T
        title_len = len(slide.title)
        title_pt = 30 if title_len < 60 else (26 if title_len < 100 else 22)

        # --- Big title: centered, upper half ---
        ph = s.shapes.title
        if ph is not None:
            ph.left   = Inches(1.2)
            ph.top    = Inches(1.0)
            ph.width  = Inches(10.9)
            ph.height = Inches(2.8)
            ph.text_frame.word_wrap = True
            ph.text_frame.text = slide.title
            p = ph.text_frame.paragraphs[0]
            if p.runs:
                _run_style(p.runs[0], Pt(title_pt), True, T.TEXT, T.LAT_SERIF, T.EA_SERIF)
            p.alignment = PP_ALIGN.CENTER

        # Remove subtitle placeholder from template
        for ph2 in list(s.placeholders):
            if ph2.placeholder_format.idx == 1:
                ph2._element.getparent().remove(ph2._element); break

        # --- Thin rule below title block (centered, 3.5" wide) ---
        rule_w = Inches(3.5)
        rule_x = (_T.W - rule_w) / 2
        _line(s, rule_x, Inches(3.95), rule_x + rule_w, Inches(3.95), T.RULE, Pt(0.75))

        # --- Subtitle: from param or sensible default ---
        subtitle_text = self.subtitle or f"· {doc.lang.upper()} · A PAPER MOMENT ·"
        _tb1(s, subtitle_text,
             Inches(1.5), Inches(4.1), Inches(10.333), Inches(0.5),
             Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True, align=PP_ALIGN.CENTER)

        # --- Metadata block: centered in lower half ---
        today = datetime.date.today()
        meta_x = Inches(3.5)
        meta_w = Inches(6.333)
        meta_top = Inches(4.75)

        # PRESENTER row
        _tb1(s, "演讲者  PRESENTER",
             meta_x, meta_top, meta_w, Inches(0.3),
             Pt(10), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS, align=PP_ALIGN.LEFT)
        _tb1(s, self.presenter,
             meta_x, meta_top + Inches(0.28), meta_w, Inches(0.4),
             Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, bold=False, align=PP_ALIGN.LEFT)

        # AFFILIATION row
        aff_top = meta_top + Inches(0.75)
        _tb1(s, "单 位  AFFILIATION",
             meta_x, aff_top, meta_w, Inches(0.3),
             Pt(10), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS, align=PP_ALIGN.LEFT)
        _tb1(s, self.affiliation,
             meta_x, aff_top + Inches(0.28), meta_w, Inches(0.4),
             Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, align=PP_ALIGN.LEFT)

        # DATE row
        date_top = aff_top + Inches(0.75)
        _tb1(s, "日 期  DATE",
             meta_x, date_top, meta_w, Inches(0.3),
             Pt(10), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS, align=PP_ALIGN.LEFT)
        date_str = f"{today.year}-{today.month:02d}-{today.day:02d}"
        _tb1(s, date_str,
             meta_x, date_top + Inches(0.28), meta_w, Inches(0.4),
             Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, align=PP_ALIGN.LEFT)

        # Footer page number only on title slide (no chapter label)
        _footer(s, idx, total, chapter="")
        _notes(s, slide.notes)

    def _outline(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        # Title: 22pt serif
        _tb1(s, "目  录  ·  Contents",
             Inches(0.8), Inches(0.45), Inches(11.7), Inches(0.6),
             Pt(22), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True)
        _line(s, Inches(0.8), Inches(1.05), Inches(12.5), Inches(1.05), T.RULE, Pt(1))

        row_h = Inches(0.35)  # tighter spacing
        n = len(slide.bullets)

        if n >= 5:
            # Dense 2-column layout: col1 = first ceil(n/2) items, col2 = rest
            half = (n + 1) // 2
            for i, bul in enumerate(slide.bullets):
                col = 0 if i < half else 1
                row = i if i < half else i - half
                x_num = Inches(0.8) + col * Inches(6.3)
                x_txt = Inches(1.4) + col * Inches(6.3)
                txt_w = Inches(5.4)
                y = Inches(1.15) + row * row_h
                _tb1(s, f"{i+1:02d}", x_num, y, Inches(0.55), row_h,
                     Pt(11), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, bold=True)
                _tb1(s, bul, x_txt, y, txt_w, row_h,
                     Pt(11), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
                _line(s, x_num, y + row_h - Inches(0.02),
                      x_num + Inches(5.8), y + row_h - Inches(0.02), T.RULE, Pt(0.3))
        else:
            for i, bul in enumerate(slide.bullets):
                y = Inches(1.15) + i * row_h
                _tb1(s, f"{i+1:02d}", Inches(0.8), y, Inches(0.55), row_h,
                     Pt(13), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, bold=True)
                _tb1(s, bul, Inches(1.4), y, Inches(10.8), row_h,
                     Pt(13), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
                if i < n - 1:
                    _line(s, Inches(0.8), y + row_h - Inches(0.02),
                          Inches(12.5), y + row_h - Inches(0.02), T.RULE, Pt(0.3))

        _footer(s, idx, total, chapter="")
        _notes(s, slide.notes)

    def _divider(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        num_label = f"§{self._ch + 1}"

        # Section number — centered, gray, 18pt
        _tb1(s, num_label,
             Inches(0), Inches(2.2), Inches(13.333), Inches(0.55),
             Pt(18), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, align=PP_ALIGN.CENTER)

        # Chapter title — centered, large serif bold, 32pt
        _tb1(s, slide.title,
             Inches(1.5), Inches(2.85), Inches(10.333), Inches(1.3),
             Pt(32), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True,
             align=PP_ALIGN.CENTER, wrap=True)

        # Thin rule — centered, 4" wide
        rule_w = Inches(4.0)
        rule_x = (_T.W - rule_w) / 2
        _line(s, rule_x, Inches(4.25), rule_x + rule_w, Inches(4.25), T.RULE, Pt(1))

        # Localized subtitle: "第N章 · {heading}" or "Chapter N · {heading}"
        ch_n = self._ch + 1
        if doc.lang == "zh":
            zh_n = _ZH_NUMS[ch_n - 1] if ch_n <= len(_ZH_NUMS) else str(ch_n)
            subtitle = f"第 {zh_n} 章  ·  {slide.title}"
        else:
            subtitle = f"Chapter {ch_n}  ·  {slide.title}"

        _tb1(s, subtitle,
             Inches(1.5), Inches(4.4), Inches(10.333), Inches(0.5),
             Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True,
             align=PP_ALIGN.CENTER)

        _footer(s, idx, total, chapter=slide.title)
        _notes(s, slide.notes)

    def _bullets(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        # Use heading→index map so §N is correct even when no divider fired
        chi = self._ch_idx.get(slide.title, max(self._ch, 0))
        is_closing = slide.kind == "closing"

        # Header: include "Key Insights" / "要点" to add info beyond chapter name
        if is_closing:
            sec_label = "总结 · Conclusion"
        else:
            kw = "要点" if doc.lang == "zh" else "Key Insights"
            sec_label = f"§{chi + 1}  ·  {slide.title}  ·  {kw}"

        # Header at top (y=0.15 to 0.6)
        _tb1(s, sec_label,
             Inches(0.7), Inches(0.15), Inches(12.0), Inches(0.45),
             Pt(12), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, wrap=True)
        _line(s, Inches(0.7), Inches(0.63), Inches(12.6), Inches(0.63), T.RULE, Pt(0.75))

        # NO duplicate chapter heading line — body starts with clearance at y=0.9
        MARKERS = ["❶", "❷", "❸", "❹", "❺", "❻", "❼", "❽", "❾", "❿"]
        if slide.bullets:
            body_top = Inches(0.9)
            row_h = Inches(0.62)
            for i, bul in enumerate(slide.bullets):
                by = body_top + i * row_h
                marker = MARKERS[i] if i < len(MARKERS) else "▸"
                _tb1(s, marker, Inches(0.7), by, Inches(0.45), row_h,
                     Pt(14), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS)
                _tb1(s, bul, Inches(1.2), by, Inches(11.6), row_h,
                     Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)

        # No key takeaway line (removed per v4 spec)

        _footer(s, idx, total, chapter=self._cur_chapter)
        _notes(s, slide.notes)

    def _figure(self, prs, slide, *, idx, total, doc):
        s = prs.slides.add_slide(self._lay(prs, _IDX_BLANK))
        _bg(s)
        T = _T
        chi = self._ch_idx.get(self._cur_chapter, max(self._ch, 0))

        # Parse figure number from slide.title (e.g. "图 1: CAFE 相调控...")
        fig_num = _parse_fig_num(slide.title)
        fig_label = f"Fig. {fig_num}" if fig_num else "Fig."
        # Build header with fig number
        header_text = f"§{chi + 1}  ·  {fig_label}  ·  {_short_title(slide.title, 50)}"
        _tb1(s, header_text,
             Inches(0.7), Inches(0.15), Inches(12.0), Inches(0.45),
             Pt(12), T.TEXT_DIM, T.LAT_SERIF, T.EA_SERIF, wrap=True)
        _line(s, Inches(0.7), Inches(0.63), Inches(12.6), Inches(0.63), T.RULE, Pt(0.75))

        # Side-by-side layout: alternate image-left / image-right
        img_on_left = (self._fig_idx % 2 == 0)

        slide_w = 13.333
        margin = 0.5
        mid = slide_w / 2.0
        half_w = mid - margin          # ≈6.166"

        # Body area starts at y=0.9 (after header + 0.3" clearance)
        body_top = 0.9
        body_h   = 7.5 - body_top - 0.45  # leave room for footer

        img_area_x  = margin if img_on_left else mid
        text_area_x = mid    if img_on_left else margin

        # --- IMAGE HALF ---
        img_max_w = Inches(half_w)
        img_max_h = Inches(body_h - 0.1)
        img_top   = Inches(body_top + 0.1)

        for ip in slide.image_paths:
            if not ip.exists(): continue
            pic = s.shapes.add_picture(str(ip), Inches(img_area_x), img_top, img_max_w)
            # Scale to fit
            if pic.height > img_max_h:
                r = img_max_h / pic.height
                pic.height = img_max_h
                pic.width  = int(pic.width * r)
            if pic.width > img_max_w:
                r = img_max_w / pic.width
                pic.width  = img_max_w
                pic.height = int(pic.height * r)
            # Center image within its half
            half_center_x = Inches(img_area_x) + (img_max_w - pic.width) // 2
            half_center_y = img_top + (img_max_h - pic.height) // 2
            pic.left = int(half_center_x)
            pic.top  = int(half_center_y)
            break

        # --- TEXT HALF ---
        tx = Inches(text_area_x + 0.2)
        tw = Inches(half_w - 0.3)

        # Caption: bold serif 14pt
        caption_text = slide.title  # full "图 N: ..." string
        _tb1(s, caption_text,
             tx, Inches(body_top + 0.1), tw, Inches(0.7),
             Pt(14), T.TEXT, T.LAT_SERIF, T.EA_SERIF, bold=True, wrap=True)
        _line(s, tx, Inches(body_top + 0.85), tx + tw, Inches(body_top + 0.85), T.RULE, Pt(0.5))

        # "深度观察" label
        _tb1(s, "深度观察" if doc.lang == "zh" else "Deep Observation",
             tx, Inches(body_top + 1.0), tw, Inches(0.35),
             Pt(12), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, bold=True)

        # Observation text
        if slide.deep_observation:
            _tb1(s, slide.deep_observation,
                 tx, Inches(body_top + 1.4), tw, Inches(body_h - 1.5),
                 Pt(12), T.TEXT_DIM, T.LAT_SANS, T.EA_SANS, italic=True, wrap=True)

        _footer(s, idx, total, chapter=self._cur_chapter)
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


def _footer(s, slide_idx, total, *, chapter: str = "") -> None:
    """Footer: chapter name left + page number right."""
    T = _T
    if chapter:
        _tb1(s, f"Chapter: {chapter}",
             Inches(0.7), Inches(7.1), Inches(8.0), Inches(0.3),
             Pt(9), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS, italic=True)
    _tb1(s, f"{slide_idx} of {total}",
         Inches(11.5), Inches(7.1), Inches(1.5), Inches(0.3),
         Pt(9), T.TEXT_FAINT, T.LAT_SANS, T.EA_SANS)


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


def _parse_fig_num(title: str) -> str:
    """Extract figure number from slide title like '图 1: ...' or 'Fig. 2 ...'"""
    m = re.search(r'(?:图|Fig\.?)\s*(\d+)', title, re.IGNORECASE)
    return m.group(1) if m else ""


def _short_title(title: str, maxlen: int) -> str:
    """Truncate title, stripping the 'Fig N: ' prefix first."""
    # Remove leading "图 N: " or "Fig. N: " portion
    clean = re.sub(r'^(?:图|Fig\.?)\s*\d+[:\s]*', '', title, flags=re.IGNORECASE).strip()
    return clean[:maxlen] + ("…" if len(clean) > maxlen else "")


RENDERERS["pptx"] = PptxRenderer
