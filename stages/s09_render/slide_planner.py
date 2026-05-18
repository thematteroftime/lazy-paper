"""Cut a Document into Slide units for the PPT renderer.

Deterministic logic only — LLM summaries (if any) are passed in by the caller.
No IO, no model state."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from stages.s09_render.model import (
    Chapter, Document, FigureBlock, Paragraph,
)


@dataclass(frozen=True)
class Slide:
    kind: str                              # title | outline | divider | bullets | figure | closing
    title: str
    bullets: tuple[str, ...] = field(default_factory=tuple)
    image_paths: tuple[Path, ...] = field(default_factory=tuple)
    caption: str = ""
    deep_observation: str = ""
    notes: str = ""                        # speaker notes


@dataclass(frozen=True)
class SlideDeck:
    slides: tuple[Slide, ...]
    lang: str


class SlidePlanner:
    MAX_BULLETS_PER_SLIDE: ClassVar[int] = 5
    MIN_PARAGRAPHS_FOR_DIVIDER: ClassVar[int] = 2

    def __init__(self, lang: str):
        self.lang = lang

    def plan(self, doc: Document, summaries: dict | None) -> SlideDeck:
        slides: list[Slide] = [self._title_slide(doc), self._outline_slide(doc)]
        for chapter in doc.chapters:
            ch_summary = (summaries or {}).get(chapter.heading)
            slides.extend(self._chapter_slides(chapter, ch_summary))
        slides.append(self._closing_slide(doc))
        return SlideDeck(slides=tuple(slides), lang=self.lang)

    # ---------- per-section planners ----------

    def _title_slide(self, doc: Document) -> Slide:
        return Slide(kind="title", title=doc.paper_title)

    def _outline_slide(self, doc: Document) -> Slide:
        bullets = tuple(ch.heading for ch in doc.chapters)
        return Slide(kind="outline",
                     title=self._localize("Outline", "目录"),
                     bullets=bullets)

    def _closing_slide(self, doc: Document) -> Slide:
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

    def _chapter_slides(self, chapter: Chapter, summary: dict | None) -> list[Slide]:
        paragraphs = [b for b in chapter.blocks if isinstance(b, Paragraph)]
        figures = [b for b in chapter.blocks if isinstance(b, FigureBlock)]

        slides: list[Slide] = []
        if len(paragraphs) >= self.MIN_PARAGRAPHS_FOR_DIVIDER:
            slides.append(Slide(kind="divider", title=chapter.heading))

        slides.extend(self._bullets_slides(chapter, paragraphs, summary))
        slides.extend(self._figure_slides(chapter, figures, summary))
        return slides

    def _bullets_slides(self, chapter: Chapter, paragraphs: list[Paragraph],
                        summary: dict | None) -> list[Slide]:
        if not paragraphs:
            return []
        notes_full = "\n\n".join(p.text for p in paragraphs)
        if summary and summary.get("bullets"):
            source = list(summary["bullets"])
        else:
            source = self._paragraph_bullets(paragraphs)
        slides: list[Slide] = []
        for chunk in _chunked(source, self.MAX_BULLETS_PER_SLIDE):
            slides.append(Slide(
                kind="bullets",
                title=chapter.heading,
                bullets=tuple(chunk),
                notes=notes_full,
            ))
        return slides

    def _figure_slides(self, chapter: Chapter, figures: list[FigureBlock],
                       summary: dict | None) -> list[Slide]:
        one_liners = (summary or {}).get("figure_one_liners", {})
        slides: list[Slide] = []
        for fb in figures:
            obs = one_liners.get(fb.fig_id) or fb.deep_observation
            slides.append(Slide(
                kind="figure",
                title=f"{fb.label}: {fb.caption}",
                image_paths=fb.image_paths,
                caption=fb.caption,
                deep_observation=obs,
                notes=f"Full deep observation:\n{fb.deep_observation}",
            ))
        return slides

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
