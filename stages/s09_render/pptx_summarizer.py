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

v11 additions:
- Two-pass summarize(): pass 1 computes outline (cheap), pass 2 feeds per-chapter
  summaries with cross-chapter context (system, keywords, section_name, prior_bullet,
  next_heading) for connective analysis
- Outline prompt now includes per-chapter (has_figures, n_paragraphs) metadata
  so grouping is budget-aware (Enhancement 2)
- Low-diversity group-name rejection: if >2 of 4+ groups share a common word,
  retry once with an amended prompt (Enhancement 3)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stages._common import load_yaml
from stages._common.paths import slugify
from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


_MAX_RETRIES = 3
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_summarize.md"
_OUTLINE_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_outline.md"
_PAPER_SUMMARY_PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "pptx_paper_summary.md"

# Bump these constants to invalidate old caches when prompts change.
_CHAPTER_PROMPT_VERSION = "v12-quantitative-preservation"
_OUTLINE_PROMPT_VERSION = "v12-extended-template"
_PAPER_PROMPT_VERSION = "v12-quantitative-takeaway"


def _is_low_diversity(groups: list[dict]) -> bool:
    """Return True if >2 of 4+ group names share a common content word.

    This detects the "all groups start with 弛豫反铁电" syndrome and triggers
    a diversity-boosting retry (Enhancement 3).
    """
    if len(groups) < 4:
        return False
    names = [g.get("name", "") for g in groups]
    # Build set of all unique 2+ character segments from each name
    # and check if any single word appears in >2 names
    from collections import Counter
    word_counts: Counter = Counter()
    for name in names:
        # Split Chinese names by common separators; for CJK just use substrings
        # Check bigrams and trigrams as "words"
        for length in (2, 3, 4):
            for start in range(len(name) - length + 1):
                word_counts[name[start:start + length]] += 1
    # If any substring appears in >2 out of len(groups) names → low diversity
    threshold = max(2, len(groups) - 1)
    return any(count > threshold for count in word_counts.values())


def _strip_md_heading(heading: str) -> str:
    """Strip leading markdown heading markers (##, #, etc.) from a heading string."""
    stripped = heading.lstrip("# ").strip()
    return stripped if stripped else heading


