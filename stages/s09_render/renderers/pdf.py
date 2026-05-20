"""Render PDF by running the HtmlRenderer output through WeasyPrint."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import weasyprint

from stages.s09_render.model import Document
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer
from stages.s09_render.renderers.html import HtmlRenderer


class PdfRenderer(Renderer):
    extension: ClassVar[str] = "pdf"

    def render(self, doc: Document, out_path: Path) -> None:
        html_str = HtmlRenderer(citation_mode=self.citation_mode).render_to_string(doc)
        weasyprint.HTML(string=html_str).write_pdf(target=str(out_path))


RENDERERS["pdf"] = PdfRenderer
