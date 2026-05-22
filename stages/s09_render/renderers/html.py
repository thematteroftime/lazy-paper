"""Render a Document to a single self-contained HTML file with base64 images."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from llm.citation import CitationMode
from stages._common.images import image_to_data_url
from stages.s09_render.model import Document, FigureBlock
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# Span-marker pattern (mirrors llm.citation._MARKER).
_SPAN = re.compile(r"\[span:([^:\]]+):(\d+)-(\d+)\]")


class HtmlRenderer(Renderer):
    """HTML output with clickable per-claim citation anchors by default.

    The verifier in v1.8.1+ already validates every quote against its
    source span; HYPERLINK mode surfaces that effort to the reader as a
    superscript link that jumps to a `Sources` footer. Disable with
    `LAZY_PAPER_HTML_CITATIONS=remove` to fall back to plain prose, or
    pass `--debug-citations` to keep the raw `[span:...]` markers.
    """

    extension: ClassVar[str] = "html"

    def __init__(self, *, citation_mode: CitationMode = CitationMode.HYPERLINK, **kwargs):
        # HTML default is HYPERLINK (the parameter default reflects that).
        # Precedence when resolving the effective mode:
        #   1. CLI `--debug-citations` is honored — caller passes KEEP.
        #   2. env `LAZY_PAPER_HTML_CITATIONS=remove|keep|hyperlink` overrides.
        #   3. Caller's explicit citation_mode wins over the default.
        #   4. Else HYPERLINK.
        # `.strip()` first so trailing whitespace from .env files doesn't
        # silently break the override (audit β#2).
        env_mode = os.environ.get("LAZY_PAPER_HTML_CITATIONS", "").strip().lower()
        if citation_mode == CitationMode.KEEP:
            effective = CitationMode.KEEP
        elif env_mode == "remove":
            effective = CitationMode.REMOVE
        elif env_mode == "keep":
            effective = CitationMode.KEEP
        elif env_mode == "hyperlink":
            effective = CitationMode.HYPERLINK
        else:
            effective = citation_mode
        super().__init__(citation_mode=effective, **kwargs)
        # Per-render citation registry, populated by _render_paragraph and
        # consumed by the template footer.
        self._cite_registry: dict[tuple[str, int, int], int] = {}

    def render(self, doc: Document, out_path: Path) -> None:
        html = self.render_to_string(doc)
        Path(out_path).write_text(html, encoding="utf-8")

    def render_to_string(self, doc: Document) -> str:
        self._cite_registry = {}
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )
        env.globals["block_images"] = self._block_images
        env.globals["render_paragraph"] = self._render_paragraph
        styles = (_TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")
        template = env.get_template("preview.html.j2")
        # Two-pass render: the first pass walks every paragraph via
        # _render_paragraph, which populates self._cite_registry as a
        # side effect. The result is discarded; the second pass uses
        # the now-populated registry to emit the sources footer.
        # Render is sub-100ms, so the cost is acceptable.
        template.render(doc=doc, styles=styles, sources=[])
        return template.render(doc=doc, styles=styles, sources=self._sources_list())

    def _render_paragraph(self, text: str) -> Markup:
        """Render paragraph text, converting span markers to anchor markup
        when in HYPERLINK mode and tracking the citation registry."""
        if self.citation_mode == CitationMode.KEEP:
            return Markup(escape(text))
        if self.citation_mode == CitationMode.REMOVE:
            return Markup(escape(_SPAN.sub("", text)))
        # HYPERLINK
        out: list[str] = []
        pos = 0
        for m in _SPAN.finditer(text):
            if m.start() > pos:
                out.append(str(escape(text[pos:m.start()])))
            doc_id, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            n = self._register_cite((doc_id, start, end))
            out.append(
                f'<sup class="cite-anchor"><a href="#cite-{n}" '
                f'title="{escape(doc_id)}:{start}-{end}">[{n}]</a></sup>'
            )
            pos = m.end()
        if pos < len(text):
            out.append(str(escape(text[pos:])))
        return Markup("".join(out))

    def _register_cite(self, key: tuple[str, int, int]) -> int:
        n = self._cite_registry.get(key)
        if n is not None:
            return n
        n = len(self._cite_registry) + 1
        self._cite_registry[key] = n
        return n

    def _sources_list(self) -> list[dict]:
        return [
            {"n": n, "doc_id": k[0], "start": k[1], "end": k[2]}
            for k, n in sorted(self._cite_registry.items(), key=lambda kv: kv[1])
        ]

    @staticmethod
    def _block_images(block: FigureBlock) -> list[str]:
        return [image_to_data_url(p) for p in block.image_paths if p.exists()]


RENDERERS["html"] = HtmlRenderer
