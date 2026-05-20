from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stages.s06_context.kg_extract import build_paper_kg
from llm.paper_kg import PaperKG, Entity, Relation


def _fixture_chapters(dirpath: Path) -> Path:
    cdir = dirpath / "chapters"
    cdir.mkdir()
    (cdir / "chapter_001_introduction.md").write_text(
        "0.85NBST-0.15BMZ achieves E_b = 348 kV/cm at room temperature.",
        encoding="utf-8",
    )
    return cdir


def test_build_paper_kg_writes_parquet(tmp_path: Path):
    cdir = _fixture_chapters(tmp_path)
    out = tmp_path / "s06"
    out.mkdir()

    fake_kg = PaperKG(
        entities=[
            Entity(id="m1", type="material", text="0.85NBST-0.15BMZ",
                   source_span=("chapter_001_introduction.md", 0, 16)),
            Entity(id="v1", type="value", text="348",
                   source_span=("chapter_001_introduction.md", 22, 25)),
            Entity(id="u1", type="unit", text="kV/cm",
                   source_span=("chapter_001_introduction.md", 26, 31)),
        ],
        relations=[Relation(subject="m1", predicate="has_E_b", object="v1")],
    )

    with patch("stages.s06_context.kg_extract._extract_via_llm",
               return_value=fake_kg):
        result = build_paper_kg(chapters_dir=cdir, out_dir=out)

    assert result is not None
    assert (out / "paper_kg.parquet").exists()
    assert result.query("material")[0].text == "0.85NBST-0.15BMZ"


def test_build_paper_kg_failure_writes_marker(tmp_path: Path):
    cdir = _fixture_chapters(tmp_path)
    out = tmp_path / "s06"
    out.mkdir()

    with patch("stages.s06_context.kg_extract._extract_via_llm",
               side_effect=ValueError("parse failed")):
        result = build_paper_kg(chapters_dir=cdir, out_dir=out)

    assert result is None
    assert (out / "kg_extract.failed").exists()
    assert not (out / "paper_kg.parquet").exists()


def test_build_paper_kg_empty_chapters(tmp_path: Path):
    cdir = tmp_path / "chapters"
    cdir.mkdir()
    out = tmp_path / "s06"
    out.mkdir()

    result = build_paper_kg(chapters_dir=cdir, out_dir=out)
    assert result is None
    assert (out / "kg_extract.failed").exists()
