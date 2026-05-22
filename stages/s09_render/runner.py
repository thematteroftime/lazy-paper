"""Stage 09: build the Document model and render to one or more formats."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Iterable

from llm.citation import CitationMode
from stages._common import load_yaml, mark_done
from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.renderers import RENDERERS

# Renderer registration side-effects:
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401
import stages.s09_render.renderers.pdf   # noqa: F401
import stages.s09_render.renderers.pptx  # noqa: F401


BUNDLE_README = """\
# mypaper bundle

Drop this folder's contents into mypaper/ to render the styled thesis:

    cp -r chapters/* /path/to/mypaper/chapters/
    cp -r figures/*  /path/to/mypaper/figures/
    cd /path/to/mypaper && uv run python scripts/build.py

The README of mypaper has the full template-swap instructions.
"""

DEFAULT_FORMATS = ("docx", "pdf", "html", "pptx")


class _ContextResolver:
    def __init__(self, context_dir: Path | None):
        self._ctx: dict = {}
        if context_dir is not None:
            path = Path(context_dir) / "context.yaml"
            if path.exists():
                try:
                    self._ctx = load_yaml(path) or {}
                except Exception as exc:
                    # Context is best-effort metadata for the renderer;
                    # fall through with fallbacks rather than crash.
                    print(f"[s09] context.yaml unreadable: {exc!r}",
                          flush=True)

    def title(self, fallback: str) -> str:
        t = self._ctx.get("title")
        if isinstance(t, str) and t.strip():
            return t.strip()
        return fallback

    def subtitle(self, override: str | None) -> str | None:
        if override:
            return override
        keywords = self._ctx.get("keywords") or []
        if not isinstance(keywords, list) or not keywords:
            return None
        top = [str(k).strip() for k in keywords[:3] if k]
        if not top:
            return None
        return "·  " + "  ·  ".join(top) + "  ·"


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview", lang: str = "zh",
        formats: Iterable[str] | None = None,
        pptx_bullets: str = "llm",
        context_dir: Path | None = None,
        pptx_template: Path | None = None,
        presenter: str | None = None,
        affiliation: str | None = None,
        pptx_subtitle: str | None = None,
        citation_mode: CitationMode | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_md = _read_chapters(Path(compose_dir))
    fig_notes = _read_fig_notes(Path(fig_notes_dir))
    ctx = _ContextResolver(context_dir)
    doc = DocumentBuilder(lang=lang, paper_title=ctx.title(paper_title)).build(chapters_md, fig_notes)

    requested = list(formats) if formats is not None else list(DEFAULT_FORMATS)
    summaries, outline, paper_brief = _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir, context_dir=context_dir)

    results: dict[str, object] = {}
    partial = False
    resolved_subtitle = ctx.subtitle(pptx_subtitle)
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        try:
            # Per-format default citation_mode (audit β#1: HtmlRenderer's
            # docstring promises HYPERLINK; runner used to force REMOVE
            # for all formats, silently stripping HTML citations.) When
            # the caller passes citation_mode explicitly (e.g. KEEP via
            # --debug-citations), that wins. Each renderer can further
            # override its own default via env (e.g. HtmlRenderer
            # honors LAZY_PAPER_HTML_CITATIONS).
            if citation_mode is not None:
                effective_mode = citation_mode
            elif fmt == "html":
                effective_mode = CitationMode.HYPERLINK
            else:
                effective_mode = CitationMode.REMOVE
            if fmt == "pptx":
                renderer = RENDERERS[fmt](summaries=summaries,
                                         outline=outline,
                                         paper_brief=paper_brief,
                                         template_path=pptx_template,
                                         presenter=presenter,
                                         affiliation=affiliation,
                                         subtitle=resolved_subtitle)
            else:
                renderer = RENDERERS[fmt](citation_mode=effective_mode)
            renderer.render(doc, out_path)
            results[fmt] = str(out_path)
        except Exception as exc:
            partial = True
            # Persist a compact error so done.yaml stays small and doesn't
            # leak prompt fragments or URLs from upstream HTTP excs.
            results[fmt] = {
                "error": f"{type(exc).__name__}: {str(exc)[:200]}"
            }
            print(f"[s09_render] WARNING: {fmt} render failed: {exc}. "
                  f"Other formats continue.", file=sys.stderr, flush=True)

    if requested and all(isinstance(v, dict) and "error" in v for v in results.values()):
        # All requested renderers failed — surface as a hard failure so the CLI
        # exits non-zero and downstream agents can react.
        errors = "; ".join(f"{k}: {v['error']}" for k, v in results.items())
        raise RuntimeError(f"All requested formats failed: {errors}")

    bundle = _write_bundle(Path(compose_dir), fig_notes, out_dir)
    pptx_state = _pptx_state(summaries, outline, paper_brief, requested, pptx_bullets)

    mark_done(out_dir, {
        "formats": results,
        "partial": partial,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
        "pptx_summarizer": pptx_state,
    })
    return {
        "preview_files": results,
        "bundle": str(bundle),
        "pptx_summarizer": pptx_state,
        "partial": partial,
    }


def _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir,
                               context_dir=None):
    if "pptx" not in requested or pptx_bullets != "llm":
        return None, None, None
    from llm.client import LLM
    from stages.s09_render.pptx_summarizer import PptxSummarizer
    llm = LLM("text")
    summarizer = PptxSummarizer(llm=llm, cache_dir=out_dir / "llm_cache",
                                lang=doc.lang, context_dir=context_dir)
    # v11 two-pass approach: outline first (cheap), then summaries with context
    outline = summarizer.summarize_outline(doc)
    summaries = summarizer.summarize(doc, outline=outline)
    paper_brief = summarizer.summarize_paper(doc)
    return summaries, outline, paper_brief


def _pptx_state(summaries, outline, paper_brief, requested, pptx_bullets) -> str:
    if "pptx" not in requested:
        return "not_requested"
    if pptx_bullets != "llm":
        return "rule"
    return "ok" if summaries is not None else "degraded"


def _read_chapters(compose_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted((compose_dir / "chapters").glob("*.md"))}


def _read_fig_notes(fig_notes_dir: Path) -> list[dict]:
    """Load figure-analysis notes, recovering text fields from `raw` when
    the YAML parse failed (v1.3.3: prevents blank figure slides).

    s07 stores `error: 'yaml-parse: defensive parse failed'` + `raw: <text>`
    when the vision-LLM output couldn't be parsed cleanly (often because
    of stray LaTeX). The text fields are still inside `raw`; extract them
    with a regex so the slide planner has captions / observations to show.
    """
    import re as _re
    path = fig_notes_dir / "fig_notes.yaml"
    notes = load_yaml(path) or []
    recovered = []
    for n in notes:
        if not isinstance(n, dict):
            continue
        if n.get("error") and n.get("raw") and not n.get("deep_observation"):
            raw = n["raw"]
            # Recover key text fields with line-anchored regex (DOTALL so
            # multi-line values are captured up to the next `field:` line).
            for key in ("caption", "deep_observation", "visual_summary"):
                m = _re.search(
                    rf"^{key}:\s*(.+?)(?=\n[a-z_]+:|\Z)", raw, _re.MULTILINE | _re.DOTALL,
                )
                if m and not n.get(key):
                    n[key] = m.group(1).strip().strip('"').strip()
        recovered.append(n)
    return recovered


def _write_bundle(compose_dir: Path, fig_notes: list[dict], out_dir: Path) -> Path:
    bundle = out_dir / "mypaper_bundle"
    (bundle / "chapters").mkdir(parents=True, exist_ok=True)
    (bundle / "figures").mkdir(exist_ok=True)
    for stale in (bundle / "chapters").glob("*.md"):
        stale.unlink()
    for stale in (bundle / "figures").iterdir():
        if stale.is_file():
            stale.unlink()
    for md in (compose_dir / "chapters").glob("*.md"):
        shutil.copy2(md, bundle / "chapters" / md.name)
    for note in fig_notes:
        paths = list(note.get("image_paths") or [])
        if note.get("image_abs_path"):
            paths.append(note["image_abs_path"])
        for p in paths:
            ap = Path(p)
            if ap.exists():
                shutil.copy2(ap, bundle / "figures" / ap.name)
    (bundle / "README.md").write_text(BUNDLE_README, encoding="utf-8")
    return bundle
