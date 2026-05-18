"""Abstract renderer interface — every output format implements this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from stages.s09_render.model import Document


class Renderer(ABC):
    """Render a Document to a single file. Stateless or per-instance state only;
    must not mutate the input Document."""

    extension: ClassVar[str]   # "docx" | "html" | "pdf" | "pptx"

    @abstractmethod
    def render(self, doc: Document, out_path: Path) -> None:
        ...
