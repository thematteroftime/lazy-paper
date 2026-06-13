"""TDD tests for llm/garden.py (v1.19).

Mirror of _make_run from test_library.py — copied minimal fixture, NOT imported.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from llm.library import Library
from llm.paper_kg import Entity, PaperKG, Relation
from llm.retriever import Retriever
from stages._common import dump_yaml


# ---------------------------------------------------------------------------
# Fixture helpers (copied from test_library.py, not imported)
# ---------------------------------------------------------------------------

def _fake_embed(texts):
    """Deterministic 8-dim embedding."""
    out = []
    for t in texts:
        out.append([1.0 if "alpha" in t else 0.0,
                    1.0 if "beta" in t else 0.0] + [0.1] * 6)
    return np.asarray(out, dtype=np.float32)


def _make_run(tmp_path: Path, paper_id: str, marker: str,
              embed=_fake_embed) -> Path:
    """Fake a finished run: s03 chapters -> real Retriever.build -> s08/retrieval.parquet."""
    run = tmp_path / "runs" / paper_id
    chapters = run / "s03_chapter" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "chapter_000_intro.md").write_text(
        f"This paper studies {marker} dynamics in detail. " * 30,
        encoding="utf-8")
    s06 = run / "s06_context"
    s06.mkdir()
    s08 = run / "s08_section_compose"
    s08.mkdir()
    with patch("llm.retriever._embed_texts", side_effect=embed):
        Retriever().build(chapters_dir=chapters,
                          out_path=s08 / "retrieval.parquet")
    kg = PaperKG(
        entities=[Entity(id="e1", type="method", text=marker,
                         source_span=("chapter_000_intro.md", 0, 10))],
        relations=[Relation(subject="e1", predicate="uses", object="e1")],
    )
    kg.to_parquet(s06 / "paper_kg.parquet")
    dump_yaml(s06 / "context.yaml",
              {"title": f"{marker} paper",
               "keywords": [marker],
               "critical_questions": ["What is the main contribution?",
                                      "How does it compare to prior work?"]})
    dump_yaml(s06 / "done.yaml", {"tokens": 100})
    dump_yaml(run / "meta.yaml", {"paper_id": paper_id, "lang": "zh"})
    # s04 figures.yaml
    s04 = run / "s04_figures"
    s04.mkdir()
    dump_yaml(s04 / "figures.yaml", [
        {"fig_id": "fig_1", "caption": "First figure caption."},
        {"fig_id": "fig_2", "caption": "Second figure caption."},
    ])
    (s08 / "01-intro.md").write_text("composed section", encoding="utf-8")
    (s08 / "01-intro.prompt.md").write_text("audit prompt", encoding="utf-8")
    return run


# ---------------------------------------------------------------------------
# Test 1: export_data shape
# ---------------------------------------------------------------------------

def test_export_data_shape(tmp_path: Path):
    """export_data returns correct structure: ingested_at ISO-Z, questions, figures,
    entities grouped under pid with id/type/text, relations as 3-element lists."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    export = garden.export_data(lib)

    papers = export["manifest"]["papers"]
    assert len(papers) == 1
    p = papers[0]
    assert p["id"] == "alpha-paper"
    assert p["title"] == "alpha paper"
    assert p["lang"] == "zh"
    assert p["n_chunks"] > 0
    assert p["n_entities"] == 1
    assert p["total_tokens"] == 100
    assert "ingested_at" in p
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*Z", p["ingested_at"])
    assert p["keywords"] == ["alpha"]
    assert p["questions"] == ["What is the main contribution?",
                               "How does it compare to prior work?"]
    assert p["figures"] == [{"id": "fig_1", "caption": "First figure caption."},
                             {"id": "fig_2", "caption": "Second figure caption."}]
    assert p["kind"] == "paper"

    # entities grouped by pid
    assert "alpha-paper" in export["entities"]
    ents = export["entities"]["alpha-paper"]
    assert len(ents) == 1
    assert set(ents[0].keys()) >= {"id", "type", "text"}
    assert ents[0]["text"] == "alpha"

    # relations as [subject, predicate, object] lists
    assert "alpha-paper" in export["relations"]
    rels = export["relations"]["alpha-paper"]
    assert len(rels) == 1
    assert len(rels[0]) == 3
    assert rels[0][1] == "uses"


# ---------------------------------------------------------------------------
# Test 2: experiments included without crash
# ---------------------------------------------------------------------------

