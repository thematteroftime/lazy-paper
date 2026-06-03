"""Stage 03: split cleaned doc_*.md into chapters using IMRaD section anchors."""
from __future__ import annotations

import re
from pathlib import Path

from stages._common import dump_yaml, mark_done, slugify

# ─── Bilingual section anchors (add a new key to extend a language) ───────
# Each entry: lowercased English form OR Chinese literal. Matched against
# the line's title; if any matches the chapter starts. Chinese papers
# previously collapsed to a single chapter because only English anchors
# were here.
SECTION_ANCHORS = {
    # English IMRaD
    "abstract", "introduction", "experimental", "experiments",
    "materials and methods", "methods", "methodology",
    "results", "results and discussion", "discussion",
    "conclusion", "conclusions", "summary",
    "acknowledgements", "acknowledgments",
    "references", "supplementary", "appendix",
    # Common conference-paper variants (IEEE / robotics / RL):
    "related work", "related works", "background",
    "problem formulation", "problem statement",
    "approach", "method", "system overview", "system design",
    "evaluation", "evaluations", "ablation", "ablations",
    "discussion and conclusion", "discussions and conclusions",
    "limitations", "future work",
    # Chinese equivalents
    "摘要", "引言", "前言", "绪论", "实验", "实验方法",
    "材料与方法", "材料和方法", "方法", "结果", "结果与讨论",
    "结果和讨论", "讨论", "结论", "总结", "致谢", "参考文献",
    "补充材料", "附录", "相关工作", "背景", "问题描述",
    "方法概述", "系统设计", "评估", "消融",
}

# Heading regex: number prefix optional; title starts with [A-Z一-鿿]
# (latin capital OR CJK), continues with mixed alphanumeric + CJK + spaces.
# Number prefix accepts either arabic ("1.", "2.3.") or Roman ("I.", "II.")
# — IEEE/conference papers often use Roman numerals for top-level sections.
_ANCHOR_LINE_RE = re.compile(
    r"^\s*(#{0,4}\s*)?(\d+(?:\.\d+){0,2}\.?\s+|[IVX]{1,5}\.\s+)?"
    r"(?P<title>[A-Z一-鿿][A-Za-z一-鿿 &/-]{1,60})\s*$"
)


def detect_science_anchor(line: str) -> str | None:
    m = _ANCHOR_LINE_RE.match(line.strip())
    if not m:
        return None
    title = m.group("title").strip()
    # exact-match against bilingual anchor set
    if title.lower() in SECTION_ANCHORS:
        return title
    if m.group(2) and 4 <= len(title) <= 60:
        return f"{m.group(2).strip()} {title}".strip()
    return None


def _clean_len(lines: list[str]) -> int:
    text = re.sub(r"<[^>]+>", "", "\n".join(lines))
    return len(re.sub(r"\s+", "", text))


def run(*, in_dir: Path, out_dir: Path, min_chars: int = 1) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir = out_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    for stale in chapters_dir.glob("chapter_*.md"):
        stale.unlink()

    docs = sorted(in_dir.glob("doc_*.md"))
    if not docs:
        raise FileNotFoundError(f"no doc_*.md in {in_dir}")

    chapter_no = 0
    current_title = "Preface"
    current_lines: list[str] = []
    current_sources: list[str] = []
    chapter_index: list[dict] = []

    def flush() -> None:
        nonlocal chapter_no, current_lines, current_sources, current_title
        body = "\n".join(current_lines).strip()
        if not body:
            return
        fname = f"chapter_{chapter_no:03d}_{slugify(current_title)}.md"
        (chapters_dir / fname).write_text(
            f"<!-- sources: {', '.join(current_sources)} -->\n\n{body}\n",
            encoding="utf-8",
        )
        chapter_index.append({
            "chapter_no": chapter_no,
            "title": current_title,
            "file": fname,
            "sources": current_sources[:],
            "chars": _clean_len(current_lines),
        })
        chapter_no += 1
        current_lines = []
        current_sources = []

    for doc in docs:
        for line in doc.read_text(encoding="utf-8").splitlines():
            heading = detect_science_anchor(line)
            if heading and _clean_len(current_lines) >= min_chars:
                flush()
                current_title = heading
            current_lines.append(line)
        current_sources.append(doc.name)
        current_lines.append("")
    flush()

    dump_yaml(out_dir / "chapter_index.yaml", chapter_index)
    mark_done(out_dir, {"count": len(chapter_index)})
    return {"count": len(chapter_index)}
