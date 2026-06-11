"""Cross-paper knowledge library: persistent store over per-run artifacts.

v1.14 foundation for the knowledge-base loop. `ingest` re-uses the retrieval
assets a finished run already produced (chunks + embeddings + KG) — zero LLM
calls — so the data survives runs/ cleanup and becomes searchable across
papers. `kind` reserves "experiment" for the v1.17 experiment loop.

Layout (under LAZY_PAPER_LIBRARY_DIR, default ./library):
    manifest.yaml      one entry per paper: title, kind, keywords, tokens, ...
    lancedb/           tables: chunks, entities, relations
    bm25/              persisted bm25s index over all child chunks
    bm25_ids.json      corpus-order global chunk ids ("<paper_id>::<chunk_id>")
    papers/<id>/       archived artifacts (context, fig_notes, sections, imgs)
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import bm25s
import lancedb
import pyarrow as pa
import pyarrow.parquet as pq

from llm.retriever import _embed_texts
from stages._common import dump_yaml, load_yaml

# (run-relative source, archive name) — small YAMLs copied verbatim
_ARCHIVE = [
    ("s06_context/context.yaml", "context.yaml"),
    ("s07_figure_analyze/fig_notes.yaml", "fig_notes.yaml"),
    ("s04_figures/figures.yaml", "figures.yaml"),
]


class Library:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or os.environ.get("LAZY_PAPER_LIBRARY_DIR", "library"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.root / "lancedb"))

    # -- manifest ----------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.yaml"

    def papers(self) -> dict:
        if self.manifest_path.exists():
            return load_yaml(self.manifest_path) or {}
        return {}

    # -- query ---------------------------------------------------------------
    def query(self, text: str, *, top_k: int = 8,
              papers: list[str] | None = None) -> list[dict]:
        """Hybrid dense + BM25 via RRF across all ingested papers.

        Same fusion as llm.retriever.Retriever.retrieve (1/(60+rank)), minus
        the entity-span boost (no section context at library-query time).
        """
        if "chunks" not in self._db.table_names():
            return []
        qvec = _embed_texts([text])[0]

        tbl = self._db.open_table("chunks")
        where = "is_parent = false"
        if papers:
            quoted = ", ".join(f"'{p}'" for p in papers)
            where += f" AND paper_id IN ({quoted})"
        dense = (tbl.search(qvec.tolist()).metric("cosine")
                 .where(where, prefilter=True).limit(top_k * 2).to_list())

        ids = json.loads((self.root / "bm25_ids.json").read_text(encoding="utf-8"))
        bm = bm25s.BM25.load(str(self.root / "bm25"), mmap=True)
        k = min(top_k * 2, len(ids))
        sparse_gids: list[str] = []
        if k > 0:
            res, _scores = bm.retrieve(bm25s.tokenize([text]), k=k)
            sparse_gids = [ids[i] for i in res[0]]
            if papers:
                allowed = set(papers)
                sparse_gids = [g for g in sparse_gids
                               if g.split("::", 1)[0] in allowed]

        rrf: dict[str, float] = {}
        for rank, row in enumerate(dense):
            rrf[row["gid"]] = rrf.get(row["gid"], 0.0) + 1.0 / (60 + rank + 1)
        for rank, gid in enumerate(sparse_gids):
            rrf[gid] = rrf.get(gid, 0.0) + 1.0 / (60 + rank + 1)

        by_gid = {row["gid"]: row for row in dense}
        missing = {g for g in rrf if g not in by_gid}
        if missing:
            # Filter-only lookups vary across lancedb versions; a projected
            # full scan is fine at personal-library scale.
            scan = (tbl.to_arrow()
                    .select(["gid", "paper_id", "doc_name",
                             "char_start", "char_end", "text"])
                    .to_pylist())
            for row in scan:
                if row["gid"] in missing:
                    by_gid[row["gid"]] = row

        out = []
        for gid, score in sorted(rrf.items(), key=lambda kv: -kv[1])[:top_k]:
            row = by_gid.get(gid)
            if row is None:
                continue
            out.append({
                "gid": gid,
                "paper_id": row["paper_id"],
                "doc_name": row["doc_name"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "score": round(score, 6),
                "text": row["text"],
            })
        return out

    # -- ingest --------------------------------------------------------------
    def ingest(self, run_dir: Path | str, *, kind: str = "paper") -> dict:
        run_dir = Path(run_dir)
        paper_id = run_dir.name
        rp = run_dir / "s06_context" / "retriever.parquet"
        if not rp.exists():
            raise SystemExit(
                f"{rp} not found — run the pipeline through s06_context first")

        rows = pq.read_table(rp).to_pylist()
        children = [r for r in rows if not r.get("is_parent")]
        if not children:
            raise SystemExit(f"{rp} contains no chunks")
        dim = len(children[0]["vector"])
        self._check_dim(dim)

        chunk_tbl = pa.table({
            "gid":        [f"{paper_id}::{r['id']}" for r in rows],
            "paper_id":   [paper_id] * len(rows),
            "chunk_id":   [r["id"] for r in rows],
            "text":       [r["text"] for r in rows],
            "doc_name":   [r["doc_name"] for r in rows],
            "char_start": [r["char_start"] for r in rows],
            "char_end":   [r["char_end"] for r in rows],
            "parent_id":  [r.get("parent_id") or "" for r in rows],
            "is_parent":  [bool(r.get("is_parent")) for r in rows],
            "vector":     pa.array([r["vector"] for r in rows],
                                   type=pa.list_(pa.float32(), dim)),
        })
        self._upsert("chunks", paper_id, chunk_tbl)
        n_entities = self._ingest_kg(run_dir, paper_id)
        self._archive(run_dir, paper_id)
        self._rebuild_bm25()

        meta_path = run_dir / "meta.yaml"
        meta = load_yaml(meta_path) if meta_path.exists() else {}
        ctx_path = run_dir / "s06_context" / "context.yaml"
        ctx = load_yaml(ctx_path) if ctx_path.exists() else {}
        entry = {
            "kind": kind,
            "title": (ctx or {}).get("title") or paper_id,
            "keywords": (ctx or {}).get("keywords") or [],
            "lang": (meta or {}).get("lang"),
            "pdf": (meta or {}).get("pdf"),
            "template": (meta or {}).get("template"),
            "n_chunks": len(children),
            "n_entities": n_entities,
            "embedding_dim": dim,
            "total_tokens": _sum_tokens(run_dir),
            "ingested_at": time.time(),
            "source_run": str(run_dir.resolve()),
        }
        manifest = self.papers()
        manifest[paper_id] = entry
        dump_yaml(self.manifest_path, manifest)
        return entry

    def _check_dim(self, dim: int) -> None:
        if "chunks" not in self._db.table_names():
            return
        existing = (self._db.open_table("chunks")
                    .schema.field("vector").type.list_size)
        if existing != dim:
            raise SystemExit(
                f"embedding dim mismatch: library has {existing}, new paper "
                f"has {dim}. All papers must share one embeddings model — "
                f"re-run s06_context or point LAZY_PAPER_LIBRARY_DIR at a "
                f"fresh directory.")

    def _upsert(self, name: str, paper_id: str, data: pa.Table) -> None:
        # paper_id comes from slugify() so it can't contain quotes.
        if name in self._db.table_names():
            tbl = self._db.open_table(name)
            tbl.delete(f"paper_id = '{paper_id}'")
            tbl.add(data)
        else:
            self._db.create_table(name, data=data)

    def _ingest_kg(self, run_dir: Path, paper_id: str) -> int:
        # Unconditionally clear stale rows so a re-ingest with no/empty KG
        # doesn't leave old entities/relations behind.
        for name in ("entities", "relations"):
            if name in self._db.table_names():
                self._db.open_table(name).delete(f"paper_id = '{paper_id}'")

        kg_path = run_dir / "s06_context" / "paper_kg.parquet"
        if not kg_path.exists():
            return 0
        ents = pq.read_table(kg_path).to_pylist()
        if ents:
            self._upsert("entities", paper_id, pa.table({
                "paper_id": [paper_id] * len(ents),
                "id":    [e["id"] for e in ents],
                "type":  [e["type"] for e in ents],
                "text":  [e["text"] for e in ents],
                "doc":   [e["doc"] for e in ents],
                "start": [e["start"] for e in ents],
                "end":   [e["end"] for e in ents],
            }))
        rel_path = kg_path.with_suffix(".rel.parquet")
        if rel_path.exists():
            rels = pq.read_table(rel_path).to_pylist()
            if rels:
                self._upsert("relations", paper_id, pa.table({
                    "paper_id":  [paper_id] * len(rels),
                    "subject":   [r["subject"] for r in rels],
                    "predicate": [r["predicate"] for r in rels],
                    "object":    [r["object"] for r in rels],
                }))
        return len(ents)

    def _archive(self, run_dir: Path, paper_id: str) -> None:
        dest = self.root / "papers" / paper_id
        dest.mkdir(parents=True, exist_ok=True)
        for src_rel, dst_name in _ARCHIVE:
            src = run_dir / src_rel
            if src.exists():
                shutil.copy2(src, dest / dst_name)
        sections = run_dir / "s08_section_compose"
        if sections.is_dir():
            sec_dest = dest / "sections"
            sec_dest.mkdir(exist_ok=True)
            for md in sections.glob("*.md"):
                if md.name.endswith(".prompt.md"):
                    continue
                shutil.copy2(md, sec_dest / md.name)
        imgs = run_dir / "s01_ocr" / "imgs"
        if imgs.is_dir():
            shutil.copytree(imgs, dest / "imgs", dirs_exist_ok=True)

    def _rebuild_bm25(self) -> None:
        rows = (self._db.open_table("chunks").to_arrow()
                .select(["gid", "text", "is_parent"]).to_pylist())
        children = [r for r in rows if not r["is_parent"]]
        bm = bm25s.BM25()
        bm.index(bm25s.tokenize([r["text"] for r in children]))
        bm.save(str(self.root / "bm25"))
        (self.root / "bm25_ids.json").write_text(
            json.dumps([r["gid"] for r in children]), encoding="utf-8")


def _sum_tokens(run_dir: Path) -> int:
    """Aggregate LLM token usage recorded in each stage's done.yaml."""
    total = 0
    for done in run_dir.glob("s*/done.yaml"):
        payload = load_yaml(done) or {}
        if isinstance(payload, dict):
            for key in ("tokens", "total_tokens"):
                v = payload.get(key)
                if isinstance(v, (int, float)):
                    total += int(v)
    return total
