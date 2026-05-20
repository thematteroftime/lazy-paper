"""Citation rendering adapter — wires vendored Onyx stream_processor to s09.

`process_text(text, mode, sources)` parses [span:doc:start-end] markers and
returns either a cleaned string (REMOVE/KEEP) or a segmented list (HYPERLINK)
suitable for renderer-specific output.
"""
from __future__ import annotations

import enum
import re
from typing import Union

from llm.citation.models import SearchDoc, CitationInfo, STOP_STREAM_PAT


class CitationMode(str, enum.Enum):
    HYPERLINK = "hyperlink"
    KEEP = "keep"
    REMOVE = "remove"


_MARKER = re.compile(r"\[span:([^:\]]+):(\d+)-(\d+)\]")


def process_text(
    text: str,
    *,
    mode: CitationMode,
    sources: list[dict],
) -> Union[str, list]:
    """Render citations per mode.

    - REMOVE: returns plain text with markers stripped.
    - KEEP:   returns text verbatim.
    - HYPERLINK: returns list[str | {"text": str, "href": str}] segments.
    """
    docs_by_id = {s["document_id"]: s for s in sources}

    if mode == CitationMode.KEEP:
        return text
    if mode == CitationMode.REMOVE:
        return _MARKER.sub("", text)

    # HYPERLINK
    segments: list = []
    pos = 0
    for m in _MARKER.finditer(text):
        if m.start() > pos:
            segments.append(text[pos:m.start()])
        doc_id, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        src = docs_by_id.get(doc_id)
        if src and src.get("link"):
            segments.append({
                "text": m.group(0),
                "href": f"{src['link']}#L{start}-L{end}",
            })
        else:
            segments.append(m.group(0))
        pos = m.end()
    if pos < len(text):
        segments.append(text[pos:])
    return segments


__all__ = [
    "CitationMode",
    "process_text",
    "SearchDoc",
    "CitationInfo",
    "STOP_STREAM_PAT",
]
