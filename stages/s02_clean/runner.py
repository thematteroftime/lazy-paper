"""Stage 02: clean OCR doc_*.md (header strip, char repair, column-flow flag)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from stages._common import mark_done


def strip_running_headers(docs: list[str], min_repeat: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for d in docs:
        seen: set[str] = set()
        for raw in d.splitlines():
            line = raw.strip()
            if not line or len(line) > 120 or line in seen:
                continue
            seen.add(line)
            counter[line] += 1
    drop = {ln for ln, n in counter.items() if n >= min_repeat}
    return ["\n".join(raw for raw in d.splitlines() if raw.strip() not in drop) for d in docs]


_CID_MAP = {"(cid:0)": "−"}
_SUB_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_OXIDE_RE = re.compile(r"\b([A-Z][a-z]?(?:[A-Z][a-z]?\d*)*[A-Z][a-z]?)\s+(\d{1,2})\b")
_CATION_PLUS_RE = re.compile(r"\b([A-Z][a-z]?)\s+\+\s*\)")


def repair_chars(text: str) -> str:
    for k, v in _CID_MAP.items():
        text = text.replace(k, v)

    def _ox(m: re.Match[str]) -> str:
        prefix, digits = m.group(1), m.group(2)
        if not re.search(r"[A-Z]", prefix):
            return m.group(0)
        return f"{prefix}{digits.translate(_SUB_DIGITS)}"

    text = _OXIDE_RE.sub(_ox, text)
    text = _CATION_PLUS_RE.sub(lambda m: f"{m.group(1)}⁺)", text)
    return text


def flag_corrupted_column_flow(text: str) -> str:
    out_lines = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) >= 20:
            singletons = sum(1 for t in tokens if len(t) == 1)
            if singletons / len(tokens) > 0.6:
                out_lines.append("<!-- corrupted-column-flow -->\n" + line)
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


def run(*, in_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = sorted(in_dir.glob("doc_*.md"))
    if not docs:
        raise FileNotFoundError(f"no doc_*.md in {in_dir}")
    texts = [p.read_text(encoding="utf-8") for p in docs]
    texts = strip_running_headers(texts, min_repeat=3)
    for src, txt in zip(docs, texts):
        cleaned = flag_corrupted_column_flow(repair_chars(txt))
        (out_dir / src.name).write_text(cleaned, encoding="utf-8")
    # also copy imgs/ if present so downstream stages still find images relative to out_dir
    imgs = in_dir / "imgs"
    if imgs.exists():
        dst = out_dir / "imgs"
        dst.mkdir(exist_ok=True)
        for p in imgs.iterdir():
            (dst / p.name).write_bytes(p.read_bytes())
    mark_done(out_dir, {"docs": len(docs)})
    return {"docs": len(docs)}
