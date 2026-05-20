"""Abstract renderer interface — every output format implements this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from llm.citation import CitationMode, process_text
from stages.s09_render.model import Document


class Renderer(ABC):
    """Render a Document to a single file. Stateless or per-instance state only;
    must not mutate the input Document."""

    extension: ClassVar[str]   # "docx" | "html" | "pdf" | "pptx"

    def __init__(self, *, citation_mode: CitationMode = CitationMode.REMOVE, **kwargs):
        self.citation_mode = citation_mode
        super().__init__(**kwargs)

    def _process_text(self, text: str) -> str:
        """Strip, keep, or (no-op) hyperlink citation markers based on citation_mode.

        Returns a plain string in all cases (HYPERLINK falls back to REMOVE for
        renderers that don't support rich segments — subclasses may override).
        """
        result = process_text(text, mode=self.citation_mode, sources=[])
        if isinstance(result, list):
            # HYPERLINK with empty sources: segments are all plain strings
            return "".join(s if isinstance(s, str) else s.get("text", "") for s in result)
        return result

    @abstractmethod
    def render(self, doc: Document, out_path: Path) -> None:
        ...
