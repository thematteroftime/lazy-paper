"""Frozen data model consumed by all renderers (docx/html/pdf/pptx)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class FigureBlock:
    fig_id: str                       # canonical "Fig. 5"
    label: str                        # localized "Fig. 5" or "图 5"
    image_paths: tuple[Path, ...]     # one path per panel
    caption: str
    deep_observation: str             # may be empty string


Block = Union[Paragraph, FigureBlock]   # union type for static dispatch


@dataclass(frozen=True)
class Chapter:
    heading: str
    level: int                        # 1 = H1
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                         # "zh" | "en"
    chapters: tuple[Chapter, ...]
