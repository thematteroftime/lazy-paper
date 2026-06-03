"""Render a Document to a self-contained HTML file with base64 images.

Inline / display math becomes ``<span class="math-inline" data-tex="…">``
so KaTeX picks it up in the browser; a Unicode fallback inside each span
keeps WeasyPrint (no JS) readable. Bold ``**…**`` → ``<strong>``;
``[span:…]`` citation markers → superscript links into the
``<section class="sources-footer">`` populated by a two-pass template render.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from llm.citation import CitationMode
from stages._common.images import image_to_data_url
from stages.s09_render._math import iter_html_runs, normalize_math
from stages.s09_render.model import Document, FigureBlock
from stages.s09_render.renderers import RENDERERS
from stages.s09_render.renderers.base import Renderer


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_KATEX_DIR = _TEMPLATE_DIR / "vendor" / "katex"

# Span-marker pattern (mirrors llm.citation._MARKER).
_SPAN = re.compile(r"\[span:([^:\]]+):(\d+)-(\d+)\]")

# Long-formula heuristic: math-auto if structurally heavy or longer than 40
# chars, so the in-browser JS promotes it to a display block.
_LONG_MATH_RE = re.compile(r"\\(?:frac|dfrac|sum|int|prod|bigg|Big)\b")


def _is_long_math(tex: str) -> bool:
    return bool(_LONG_MATH_RE.search(tex)) or len(tex) > 40


def _fallback_unicode(tex: str) -> str:
    """Unicode rendering of *tex* for non-JS viewers; KaTeX overwrites this."""
    return normalize_math(tex, mark_inline=False)


# ──────────────────────────── KaTeX asset packaging ────────────────────────────

_KATEX_FONT_RE = re.compile(
    r"url\((fonts/(KaTeX_[A-Za-z0-9_-]+\.woff2))\)\s*format\(['\"]?woff2['\"]?\)"
)
_KATEX_NON_WOFF2_SRC_RE = re.compile(
    r",\s*url\(fonts/KaTeX_[A-Za-z0-9_-]+\.(?:woff|ttf)\)\s*format\(['\"]?(?:woff|truetype)['\"]?\)"
)


def _load_inline_katex_assets() -> tuple[str, str] | None:
    """Return (css, js) with woff2 fonts base64-inlined as ``data:`` URIs, or
    ``None`` when the vendor dir is missing. KaTeX's CSS also references
    .woff / .ttf fallbacks that would 404 in an offline file — strip them.
    """
    css_path = _KATEX_DIR / "katex.min.css"
    js_path = _KATEX_DIR / "katex.min.js"
    fonts_dir = _KATEX_DIR / "fonts"
    if not css_path.exists() or not js_path.exists() or not fonts_dir.exists():
        return None

    css = css_path.read_text(encoding="utf-8")

    def _inline_font(m: re.Match[str]) -> str:
        rel = m.group(1)  # "fonts/KaTeX_Main-Regular.woff2"
        fpath = _KATEX_DIR / rel
        if not fpath.exists():
            return m.group(0)
        b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
        return f"url(data:font/woff2;base64,{b64}) format('woff2')"

    css = _KATEX_FONT_RE.sub(_inline_font, css)
    # Drop dangling woff / ttf src() entries — they'd 404 in an offline file.
    css = _KATEX_NON_WOFF2_SRC_RE.sub("", css)

    js = js_path.read_text(encoding="utf-8")
    return css, js


def _katex_inline_enabled() -> bool:
    raw = os.environ.get("LAZY_PAPER_INLINE_KATEX", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class HtmlRenderer(Renderer):
    """HTML output with clickable per-claim citation anchors by default."""

    extension: ClassVar[str] = "html"

    def __init__(self, *, citation_mode: CitationMode = CitationMode.HYPERLINK, **kwargs):
        env_mode = os.environ.get("LAZY_PAPER_HTML_CITATIONS", "").strip().lower()
        env_override = {"remove": CitationMode.REMOVE,
                        "keep": CitationMode.KEEP,
                        "hyperlink": CitationMode.HYPERLINK}.get(env_mode)
        # CLI --debug-citations (KEEP) wins over the env override.
        effective = (CitationMode.KEEP if citation_mode == CitationMode.KEEP
                     else env_override or citation_mode)
        super().__init__(citation_mode=effective, **kwargs)
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
        bundle = _load_inline_katex_assets() if _katex_inline_enabled() else None
        ctx = dict(
            doc=doc, styles=styles, sources=[],
            katex_inline=bundle is not None,
            katex_css_inline=Markup(bundle[0] if bundle else ""),
            katex_js_inline=Markup(bundle[1] if bundle else ""),
        )
        template = env.get_template("preview.html.j2")
        # Two-pass: pass 1 populates _cite_registry as a side effect, pass 2
        # emits sources.
        template.render(**ctx)
        ctx["sources"] = self._sources_list()
        return template.render(**ctx)

    # ────────────────────────── paragraph rendering ──────────────────────────

    def _render_paragraph(self, raw_text: str) -> Markup:
        """Split raw LLM text on ``**bold**`` / inline / display LaTeX, emit
        ``<strong>`` / ``<span data-tex>`` / ``<figure class="formula-block">``;
        process citation markers inside plain segments.
        """
        out: list[str] = []
        for kind, payload in iter_html_runs(raw_text or ""):
            if kind == "plain":
                out.append(self._render_plain_with_citations(payload))
            elif kind == "bold":
                # Bold body may itself contain citations / math — recurse one level.
                inner = self._render_plain_with_citations(payload)
                out.append(f"<strong>{inner}</strong>")
            elif kind == "math_inline":
                out.append(self._render_inline_math(payload))
            elif kind == "math_display":
                out.append(self._render_display_math(payload))
        return Markup("".join(out))

    def _render_plain_with_citations(self, text: str) -> str:
        if self.citation_mode == CitationMode.KEEP:
            return str(escape(text))
        if self.citation_mode == CitationMode.REMOVE:
            return str(escape(_SPAN.sub("", text)))
        # HYPERLINK
        chunks: list[str] = []
        pos = 0
        for m in _SPAN.finditer(text):
            if m.start() > pos:
                chunks.append(str(escape(text[pos:m.start()])))
            doc_id, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            n = self._register_cite((doc_id, start, end))
            chunks.append(
                f'<sup class="cite-anchor"><a href="#cite-{n}" '
                f'title="{escape(doc_id)}:{start}-{end}">[{n}]</a></sup>'
            )
            pos = m.end()
        if pos < len(text):
            chunks.append(str(escape(text[pos:])))
        return "".join(chunks)

    @staticmethod
    def _render_inline_math(tex: str) -> str:
        cls = "math-auto" if _is_long_math(tex) else "math-inline"
        fallback = escape(_fallback_unicode(tex))
        return (f'<span class="{cls}" data-tex="{escape(tex)}">{fallback}</span>')

    @staticmethod
    def _render_display_math(tex: str) -> str:
        # Display math gets its own block + copy-on-click affordances.
        fallback = escape(_fallback_unicode(tex))
        chip = '</> click to copy'
        return (
            f'<figure class="formula-block" data-tex="{escape(tex)}">'
            f'<div class="math-fallback">{fallback}</div>'
            f'<span class="tex-chip">{chip}</span>'
            f'</figure>'
        )

    # ────────────────────────── citation registry ──────────────────────────

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
