"""Hybrid retriever: llama-index chunking + bm25s sparse + dense + RRF fusion."""
from __future__ import annotations

import json
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

    def to_dict(self) -> dict:
        return asdict(self)


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Batch-embed via DashScope text-embedding-3-small."""
    llm = LLM(role="embeddings")
    # DashScope batch limit is 25; chunk into batches
    out: list[list[float]] = []
    for i in range(0, len(texts), 25):
        batch = texts[i:i + 25]
        resp = llm._client.embeddings.create(model=llm.model, input=batch)
        out.extend([d.embedding for d in resp.data])
    return np.asarray(out, dtype=np.float32)


class Retriever:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray | None = None
        self.bm25: bm25s.BM25 | None = None

    def build(self, *, chapters_dir: Path, out_path: Path,
              chunk_size: int = 400, overlap: int = 80) -> Path:
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        docs: list[Document] = []
        doc_offsets: dict[str, int] = {}
        for p in sorted(chapters_dir.glob("chapter_*.md")):
            text = p.read_text(encoding="utf-8")
            docs.append(Document(text=text, doc_id=p.name,
                                 metadata={"doc_name": p.name}))
            doc_offsets[p.name] = 0

        nodes: list[TextNode] = splitter.get_nodes_from_documents(docs)
        self.chunks = []
        for i, n in enumerate(nodes):
            doc_name = n.metadata.get("doc_name", "unknown")
            start = doc_offsets.get(doc_name, 0)
            end = start + len(n.text)
            doc_offsets[doc_name] = end
            self.chunks.append(Chunk(
                id=f"c{i:04d}",
                text=n.text,
                doc_name=doc_name,
                char_start=start,
                char_end=end,
            ))

        texts = [c.text for c in self.chunks]
        self.vectors = _embed_texts(texts)

        self.bm25 = bm25s.BM25()
        self.bm25.index(bm25s.tokenize([c.text for c in self.chunks]))

        self._write_parquet(out_path)
        return out_path

    def _write_parquet(self, out_path: Path) -> None:
        tbl = pa.table({
            "id": [c.id for c in self.chunks],
            "text": [c.text for c in self.chunks],
            "doc_name": [c.doc_name for c in self.chunks],
            "char_start": [c.char_start for c in self.chunks],
            "char_end": [c.char_end for c in self.chunks],
            "vector": [v.tolist() for v in (self.vectors if self.vectors is not None else np.zeros((0, 0)))],
        })
        pq.write_table(tbl, out_path)
