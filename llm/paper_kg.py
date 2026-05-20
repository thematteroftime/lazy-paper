"""PaperKG: closed 10/11-type entity/relation graph for one paper.

`author` was added in v1.7 (KG-v3 prompt). Backward-compatible: parquets
written by v1/v2 prompts deserialize fine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

EntityType = Literal[
    "material", "dopant", "parameter", "value", "unit",
    "figure", "table", "claim", "method", "comparator",
    "author",  # v1.7 / KG-v3
]


class Entity(BaseModel):
    id: str
    type: EntityType
    text: str
    source_span: tuple[str, int, int]  # (doc_name, char_start, char_end)


class Relation(BaseModel):
    subject: str   # Entity.id
    predicate: str
    object: str    # Entity.id


class PaperKG(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)

    def query(self, entity_type: EntityType, filter: dict | None = None) -> list[Entity]:
        out = [e for e in self.entities if e.type == entity_type]
        if filter:
            for k, v in filter.items():
                out = [e for e in out if getattr(e, k, None) == v]
        return out

    def to_parquet(self, path: Path) -> None:
        ent_tbl = pa.table({
            "id": [e.id for e in self.entities],
            "type": [e.type for e in self.entities],
            "text": [e.text for e in self.entities],
            "doc": [e.source_span[0] for e in self.entities],
            "start": [e.source_span[1] for e in self.entities],
            "end": [e.source_span[2] for e in self.entities],
        })
        rel_tbl = pa.table({
            "subject": [r.subject for r in self.relations],
            "predicate": [r.predicate for r in self.relations],
            "object": [r.object for r in self.relations],
        })
        # Single-file parquet with two row-groups: entities first, then a
        # padding row marking the relations section. We use a sibling file
        # for relations to keep the schema clean.
        pq.write_table(ent_tbl, path)
        pq.write_table(rel_tbl, path.with_suffix(".rel.parquet"))

    @classmethod
    def from_parquet(cls, path: Path) -> "PaperKG":
        ent_tbl = pq.read_table(path).to_pylist()
        entities = [
            Entity(id=r["id"], type=r["type"], text=r["text"],
                   source_span=(r["doc"], r["start"], r["end"]))
            for r in ent_tbl
        ]
        rel_path = path.with_suffix(".rel.parquet")
        relations: list[Relation] = []
        if rel_path.exists():
            rel_tbl = pq.read_table(rel_path).to_pylist()
            relations = [Relation(**r) for r in rel_tbl]
        return cls(entities=entities, relations=relations)
