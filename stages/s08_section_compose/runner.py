"""Stage 08: write per-section Chinese body via text LLM, driven by template."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from llm.client import LLM, max_tokens
from llm.paper_kg import PaperKG
from llm.retriever import Retriever
from stages._common import dump_yaml, mark_done, slugify
from stages.s08_section_compose.reviewer import regex_check

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
            # v1.3 T5: keep more caption context (was 120) so the composer can
            # cite specific table columns rather than a hint.
            cap_short = cap[:300].replace("\n", " ").strip()
            tbl_lines.append(f"{tid}: {cap_short}")
        tables_str = "\n".join(tbl_lines)
    else:
        tables_str = _MISSING["tables"]

    # v1.3 T5: each figure's deep_observation truncated to 400 chars (was 100)
    # so chapters can integrate caveats and quantitative anchors instead of
    # paraphrasing.
    if fig_notes:
        obs_lines = []
        for note in fig_notes:
            fid = note.get("fig_id", "?")
            obs = (note.get("deep_observation") or note.get("deep_observation_cn") or "").strip()
            obs_short = obs[:400].replace("\n", " ")
            if len(obs) > 400:
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
    """Return up to 15000 chars (v1.3 T8: was 8000) of the most-keyword-relevant
    source chapters. Bigger budget lets the composer notice cross-chapter
    contradictions instead of paraphrasing one segment.
    """
    chapter_paths = sorted(chapters_dir.glob("chapter_*.md"))
    # If the paper has ≤ 8 source chapters, fold them all in — most short
    # papers fit comfortably under 15000 chars combined and we then get true
    # paper-wide synthesis instead of keyword-window peeking.
    if len(chapter_paths) <= 8:
        full = "\n\n---\n\n".join(p.read_text(encoding="utf-8") for p in chapter_paths)
        return full[:15000]
    scored: list[tuple[int, str]] = []
    for p in chapter_paths:
        text = p.read_text(encoding="utf-8")
        scored.append((_keyword_score(text, keywords), text))
    scored.sort(key=lambda t: -t[0])
    selected = [t for s, t in scored[:top_k] if s > 0]
    if not selected:
        # Fall back: include results chapter or first content chapter
        for p in chapter_paths:
            if "Results" in p.name or "Introduction" in p.name:
                selected.append(p.read_text(encoding="utf-8"))
                break
    return "\n\n---\n\n".join(selected)[:15000]


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


def _legacy_compose(llm, system_tpl, user_tpl, paper_context_str, node, idx,
                    title_cn, title_en, guidance, hints, keywords,
                    chapters_dir, fig_notes, figures, retriever,
                    out_dir, basename) -> str:
    """v1.3.x prompt-stuffed compose path. Used as agent fallback or when no PaperDB."""
    if retriever is not None:
        chunks = retriever.retrieve(guidance, top_k=8)
        excerpts = "\n\n---\n\n".join(c.text for c in chunks)[:15000]
    else:
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
    return response.content.strip()


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

    # v1.4: PaperDB load (soft-degrade to v1.3.3 behavior on failure)
    kg: PaperKG | None = None
    retriever: Retriever | None = None
    kg_path = context_dir / "paper_kg.parquet"
    if kg_path.exists() and not (context_dir / "kg_extract.failed").exists():
        try:
            kg = PaperKG.from_parquet(kg_path)
        except Exception as exc:
            print(f"[s08] kg load failed: {exc!r}; degrading", flush=True)
    retr_path = out_dir / "retrieval.parquet"
    try:
        if not retr_path.exists():
            Retriever().build(chapters_dir=chapters_dir, out_path=retr_path)
        retriever = Retriever.load(retr_path)
    except Exception as exc:
        print(f"[s08] retriever build failed: {exc!r}; using keyword fallback", flush=True)
        retriever = None

    # Source docs cache for reviewer
    source_docs: dict[str, str] = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(chapters_dir.glob("chapter_*.md"))
    }

    llm = LLM(role="text")
    written: list[str] = []
    all_flags: dict[str, list[dict]] = {}

    for idx, node in enumerate(template):
        title_cn = node["title"]
        title_en = node["title"]
        guidance = node.get("guidance", "")
        guidance = substitute_placeholders(guidance, paper_data)
        title_cn = substitute_placeholders(title_cn, paper_data)
        hints = node.get("hints", {})
        keywords = re.findall(r"[A-Za-z一-鿿]{3,}", f"{title_cn} {guidance}")

        slug = slugify(title_cn, maxlen=30)
        basename = f"{idx + 1:02d}-{slug}"

        # v1.4: prompt-stuffed compose with retriever-fed evidence. The
        # tool-using agent (stages.s08_section_compose.agent) is experimental
        # and disabled by default — set LAZY_PAPER_AGENT=1 to opt in. Live
        # runs showed the LLM occasionally returning meta-commentary instead
        # of section prose when given a tool-using agent loop; the
        # retriever-fed compose path delivers the quality win without that
        # failure mode. Reviewer + KG + citations remain active either way.
        composed: str
        if os.environ.get("LAZY_PAPER_AGENT") == "1" and retriever is not None and kg is not None:
            try:
                from stages.s08_section_compose.agent import run_section_agent
                prior_bullet = written[-1] if written else ""
                composed = run_section_agent(
                    section={"title": title_cn, "guidance": guidance},
                    kg=kg, retriever=retriever,
                    prior_bullet=prior_bullet, max_iters=8,
                )
            except Exception as exc:
                print(f"[s08] agent failed for {basename}: {exc!r}; legacy compose",
                      flush=True)
                composed = _legacy_compose(
                    llm, system_tpl, user_tpl, paper_context_str, node, idx,
                    title_cn, title_en, guidance, hints, keywords,
                    chapters_dir, fig_notes, figures, retriever,
                    out_dir, basename,
                )
        else:
            composed = _legacy_compose(
                llm, system_tpl, user_tpl, paper_context_str, node, idx,
                title_cn, title_en, guidance, hints, keywords,
                chapters_dir, fig_notes, figures, retriever,
                out_dir, basename,
            )

        # Critic — regex tier always; LLM tier only when flags > 0
        flags = []
        if kg is not None:
            flags = regex_check(composed, source_docs, kg=kg, fig_yaml=figures)
            if flags:
                from stages.s08_section_compose.reviewer import llm_review
                evidence = "\n".join(
                    f"[{c.doc_name}] {c.text[:200]}"
                    for c in (retriever.retrieve(guidance, top_k=4) if retriever else [])
                )
                try:
                    rev = llm_review(composed, flags, evidence)
                    composed = rev.revised_draft
                    flags2 = regex_check(composed, source_docs, kg=kg, fig_yaml=figures)
                    if flags2:
                        all_flags[basename] = [f.model_dump() for f in flags2]
                        print(f"[critic-unresolved] {basename}: {len(flags2)} flags",
                              flush=True)
                except Exception as exc:
                    all_flags[basename] = [f.model_dump() for f in flags]
                    print(f"[critic-llm-failed] {basename}: {exc!r}; keeping flags",
                          flush=True)

        # v1.5 stub
        from stages.s08_section_compose.findings import (
            extract_claims, append_verified_claims,
        )
        append_verified_claims(
            out_dir=out_dir, section_name=basename, claims=extract_claims(composed),
        )

        md_file = out_chapters / f"{basename}.md"
        heading = f"# {title_cn}\n\n"
        md_file.write_text(heading + composed + "\n", encoding="utf-8")
        written.append(md_file.name)

    if all_flags:
        dump_yaml(out_dir / "critic_flags.yaml", all_flags)

    agent_enabled = os.environ.get("LAZY_PAPER_AGENT") == "1"
    dump_yaml(out_dir / "written.yaml", written)
    mark_done(out_dir, {
        "sections": len(written),
        "retriever": "ok" if retriever else "degraded",
        "kg": "ok" if kg else "missing",
        "agent": "enabled" if (agent_enabled and kg and retriever) else "disabled",
        "flagged_sections": len(all_flags),
    })
    return {"sections": len(written)}
