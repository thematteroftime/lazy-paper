"""Path/slug utilities shared by all stages."""
from __future__ import annotations

import re as _re
from pathlib import Path


def slugify(text: str, maxlen: int = 50) -> str:
    s = _re.sub(r"[^\w一-鿿-]+", "_", text.strip(), flags=_re.UNICODE)
    # Strip leading dots/underscores so `.env` etc. can't become a path target.
    s = s.strip("._")
    return s[:maxlen] if s else "untitled"


def stage_dir(run_root: Path, paper_id: str, stage_name: str) -> Path:
    d = Path(run_root) / paper_id / stage_name
    d.mkdir(parents=True, exist_ok=True)
    return d