def test_export_data_includes_experiments(tmp_path: Path):
    """Experiments appear in manifest.papers with kind=experiment and n_entities=0,
    no crash even when no archived context/figures exist."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    # Inject a fake experiment entry directly into manifest.yaml
    manifest = lib.papers()
    manifest["exp-001"] = {
        "kind": "experiment",
        "title": "Flash experiment",
        "keywords": ["flash"],
        "n_chunks": 5,
        "n_entities": 0,
        "total_tokens": 0,
        "ingested_at": 1700000000.0,
    }
    dump_yaml(lib.manifest_path, manifest)

    lib2 = Library(tmp_path / "library")
    export = garden.export_data(lib2)

    ids = {p["id"] for p in export["manifest"]["papers"]}
    assert "exp-001" in ids

    exp_entry = next(p for p in export["manifest"]["papers"] if p["id"] == "exp-001")
    assert exp_entry["kind"] == "experiment"
    assert exp_entry["n_entities"] == 0
    # No crash on missing archives — questions/figures should be absent or empty
    assert exp_entry.get("questions", []) == []
    assert exp_entry.get("figures", []) == []


# ---------------------------------------------------------------------------
# Test 3: empty library creates no directories
# ---------------------------------------------------------------------------

def test_export_data_empty_library_no_dirs(tmp_path: Path):
    """export_data on a fresh library returns empty papers list and creates no dirs."""
    from llm import garden

    fresh = tmp_path / "fresh"
    lib = Library(fresh)
    export = garden.export_data(lib)

    assert export["manifest"]["papers"] == []
    assert not fresh.exists(), "Empty library must not create directories"


# ---------------------------------------------------------------------------
# Test 4: build injects inline export
# ---------------------------------------------------------------------------

def test_build_injects_inline_export(tmp_path: Path):
    """build() writes garden.html with GARDEN_EXPORT inline before garden-data.js,
    garden-export.json exists, all JS files copied, DATA_ADAPTER.md not copied."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    out_dir = tmp_path / "out"
    page = garden.build(lib, out_dir)

    assert page == out_dir / "garden.html"
    assert page.exists()

    html = page.read_text(encoding="utf-8")
    # GARDEN_EXPORT must appear before garden-data.js
    export_pos = html.find("window.GARDEN_EXPORT")
    data_js_pos = html.find('<script src="garden-data.js">')
    assert export_pos != -1, "window.GARDEN_EXPORT not found in garden.html"
    assert data_js_pos != -1, "'garden-data.js' script tag not found"
    assert export_pos < data_js_pos, "GARDEN_EXPORT must come BEFORE garden-data.js"

    # garden-export.json exists
    assert (out_dir / "garden-export.json").exists()
    exported = json.loads((out_dir / "garden-export.json").read_text(encoding="utf-8"))
    assert "manifest" in exported

    # All frontend JS files are copied
    for js_file in ["garden-app.js", "garden-render.js", "garden-hud.js",
                    "garden-data.js", "garden-tweaks.jsx", "tweaks-panel.jsx"]:
        assert (out_dir / js_file).exists(), f"{js_file} not copied"

    # DATA_ADAPTER.md must NOT be copied
    assert not (out_dir / "DATA_ADAPTER.md").exists()


# ---------------------------------------------------------------------------
# Test 5: build on empty library raises SystemExit
# ---------------------------------------------------------------------------

def test_build_empty_library_exits(tmp_path: Path):
    """build() on an empty library raises SystemExit with a helpful message."""
    from llm import garden

    lib = Library(tmp_path / "fresh")
    with pytest.raises(SystemExit, match="empty"):
        garden.build(lib, tmp_path / "out")


# ---------------------------------------------------------------------------
# Test 6: CLI e2e
# ---------------------------------------------------------------------------

