"""Generate PPT bullets and figure observations via the text LLM.

Caches per-chapter results: if the chapter's input hash matches the cached one,
the LLM is not called. Always writes prompt/response files alongside the cache
for auditability.

v7 additions:
- summarize_outline(): group chapters into 4-5 high-level sections
- summarize_paper(): produce rich 5-7-bullet closing summary + take-away

v9 additions:
- figure_observations replaces figure_one_liners (2-3 points per figure)
- Legacy cache compatibility: old figure_one_liners auto-converted
- _PROMPT_VERSION constants invalidate old caches on prompt changes
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stages._common.paths import slugify
from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


_MAX_RETRIES = 3
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_summarize.md"
_OUTLINE_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_outline.md"
_PAPER_SUMMARY_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_paper_summary.md"

# Bump these constants to invalidate old caches when prompts change.
_CHAPTER_PROMPT_VERSION = "v9-figure-observations"
_OUTLINE_PROMPT_VERSION = "v9-unicode-math"
_PAPER_PROMPT_VERSION = "v9-unicode-math"


def _normalize_chapter_summary(payload: dict) -> dict:
    """Ensure payload uses figure_observations (list-per-fig) format.

    Legacy caches produced figure_one_liners: {fig_id: str}.
    Convert those to figure_observations: {fig_id: [str]} for backward compat.
    """
    if "figure_observations" not in payload and "figure_one_liners" in payload:
        payload["figure_observations"] = {
            fid: [obs]
            for fid, obs in payload["figure_one_liners"].items()
        }
    # If neither key, add empty dict
    if "figure_observations" not in payload:
        payload["figure_observations"] = {}
    return payload


class PptxSummarizer:
    """LLM-backed summarizer with double-track cache (audit + reuse)."""

    def __init__(self, llm, cache_dir: Path, lang: str):
        self.llm = llm
        self.cache_dir = Path(cache_dir)
        self.lang = lang
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")
        self._outline_template = _OUTLINE_PROMPT_PATH.read_text(encoding="utf-8")
        self._paper_summary_template = _PAPER_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")

    def summarize(self, doc: Document) -> dict | None:
        """Returns {chapter_heading: {bullets, figure_one_liners}} or None on
        total failure (3 consecutive LLM errors on the same chapter)."""
        out: dict[str, dict] = {}
        for chapter in doc.chapters:
            chapter_out = self._summarize_chapter(chapter)
            if chapter_out is None:
                return None
            out[chapter.heading] = chapter_out
        return out

    def summarize_outline(self, doc: Document) -> list[dict] | None:
        """Group chapters into 4-5 high-level sections.

        Returns: [{"name": str, "chapter_headings": [str], "takeaway": str}]
        Cached at: <cache_dir>/_outline.json
        """
        input_hash = self._outline_input_hash(doc)
        cached = self._try_cache("_outline", input_hash)
        if cached is not None:
            return cached.get("groups")

        prompt = self._build_outline_prompt(doc)
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=1200,
                )
                payload = json.loads(response.content)
                if "groups" not in payload:
                    raise ValueError("Missing 'groups' key in LLM response")
                self._write_cache("_outline", input_hash, payload, prompt, response)
                return payload.get("groups")
            except Exception as exc:
                last_error = exc
                continue
        return None

    def summarize_paper(self, doc: Document) -> dict | None:
        """Final paper summary for the closing slide.

        Returns: {"bullets": [5-7 strings], "takeaway": "1 sentence"}
        Cached at: <cache_dir>/_paper.json
        """
        input_hash = self._paper_input_hash(doc)
        cached = self._try_cache("_paper", input_hash)
        if cached is not None:
            return cached

        prompt = self._build_paper_summary_prompt(doc)
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=1000,
                )
                payload = json.loads(response.content)
                if "bullets" not in payload or "takeaway" not in payload:
                    raise ValueError("Missing 'bullets' or 'takeaway' in LLM response")
                self._write_cache("_paper", input_hash, payload, prompt, response)
                return payload
            except Exception as exc:
                last_error = exc
                continue
        return None

    # ---------- per-chapter ----------

    def _summarize_chapter(self, chapter: Chapter) -> dict | None:
        slug = slugify(chapter.heading)
        input_hash = self._input_hash(chapter)
        cached = self._try_cache(slug, input_hash)
        if cached is not None:
            return cached

        prompt = self._build_prompt(chapter)
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=1000,
                )
                payload = json.loads(response.content)
                payload = _normalize_chapter_summary(payload)
                self._write_cache(slug, input_hash, payload, prompt, response)
                return payload
            except Exception as exc:
                last_error = exc
                continue
        # All retries exhausted
        return None

    # ---------- cache I/O ----------

    def _input_hash(self, chapter: Chapter) -> str:
        # Hash the chapter content + lang so a language switch invalidates.
        # _CHAPTER_PROMPT_VERSION included so prompt changes invalidate old caches.
        h = hashlib.sha256()
        h.update(_CHAPTER_PROMPT_VERSION.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.lang.encode("utf-8"))
        h.update(b"\x00")
        h.update(chapter.heading.encode("utf-8"))
        h.update(b"\x00")
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                h.update(b"P:")
                h.update(block.text.encode("utf-8"))
                h.update(b"\x00")
            elif isinstance(block, FigureBlock):
                h.update(b"F:")
                h.update(block.fig_id.encode("utf-8"))
                h.update(b"|")
                h.update(block.caption.encode("utf-8"))
                h.update(b"|")
                h.update(block.deep_observation.encode("utf-8"))
                h.update(b"\x00")
        return h.hexdigest()

    def _outline_input_hash(self, doc: Document) -> str:
        """sha256 of (version + lang + all chapter headings + first 200 chars of each chapter's first paragraph)."""
        h = hashlib.sha256()
        h.update(_OUTLINE_PROMPT_VERSION.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.lang.encode("utf-8"))
        h.update(b"\x00")
        for ch in doc.chapters:
            h.update(ch.heading.encode("utf-8"))
            h.update(b"\x00")
            # First paragraph preview
            first_para = next(
                (b for b in ch.blocks if isinstance(b, Paragraph)), None
            )
            preview = (first_para.text[:200] if first_para else "")
            h.update(preview.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def _paper_input_hash(self, doc: Document) -> str:
        """sha256 of (version + lang + all chapter headings + last chapter's full text + first 500 chars of each chapter)."""
        h = hashlib.sha256()
        h.update(_PAPER_PROMPT_VERSION.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.lang.encode("utf-8"))
        h.update(b"\x00")
        for ch in doc.chapters:
            h.update(ch.heading.encode("utf-8"))
            h.update(b"\x00")
        # First 500 chars of each chapter
        for ch in doc.chapters:
            paras = [b for b in ch.blocks if isinstance(b, Paragraph)]
            text = " ".join(p.text for p in paras)
            h.update(text[:500].encode("utf-8"))
            h.update(b"\x00")
        # Last chapter's full text
        if doc.chapters:
            last_ch = doc.chapters[-1]
            paras = [b for b in last_ch.blocks if isinstance(b, Paragraph)]
            full_text = " ".join(p.text for p in paras)
            h.update(full_text.encode("utf-8"))
        return h.hexdigest()

    def _try_cache(self, slug: str, input_hash: str) -> dict | None:
        hash_file = self.cache_dir / f"{slug}.input_hash.json"
        out_file = self.cache_dir / f"{slug}.json"
        if not hash_file.exists() or not out_file.exists():
            return None
        try:
            stored = json.loads(hash_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if stored.get("hash") != input_hash:
            return None
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        # Normalize legacy figure_one_liners → figure_observations for chapter payloads.
        # Chapter payloads have "bullets" but NOT "takeaway" (paper payload) or "groups" (outline).
        is_chapter_payload = (
            "bullets" in payload
            and "takeaway" not in payload
            and "groups" not in payload
        )
        if is_chapter_payload:
            payload = _normalize_chapter_summary(payload)
        return payload

    def _write_cache(self, slug: str, input_hash: str, output: dict,
                     prompt: str, response) -> None:
        (self.cache_dir / f"{slug}.input_hash.json").write_text(
            json.dumps({"hash": input_hash}), encoding="utf-8",
        )
        (self.cache_dir / f"{slug}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (self.cache_dir / f"{slug}.prompt.md").write_text(prompt, encoding="utf-8")
        (self.cache_dir / f"{slug}.response.json").write_text(
            json.dumps({
                "content": response.content,
                "model": getattr(response, "model", None),
                "usage": getattr(response, "usage", None),
                "latency_ms": getattr(response, "latency_ms", None),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- prompt builders ----------

    def _build_prompt(self, chapter: Chapter) -> str:
        body = "\n\n".join(
            b.text for b in chapter.blocks if isinstance(b, Paragraph)
        )
        figures = [b for b in chapter.blocks if isinstance(b, FigureBlock)]
        if figures:
            figures_block = "\n".join(
                f"- {fb.fig_id}: {fb.caption} (deep_obs: {fb.deep_observation})"
                for fb in figures
            )
        else:
            figures_block = "(no figures in this chapter)"
        return (
            self._template
            .replace("{heading}", chapter.heading)
            .replace("{body}", body or "(no body text)")
            .replace("{figures_block}", figures_block)
        )

    def _build_outline_prompt(self, doc: Document) -> str:
        lines: list[str] = []
        for ch in doc.chapters:
            first_para = next(
                (b for b in ch.blocks if isinstance(b, Paragraph)), None
            )
            preview = (first_para.text[:200] if first_para else "(no text)")
            lines.append(f"## {ch.heading}\n{preview}")
        chapters_block = "\n\n".join(lines)
        return (
            self._outline_template
            .replace("{title}", doc.paper_title)
            .replace("{chapters_block}", chapters_block)
        )

    def _build_paper_summary_prompt(self, doc: Document) -> str:
        lines: list[str] = []
        for ch in doc.chapters:
            paras = [b for b in ch.blocks if isinstance(b, Paragraph)]
            text = " ".join(p.text for p in paras)
            lines.append(f"## {ch.heading}\n{text[:800]}")
        chapters_block = "\n\n".join(lines)
        return (
            self._paper_summary_template
            .replace("{title}", doc.paper_title)
            .replace("{chapters_block}", chapters_block)
        )
