"""Findings memory — write-only stub for v1.4; v1.5 will consume."""
from __future__ import annotations

import re as _re
from pathlib import Path

import yaml

from stages._common import dump_yaml

_CITED_CLAIM = _re.compile(r"([^.。\n]*?\[span:[^\]]+\][^.。\n]*[.。])")


def extract_claims(text: str) -> list[str]:
    """Return sentences that contain at least one [span:...] citation."""
    return [m.group(1).strip() for m in _CITED_CLAIM.finditer(text)]


def append_verified_claims(*, out_dir: Path, section_name: str,
                           claims: list[str]) -> None:
    path = out_dir / "findings.yaml"
    existing: dict = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    existing[section_name] = claims
    dump_yaml(path, existing)
