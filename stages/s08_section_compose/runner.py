"""Stage 08: write per-section Chinese body via text LLM, driven by template."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from llm.client import LLM, max_tokens
from stages._common import dump_yaml, mark_done, slugify

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "section_compose.md"

# Fallback text when a placeholder has no data
_MISSING = {
    "tables": "本论文未检出独立表格 / No standalone tables detected in this paper.",
    "figures": "（图信息未检出 / No figure data available）",
    "fig_observations_brief": "（无图注分析数据 / No figure observation data available）",
    "abbreviations": "（缩写信息未检出 / No abbreviation data available）",
    "keywords": "（关键词未检出 / No keywords available）",
    "key_terms": "（关键术语未检出 / No key terms available）",
    "title": "（标题未检出 / Title not available）",
    "system": "（研究体系未检出 / System not available）",
}


def _build_paper_data(
    context: dict,
    figures: list[dict],
    tables: list[dict],
    fig_notes: list[dict],
) -> dict[str, str]:
    """Build the {paper.X} substitution dictionary from per-paper data sources.

    Keys match the placeholder vocabulary: title, system, keywords, key_terms,
    abbreviations, figures, tables, fig_observations_brief.
    """
    # title
    title = str(context.get("title", "")).strip() or _MISSING["title"]

    # system
    system = str(context.get("system", "")).strip() or _MISSING["system"]

    # keywords — top 5, semicolon-joined
    raw_kw = context.get("keywords", []) or []
    keywords_str = "; ".join(str(k) for k in raw_kw[:5]) if raw_kw else _MISSING["keywords"]

    # key_terms — all, semicolon-joined
    raw_kt = context.get("key_terms", []) or []
    key_terms_str = "; ".join(str(k) for k in raw_kt) if raw_kt else _MISSING["key_terms"]

    # abbreviations — inline "ABB = expansion" list
    raw_abbr = context.get("abbreviations", []) or []
    if raw_abbr:
        abbr_parts = [
            f"{a.get('abbr', '')} = {a.get('expansion', '')}"
            for a in raw_abbr
            if a.get("abbr") or a.get("expansion")
        ]
        abbreviations_str = "; ".join(abbr_parts) if abbr_parts else _MISSING["abbreviations"]
    else:
        abbreviations_str = _MISSING["abbreviations"]

    # figures — one-line-per-fig "Fig.N: caption (truncated)"
    if figures:
        fig_lines = []
        for f in figures:
            fid = f.get("fig_id", "?")
            cap = f.get("caption", "")
            # Truncate caption to 120 chars to keep prompt manageable
            cap_short = cap[:120].replace("\n", " ").strip()
            if len(cap) > 120:
                cap_short += "..."
            fig_lines.append(f"{fid}: {cap_short}")
        figures_str = "\n".join(fig_lines)
    else:
        figures_str = _MISSING["figures"]

    # tables — one-line-per-table, or fallback
    if tables:
        tbl_lines = []
        for t in tables:
            tid = t.get("table_id", t.get("fig_id", "?"))
            cap = t.get("caption", "")
            cap_short = cap[:120].replace("\n", " ").strip()
            tbl_lines.append(f"{tid}: {cap_short}")
        tables_str = "\n".join(tbl_lines)
    else:
        tables_str = _MISSING["tables"]

    # fig_observations_brief — each fig's deep_observation truncated to 100 chars
    if fig_notes:
        obs_lines = []
        for note in fig_notes:
            fid = note.get("fig_id", "?")
            obs = (note.get("deep_observation") or note.get("deep_observation_cn") or "").strip()
            obs_short = obs[:100].replace("\n", " ")
            if len(obs) > 100:
                obs_short += "..."
            if obs_short:
                obs_lines.append(f"{fid} — {obs_short}")
        fig_observations_brief_str = "\n".join(obs_lines) if obs_lines else _MISSING["fig_observations_brief"]
    else:
        fig_observations_brief_str = _MISSING["fig_observations_brief"]

    return {
        "title": title,
        "system": system,
        "keywords": keywords_str,
        "key_terms": key_terms_str,
        "abbreviations": abbreviations_str,
        "figures": figures_str,
        "tables": tables_str,
        "fig_observations_brief": fig_observations_brief_str,
    }


def substitute_placeholders(text: str, paper_data: dict[str, str]) -> str:
    """Replace all {paper.X} tokens in *text* with concrete values from *paper_data*.

    Unknown placeholder keys are left as-is (not silently dropped).
    """
    def _sub(m: re.Match) -> str:
        key = m.group(1)  # e.g. "system" or "figures"
        val = paper_data.get(key)
        if val is None:
            # Unknown key — leave verbatim so authors notice
            return m.group(0)
        if isinstance(val, list):
            return "; ".join(str(v) for v in val)
        return str(val)

    return re.sub(r"\{paper\.([a-z_]+)\}", _sub, text)


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

    # Load tables (optional — path may not exist or be empty)
    tables_path = figures_stage_dir / "tables.yaml"
    tables: list[dict] = []
    if tables_path.exists():
        tables = yaml.safe_load(tables_path.read_text(encoding="utf-8")) or []

    # Build paper-specific substitution dictionary
    paper_data = _build_paper_data(context, figures, tables, fig_notes)

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

        # --- SUBSTITUTE {paper.X} placeholders BEFORE building the LLM prompt ---
        guidance = substitute_placeholders(guidance, paper_data)
        title_cn = substitute_placeholders(title_cn, paper_data)

        hints = node.get("hints", {})
        keywords = re.findall(r"[A-Za-z一-鿿]{3,}", f"{title_cn} {guidance}")

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
        response = llm.chat(system=system_tpl, user=user_msg, max_tokens=max_tokens(12000))
        (out_dir / f"{basename}.response.json").write_text(
            json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                        "usage": response.usage, "content": response.content},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_file = out_chapters / f"{basename}.md"
        heading = f"# {title_cn}\n\n"
        md_file.write_text(heading + response.content.strip() + "\n", encoding="utf-8")
        written.append(md_file.name)

    dump_yaml(out_dir / "written.yaml", written)
    mark_done(out_dir, {"sections": len(written)})
    return {"sections": len(written)}
