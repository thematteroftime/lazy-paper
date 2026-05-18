"""Render a Document to a single self-contained HTML file with base64 images."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, select_autoescape

from stages.s09_render.model import Document, FigureBlock
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


class HtmlRenderer(Renderer):
    extension: ClassVar[str] = "html"

    def render(self, doc: Document, out_path: Path) -> None:
        html = self.render_to_string(doc)
        Path(out_path).write_text(html, encoding="utf-8")

    def render_to_string(self, doc: Document) -> str:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )
        env.globals["block_images"] = self._block_images
        styles = (_TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")
        template = env.get_template("preview.html.j2")
        return template.render(doc=doc, styles=styles)

    @staticmethod
    def _block_images(block: FigureBlock) -> list[str]:
        out: list[str] = []
        for img_path in block.image_paths:
            if not img_path.exists():
                continue
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp",
                    "gif": "gif"}.get(img_path.suffix.lstrip(".").lower(), "jpeg")
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            out.append(f"data:image/{mime};base64,{b64}")
        return out


RENDERERS["html"] = HtmlRenderer
