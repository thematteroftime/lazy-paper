"""Bounding-box helpers extracted from filename conventions."""
from __future__ import annotations

import re as _re
from pathlib import Path


BBOX_FROM_NAME = _re.compile(r"_(\d+)_(\d+)_(\d+)_(\d+)\.[A-Za-z0-9]+$")
DOC_PAGE = _re.compile(r"doc_(\d+)\.md$")


def bbox_from_filename(rel_path: str) -> "tuple[int, int, int, int] | None":
    m = BBOX_FROM_NAME.search(Path(rel_path).name)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]
