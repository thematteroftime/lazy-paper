"""Stage 09: build the Document model and render to one or more formats."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

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

DEFAULT_FORMATS = ("docx", "pdf", "html")


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview", lang: str = "zh",
        formats: Iterable[str] | None = None,
        pptx_bullets: str = "llm") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_md = _read_chapters(Path(compose_dir))
    fig_notes = _read_fig_notes(Path(fig_notes_dir))
    doc = DocumentBuilder(lang=lang, paper_title=paper_title).build(chapters_md, fig_notes)

    requested = list(formats) if formats is not None else list(DEFAULT_FORMATS)
    summaries = _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir)

    results: dict[str, str] = {}
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        if fmt == "pptx":
            renderer = RENDERERS[fmt](summaries=summaries)
        else:
            renderer = RENDERERS[fmt]()
        renderer.render(doc, out_path)
        results[fmt] = str(out_path)

    bundle = _write_bundle(Path(compose_dir), fig_notes, out_dir)
    pptx_state = _pptx_state(summaries, requested, pptx_bullets)

    mark_done(out_dir, {
        "formats": results,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
        "pptx_summarizer": pptx_state,
    })
    return {"preview_files": results, "bundle": str(bundle),
            "pptx_summarizer": pptx_state}


def _maybe_summarize_for_pptx(doc, requested, pptx_bullets, out_dir):
    if "pptx" not in requested or pptx_bullets != "llm":
        return None
    from llm.client import LLM
    from stages.s09_render.pptx_summarizer import PptxSummarizer
    llm = LLM("text")
    summarizer = PptxSummarizer(llm=llm, cache_dir=out_dir / "llm_cache", lang=doc.lang)
    return summarizer.summarize(doc)


def _pptx_state(summaries, requested, pptx_bullets) -> str:
    if "pptx" not in requested:
        return "not_requested"
    if pptx_bullets != "llm":
        return "rule"
    return "ok" if summaries is not None else "degraded"


def _read_chapters(compose_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted((compose_dir / "chapters").glob("*.md"))}


def _read_fig_notes(fig_notes_dir: Path) -> list[dict]:
    path = fig_notes_dir / "fig_notes.yaml"
    return load_yaml(path) or []


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