def _normalize_outline_groups(groups: list[dict] | None) -> list[dict] | None:
    """Normalize chapter_headings in outline groups by stripping ## prefixes.

    Some LLMs echo back the markdown heading format (## Heading) used in the
    input chapters_block. This strips those prefixes so the headings match the
    actual ch.heading values in the Document model.
    """
    if not groups:
        return groups
    normalized = []
    for g in groups:
        headings = g.get("chapter_headings") or []
        normalized_headings = [_strip_md_heading(h) for h in headings]
        normalized.append({**g, "chapter_headings": normalized_headings})
    return normalized


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

    def __init__(self, llm, cache_dir: Path, lang: str,
                 context_dir: Path | None = None):
        self.llm = llm
        self.cache_dir = Path(cache_dir)
        self.lang = lang
        self.context_dir = Path(context_dir) if context_dir is not None else None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")
        self._outline_template = _OUTLINE_PROMPT_PATH.read_text(encoding="utf-8")
        self._paper_summary_template = _PAPER_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")

    def summarize(self, doc: Document,
                  outline: list[dict] | None = None) -> dict | None:
        """Returns {chapter_heading: {bullets, figure_observations}} or None on
        total failure (3 consecutive LLM errors on the same chapter).

        v11: two-pass approach.
        Pass 1: compute outline (cheap, just headings+previews) if not supplied.
        Pass 2: per-chapter summary enriched with cross-chapter context:
          - system + keywords (from context.yaml)
          - section_name (from outline group this chapter belongs to)
          - prior chapter's first bullet (avoid restatement; build on it)
          - next chapter's heading (avoid pre-empting it)
        """
        # Build chapter → section_name lookup from outline
        chapter_to_section: dict[str, str] = {}
        if outline:
            for group in outline:
                for h in group.get("chapter_headings") or []:
                    chapter_to_section[h] = group.get("name", "")

        ctx = self._load_context()
        system = ctx.get("system", "") or ""
        keywords_list = ctx.get("keywords") or []
        keywords = "; ".join(str(k) for k in keywords_list[:5])

        out: dict[str, dict] = {}
        prior_bullet: str = ""
        for i, chapter in enumerate(doc.chapters):
            next_heading = doc.chapters[i + 1].heading if i + 1 < len(doc.chapters) else ""
            section_name = chapter_to_section.get(chapter.heading, "")
            chapter_out = self._summarize_chapter(
                chapter,
                system=system,
                keywords=keywords,
                section_name=section_name,
                prior_bullet=prior_bullet,
                next_heading=next_heading,
            )
            if chapter_out is None:
                return None
            out[chapter.heading] = chapter_out
            # Update prior_bullet: take the first bullet for the next iteration
            bullets = chapter_out.get("bullets") or []
            prior_bullet = bullets[0] if bullets else ""
        return out

    def summarize_outline(self, doc: Document) -> list[dict] | None:
        """Group chapters into 4-5 high-level sections.

        Returns: [{"name": str, "chapter_headings": [str], "takeaway": str}]
        Cached at: <cache_dir>/_outline.json

        v11: includes per-chapter (has_figures, n_paragraphs) metadata in prompt
        (Enhancement 2) and applies low-diversity group-name rejection with one
        retry (Enhancement 3).
        """
        input_hash = self._outline_input_hash(doc)
        cached = self._try_cache("_outline", input_hash)
        if cached is not None:
            return _normalize_outline_groups(cached.get("groups"))

        all_chapter_headings = [ch.heading for ch in doc.chapters]
        prompt = self._build_outline_prompt(doc)
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                user_prompt = prompt
                temp = 0.2
                if attempt > 0:
                    # Reinforcement on retry
                    user_prompt = prompt + (
                        f"\n\n**RETRY — STRICT ENFORCEMENT**: Your previous response was rejected. "
                        f"Output EXACTLY 4 or 5 groups (not 1, not 11). "
                        f"Every one of the {len(all_chapter_headings)} input chapter headings "
                        f"MUST appear in exactly one group's `chapter_headings` array. "
                        f"Each group name must be lexically distinct from the others."
                    )
                    temp = 0.4
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=user_prompt,
                    temperature=temp,
                    max_tokens=2400,
                )
                payload = json.loads(response.content)
                if "groups" not in payload:
                    raise ValueError("Missing 'groups' key in LLM response")
                groups = payload.get("groups") or []
                # Validate: chapter coverage always; group count only for ≥5-chapter papers
                n = len(groups)
                if len(all_chapter_headings) >= 5 and (n < 3 or n > 6):
                    raise ValueError(f"Group count {n} outside [3, 6] for {len(all_chapter_headings)}-chapter paper")
                assigned = []
                for g in groups:
                    assigned.extend(g.get("chapter_headings") or [])
                missing = [h for h in all_chapter_headings if h not in assigned]
                if missing:
                    raise ValueError(f"Chapters not assigned to any group: {missing}")
                if len(all_chapter_headings) >= 5 and _is_low_diversity(groups):
                    raise ValueError("Low diversity: group names share too many roots")
                self._write_cache("_outline", input_hash, payload, prompt, response)
                return _normalize_outline_groups(payload.get("groups"))
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
                    max_tokens=2000,
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

    def _summarize_chapter(self, chapter: Chapter, *,
                           system: str = "",
                           keywords: str = "",
                           section_name: str = "",
                           prior_bullet: str = "",
                           next_heading: str = "") -> dict | None:
        """Summarize a single chapter with optional cross-chapter context.

        v11: accepts system, keywords, section_name, prior_bullet, next_heading
        for connective bullet generation. These are baked into the input hash so
        cache correctly invalidates when context changes.
        """
        slug = slugify(chapter.heading)
        input_hash = self._input_hash(
            chapter,
            system=system,
            keywords=keywords,
            section_name=section_name,
            prior_bullet=prior_bullet,
            next_heading=next_heading,
        )
        cached = self._try_cache(slug, input_hash)
        if cached is not None:
            return cached

        prompt = self._build_prompt(
            chapter,
            system=system,
            keywords=keywords,
            section_name=section_name,
            prior_bullet=prior_bullet,
            next_heading=next_heading,
        )
        last_error: Exception | None = None
        for _ in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    system="You output strict JSON only.",
                    user=prompt,
                    temperature=0.2,
                    max_tokens=2000,
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

    @staticmethod
    def _make_hash(version: str, lang: str, *parts: bytes) -> str:
        h = hashlib.sha256()
        h.update(version.encode("utf-8"))
        h.update(b"\x00")
        h.update(lang.encode("utf-8"))
        h.update(b"\x00")
        for p in parts:
            h.update(p)
        return h.hexdigest()

    def _input_hash(self, chapter: Chapter, *,
                    system: str = "",
                    keywords: str = "",
                    section_name: str = "",
                    prior_bullet: str = "",
                    next_heading: str = "") -> str:
        chunks: list[bytes] = [chapter.heading.encode("utf-8"), b"\x00"]
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                chunks += [b"P:", block.text.encode("utf-8"), b"\x00"]
            elif isinstance(block, FigureBlock):
                chunks += [
                    b"F:", block.fig_id.encode("utf-8"), b"|",
                    block.caption.encode("utf-8"), b"|",
                    block.deep_observation.encode("utf-8"), b"\x00",
                ]
        # Include cross-chapter context in hash so cache invalidates when context changes
        chunks += [
            system.encode("utf-8"), b"\x00",
            keywords.encode("utf-8"), b"\x00",
            section_name.encode("utf-8"), b"\x00",
            prior_bullet.encode("utf-8"), b"\x00",
            next_heading.encode("utf-8"), b"\x00",
        ]
        return self._make_hash(_CHAPTER_PROMPT_VERSION, self.lang, *chunks)

    def _outline_input_hash(self, doc: Document) -> str:
        chunks: list[bytes] = []
        for ch in doc.chapters:
            first_para = next((b for b in ch.blocks if isinstance(b, Paragraph)), None)
            preview = first_para.text[:200] if first_para else ""
            has_figures = any(isinstance(b, FigureBlock) for b in ch.blocks)
            n_paragraphs = sum(1 for b in ch.blocks if isinstance(b, Paragraph))
            chunks += [ch.heading.encode("utf-8"), b"\x00",
                       preview.encode("utf-8"), b"\x00",
                       str(has_figures).encode("utf-8"), b"\x00",
                       str(n_paragraphs).encode("utf-8"), b"\x00"]
        # Include context terms so cache invalidates when context.yaml changes
        ctx = self._load_context()
        system = ctx.get("system", "") or ""
        key_terms = "; ".join(ctx.get("key_terms", []) or [])
        keywords = "; ".join(ctx.get("keywords", []) or [])
        chunks += [system.encode("utf-8"), b"\x00",
                   key_terms.encode("utf-8"), b"\x00",
                   keywords.encode("utf-8"), b"\x00"]
        return self._make_hash(_OUTLINE_PROMPT_VERSION, self.lang, *chunks)

    def _paper_input_hash(self, doc: Document) -> str:
        chunks: list[bytes] = []
        for ch in doc.chapters:
            chunks += [ch.heading.encode("utf-8"), b"\x00"]
        for ch in doc.chapters:
            paras = [b for b in ch.blocks if isinstance(b, Paragraph)]
            text = " ".join(p.text for p in paras)
            chunks += [text[:500].encode("utf-8"), b"\x00"]
        if doc.chapters:
            last_ch = doc.chapters[-1]
            paras = [b for b in last_ch.blocks if isinstance(b, Paragraph)]
            chunks.append(" ".join(p.text for p in paras).encode("utf-8"))
        return self._make_hash(_PAPER_PROMPT_VERSION, self.lang, *chunks)

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

    def _build_prompt(self, chapter: Chapter, *,
                      system: str = "",
                      keywords: str = "",
                      section_name: str = "",
                      prior_bullet: str = "",
                      next_heading: str = "") -> str:
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
            .replace("{system}", system or "(not specified)")
            .replace("{keywords}", keywords or "(not specified)")
            .replace("{section_name}", section_name or "(not specified)")
            .replace("{prior_bullet}", prior_bullet or "(this is the first chapter)")
            .replace("{next_heading}", next_heading or "(this is the last chapter)")
        )

    def _build_outline_prompt(self, doc: Document) -> str:
        lines: list[str] = []
        for ch in doc.chapters:
            first_para = next(
                (b for b in ch.blocks if isinstance(b, Paragraph)), None
            )
            preview = (first_para.text[:200] if first_para else "(no text)")
            has_figures = any(isinstance(b, FigureBlock) for b in ch.blocks)
            n_paragraphs = sum(1 for b in ch.blocks if isinstance(b, Paragraph))
            # Enhancement 2: include substance metadata so outline can group by content
            meta = f"[has_figures={has_figures}, n_paragraphs={n_paragraphs}]"
            lines.append(f"## {ch.heading} {meta}\n{preview}")
        chapters_block = "\n\n".join(lines)
        ctx = self._load_context()
        system = ctx.get("system", "") or ""
        key_terms = "; ".join(ctx.get("key_terms", []) or [])
        keywords = "; ".join(ctx.get("keywords", []) or [])
        return (
            self._outline_template
            .replace("{title}", doc.paper_title)
            .replace("{chapters_block}", chapters_block)
            .replace("{system}", system)
            .replace("{key_terms}", key_terms)
            .replace("{keywords}", keywords)
        )

    def _load_context(self) -> dict:
        """Load context.yaml if context_dir is set, else return empty dict."""
        if self.context_dir is None:
            return {}
        ctx_path = self.context_dir / "context.yaml"
        if not ctx_path.exists():
            return {}
        try:
            return load_yaml(ctx_path) or {}
        except Exception:
            return {}

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
