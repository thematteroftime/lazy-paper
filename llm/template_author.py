"""Template author (v1.15): user idea -> question-driven outline docx.

Drafts an s05-compatible outline docx for ONE paper: cheap prescan (pdfplumber
or existing run artifacts) + one text-LLM call + deterministic docx writer.
The generated docx round-trips losslessly through s05's parser because only
manually numbered lines ("1 Title") become headings there — every question is
a plain paragraph and lands in `guidance` (s05 treats "?"-ending lines as
guidance by rule).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber
import yaml

from llm.client import LLM
from stages._common import load_yaml, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "template_author.md"

# Mirror of s05's _NUMBERED_RE (stages/s05_template/runner.py): lines matching
# this would be promoted to headings, so questions must never match it.
_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\s+(.+?)\s*$")
_LEADING_NUM_RE = re.compile(r"^\s*\d+(?:\.\d+){0,2}[.)]?\s+")
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def prescan_pdf(pdf: Path, *, max_pages: int = 4, max_chars: int = 6000) -> str:
    """Cheap text-layer extraction (no OCR API). Good enough for title/abstract."""
    parts: list[str] = []
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise SystemExit(
            f"prescan: no text layer in {pdf} — run s01 OCR first and use --run instead")
    return text[:max_chars]


def prescan_run(run_dir: Path, *, max_chars: int = 6000) -> str:
    """Digest from existing run artifacts: context > chapters > captions > OCR head."""
    parts: list[str] = []
    ctx_path = run_dir / "s06_context" / "context.yaml"
    if ctx_path.exists():
        ctx = load_yaml(ctx_path) or {}
        parts.append(yaml.safe_dump(ctx, allow_unicode=True, sort_keys=False))
    idx_path = run_dir / "s03_chapter" / "chapter_index.yaml"
    if idx_path.exists():
        chapters = (load_yaml(idx_path) or {}).get("chapters") or []
        titles = [str(c.get("title", "")) for c in chapters if c.get("title")]
        if titles:
            parts.append("Chapter titles: " + " | ".join(titles))
    figs_path = run_dir / "s04_figures" / "figures.yaml"
    if figs_path.exists():
        figs = load_yaml(figs_path) or []
        captions = [f"{f.get('fig_id', '')}: {f.get('caption', '')}"
                    for f in figs if f.get("caption")][:15]
        if captions:
            parts.append("Figure captions:\n" + "\n".join(captions))
    docs = sorted((run_dir / "s02_clean").glob("doc_*.md"))
    if docs:
        parts.append(docs[0].read_text(encoding="utf-8")[:2500])
    digest = "\n\n".join(p for p in parts if p.strip()).strip()
    if not digest:
        raise SystemExit(
            f"prescan: no usable artifacts under {run_dir} "
            f"(need any of s06 context.yaml / s03 chapter_index.yaml / "
            f"s04 figures.yaml / s02 doc_*.md)")
    return digest[:max_chars]
