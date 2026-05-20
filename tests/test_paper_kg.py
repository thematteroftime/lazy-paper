from pathlib import Path

import pytest

from llm.paper_kg import Entity, Relation, PaperKG


def test_entity_types_closed():
    e = Entity(id="m1", type="material", text="0.85NBST-0.15BMZ",
               source_span=("doc_1", 100, 120))
    assert e.type == "material"
    with pytest.raises(ValueError):
        Entity(id="m2", type="not_a_real_type", text="x",
               source_span=("doc_1", 0, 1))


def test_relation_refs_entities():
    e1 = Entity(id="m1", type="material", text="x",
                source_span=("doc_1", 0, 1))
    e2 = Entity(id="v1", type="value", text="340",
                source_span=("doc_1", 2, 5))
    r = Relation(subject="m1", predicate="has_value", object="v1")
    kg = PaperKG(entities=[e1, e2], relations=[r])
    assert kg.query("material") == [e1]


def test_parquet_roundtrip(tmp_path: Path):
    kg = PaperKG(
        entities=[
            Entity(id="m1", type="material", text="x",
                   source_span=("doc_1", 0, 1)),
        ],
        relations=[],
    )
    p = tmp_path / "kg.parquet"
    kg.to_parquet(p)
    loaded = PaperKG.from_parquet(p)
    assert loaded.entities[0].id == "m1"
    assert loaded.entities[0].type == "material"
