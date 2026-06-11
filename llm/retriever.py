"""Hybrid retriever: llama-index chunking + bm25s sparse + dense + RRF fusion."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import bm25s
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode

from llm.client import LLM, max_tokens


@dataclass
class Chunk:
    id: str
    text: str
    doc_name: str
    char_start: int
    char_end: int
    parent_id: str | None = None   # Strategy H: link child → parent chunk
    is_parent: bool = False         # Strategy H: True for parent (~2000 char) chunks

    def to_dict(self) -> dict:
        return asdict(self)


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Batch-embed via the configured embeddings endpoint.

    DashScope (Qwen text-embedding-v3) caps batch size at 10. Override
    via env `LLM_EMBEDDINGS_BATCH_SIZE` if your endpoint allows larger.
    """
    llm = LLM(role="embeddings")
    batch_size = int(os.environ.get("LLM_EMBEDDINGS_BATCH_SIZE", "10"))
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = llm._client.embeddings.create(model=llm.model, input=batch)
        out.extend([d.embedding for d in resp.data])
    return np.asarray(out, dtype=np.float32)


class Retriever:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []          # children (indexed; what we search)
        self.parents: list[Chunk] = []         # Strategy H: rich-context parents
        self._parents_by_id: dict[str, Chunk] = {}
        self.vectors: np.ndarray | None = None
        self.bm25: bm25s.BM25 | None = None

    def build(self, *, chapters_dir: Path, out_path: Path,
              chunk_size: int | None = None,
              overlap: int | None = None) -> Path:
        # Strategy G: env-overridable chunk size + overlap.
        # Defaults 400/80 give precise retrieval; 2000/400 give richer context.
        # Strategy H: LAZY_PAPER_HIERARCHICAL=1 builds both child (precise)
        # and parent (rich-context) chunks; retrieve() auto-merges children
        # to their parent when ≥2 children of the same parent are ranked
        # together.
        if chunk_size is None:
            chunk_size = int(os.environ.get("LAZY_PAPER_CHUNK_SIZE", "400"))
        if overlap is None:
            overlap = int(os.environ.get("LAZY_PAPER_CHUNK_OVERLAP",
                                          str(min(400, chunk_size // 5))))
        hierarchical = os.environ.get("LAZY_PAPER_HIERARCHICAL") == "1"
        parent_size = int(os.environ.get("LAZY_PAPER_PARENT_SIZE", "2000"))
        parent_overlap = int(os.environ.get("LAZY_PAPER_PARENT_OVERLAP", "200"))

        child_splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        parent_splitter = (SentenceSplitter(chunk_size=parent_size,
                                            chunk_overlap=parent_overlap)
                           if hierarchical else None)

        docs: list[Document] = []
        for p in sorted(chapters_dir.glob("chapter_*.md")):
            text = p.read_text(encoding="utf-8")
            docs.append(Document(text=text, doc_id=p.name,
                                 metadata={"doc_name": p.name}))

        # Build parent chunks first (if hierarchical) so children can be assigned.
        parents: list[Chunk] = []
        parent_offsets: dict[str, int] = {}
        if hierarchical and parent_splitter is not None:
            parent_nodes = parent_splitter.get_nodes_from_documents(docs)
            for i, n in enumerate(parent_nodes):
                doc_name = n.metadata.get("doc_name", "unknown")
                start = parent_offsets.get(doc_name, 0)
                end = start + len(n.text)
                parent_offsets[doc_name] = end
                parents.append(Chunk(
                    id=f"p{i:04d}", text=n.text, doc_name=doc_name,
                    char_start=start, char_end=end, is_parent=True,
                ))

        # Build child chunks.
        nodes: list[TextNode] = child_splitter.get_nodes_from_documents(docs)
        children: list[Chunk] = []
        doc_offsets: dict[str, int] = {}
        for i, n in enumerate(nodes):
            doc_name = n.metadata.get("doc_name", "unknown")
            start = doc_offsets.get(doc_name, 0)
            end = start + len(n.text)
            doc_offsets[doc_name] = end
            parent_id = None
            if hierarchical:
                # find the parent whose char range contains this child's midpoint
                mid = (start + end) // 2
                for p in parents:
                    if p.doc_name == doc_name and p.char_start <= mid < p.char_end:
                        parent_id = p.id
                        break
            children.append(Chunk(
                id=f"c{i:04d}", text=n.text, doc_name=doc_name,
                char_start=start, char_end=end, parent_id=parent_id,
            ))

        # Only children are embedded + BM25-indexed (precise matching).
        # Parents are looked up by id during retrieve() for merge-up.
        self.chunks = children
        self.parents = parents
        self._parents_by_id = {p.id: p for p in parents}
        texts = [c.text for c in children]
        self.vectors = _embed_texts(texts)

        self.bm25 = bm25s.BM25()
        self.bm25.index(bm25s.tokenize([c.text for c in children]))

        self._write_parquet(out_path)
        return out_path

    def _write_parquet(self, out_path: Path) -> None:
        # Serialize children (with vectors) + parents (no vectors) into one table.
        all_chunks = self.chunks + self.parents
        n_children = len(self.chunks)
        empty_vec = [0.0] * (self.vectors.shape[1] if self.vectors is not None and self.vectors.size else 0)
        tbl = pa.table({
            "id":         [c.id for c in all_chunks],
            "text":       [c.text for c in all_chunks],
            "doc_name":   [c.doc_name for c in all_chunks],
            "char_start": [c.char_start for c in all_chunks],
            "char_end":   [c.char_end for c in all_chunks],
            "parent_id":  [c.parent_id or "" for c in all_chunks],
            "is_parent":  [c.is_parent for c in all_chunks],
            "vector":     [v.tolist() for v in (self.vectors if self.vectors is not None
                                                else np.zeros((0, 0)))]
                          + [empty_vec for _ in self.parents],
        })
        pq.write_table(tbl, out_path)

    @classmethod
    def load(cls, parquet_path: Path) -> "Retriever":
        tbl = pq.read_table(parquet_path).to_pylist()
        r = cls()
        children: list[Chunk] = []
        parents: list[Chunk] = []
        child_vectors: list[list[float]] = []
        for row in tbl:
            parent_id = row.get("parent_id") or None
            is_parent = bool(row.get("is_parent", False))
            ch = Chunk(id=row["id"], text=row["text"], doc_name=row["doc_name"],
                       char_start=row["char_start"], char_end=row["char_end"],
                       parent_id=parent_id, is_parent=is_parent)
            if is_parent:
                parents.append(ch)
            else:
                children.append(ch)
                child_vectors.append(row["vector"])
        r.chunks = children
        r.parents = parents
        r._parents_by_id = {p.id: p for p in parents}
        r.vectors = np.asarray(child_vectors, dtype=np.float32)
        r.bm25 = bm25s.BM25()
        r.bm25.index(bm25s.tokenize([c.text for c in r.chunks]))
        return r

    def retrieve(self, query: str, top_k: int = 8,
                 entity_spans: Sequence[tuple[str, int, int]] | None = None,
                 ) -> list[Chunk]:
        """Hybrid dense + sparse via RRF; optional span overlap boost."""
        top_k = max(1, min(top_k, 12))
        if not self.chunks:
            return []

        # Dense scoring (cosine on normalized vectors)
        q_vec = _embed_texts([query])[0]
        v = self.vectors
        denom = (np.linalg.norm(v, axis=1) * np.linalg.norm(q_vec)) + 1e-9
        dense_scores = (v @ q_vec) / denom

        # Sparse scoring (BM25)
        tokenized = bm25s.tokenize([query])
        bm25_k = min(top_k * 2, len(self.chunks))
        sparse_results, sparse_scores = self.bm25.retrieve(tokenized, k=bm25_k)
        sparse_idx = [int(i) for i, s in zip(sparse_results[0], sparse_scores[0]) if s > 0]
        sparse_score_map = {idx: float(sparse_scores[0][i])
                            for i, idx in enumerate(sparse_results[0])}  # unused; kept for symmetry

        # RRF fusion: each rank contributes 1 / (60 + rank)
        dense_ranks = np.argsort(-dense_scores)[:top_k * 2]
        rrf: dict[int, float] = {}
        for rank, idx in enumerate(dense_ranks):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (60 + rank + 1)
        for rank, idx in enumerate(sparse_idx):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank + 1)

        # Entity boost: chunks whose char range overlaps any entity span
        if entity_spans:
            for idx, c in enumerate(self.chunks):
                for (doc, s, e) in entity_spans:
                    if c.doc_name == doc and not (e < c.char_start or s > c.char_end):
                        rrf[idx] = rrf.get(idx, 0.0) + 0.05  # decisive bump
                        break

        # Take a wider initial ranking so the auto-merge has material to fold.
        merge_k = top_k * 2 if self._parents_by_id else top_k
        ranked = sorted(rrf.items(), key=lambda kv: -kv[1])[:merge_k]
        ranked_chunks = [self.chunks[i] for i, _ in ranked]

        # Strategy H auto-merge: when 2+ children of the same parent appear
        # in the wider top-K, return the parent text once (preserving the
        # rank of its highest-scoring child) instead of two children.
        if not self._parents_by_id:
            return ranked_chunks[:top_k]
        parent_hits: dict[str, int] = {}
        for c in ranked_chunks:
            if c.parent_id:
                parent_hits[c.parent_id] = parent_hits.get(c.parent_id, 0) + 1
        result: list[Chunk] = []
        emitted_parents: set[str] = set()
        for c in ranked_chunks:
            if c.parent_id and parent_hits.get(c.parent_id, 0) >= 2:
                if c.parent_id not in emitted_parents:
                    parent = self._parents_by_id.get(c.parent_id)
                    if parent:
                        result.append(parent)
                        emitted_parents.add(c.parent_id)
            else:
                result.append(c)
            if len(result) >= top_k:
                break
        return result[:top_k]

    def check_claim(self, claim: str, expected_value: str | None = None) -> dict:
        """Substring lookup across all chunks. Returns {found, span, evidence}."""
        needle = (expected_value or claim).strip()
        for c in self.chunks:
            idx = c.text.find(needle)
            if idx >= 0:
                return {
                    "found": True,
                    "span": (c.doc_name, c.char_start + idx,
                             c.char_start + idx + len(needle)),
                    "evidence": c.text[max(0, idx - 40):idx + len(needle) + 40],
                }
        return {"found": False, "span": None, "evidence": None}
