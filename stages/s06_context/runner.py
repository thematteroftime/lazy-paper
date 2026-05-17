"""Stage 06: extract paper context (system, abbreviations, keywords) via text LLM."""
from __future__ import annotations

import json
from pathlib import Path

from llm.client import LLM
from stages._common import dump_yaml, mark_done, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "paper_context.md"


def _gather_paper_text(chapters_dir: Path) -> str:
    pieces: list[str] = []
    for name in ("chapter_000_Preface.md", "chapter_001_Introduction.md"):
        p = chapters_dir / name
        if p.exists():
            pieces.append(p.read_text(encoding="utf-8"))
    if not pieces:
        for p in sorted(chapters_dir.glob("chapter_*.md"))[:2]:
            pieces.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(pieces)[:20000]



def _split_prompt(template_text: str, paper_text: str) -> tuple[str, str]:
    system_marker = "SYSTEM:"
    user_marker = "USER:"
    sys_idx = template_text.index(system_marker) + len(system_marker)
    user_idx = template_text.index(user_marker)
    system = template_text[sys_idx:user_idx].strip()
    user = template_text[user_idx + len(user_marker):].strip().replace("{paper_text}", paper_text)
    return system, user


def run(*, chapters_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paper_text = _gather_paper_text(chapters_dir)
    template_text = PROMPT_PATH.read_text(encoding="utf-8")
    system, user = _split_prompt(template_text, paper_text)

    (out_dir / "paper_context.prompt.md").write_text(
        f"# SYSTEM\n{system}\n\n# USER\n{user}", encoding="utf-8"
    )

    llm = LLM(role="text")
    response = llm.chat(system=system, user=user, max_tokens=1500)
    (out_dir / "paper_context.response.json").write_text(
        json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                    "usage": response.usage, "content": response.content},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    data = safe_parse_yaml(response.content) or {}
    dump_yaml(out_dir / "context.yaml", data)
    mark_done(out_dir, {"tokens": response.usage.get("total_tokens")})
    return data
