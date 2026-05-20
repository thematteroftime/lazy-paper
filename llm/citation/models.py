"""Local replacements for Onyx-internal types used by stream_processor."""
from __future__ import annotations

from pydantic import BaseModel

# Sentinel used by Onyx to terminate stream parsing on certain tool outputs.
# We keep it for parity; lazy-paper never emits it.
STOP_STREAM_PAT = "<STOP_STREAM>"

# Triple backtick constant used by in_code_block() inside stream_processor.
TRIPLE_BACKTICK = "```"


class SearchDoc(BaseModel):
    """Minimal SearchDoc-compatible shape — only fields citation_processor reads."""
    document_id: str
    link: str | None = None
    semantic_identifier: str = ""


class CitationInfo(BaseModel):
    """Emitted by the stream processor when it identifies a citation marker."""
    citation_num: int
    document_id: str
