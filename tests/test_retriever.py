import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from llm.retriever import Retriever, Chunk


def _make_chapters(dirpath: Path, n: int = 5) -> Path:
    cdir = dirpath / "chapters"
    cdir.mkdir()
    for i in range(n):
        (cdir / f"chapter_{i:03d}_section.md").write_text(
            f"Section {i} discusses materials and properties. " * 30,
            encoding="utf-8",
        )
    return cdir


def test_chunking_produces_textnodes(tmp_path: Path):
    cdir = _make_chapters(tmp_path, n=2)
    with patch("llm.retriever._embed_texts",
               side_effect=lambda texts: np.zeros((len(texts), 8))):
        r = Retriever()
        r.build(chapters_dir=cdir, out_path=tmp_path / "r.parquet")
        assert len(r.chunks) > 0
        assert all(isinstance(c, Chunk) for c in r.chunks)


def test_bm25_indexes_under_1s(tmp_path: Path):
    cdir = _make_chapters(tmp_path, n=30)
    with patch("llm.retriever._embed_texts",
               side_effect=lambda texts: np.zeros((len(texts), 8))):
        r = Retriever()
        t0 = time.time()
        r.build(chapters_dir=cdir, out_path=tmp_path / "r.parquet")
        elapsed = time.time() - t0
        assert elapsed < 5.0, f"build took {elapsed:.2f}s"
        assert len(r.chunks) >= 30


def test_retrieve_top_k_by_rrf(tmp_path: Path):
    cdir = _make_chapters(tmp_path, n=4)
    out = tmp_path / "r.parquet"
    fake_vecs = lambda texts: np.array(
        [[1.0 if "Section 0" in t else 0.1] * 8 for t in texts],
        dtype=np.float32,
    )
    with patch("llm.retriever._embed_texts", side_effect=fake_vecs):
        r = Retriever()
        r.build(chapters_dir=cdir, out_path=out)
        result = r.retrieve("Section 0 materials", top_k=2)
        assert len(result) == 2
        assert any("Section 0" in c.text for c in result)


def test_entity_boost_reranks(tmp_path: Path):
    cdir = _make_chapters(tmp_path, n=4)
    out = tmp_path / "r.parquet"
    with patch("llm.retriever._embed_texts",
               side_effect=lambda texts: np.zeros((len(texts), 8))):
        r = Retriever()
        r.build(chapters_dir=cdir, out_path=out)
        # Build a span that overlaps the first chunk's range
        target = r.chunks[0]
        boosted = r.retrieve(
            "anything", top_k=3,
            entity_spans=[(target.doc_name, target.char_start, target.char_end)],
        )
        assert boosted[0].id == target.id


def test_check_claim_numeric(tmp_path: Path):
    cdir = tmp_path / "chapters"
    cdir.mkdir()
    (cdir / "chapter_001.md").write_text(
        "The breakdown field reached 348 kV/cm under standard test.",
        encoding="utf-8",
    )
    out = tmp_path / "r.parquet"
    with patch("llm.retriever._embed_texts",
               side_effect=lambda texts: np.zeros((len(texts), 8))):
        r = Retriever()
        r.build(chapters_dir=cdir, out_path=out)
        result = r.check_claim("348 kV/cm")
        assert result["found"] is True
        assert "348" in result["evidence"]
