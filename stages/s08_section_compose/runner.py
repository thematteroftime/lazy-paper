"""Stage 08: write per-section Chinese body via text LLM, driven by template."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from llm.client import LLM
from stages._common import dump_yaml, mark_done, slugify

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "section_compose.md"


def _split_prompt(template: str) -> tuple[str, str]:
    sys_idx = template.index("SYSTEM:") + len("SYSTEM:")
    usr_idx = template.index("USER:")
    return template[sys_idx:usr_idx].strip(), template[usr_idx + len("USER:"):].strip()


def _keyword_score(text: str, keywords: list[str]) -> int:
    return sum(text.lower().count(k.lower()) for k in keywords if k)


def _relevant_chapter_excerpts(chapters_dir: Path, keywords: list[str], top_k: int = 2) -> str:
    scored: list[tuple[int, str]] = []
    for p in sorted(chapters_dir.glob("chapter_*.md")):
        text = p.read_text(encoding="utf-8")
        scored.append((_keyword_score(text, keywords), text))
    scored.sort(key=lambda t: -t[0])
    selected = [t for s, t in scored[:top_k] if s > 0]
    if not selected:
        # Fall back: include results chapter or first content chapter
        for p in sorted(chapters_dir.glob("chapter_*.md")):
            if "Results" in p.name or "Introduction" in p.name:
                selected.append(p.read_text(encoding="utf-8"))
                break
    return "\n\n---\n\n".join(selected)[:8000]


def _relevant_fig_notes(fig_notes: list[dict], figures: list[dict], keywords: list[str]) -> str:
    captions_by_fid = {f["fig_id"]: f.get("caption", "") for f in figures}
    scored: list[tuple[int, dict]] = []
    for note in fig_notes:
        fid = note.get("fig_id", "")
        cap = captions_by_fid.get(fid, "")
        score = _keyword_score(cap + " " + (note.get("deep_observation") or note.get("deep_observation_cn") or ""), keywords)
        scored.append((score, note))
    scored.sort(key=lambda t: -t[0])
    picked = [n for s, n in scored[:3] if s > 0]
    return yaml.safe_dump(picked, allow_unicode=True, sort_keys=False) if picked else "(none)"


LANG_INSTRUCTIONS = {
    "zh": "Write the section body in fluent Chinese with embedded English technical terms.",
    "en": "Write the section body in fluent English (avoid Chinese characters).",
}


def run(*, template_dir: Path, chapters_dir: Path, context_dir: Path,
        fig_notes_dir: Path, figures_stage_dir: Path, out_dir: Path,
        lang: str = "zh") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_chapters = out_dir / "chapters"
    out_chapters.mkdir(exist_ok=True)
    for stale in out_chapters.glob("*.md"):
        stale.unlink()

    template = yaml.safe_load((template_dir / "template.yaml").read_text(encoding="utf-8")) or []
    context = yaml.safe_load((context_dir / "context.yaml").read_text(encoding="utf-8")) or {}
    fig_notes = yaml.safe_load((fig_notes_dir / "fig_notes.yaml").read_text(encoding="utf-8")) or []
    figures = yaml.safe_load((figures_stage_dir / "figures.yaml").read_text(encoding="utf-8")) or []

    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    lang_text = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["zh"])
    system_tpl = system_tpl.replace("{lang_instruction}", lang_text)
    user_tpl = user_tpl.replace("{lang_instruction}", lang_text)
    paper_context_str = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)

    llm = LLM(role="text")
    written: list[str] = []
    for idx, node in enumerate(template):
        title_cn = node["title"]
        title_en = node["title"]
        guidance = node.get("guidance", "")
        hints = node.get("hints", {})
        keywords = re.findall(r"[A-Za-z一-鿿-]{3,}", f"{title_cn} {guidance}")

        excerpts = _relevant_chapter_excerpts(chapters_dir, keywords)
        notes_block = _relevant_fig_notes(fig_notes, figures, keywords)

        user_msg = (user_tpl
                    .replace("{paper_context}", paper_context_str)
                    .replace("{number}", str(node.get("number", idx + 1)))
                    .replace("{title_cn}", title_cn)
                    .replace("{title_en}", title_en)
                    .replace("{guidance}", guidance)
                    .replace("{needs_table}", str(hints.get("needs_table", False)))
                    .replace("{needs_figure}", str(hints.get("needs_figure", False)))
                    .replace("{chapter_excerpts}", excerpts)
                    .replace("{fig_notes_block}", notes_block))

        slug = slugify(title_cn, maxlen=30)
        basename = f"{idx + 1:02d}-{slug}"
        (out_dir / f"{basename}.prompt.md").write_text(
            f"# SYSTEM\n{system_tpl}\n\n# USER\n{user_msg}", encoding="utf-8"
        )
        response = llm.chat(system=system_tpl, user=user_msg, max_tokens=3000)
        (out_dir / f"{basename}.response.json").write_text(
            json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                        "usage": response.usage, "content": response.content},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_file = out_chapters / f"{basename}.md"
        heading = f"# {node.get('number', idx + 1)} {title_cn}\n\n"
        md_file.write_text(heading + response.content.strip() + "\n", encoding="utf-8")
        written.append(md_file.name)

    dump_yaml(out_dir / "written.yaml", written)
    mark_done(out_dir, {"sections": len(written)})
    return {"sections": len(written)}
