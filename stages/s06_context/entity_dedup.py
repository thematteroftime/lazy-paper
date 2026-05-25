"""LightRAG-inspired entity deduplication for the s06 KG.

Merges variant mentions of the same real-world entity within one type
("Meng et al." + "Meng 2024" + "this work" → one canonical author).
Defends against the v1.11.1 author-misattribution class at the extraction
layer rather than adding another verifier rule downstream.

Lifts the merge prompt + cluster-validate algorithm from
https://github.com/HKUDS/LightRAG without importing the library.
Gated by LAZY_PAPER_ENTITY_DEDUP=1 — default OFF until measured.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "entity_dedup.md"


def _build_user_prompt(entities: list[dict]) -> str:
    """Render the candidates block in the YAML shape the prompt expects."""
    import yaml
    candidates = []
    for e in entities:
        src = e.get("source_span")
        if isinstance(src, (list, tuple)) and len(src) == 3:
            src_str = f"{src[0]}:{src[1]}-{src[2]}"
        else:
            src_str = str(src) if src else ""
        candidates.append({
            "id": e["id"],
            "type": e["type"],
            "text": e.get("text", ""),
            "source_span": src_str,
        })
    return yaml.safe_dump({"candidates": candidates}, allow_unicode=True, sort_keys=False)


def _parse_clusters(text: str) -> list[dict]:
    """Defensive parse — bail (return []) on any structural problem."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    clusters = obj.get("clusters", [])
    if not isinstance(clusters, list):
        return []
    for c in clusters:
        if not isinstance(c, dict):
            return []
        if "canonical" not in c or "member_ids" not in c:
            return []
        if not isinstance(c["member_ids"], list):
            return []
    return clusters


def _ensure_coverage(clusters: list[dict], all_ids: set[str]) -> list[dict]:
    """Add singleton clusters for any id the LLM forgot, so apply_clusters
    doesn't silently drop entities."""
    covered: set[str] = set()
    for c in clusters:
        covered.update(c["member_ids"])
    missing = sorted(all_ids - covered)
    return clusters + [
        {"canonical": f"__id_{i}__", "member_ids": [i]} for i in missing
    ]


def apply_clusters(
    entities: list[dict],
    relations: list[dict],
    clusters: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Collapse member ids to the first id in each cluster; dedupe relation triples.

    Each entity is treated as a dict. The first id in cluster.member_ids
    becomes the canonical id; entity.text is overwritten with cluster.canonical
    unless that canonical is a `__id_X__` fallback (added by _ensure_coverage).
    Relations are rewritten using `subject` / `predicate` / `object` keys to
    match llm.paper_kg.Relation.
    """
    id_remap: dict[str, str] = {}
    for c in clusters:
        if not c["member_ids"]:
            continue
        canonical_id = c["member_ids"][0]
        for mid in c["member_ids"]:
            id_remap[mid] = canonical_id

    by_id = {e["id"]: e for e in entities}
    new_entities: list[dict] = []
    seen_ids: set[str] = set()
    for c in clusters:
        if not c["member_ids"]:
            continue
        canonical_id = c["member_ids"][0]
        if canonical_id in seen_ids or canonical_id not in by_id:
            continue
        seen_ids.add(canonical_id)
        e = dict(by_id[canonical_id])
        if not c["canonical"].startswith("__id_"):
            e["text"] = c["canonical"]
        e["dedup_member_ids"] = list(c["member_ids"])
        new_entities.append(e)

    seen_rels: set[tuple] = set()
    new_relations: list[dict] = []
    for r in relations:
        subj = id_remap.get(r["subject"], r["subject"])
        obj = id_remap.get(r["object"], r["object"])
        key = (subj, r["predicate"], obj)
        if key in seen_rels:
            continue
        seen_rels.add(key)
        new_relations.append({**r, "subject": subj, "object": obj})
    return new_entities, new_relations


def dedup_entities(
    entities: list[dict],
    relations: list[dict],
    *,
    llm_chat: Callable[..., str] | None = None,
    model: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """End-to-end entity dedup. Soft-degrades to inputs on any LLM failure.

    `llm_chat` is injectable for tests; in prod it's wired to llm.client.LLM.chat.
    """
    if not entities:
        return entities, relations
    if llm_chat is None:
        from llm.client import LLM
        client = LLM(role="text")

        def _real_chat(**kw):
            return client.chat(**kw).content

        llm_chat = _real_chat

    system = PROMPT_PATH.read_text()
    user = _build_user_prompt(entities)
    try:
        resp = llm_chat(system=system, user=user, temperature=0.1, max_tokens=4000)
    except Exception:
        return entities, relations

    clusters = _parse_clusters(resp)
    if not clusters:
        return entities, relations
    all_ids = {e["id"] for e in entities}
    clusters = _ensure_coverage(clusters, all_ids)
    return apply_clusters(entities, relations, clusters)
