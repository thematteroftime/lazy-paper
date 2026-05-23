"""Build a frozen Document model from compose_dir chapters + fig_notes."""
from __future__ import annotations

import re
from pathlib import Path

from stages.s09_render._math import normalize_math
from stages.s09_render.model import (
    Document, Chapter, Paragraph, FigureBlock, TableBlock, Block,
)


_UNTITLED_FALLBACK = {"zh": "未命名章节", "en": "Untitled"}


class DocumentBuilder:
    """Pure transform: markdown + fig_notes → Document. No IO."""

    _FIG_ID_NUM = re.compile(r"Fig\.\s*(\d+)")

    def __init__(self, lang: str, paper_title: str):
        self.lang = lang
        self.paper_title = paper_title

    def build(self,
              chapters_md: dict[str, str],
              fig_notes: list[dict]) -> Document:
        """Construct a Document from raw chapter markdown + parsed fig_notes.

        Contracts:
        - chapters_md keys are filenames; they are processed in sorted (lexical) order.
        - A figure is "referenced" by a chapter if its fig_id (e.g. "Fig. 5") appears
          literally in the chapter body OR the corresponding Chinese form ("图5" or
          "图 5") does.
        - Each figure is embedded at most once across the entire Document
          (first chapter that references it wins).
        - The returned FigureBlock.image_paths are NOT verified to exist on disk —
          renderers are responsible for skipping figures whose files are missing.
        """
        embedded: set[str] = set()
        chapters: list[Chapter] = []
        for name in sorted(chapters_md):
            chapters.append(self._build_chapter(chapters_md[name], fig_notes, embedded))
        return Document(
            paper_title=self.paper_title,
            lang=self.lang,
            chapters=tuple(chapters),
        )

    def _build_chapter(self, md: str, fig_notes: list[dict],
                       embedded: set[str]) -> Chapter:
        lines = md.splitlines()
        heading, level, body_start = self._parse_heading(lines)
        body = "\n".join(lines[body_start:]).strip()

        blocks: list[Block] = list(self._split_paragraphs(body))
        blocks.extend(self._collect_referenced_figures(body, fig_notes, embedded))
        return Chapter(heading=heading, level=level, blocks=tuple(blocks))

    def _parse_heading(self, lines: list[str]) -> tuple[str, int, int]:
        if lines and lines[0].startswith("# "):
            return lines[0][2:].strip(), 1, 1
        return _UNTITLED_FALLBACK.get(self.lang, _UNTITLED_FALLBACK["zh"]), 1, 0

    def _split_paragraphs(self, body: str):
        for para in body.split("\n\n"):
            text = para.strip()
            if not text:
                continue
            if self._looks_like_md_table(text):
                yield self._parse_md_table(text)
            else:
                yield Paragraph(text=normalize_math(text))

    @staticmethod
    def _looks_like_md_table(text: str) -> bool:
        lines = [l for l in text.splitlines() if l.strip()]
        return len(lines) >= 2 and all(l.strip().startswith("|") for l in lines)

    @staticmethod
    def _parse_md_table(text: str) -> TableBlock:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        headers: tuple[str, ...] = ()
        rows: list[tuple[str, ...]] = []
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if i == 0:
                headers = tuple(cells)
            elif set("".join(cells).strip()) <= set("-: "):
                continue  # separator row
            else:
                rows.append(tuple(cells))
        return TableBlock(headers=headers, rows=tuple(rows))

    def _collect_referenced_figures(self, body: str, fig_notes: list[dict],
                                    embedded: set[str]):
        for note in fig_notes:
            fid = note.get("fig_id")
            if not fid or fid in embedded:
                continue
            if not self._is_referenced(fid, body):
                continue
            paths = self._resolve_image_paths(note)
            if not paths:
                continue
            embedded.add(fid)
            yield FigureBlock(
                fig_id=fid,
                label=self._make_label(fid),
                image_paths=tuple(paths),
                caption=note.get("caption") or fid,
                deep_observation=note.get("deep_observation") or "",
            )

    def _is_referenced(self, fig_id: str, body: str) -> bool:
        if fig_id in body:
            return True
        m = self._FIG_ID_NUM.match(fig_id)
        if not m:
            return False
        num = m.group(1)
        return f"图{num}" in body or f"图 {num}" in body

    def _make_label(self, fig_id: str) -> str:
        if self.lang != "zh":
            return fig_id
        return fig_id.replace("Fig.", "图")

    @staticmethod
    def _resolve_image_paths(note: dict) -> list[Path]:
        raw = list(note.get("image_paths") or [])
        if not raw and note.get("image_abs_path"):
            raw = [note["image_abs_path"]]
        return [Path(p) for p in raw if p]
