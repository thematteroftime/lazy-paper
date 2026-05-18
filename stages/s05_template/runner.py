"""Stage 05: parse a user-provided outline docx into a hierarchical structure."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn as _qn

from stages._common import dump_yaml, mark_done

_NEEDS_TABLE_RE = re.compile(r"\b(?:provide|include|tabulate|tables?)\b.*\btable", re.IGNORECASE)
_NEEDS_FIGURE_RE = re.compile(r"\b(?:figure|illustration|diagram|chart)\b", re.IGNORECASE)
_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\s+(.+?)\s*$")

_GUIDANCE_PREFIXES = ("(", "-", "–", "—", "[", "·", "•")

# Action-verb starters that signal an instruction/guidance line, not a section title
_ACTION_VERB_RE = re.compile(
    r"^(?:To |Discuss |Provide |Include |Describe |Explain |Summarize |Show |Disuss |Consider )",
    re.IGNORECASE,
)


def _hints(text: str) -> dict:
    return {
        "needs_table": bool(_NEEDS_TABLE_RE.search(text)),
        "needs_figure": bool(_NEEDS_FIGURE_RE.search(text)),
    }


def _list_ilvl(para) -> int:
    """Return numbering indent level (0 = top-level list), or -1 if not in a list."""
    pPr = para._element.find(_qn("w:pPr"))
    if pPr is None:
        return -1
    numPr = pPr.find(_qn("w:numPr"))
    if numPr is None:
        return -1
    ilvl = numPr.find(_qn("w:ilvl"))
    if ilvl is None:
        return 0
    try:
        return int(ilvl.get(_qn("w:val"), "0"))
    except ValueError:
        return 0


def _is_guidance_line(text: str) -> bool:
    """Return True if *text* looks like guidance/instruction rather than a section title."""
    s = text.lstrip()
    if not s:
        return True
    # Use only the first line for prefix/length checks (multiline paragraphs may embed guidance)
    first_line = s.split("\n")[0].strip()
    if first_line[0] in _GUIDANCE_PREFIXES:
        return True
    # Short trivial fragments (e.g. "etc.", "…")
    if len(first_line) <= 5 and not first_line[0].isupper():
        return True
    if first_line.lower() in {"etc.", "etc", "...", "…"}:
        return True
    # Lines ending with '?' are rhetorical questions / discussion prompts
    if s.rstrip().endswith("?"):
        return True
    # Contains '->' or '→' arrow notation (inline notes)
    if "->" in first_line or "→" in first_line:
        return True
    if len(s) > 100 and ("," in s or ";" in s or "。" in s):
        return True
    # Lines starting with lowercase ASCII (and not numbered) are almost never section titles
    if s[0].islower() and not _NUMBERED_RE.match(s):
        return True
    # Action-verb instruction starters
    if _ACTION_VERB_RE.match(first_line):
        return True
    return False


def _split_paragraph_text(text: str) -> tuple[str, str]:
    """Split a paragraph that may embed '\\n' into (title_line, extra_guidance)."""
    parts = text.split("\n", 1)
    title = parts[0].strip()
    extra = parts[1].strip() if len(parts) > 1 else ""
    return title, extra


def parse_template(template_docx: Path) -> list[dict]:
    doc = Document(template_docx)
    nodes: list[dict] = []
    current: dict | None = None

    def _attach_to_current(title: str, body: str) -> None:
        """Either add as a child of the current node or append to its guidance."""
        if current is None:
            return
        if body:
            child = {"title": title, "guidance": body}
        else:
            child = {"title": title, "guidance": ""}
        current["children"].append(child)
        text_block = f"{title}: {body}".rstrip(": ") if body else title
        current["guidance"] = (current["guidance"] + "\n" + text_block).strip()
        current["hints"] = _hints(current["guidance"])

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        ilvl = _list_ilvl(para)
        is_list_top = (style == "List Paragraph" and ilvl <= 0)
        is_numbered = bool(_NUMBERED_RE.match(text))

        if (is_list_top or is_numbered) and not _is_guidance_line(text):
            title_line, extra_guidance = _split_paragraph_text(text)
            m = _NUMBERED_RE.match(title_line)
            if m:
                number, title = m.group(1), m.group(2)
                level = number.count(".") + 1
            else:
                number, title, level = "", title_line, 1
            current = {
                "level": level,
                "number": number,
                "title": title,
                "guidance": extra_guidance,
                "hints": _hints(extra_guidance),
                "children": [],
            }
            nodes.append(current)
        elif style == "List Paragraph" and ilvl >= 1:
            # Sub-bullet: attach to current as a child
            _attach_to_current(text, "")
        else:
            # Normal body / guidance for the most recently opened heading
            if current is None:
                continue
            current["guidance"] = (current["guidance"] + "\n" + text).strip()
            current["hints"] = _hints(current["guidance"])

    return nodes


def run(*, template_docx: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tree = parse_template(template_docx)
    dump_yaml(out_dir / "template.yaml", tree)
    mark_done(out_dir, {"top_level_nodes": len(tree)})
    return {"top_level_nodes": len(tree)}