def test_cli_garden_e2e(tmp_path: Path, capsys, monkeypatch):
    """cli.main(['garden']) returns 0, prints '[garden] built', file exists."""
    import cli

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib_dir = tmp_path / "library"
    lib = Library(lib_dir)
    lib.ingest(run)

    monkeypatch.setenv("LAZY_PAPER_LIBRARY_DIR", str(lib_dir))

    rc = cli.main(["garden"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[garden] built" in out

    # garden.html must exist under default out dir
    page = lib_dir / "garden" / "garden.html"
    assert page.exists()


# ---------------------------------------------------------------------------
# Coverage: export_data edge cases
# ---------------------------------------------------------------------------

def test_export_data_missing_ingested_at(tmp_path: Path):
    """A manifest entry without `ingested_at` is still exported — the field is
    simply absent, no crash."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    manifest = lib.papers()
    del manifest["alpha-paper"]["ingested_at"]
    dump_yaml(lib.manifest_path, manifest)

    export = garden.export_data(Library(tmp_path / "library"))
    p = next(p for p in export["manifest"]["papers"] if p["id"] == "alpha-paper")
    assert "ingested_at" not in p
    assert p["title"] == "alpha paper"


def test_export_data_ingested_at_iso_format(tmp_path: Path):
    """epoch 1750000000.0 -> exact ISO-8601 UTC string ending in Z."""
    from datetime import datetime, timezone

    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    manifest = lib.papers()
    manifest["alpha-paper"]["ingested_at"] = 1750000000.0
    dump_yaml(lib.manifest_path, manifest)

    expected = (datetime.fromtimestamp(1750000000.0, tz=timezone.utc)
                .isoformat().replace("+00:00", "Z"))
    assert expected.startswith("2025-06-15T") and expected.endswith("Z")

    export = garden.export_data(Library(tmp_path / "library"))
    p = next(p for p in export["manifest"]["papers"] if p["id"] == "alpha-paper")
    assert p["ingested_at"] == expected


# ---------------------------------------------------------------------------
# Coverage: build robustness + injection ordering
# ---------------------------------------------------------------------------

def test_build_missing_marker_exits(tmp_path: Path, monkeypatch):
    """If the vendored garden.html loses the garden-data.js marker, build must
    raise a clear SystemExit instead of silently producing a broken page."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    fake_front = tmp_path / "fake_frontend"
    fake_front.mkdir()
    # garden.html WITHOUT the expected <script src="garden-data.js"> marker
    (fake_front / "garden.html").write_text(
        "<html><body>no marker here</body></html>", encoding="utf-8")
    (fake_front / "garden-data.js").write_text("// data", encoding="utf-8")
    (fake_front / "garden-app.js").write_text("// app", encoding="utf-8")
    monkeypatch.setattr(garden, "FRONTEND_DIR", fake_front)

    with pytest.raises(SystemExit, match="marker"):
        garden.build(lib, tmp_path / "out")


def test_build_injection_position(tmp_path: Path):
    """In the built garden.html, the window.GARDEN_EXPORT inline block appears
    before the garden-data.js script tag (so data is defined first)."""
    from llm import garden

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)

    page = garden.build(lib, tmp_path / "out")
    html = page.read_text(encoding="utf-8")
    export_idx = html.index("window.GARDEN_EXPORT")
    data_js_idx = html.index('<script src="garden-data.js"></script>')
    assert export_idx < data_js_idx


def test_export_figures_src_and_preview(tmp_path: Path, monkeypatch):
    from llm.garden import export_data, build
    from llm.library import Library

    run = _make_run(tmp_path, "alpha-paper", "alpha")
    # fake the s09 preview + an archived figure image
    (run / "s09_render").mkdir()
    (run / "s09_render" / "preview.html").write_text("<html>", encoding="utf-8")
    lib = Library(tmp_path / "library")
    lib.ingest(run)
    imgs = lib.root / "papers" / "alpha-paper" / "imgs"
    imgs.mkdir(parents=True, exist_ok=True)
    (imgs / "img_001.jpg").write_bytes(b"\xff\xd8 fake")
    dump_yaml(lib.root / "papers" / "alpha-paper" / "figures.yaml",
              [{"fig_id": "Fig. 1", "image_rel_path": "imgs/img_001.jpg",
                "caption": "gait curve"},
               {"fig_id": "Fig. 2", "caption": "no image archived"}])

    export = export_data(lib)
    paper = next(p for p in export["manifest"]["papers"]
                 if p["id"] == "alpha-paper")
    figs = {f["id"]: f for f in paper["figures"]}
    assert figs["Fig. 1"]["src"] == "imgs/alpha-paper/img_001.jpg"
    assert "src" not in figs["Fig. 2"]
    # preview is a RELATIVE path under the garden dir — browsers block file://
    # navigation outside the page's own directory tree
    assert paper["preview"] == "previews/alpha-paper.html"

    out = build(lib, tmp_path / "out")
    assert (tmp_path / "out" / "imgs" / "alpha-paper" / "img_001.jpg").exists()
    # the self-contained preview.html is copied into the garden tree
    assert (tmp_path / "out" / "previews" / "alpha-paper.html").read_text(
        encoding="utf-8") == "<html>"
