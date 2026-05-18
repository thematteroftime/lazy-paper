"""Stage 09: build the Document model and render to one or more formats.

Default formats are docx + the mypaper_bundle (legacy contract). HTML/PDF/PPTX
are added in later milestones and exposed via the `formats` parameter."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from stages._common import load_yaml, mark_done
from stages.s09_render.builder import DocumentBuilder
from stages.s09_render.renderers import RENDERERS

# Import side-effect: each renderer module registers itself in RENDERERS.
# Import here (not in __init__.py) to keep the module graph explicit.
import stages.s09_render.renderers.docx  # noqa: F401
import stages.s09_render.renderers.html  # noqa: F401


BUNDLE_README = """\
# mypaper bundle

Drop this folder's contents into mypaper/ to render the styled thesis:

    cp -r chapters/* /path/to/mypaper/chapters/
    cp -r figures/*  /path/to/mypaper/figures/
    cd /path/to/mypaper && uv run python scripts/build.py

The README of mypaper has the full template-swap instructions.
"""


def run(*, compose_dir: Path, fig_notes_dir: Path, out_dir: Path,
        paper_title: str = "Paper Preview", lang: str = "zh",
        formats: Iterable[str] | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_md = _read_chapters(Path(compose_dir))
    fig_notes = _read_fig_notes(Path(fig_notes_dir))
    doc = DocumentBuilder(lang=lang, paper_title=paper_title).build(chapters_md, fig_notes)

    requested = list(formats) if formats is not None else ["docx"]
    results: dict[str, str] = {}
    for fmt in requested:
        if fmt not in RENDERERS:
            raise ValueError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}")
        out_path = out_dir / f"preview.{fmt}"
        RENDERERS[fmt]().render(doc, out_path)
        results[fmt] = str(out_path)

    bundle = _write_bundle(Path(compose_dir), fig_notes, out_dir)

    mark_done(out_dir, {
        "formats": results,
        "bundle_chapters": len(list((bundle / "chapters").glob("*.md"))),
        "bundle_figures": len(list((bundle / "figures").glob("*"))),
    })
    return {"preview_files": results, "bundle": str(bundle)}


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
    # Clear stale files from prior runs
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
