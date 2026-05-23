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
from stages.s08_section_compose.reviewer import Flag, regex_check

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


_CHINESE = re.compile(r"[一-鿿]")


def _zh_ratio(text: str) -> float:
    text = re.sub(r"#.*", "", text)  # strip header
    body = "".join(text.split())
    if not body:
        return 0.0
    return len(_CHINESE.findall(body)) / len(body)


def _build_retrieval_query(title: str, guidance: str, kg, keywords: list[str]) -> str:
    """Strategy C: expand the retrieval query beyond raw guidance.

    Adds section title + (when KG is available) the text of any KG entity
    whose tokens overlap the section title/guidance. This surfaces source
    chunks the retriever might miss when guidance is short or generic.
    """
    parts = [title, guidance]
    if kg is not None:
        try:
            from stages.s08_section_compose.structured import entities_in_scope
            scoped = entities_in_scope(title, guidance, kg)
            # cap to first 20 entity texts to keep query bounded
            parts.extend(e.text for e in scoped[:20])
        except Exception as exc:
            # Query expansion is best-effort; fall back to base query.
            print(f"[s08] query expansion skipped: {exc!r}", flush=True)
    parts.extend(keywords[:10])
    return " ; ".join(p for p in parts if p)


def _legacy_compose(llm, system_tpl, user_tpl, paper_context_str, node, idx,
                    title_cn, title_en, guidance, hints, keywords,
                    chapters_dir, fig_notes, figures, retriever,
                    out_dir, basename, lang: str = "zh",
                    prior_findings: str = "", kg=None) -> str:
    """Prompt-stuffed section composer with expanded retrieval (default v1.4.2+).

    Query is built from section title + guidance + KG-scoped entity texts;
    top_k=15 with up to 25K char excerpt context. This consistently outperformed
    the narrower v1.4.1 default on the meng2024 4-way A/B comparison (chapters
    averaged 1932 vs 1791 bytes, with the fewest critic flags).

    Env knobs (opt-in only):
      LAZY_PAPER_TWO_STEP=1     experimental — outline → expand pipeline.
      LAZY_PAPER_WHOLE_PAPER=1  Strategy I — skip retriever entirely and
                                pass the full cleaned source corpus
                                (capped at 50K chars to stay within
                                DeepSeek-Reasoner's 64K context). The
                                LLM is given a "focus" instruction to
                                identify the relevant subsection rather
                                than try to summarize the whole paper.
    """
    two_step = os.environ.get("LAZY_PAPER_TWO_STEP") == "1"
    whole_paper = os.environ.get("LAZY_PAPER_WHOLE_PAPER") == "1"

    chunks_for_two_step = []
    if whole_paper:
        # Strategy I: read the cleaned source corpus and feed it whole.
        clean_dir = chapters_dir.parent.parent / "s02_clean"
        pieces: list[str] = []
        for p in sorted(clean_dir.glob("doc_*.md")):
            pieces.append(f"=== {p.name} ===\n" + p.read_text(encoding="utf-8"))
        excerpts = "\n\n".join(pieces)[:50000]
    elif retriever is not None:
        query = _build_retrieval_query(title_cn, guidance, kg, keywords)
        chunks_for_two_step = retriever.retrieve(query, top_k=15)
        excerpts = "\n\n---\n\n".join(c.text for c in chunks_for_two_step)[:25000]
    else:
        excerpts = _relevant_chapter_excerpts(chapters_dir, keywords)

    # Strategy B short-circuits the rest of the prompt-stuffed path.
    if two_step and retriever is not None and chunks_for_two_step:
        from stages.s08_section_compose.two_step import compose_two_step
        try:
            composed = compose_two_step(
                llm=llm, section_title=title_cn, section_guidance=guidance,
                chunks=chunks_for_two_step, lang=lang,
            )
            (out_dir / f"{basename}.two_step.outline.md").write_text(
                f"# Two-step compose used for {basename}\n", encoding="utf-8"
            )
            if composed.strip():
                return composed
            print(f"[s08] two-step compose returned empty for {basename}; "
                  f"falling back to single-shot", flush=True)
        except Exception as exc:
            print(f"[s08] two-step compose failed for {basename}: {exc!r}; "
                  f"falling back to single-shot", flush=True)
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
                .replace("{fig_notes_block}", notes_block)
                .replace("{prior_findings}", prior_findings or "（本节为首节，无前文要点）"))
    # Strategy I: amend system prompt with "focus" instruction so the LLM
    # picks the relevant ~paragraphs from the whole paper rather than
    # trying to synthesize across the entire document.
    effective_system = system_tpl
    if whole_paper:
        effective_system = system_tpl + (
            "\n\n## WHOLE-PAPER MODE\n"
            "The {chapter_excerpts} block below contains the ENTIRE cleaned "
            "source paper, not pre-filtered chunks. For THIS section, your "
            "task is two-step:\n"
            "1. Mentally identify the 1–3 source paragraphs most relevant to "
            "this section's title + guidance. State the doc names you used "
            "in a comment-style first line (e.g. '> grounded in doc_5.md + "
            "doc_12.md').\n"
            "2. Write the section body grounded ONLY in those paragraphs. "
            "Do NOT pad with content from unrelated parts of the paper. "
            "Do NOT compress the whole paper into this section.\n"
            "Hallucination check: every number / chemical formula in your "
            "draft MUST appear in the source paragraphs you cited."
        )
    (out_dir / f"{basename}.prompt.md").write_text(
        f"# SYSTEM\n{effective_system}\n\n# USER\n{user_msg}", encoding="utf-8"
    )
    response = llm.chat(system=effective_system, user=user_msg,
                        max_tokens=max_tokens(12000))

    # Post-LLM language guard: if zh was requested but the draft came out
    # mostly English (LLM defaulting to source-paper language), retry once
    # with a system-prompt amendment that hard-enforces Chinese.
    composed = response.content.strip()
    ratio = _zh_ratio(composed)
    if lang == "zh" and len(composed) > 100 and ratio < 0.3:
        print(f"[s08] {basename}: zh requested but draft is mostly English "
              f"(zh ratio {ratio:.2f}); retrying", flush=True)
        forced_system = (system_tpl
                         + "\n\n## HARD LANGUAGE OVERRIDE\n"
                         "OUTPUT MUST BE WRITTEN IN CHINESE (中文) PROSE. "
                         "Embedded English technical terms (e.g., 'tape-casting', "
                         "'Vogel-Fulcher', chemical formulas) are allowed, but the "
                         "narrative sentences must be Chinese. If the previous "
                         "attempt was English, write the same content in Chinese now.")
        response = llm.chat(system=forced_system, user=user_msg,
                            max_tokens=max_tokens(12000))
        composed = response.content.strip()

    (out_dir / f"{basename}.response.json").write_text(
        json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                    "usage": response.usage, "content": response.content},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return composed


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
    prior_section_claims: list[str] = []  # accumulated across sections (v1.4.1)
    agent_actually_ran = False  # true iff at least one section used the agent path

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

        # v1.4.1: pass at most the last 8 prior-section claim bullets so the
        # composer can build on / refer back / contrast instead of restating.
        prior_findings_block = (
            "\n".join(f"- {c}" for c in prior_section_claims[-8:])
            if prior_section_claims else ""
        )

        # v1.6 Strategy J: structured compose with pre-injection (gated).
        # When LAZY_PAPER_STRUCTURED=1 and we have both KG + retriever, build
        # required-mentions + chunk list + run the instructor flow with the
        # verifier gate. This is the highest-grounding path; falls back to
        # _legacy_compose on any exception.
        composed: str
        structured_used = False
        if (os.environ.get("LAZY_PAPER_STRUCTURED") == "1"
                and retriever is not None and kg is not None):
            try:
                from stages.s08_section_compose.structured import (
                    build_required_mentions, select_top_required,
                    compose_structured, missing_required, _figure_relevance,
                )
                query = _build_retrieval_query(title_cn, guidance, kg, keywords)
                chunks = retriever.retrieve(query, top_k=15)
                required_all = build_required_mentions(
                    section_title=title_cn, section_guidance=guidance,
                    kg=kg, source_docs=source_docs, retrieved_chunks=chunks,
                )
                required = select_top_required(required_all, cap=5)
                # Figure-section binding is opt-in (LAZY_PAPER_FIGURE_BIND=1).
                # The extra prompt block can deprioritize required-mention
                # coverage on survey sections (observed regression on
                # meng2024 ch01 vs v1.8.1 baseline); enable for non-survey
                # sections that have visible figure-binding bugs.
                if os.environ.get("LAZY_PAPER_FIGURE_BIND") == "1":
                    section_figures = _figure_relevance(
                        title_cn, guidance, fig_notes, top_k=4,
                    )
                else:
                    section_figures = None
                lang_text = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["zh"])
                draft, rejected = compose_structured(
                    llm,
                    section_title=title_cn,
                    section_guidance=guidance,
                    lang_instruction=lang_text,
                    chunks=chunks,
                    required=required,
                    prior_findings=prior_findings_block,
                    paper_context=paper_context_str[:3000],
                    section_figures=section_figures,
                )
                composed = draft.render(mode="REMOVE")
                # Soft-warn audit: required mentions the LLM didn't cover
                still_missing = missing_required(required, draft)
                # variant-c: split rejected[] into real rejects (quote
                # mismatch, no matched chunk) vs figure advisories (claim
                # was accepted but its figure_ids literal isn't in text).
                # Auditor 2 cycle 2: lumping them inflated the
                # "verifier_rejects" count by ~50% in the audit log.
                real_rejects = [r for r in rejected
                                 if r.get("reason") != "figure_hint_unmet"]
                fig_advisories = [r for r in rejected
                                   if r.get("reason") == "figure_hint_unmet"]
                if still_missing or rejected:
                    note = {
                        "missing_required": [r.entity_text for r in still_missing],
                        "verifier_rejected": real_rejects,
                        "figure_advisories": fig_advisories,
                    }
                    all_flags.setdefault(basename, []).append(
                        {"problem": "structured_audit", **note}
                    )
                    print(f"[critic-structured] {basename}: "
                          f"{len(still_missing)} missing required, "
                          f"{len(real_rejects)} verifier rejects"
                          + (f", {len(fig_advisories)} figure advisories"
                             if fig_advisories else ""),
                          flush=True)
                # Audit file for the draft
                (out_dir / f"{basename}.structured.json").write_text(
                    draft.model_dump_json(indent=2), encoding="utf-8",
                )
                structured_used = True
            except Exception as exc:
                print(f"[s08] structured compose failed for {basename}: "
                      f"{exc!r}; falling back to legacy", flush=True)

        if structured_used:
            pass  # composed set above
        elif (os.environ.get("LAZY_PAPER_AGENT") == "1"
                and retriever is not None and kg is not None):
            try:
                from stages.s08_section_compose.agent import run_section_agent
                prior_bullet = written[-1] if written else ""
                composed = run_section_agent(
                    section={"title": title_cn, "guidance": guidance},
                    kg=kg, retriever=retriever,
                    prior_bullet=prior_bullet, max_iters=8,
                )
                agent_actually_ran = True
            except Exception as exc:
                print(f"[s08] agent failed for {basename}: {exc!r}; legacy compose",
                      flush=True)
                composed = _legacy_compose(
                    llm, system_tpl, user_tpl, paper_context_str, node, idx,
                    title_cn, title_en, guidance, hints, keywords,
                    chapters_dir, fig_notes, figures, retriever,
                    out_dir, basename, lang=lang,
                    prior_findings=prior_findings_block, kg=kg,
                )
        else:
            composed = _legacy_compose(
                llm, system_tpl, user_tpl, paper_context_str, node, idx,
                title_cn, title_en, guidance, hints, keywords,
                chapters_dir, fig_notes, figures, retriever,
                out_dir, basename, lang=lang,
                prior_findings=prior_findings_block, kg=kg,
            )

        # Critic — regex tier always; coverage critic (Strategy A) gated by env.
        flags = []
        # v1.6: when Strategy J ran, the verifier gate already validated each
        # claim's quote against its cited chunk. Running the regex critic +
        # LLM revisor on top would falsely flag numbers that ARE in source
        # (in LaTeX form) and the LLM critic would "fix" by deleting them —
        # destroying the structured compose's grounded content. Skip the
        # redundant critic when structured succeeded.
        if kg is not None and not structured_used:
            flags = regex_check(composed, source_docs, kg=kg, fig_yaml=figures)

            if flags:
                from stages.s08_section_compose.reviewer import llm_review
                # Build evidence: retrieved chunks + the source spans of any
                # missing entities (so the LLM critic can see where each missing
                # comparator/claim was originally cited).
                evidence_parts = [
                    f"[{c.doc_name}] {c.text[:200]}"
                    for c in (retriever.retrieve(guidance, top_k=4) if retriever else [])
                ]
                for e in missing_entities:
                    doc, start, end = e.source_span
                    src = source_docs.get(doc, "")
                    if src:
                        # widen the window so the LLM sees enough surrounding context
                        ctx_start = max(0, start - 150)
                        ctx_end = min(len(src), end + 250)
                        snippet = src[ctx_start:ctx_end].replace("\n", " ").strip()
                        evidence_parts.append(
                            f"[entity ↔ {doc}:{start}-{end}] {e.text}\n"
                            f"  source context: ...{snippet}..."
                        )
                evidence = "\n".join(evidence_parts)
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

        # v1.4.1: accumulate a 1-line summary of this section into the rolling
        # prior_findings list. The legacy compose path doesn't emit [span:...]
        # markers (so extract_claims returns []); instead, take the first
        # sentence and tag it with the section title for context.
        first_sentence = re.split(r"[。！？.!?]\s*", composed.strip(), maxsplit=1)[0]
        first_sentence = first_sentence.strip()[:160]
        if first_sentence:
            prior_section_claims.append(f"§{idx + 1} {title_cn}: {first_sentence}")

        if not composed.strip():
            print(f"[s08] WARNING: {basename} produced empty content; "
                  f"writing placeholder marker", flush=True)
            composed = "（本节生成失败，未能从源论文中提取到对应内容。）"

        md_file = out_chapters / f"{basename}.md"
        heading = f"# {title_cn}\n\n"
        md_file.write_text(heading + composed + "\n", encoding="utf-8")
        written.append(md_file.name)

    if all_flags:
        dump_yaml(out_dir / "critic_flags.yaml", all_flags)

    agent_enabled = os.environ.get("LAZY_PAPER_AGENT") == "1"
    if agent_actually_ran:
        agent_status = "active"
    elif agent_enabled and kg and retriever:
        agent_status = "enabled_but_unused"  # opted in, but every call failed
    else:
        agent_status = "disabled"
    dump_yaml(out_dir / "written.yaml", written)
    mark_done(out_dir, {
        "sections": len(written),
        "retriever": "ok" if retriever else "degraded",
        "kg": "ok" if kg else "missing",
        "agent": agent_status,
        "flagged_sections": len(all_flags),
    })
    return {"sections": len(written)}
