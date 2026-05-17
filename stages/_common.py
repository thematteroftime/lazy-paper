"""Shared stage helpers: run-dir layout, YAML I/O, slug, done-marker."""
from __future__ import annotations

import re as _re
import time
from pathlib import Path
from typing import Any

import yaml


def slugify(text: str, maxlen: int = 50) -> str:
    s = _re.sub(r"[^\w一-鿿-]+", "_", text.strip(), flags=_re.UNICODE)
    s = s.strip("_")
    return s[:maxlen] if s else "untitled"


def stage_dir(run_root: Path, paper_id: str, stage_name: str) -> Path:
    d = Path(run_root) / paper_id / stage_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, obj: Any) -> None:
    path.write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def mark_done(stage_path: Path, extra: dict[str, Any] | None = None) -> None:
    dump_yaml(stage_path / "done.yaml", {"finished_at": time.time(), **(extra or {})})


def is_done(stage_path: Path) -> bool:
    return (stage_path / "done.yaml").exists()


BBOX_FROM_NAME = _re.compile(r"_(\d+)_(\d+)_(\d+)_(\d+)\.[A-Za-z0-9]+$")
DOC_PAGE = _re.compile(r"doc_(\d+)\.md$")


def bbox_from_filename(rel_path: str) -> "tuple[int, int, int, int] | None":
    m = BBOX_FROM_NAME.search(Path(rel_path).name)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


_FLOW_SEQ_FIX = _re.compile(r"\[([^\]\n]*)\]")


def _quote_flow_items(match: _re.Match) -> str:
    body = match.group(1)
    # Split on commas not in quotes
    items = [s.strip() for s in body.split(",")]
    quoted = []
    for it in items:
        if not it:
            continue
        if (it.startswith('"') and it.endswith('"')) or (it.startswith("'") and it.endswith("'")):
            quoted.append(it)
        elif _re.search(r"[:?#&*!|>%@`,\[\]{}]", it):
            esc = it.replace("'", "''")
            quoted.append(f"'{esc}'")
        else:
            quoted.append(it)
    return "[" + ", ".join(quoted) + "]"


_TOP_LEVEL_KV = _re.compile(r"^([A-Za-z_]\w*):\s+(.+)$")


def _quote_unquoted_scalar(text: str) -> str:
    """For top-level 'key: value' lines where value is unquoted and contains a problematic
    ': ' or '?' that would confuse YAML, wrap the value in double quotes."""
    out_lines: list[str] = []
    for line in text.splitlines():
        m = _TOP_LEVEL_KV.match(line)
        if not m:
            out_lines.append(line)
            continue
        key, value = m.group(1), m.group(2).rstrip()
        if not value:
            out_lines.append(line)
            continue
        first = value[0]
        # Already quoted / a flow collection / block scalar / alias → leave alone
        if first in ('"', "'", '[', '{', '|', '>', '&', '*', '!', '#'):
            out_lines.append(line)
            continue
        # Problematic if value contains ': ' (mapping confusion) or unquoted '?' inside
        # a sentence (flow context confusion would only matter inside [], already handled).
        if _re.search(r":\s", value) or value.endswith(":"):
            esc = value.replace("\\", "\\\\").replace('"', '\\"')
            out_lines.append(f"{key}: \"{esc}\"")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def safe_parse_yaml(text: str) -> Any:
    """Parse LLM-returned YAML defensively.

    Tries plain yaml.safe_load first; on YAMLError, attempts to repair common
    issues (quoting flow-sequence items containing reserved chars, quoting
    top-level scalar values containing colons) and retries.
    Returns None on total failure.
    """
    if not text or not text.strip():
        return None
    # 1) Plain
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        pass
    # 2) Repair flow sequences only
    fixed1 = _FLOW_SEQ_FIX.sub(_quote_flow_items, text)
    try:
        return yaml.safe_load(fixed1)
    except yaml.YAMLError:
        pass
    # 3) Quote unquoted scalars containing colons
    fixed2 = _quote_unquoted_scalar(text)
    try:
        return yaml.safe_load(fixed2)
    except yaml.YAMLError:
        pass
    # 4) Both repairs together
    fixed3 = _quote_unquoted_scalar(_FLOW_SEQ_FIX.sub(_quote_flow_items, text))
    try:
        return yaml.safe_load(fixed3)
    except yaml.YAMLError:
        return None
