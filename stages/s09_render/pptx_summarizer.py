"""Generate PPT bullets and figure one-liners via the text LLM.

Caches per-chapter results: if the chapter's input hash matches the cached one,
the LLM is not called. Always writes prompt/response files alongside the cache
for auditability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stages._common.paths import slugify
from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


_MAX_RETRIES_PER_CHAPTER = 3
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_summarize.md"


class PptxSummarizer:
    """LLM-backed summarizer with double-track cache (audit + reuse)."""

    def __init__(self, llm, cache_dir: Path, lang: str):
        self.llm = llm
        self.cache_dir = Path(cache_dir)
        self.lang = lang
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")

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

    # ---------- per-chapter ----------

    def _summarize_chapter(self, chapter: Chapter) -> dict | None:
        slug = slugify(chapter.heading)
        input_hash = self._input_hash(chapter)
        cached = self._try_cache(slug, input_hash)
        if cached is not None:
            return cached

        prompt = self._build_prompt(chapter)
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES_PER_CHAPTER):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=800,
                )
                payload = json.loads(response.content)
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
        h = hashlib.sha256()
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
        return json.loads(out_file.read_text(encoding="utf-8"))

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

    # ---------- prompt ----------

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
