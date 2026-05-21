"""Lightweight types consumed by `llm.citation.process_text`.

Originally vendored from Onyx to back a streaming `DynamicCitationProcessor`
that was never wired up in this project. Only the three names re-exported
below are needed by the in-tree citation adapter in `__init__.py`.
"""
from __future__ import annotations

from pydantic import BaseModel

# Sentinel kept for downstream parity; lazy-paper itself never emits it.
STOP_STREAM_PAT = "<STOP_STREAM>"


class SearchDoc(BaseModel):
    """Minimal source-shape understood by `process_text`."""
    document_id: str
    link: str | None = None
    semantic_identifier: str = ""


class CitationInfo(BaseModel):
    """One resolved citation marker — emitted into rendered output."""
    citation_number: int
    document_id: str

    @property
    def citation_num(self) -> int:
        return self.citation_number
