"""Tests for entity_dedup — algorithm only (LLM mocked)."""
from __future__ import annotations


def test_apply_clusters_renames_relations():
    """When 2 author entities merge, all relations referencing either id collapse to one
    canonical id, and duplicate (subject, predicate, object) triples are deduped."""
    from stages.s06_context.entity_dedup import apply_clusters

    entities = [
        {"id": "e1", "type": "author", "text": "Meng et al."},
        {"id": "e2", "type": "author", "text": "Meng 2024"},
        {"id": "e3", "type": "material", "text": "BMZ"},
    ]
    relations = [
        {"subject": "e1", "predicate": "reports", "object": "e3"},
        {"subject": "e2", "predicate": "reports", "object": "e3"},
    ]
    clusters = [
        {"canonical": "Meng et al. 2024", "member_ids": ["e1", "e2"]},
        {"canonical": "BMZ", "member_ids": ["e3"]},
    ]
    new_entities, new_relations = apply_clusters(entities, relations, clusters)
    assert len(new_entities) == 2
    # Canonical id is the first member of each cluster.
    assert {e["id"] for e in new_entities} == {"e1", "e3"}
    # Canonical text was carried over from cluster.canonical (not the fallback __id_x__).
    e1 = next(e for e in new_entities if e["id"] == "e1")
    assert e1["text"] == "Meng et al. 2024"
    # Duplicate relations collapsed.
    assert len(new_relations) == 1
    assert new_relations[0] == {"subject": "e1", "predicate": "reports", "object": "e3"}


def test_dedup_skips_empty_input():
    from stages.s06_context.entity_dedup import dedup_entities
    out_e, out_r = dedup_entities([], [], llm_chat=lambda **_: '{"clusters": []}')
    assert out_e == [] and out_r == []


def test_dedup_handles_malformed_llm_output():
    """If LLM returns garbage, dedup soft-degrades to the original inputs unchanged."""
    from stages.s06_context.entity_dedup import dedup_entities
    entities = [{"id": "e1", "type": "author", "text": "X"}]
    out_e, out_r = dedup_entities(entities, [], llm_chat=lambda **_: "not json")
    assert out_e == entities and out_r == []


def test_dedup_validates_cluster_coverage():
    """If LLM forgets an entity, the defensive fallback adds a singleton cluster so the
    entity isn't silently dropped."""
    from stages.s06_context.entity_dedup import dedup_entities
    entities = [
        {"id": "e1", "type": "author", "text": "A"},
        {"id": "e2", "type": "author", "text": "B"},
    ]
    incomplete = '{"clusters": [{"canonical": "A", "member_ids": ["e1"]}]}'
    out_e, _ = dedup_entities(entities, [], llm_chat=lambda **_: incomplete)
    # Both entities must survive even though LLM only covered e1.
    assert {e["id"] for e in out_e} == {"e1", "e2"}
