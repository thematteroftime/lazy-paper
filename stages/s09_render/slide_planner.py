"""Cut a Document into Slide units for the PPT renderer.

Deterministic logic only — LLM summaries (if any) are passed in by the caller.
No IO, no model state.

v7 changes:
- plan() now accepts optional outline (4-5 groups) and paper_brief
- Outline slide shows 4-5 groups (not individual chapters)
- Per-group section_divider slides replace per-chapter dividers
- Pure-bullet chapters folded into section dividers; only figure-bearing chapters
  produce standalone content slides
- Closing slide uses paper_brief when available (kind="closing_rich")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from stages.s09_render._math import normalize_math
from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


@dataclass(frozen=True)
class Slide:
    kind: str                              # title | outline | section_divider | divider | bullets | figure | combined | closing | closing_rich
    title: str
    bullets: tuple[str, ...] = field(default_factory=tuple)
    image_paths: tuple[Path, ...] = field(default_factory=tuple)
    caption: str = ""
    deep_observation: str = ""            # joined string (backward compat + speaker notes)
    observations: tuple[str, ...] = field(default_factory=tuple)  # v9: 2-3 analytical points
    notes: str = ""                        # speaker notes
    group_idx: int = 0                     # v12: 1-based group index (0 = not part of a group)
    chapter_in_group: int = 0              # v12: 1-based chapter position within its group (0 = section divider)


@dataclass(frozen=True)
class SlideDeck:
    slides: tuple[Slide, ...]
    lang: str


class SlidePlanner:
    MAX_BULLETS_PER_SLIDE: ClassVar[int] = 7   # v13: was 5; allows more content per slide
    MIN_PARAGRAPHS_FOR_DIVIDER: ClassVar[int] = 2

    def __init__(self, lang: str):
        self.lang = lang

    def plan(self, doc: Document, summaries: dict | None,
             outline: list[dict] | None = None,
             paper_brief: dict | None = None) -> SlideDeck:
        slides: list[Slide] = [self._title_slide(doc)]

        if outline:
            slides.append(self._outline_slide_grouped(doc, outline))
            chapter_to_group = {h: g["name"] for g in outline for h in g["chapter_headings"]}
            groups = outline
        else:
            # Fallback: use chapter list as before (v6 behavior)
            slides.append(self._outline_slide(doc))
            chapter_to_group = None
            groups = [{"name": "All Chapters",
                       "chapter_headings": [ch.heading for ch in doc.chapters],
                       "takeaway": ""}]

        # Per-group: section divider + chapter content slides
        for g_num, group in enumerate(groups, start=1):
            group_headings = group.get("chapter_headings") or []

            # Gather bullets from pure-bullet chapters in this group for section divider
            bullets_preview = self._extract_group_preview_bullets(group, doc, summaries)
            slides.append(Slide(
                kind="section_divider",
                title=group["name"],
                bullets=tuple(bullets_preview),
                caption=group.get("takeaway", ""),
                notes="",
                group_idx=g_num,
                chapter_in_group=0,
            ))

            # Per-chapter content slides (only figure-bearing chapters)
            # Track position-within-group for hierarchical §g.c numbering
            ch_pos = 0
            for ch in doc.chapters:
                if ch.heading not in group_headings:
                    continue
                ch_pos += 1
                has_figure = any(isinstance(b, FigureBlock) for b in ch.blocks)
                if not has_figure:
                    # Pure-bullet chapter: already absorbed into section divider
                    continue
                ch_summary = (summaries or {}).get(ch.heading)
                for sl in self._chapter_slides(ch, ch_summary):
                    # Drop old per-chapter divider slides — section_divider replaces them
                    if sl.kind == "divider":
                        continue
                    # Attach hierarchical numbering to every content slide in this chapter
                    slides.append(Slide(
                        kind=sl.kind,
                        title=sl.title,
                        bullets=sl.bullets,
                        image_paths=sl.image_paths,
                        caption=sl.caption,
                        deep_observation=sl.deep_observation,
                        observations=sl.observations,
                        notes=sl.notes,
                        group_idx=g_num,
                        chapter_in_group=ch_pos,
                    ))

        # Closing slide
        if paper_brief:
            slides.append(self._closing_slide_rich(doc, paper_brief))
        else:
            slides.append(self._closing_slide(doc))

        return SlideDeck(slides=tuple(slides), lang=self.lang)

    # ---------- outline slides ----------

    def _outline_slide_grouped(self, doc: Document, outline: list[dict]) -> Slide:
        """Outline slide showing 4-5 high-level groups (v7)."""
        bullets = tuple(g["name"] for g in outline)
        # Encode takeaways in notes for the renderer to display as subtitles
        takeaways = tuple(g.get("takeaway", "") for g in outline)
        notes = "\n".join(f"{g['name']}: {g.get('takeaway', '')}" for g in outline)
        return Slide(
            kind="outline_grouped",
            title=self._localize("Contents", "目录"),
            bullets=bullets,
            caption="\n".join(takeaways),  # pass takeaways for renderer
            notes=notes,
        )

    def _outline_slide(self, doc: Document) -> Slide:
        """Fallback flat outline (v6 style)."""
        bullets = tuple(ch.heading for ch in doc.chapters)
        return Slide(kind="outline",
                     title=self._localize("Outline", "目录"),
                     bullets=bullets)

    # ---------- closing slides ----------

    def _closing_slide_rich(self, doc: Document, paper_brief: dict) -> Slide:
        """Rich closing slide using paper_brief (v7)."""
        bullets = tuple(normalize_math(b) for b in paper_brief.get("bullets", [])[:7])
        takeaway = normalize_math(paper_brief.get("takeaway", ""))
        return Slide(
            kind="closing_rich",
            title=self._localize("Conclusion", "结论"),
            bullets=bullets,
            caption=takeaway,
            notes=takeaway,
        )

    def _closing_slide(self, doc: Document) -> Slide:
        """Fallback closing slide (v6 style)."""
        conclusion = next(
            (ch for ch in doc.chapters if "conclu" in ch.heading.lower()
             or "结论" in ch.heading),
            doc.chapters[-1] if doc.chapters else None,
        )
        bullets: tuple[str, ...] = ()
        notes = ""
        if conclusion is not None:
            paragraphs = [b for b in conclusion.blocks if isinstance(b, Paragraph)]
            bullets = tuple(self._paragraph_bullets(paragraphs)[:self.MAX_BULLETS_PER_SLIDE])
            notes = "\n\n".join(p.text for p in paragraphs)
        return Slide(kind="closing",
                     title=self._localize("Conclusion", "总结"),
                     bullets=bullets, notes=notes)

    # ---------- per-section planners ----------

    def _title_slide(self, doc: Document) -> Slide:
        return Slide(kind="title", title=doc.paper_title)

    def _chapter_slides(self, chapter: Chapter, summary: dict | None) -> list[Slide]:
        paragraphs = [b for b in chapter.blocks if isinstance(b, Paragraph)]
        figures = [b for b in chapter.blocks if isinstance(b, FigureBlock)]

        slides: list[Slide] = []
        if len(paragraphs) >= self.MIN_PARAGRAPHS_FOR_DIVIDER:
            slides.append(Slide(kind="divider", title=chapter.heading))

        bullets = self._get_bullets(chapter, paragraphs, summary)

        if figures and bullets:
            # Combined slides — pair figures with balanced bullet chunks
            figs_n = len(figures)
            per_fig = max(1, len(bullets) // figs_n)
            for i, fb in enumerate(figures):
                start = i * per_fig
                end = (i + 1) * per_fig if i < figs_n - 1 else len(bullets)
                chunk = bullets[start:end][:self.MAX_BULLETS_PER_SLIDE]
                # v9: get 2-3 observation points from figure_observations
                obs_list = (summary or {}).get("figure_observations", {}).get(fb.fig_id)
                if not obs_list:
                    # Fallback: single-element list from deep_observation
                    obs_list = [fb.deep_observation[:200]] if fb.deep_observation else []
                observations = tuple(normalize_math(o) for o in obs_list)
                deep_obs = " · ".join(observations)
                notes_full = "\n\n".join(
                    p.text for p in paragraphs
                ) + (f"\n\nFull deep observation:\n{fb.deep_observation}" if fb.deep_observation else "")
                slides.append(Slide(
                    kind="combined",
                    title=chapter.heading,
                    bullets=tuple(normalize_math(b) for b in chunk),
                    image_paths=fb.image_paths,
                    caption=normalize_math(fb.caption),
                    deep_observation=deep_obs,
                    observations=observations,
                    notes=notes_full,
                ))
        elif figures:
            # Only figures (no bullets) — fall back to figure-only slides
            fig_obs_map = (summary or {}).get("figure_observations", {})
            for fb in figures:
                obs_list = fig_obs_map.get(fb.fig_id)
                if not obs_list:
                    obs_list = [fb.deep_observation[:200]] if fb.deep_observation else []
                observations = tuple(normalize_math(o) for o in obs_list)
                deep_obs = " · ".join(observations)
                slides.append(Slide(
                    kind="figure",
                    title=f"{fb.label}: {normalize_math(fb.caption)}",
                    image_paths=fb.image_paths,
                    caption=normalize_math(fb.caption),
                    deep_observation=deep_obs,
                    observations=observations,
                    notes=f"Full deep observation:\n{fb.deep_observation}",
                ))
        elif bullets:
            # Only bullets (no figures) — fall back to bullets slides
            notes_full = "\n\n".join(p.text for p in paragraphs)
            for chunk in _chunked(bullets, self.MAX_BULLETS_PER_SLIDE):
                slides.append(Slide(
                    kind="bullets",
                    title=chapter.heading,
                    bullets=tuple(normalize_math(b) for b in chunk),
                    notes=notes_full,
                ))
        return slides

    def _extract_group_preview_bullets(self, group: dict, doc: Document,
                                       summaries: dict | None) -> list[str]:
        """Pull preview bullets for the section divider.

        Priority: bullets from pure-bullet (no-figure) chapters in the group;
        if none, fall back to bullets from figure-bearing chapters in the group
        so the divider is never empty."""
        if not summaries:
            return []

        headings = set(group.get("chapter_headings") or [])
        pure_bullets: list[str] = []
        figure_bullets: list[str] = []

        for ch in doc.chapters:
            if ch.heading not in headings:
                continue
            s = summaries.get(ch.heading) or {}
            bs = list(s.get("bullets", []))
            if not bs:
                continue
            has_figure = any(isinstance(b, FigureBlock) for b in ch.blocks)
            if has_figure:
                figure_bullets.extend(bs)
            else:
                pure_bullets.extend(bs)

        bullets = pure_bullets[:7] if pure_bullets else figure_bullets[:7]  # v13: was 5
        return bullets

    def _get_bullets(self, chapter: Chapter, paragraphs: list[Paragraph],
                     summary: dict | None) -> list[str]:
        """Centralised bullet extraction — LLM summary first, fallback to rule-based."""
        if not paragraphs:
            return []
        if summary and summary.get("bullets"):
            return list(summary["bullets"])
        return self._paragraph_bullets(paragraphs)

    # ---------- helpers ----------

    def _localize(self, en: str, zh: str) -> str:
        return zh if self.lang == "zh" else en

    @staticmethod
    def _paragraph_bullets(paragraphs: list[Paragraph]) -> list[str]:
        """Rule-based fallback: first sentence (or first 80 chars) of each para."""
        out: list[str] = []
        for p in paragraphs:
            first = p.text.split("。")[0].split(". ")[0].strip()
            if not first:
                continue
            out.append(first[:80])
        return out


def _chunked(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]
