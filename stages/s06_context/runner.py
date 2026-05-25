"""Stage 06: extract paper context (system, abbreviations, keywords) via text LLM."""
from __future__ import annotations

import json
import os
from pathlib import Path

from llm.client import LLM, max_tokens
from stages._common import dump_yaml, mark_done, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "paper_context.md"


def _gather_paper_text(chapters_dir: Path) -> str:
    """Collect text from chapters that typically contain front-matter info.

    Strategy:
    1. Always include chapter_000 (Preface/cover) if it exists.
    2. For chapter_001, use a case-insensitive glob — the name suffix may be
       ABSTRACT, Introduction, INTRODUCTION, etc. depending on the paper.
    3. If neither is found, fall back to the first 3 chapters lexically.
    """
    pieces: list[str] = []
    # Prefer preface/cover chapter
    for p in sorted(chapters_dir.glob("chapter_000_*.md")):
        pieces.append(p.read_text(encoding="utf-8"))
        break  # only the first match

    # Prefer abstract/introduction as chapter 001 — robust to name variants
    candidates_001 = sorted(chapters_dir.glob("chapter_001_*.md"))
    if candidates_001:
        pieces.append(candidates_001[0].read_text(encoding="utf-8"))

    if not pieces:
        # Fallback: first 3 chapters by filename order
        for p in sorted(chapters_dir.glob("*.md"))[:3]:
            pieces.append(p.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(pieces[:3])[:20000]



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
    response = llm.chat(system=system, user=user, max_tokens=max_tokens(4000))
    (out_dir / "paper_context.response.json").write_text(
        json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                    "usage": response.usage, "content": response.content},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    data = safe_parse_yaml(response.content) or {}

    # v1.4: KG sub-step (soft-degrade)
    from stages.s06_context.kg_extract import build_paper_kg, extract_headline_metrics
    kg = build_paper_kg(chapters_dir=chapters_dir, out_dir=out_dir)
    extra = {"tokens": response.usage.get("total_tokens")}
    if kg is None:
        extra["kg"] = "failed"
    else:
        # v1.12 phase 1: optional entity dedup before downstream consumers see
        # the KG. Gated by LAZY_PAPER_ENTITY_DEDUP=1; default OFF.
        if os.environ.get("LAZY_PAPER_ENTITY_DEDUP", "0") == "1":
            from llm.paper_kg import Entity, PaperKG, Relation
            from stages.s06_context.entity_dedup import dedup_entities
            ents = [e.model_dump() for e in kg.entities]
            rels = [r.model_dump() for r in kg.relations]
            n_ents_before, n_rels_before = len(ents), len(rels)
            new_ents, new_rels = dedup_entities(ents, rels)
            # apply_clusters adds 'dedup_member_ids' which isn't part of Entity;
            # strip it before rebuilding the Pydantic model.
            kg = PaperKG(
                entities=[Entity(**{k: v for k, v in e.items() if k != "dedup_member_ids"})
                          for e in new_ents],
                relations=[Relation(**r) for r in new_rels],
            )
            kg.to_parquet(out_dir / "paper_kg.parquet")  # rewrite with deduped KG
            print(f"[s06_context] entity_dedup: {n_ents_before} -> {len(new_ents)} entities, "
                  f"{n_rels_before} -> {len(new_rels)} relations", flush=True)
            extra["entity_dedup"] = {
                "entities_before": n_ents_before, "entities_after": len(new_ents),
                "relations_before": n_rels_before, "relations_after": len(new_rels),
            }
        extra["kg_entities"] = len(kg.entities)
        extra["kg_relations"] = len(kg.relations)
        # v1.11.1 Bug #1+#2: pipe flagship headline metrics into context.yaml
        # so s08 sees them in {paper_context} and the LLM stops scavenging
        # comparator values when discussing the main sample.
        headline = extract_headline_metrics(kg)
        if headline:
            data["headline_metrics"] = headline

    dump_yaml(out_dir / "context.yaml", data)
    mark_done(out_dir, extra)
    return data
