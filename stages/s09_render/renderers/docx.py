"""Render a Document to .docx using python-docx. Class-organized port of the
original _render_preview_docx from the legacy runner.py."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from stages.s09_render.model import Chapter, Document, FigureBlock, Paragraph, TableBlock
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


class DocxRenderer(Renderer):
    extension: ClassVar[str] = "docx"

    TITLE_PT = 16
    HEADING_PT = 14
    CAPTION_PT = 9

    def render(self, doc: Document, out_path: Path) -> None:
        body_pt = 10.5 if doc.lang == "zh" else 11
        img_cm = 13 if doc.lang == "zh" else 14
        set_ea = (doc.lang == "zh")

        out_doc = DocxDocument()
        sec = out_doc.sections[0]
        sec.top_margin = sec.bottom_margin = Cm(2.0)
        sec.left_margin = sec.right_margin = Cm(2.2)

        self._write_title(out_doc, doc.paper_title, set_ea)
        for chapter in doc.chapters:
            self._write_chapter(out_doc, chapter, body_pt, img_cm, set_ea, doc.lang)

        out_doc.save(out_path)

    # ---------- chapter / block writers ----------

    def _write_chapter(self, out, chapter: Chapter, body_pt: float,
                       img_cm: float, set_ea: bool, lang: str) -> None:
        self._write_heading(out, chapter.heading, set_ea)
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                self._write_paragraph(out, block.text, body_pt, set_ea)
            elif isinstance(block, FigureBlock):
                self._write_figure_block(out, block, img_cm, set_ea, lang)
            elif isinstance(block, TableBlock):
                self._write_table_block(out, block, set_ea)

    def _write_title(self, out, title: str, set_ea: bool) -> None:
        p = out.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._apply_cn_font(p.add_run(title), size=self.TITLE_PT, bold=True, set_ea=set_ea)

    def _write_heading(self, out, heading: str, set_ea: bool) -> None:
        try:
            p = out.add_paragraph(heading, style="Heading 1")
        except KeyError:
            p = out.add_paragraph(heading)  # fallback if style missing
        if set_ea:
            for run in p.runs:
                self._apply_cn_font(run, size=self.HEADING_PT, bold=True, set_ea=True)

    def _write_paragraph(self, out, text: str, body_pt: float, set_ea: bool) -> None:
        p = out.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.74)
        self._apply_cn_font(p.add_run(text), size=body_pt, set_ea=set_ea)

    def _write_figure_block(self, out, block: FigureBlock,
                            img_cm: float, set_ea: bool, lang: str) -> None:
        paths = [p for p in block.image_paths if p.exists()]
        if not paths:
            return
        for img_path in paths:
            ip = out.add_paragraph()
            ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ip.add_run().add_picture(str(img_path), width=Cm(img_cm))
        cap = out.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._apply_cn_font(
            cap.add_run(f"{block.label}. {block.caption}"),
            size=self.CAPTION_PT, bold=True, set_ea=set_ea,
        )
        if block.deep_observation:
            prefix = "【深度观察】" if lang == "zh" else "Deep observation: "
            obs = out.add_paragraph()
            self._apply_cn_font(
                obs.add_run(f"{prefix}{block.deep_observation}"),
                size=self.CAPTION_PT, color=(0x33, 0x33, 0x66), set_ea=set_ea,
            )

    def _write_table_block(self, out, block: TableBlock, set_ea: bool) -> None:
        n_cols = len(block.headers)
        if n_cols == 0:
            return
        n_rows = 1 + len(block.rows)
        try:
            table = out.add_table(rows=n_rows, cols=n_cols, style="Light Grid")
        except KeyError:
            table = out.add_table(rows=n_rows, cols=n_cols)
        # Header row
        for j, h in enumerate(block.headers):
            cell = table.rows[0].cells[j]
            cell.text = h
            if cell.paragraphs:
                run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(h)
                run.bold = True
        # Data rows
        for i, row in enumerate(block.rows):
            for j, c in enumerate(row):
                if j < n_cols:
                    table.rows[i + 1].cells[j].text = c

    # ---------- font helper ----------

    @staticmethod
    def _apply_cn_font(run, *, size: float, bold: bool = False,
                       color: tuple[int, int, int] | None = None,
                       set_ea: bool = True) -> None:
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        run.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        if set_ea:
            rPr = run._element.get_or_add_rPr()
            rf = rPr.find(qn("w:rFonts"))
            if rf is None:
                rf = OxmlElement("w:rFonts")
                rPr.append(rf)
            rf.set(qn("w:eastAsia"), "宋体")
            rf.set(qn("w:ascii"), "Times New Roman")
            rf.set(qn("w:hAnsi"), "Times New Roman")


RENDERERS["docx"] = DocxRenderer
