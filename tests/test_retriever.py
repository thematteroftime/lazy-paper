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
