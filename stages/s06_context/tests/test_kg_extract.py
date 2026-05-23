from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stages.s06_context.kg_extract import build_paper_kg, extract_headline_metrics
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


def test_extract_headline_metrics_picks_mat_main():
    """v1.11.1 Bug #1+#2: flagship sample's W_rec/eta values must be
    pulled out of the KG and surfaced as ground truth so s08 doesn't
    scavenge comparator numbers from neighbouring chunks."""
    kg = PaperKG(
        entities=[
            Entity(id="mat_main", type="material", text="0.85NBST-0.15BMZ",
                   source_span=("doc_0.md", 0, 10)),
            Entity(id="comp_x", type="comparator", text="Ca/Nb-codoped BNT",
                   source_span=("doc_0.md", 10, 20)),
            Entity(id="v_wrec_main", type="value", text="5.00",
                   source_span=("doc_0.md", 20, 24)),
            Entity(id="v_wrec_comp", type="value", text="2.94",
                   source_span=("doc_0.md", 24, 28)),
            Entity(id="u_jcm3", type="unit", text="J/cm^3",
                   source_span=("doc_0.md", 28, 34)),
        ],
        relations=[
            Relation(subject="mat_main", predicate="has_W_rec", object="v_wrec_main"),
            Relation(subject="comp_x", predicate="has_W_rec", object="v_wrec_comp"),
            Relation(subject="v_wrec_main", predicate="has_unit", object="u_jcm3"),
            Relation(subject="v_wrec_comp", predicate="has_unit", object="u_jcm3"),
        ],
    )
    out = extract_headline_metrics(kg)
    assert out["flagship"] == "0.85NBST-0.15BMZ"
    assert out["W_rec"] == "5.00 J/cm^3"
    # The comparator's 2.94 must NOT leak into headline_metrics
    assert "2.94" not in str(out)


def test_extract_headline_metrics_no_materials_returns_empty():
    kg = PaperKG(entities=[], relations=[])
    assert extract_headline_metrics(kg) == {}


def test_extract_headline_metrics_unitless_value():
    """A value with no `has_unit` relation should still be captured."""
    kg = PaperKG(
        entities=[
            Entity(id="mat_main", type="material", text="X",
                   source_span=("d", 0, 1)),
            Entity(id="v1", type="value", text="42",
                   source_span=("d", 1, 3)),
        ],
        relations=[
            Relation(subject="mat_main", predicate="has_count", object="v1"),
        ],
    )
    out = extract_headline_metrics(kg)
    assert out["count"] == "42"
