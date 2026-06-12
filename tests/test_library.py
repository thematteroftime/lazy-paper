from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from llm.library import Library
from llm.paper_kg import Entity, PaperKG, Relation
from llm.retriever import Retriever
from stages._common import dump_yaml


def _fake_embed(texts):
    """Deterministic 8-dim embedding: dims 0/1 mark 'alpha'/'beta' presence."""
    out = []
    for t in texts:
        out.append([1.0 if "alpha" in t else 0.0,
                    1.0 if "beta" in t else 0.0] + [0.1] * 6)
    return np.asarray(out, dtype=np.float32)


def _fake_embed4(texts):
    return np.asarray([[0.5] * 4 for _ in texts], dtype=np.float32)


def _make_run(tmp_path: Path, paper_id: str, marker: str,
              embed=_fake_embed) -> Path:
    """Fake a finished run: s03 chapters → real Retriever.build → s06 parquets."""
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
              {"title": f"{marker} paper", "keywords": [marker]})
    dump_yaml(s06 / "done.yaml", {"tokens": 100})
    dump_yaml(run / "meta.yaml", {"paper_id": paper_id, "lang": "zh"})
    (s08 / "01-intro.md").write_text("composed section", encoding="utf-8")
    (s08 / "01-intro.prompt.md").write_text("audit prompt", encoding="utf-8")
    return run


def test_ingest_writes_manifest_chunks_entities(tmp_path: Path):
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    entry = lib.ingest(run)

    assert entry["n_chunks"] > 0
    assert entry["n_entities"] == 1
    assert entry["total_tokens"] == 100
    assert entry["kind"] == "paper"
    assert entry["title"] == "alpha paper"
    assert lib.papers()["alpha-paper"]["embedding_dim"] == 8

    rows = lib._db.open_table("chunks").to_arrow().to_pylist()
    assert all(r["paper_id"] == "alpha-paper" for r in rows)
    ents = lib._db.open_table("entities").to_arrow().to_pylist()
    assert ents[0]["text"] == "alpha"
    rels = lib._db.open_table("relations").to_arrow().to_pylist()
    assert rels[0]["predicate"] == "uses"


def test_ingest_archives_artifacts_without_audit_files(tmp_path: Path):
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)
    dest = lib.root / "papers" / "alpha-paper"
    assert (dest / "context.yaml").exists()
    assert (dest / "sections" / "01-intro.md").exists()
    assert not (dest / "sections" / "01-intro.prompt.md").exists()


def test_ingest_is_idempotent(tmp_path: Path):
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)
    n1 = len(lib._db.open_table("chunks").to_arrow().to_pylist())
    lib.ingest(run)
    n2 = len(lib._db.open_table("chunks").to_arrow().to_pylist())
    assert n1 == n2
    assert len(lib.papers()) == 1


def test_ingest_rejects_embedding_dim_mismatch(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    run4 = _make_run(tmp_path, "gamma-paper", "gamma", embed=_fake_embed4)
    with pytest.raises(SystemExit, match="dim mismatch"):
        lib.ingest(run4)


def test_ingest_requires_retrieval_index_or_chapters(tmp_path: Path):
    bare = tmp_path / "runs" / "empty-run"
    bare.mkdir(parents=True)
    with pytest.raises(SystemExit, match="retrieval.parquet"):
        Library(tmp_path / "library").ingest(bare)


def test_reingest_without_kg_clears_stale_entities(tmp_path: Path):
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    lib = Library(tmp_path / "library")
    lib.ingest(run)
    assert len(lib._db.open_table("entities").to_arrow().to_pylist()) == 1

    (run / "s06_context" / "paper_kg.parquet").unlink()
    (run / "s06_context" / "paper_kg.rel.parquet").unlink()
    entry = lib.ingest(run)
    assert entry["n_entities"] == 0
    ents = [e for e in lib._db.open_table("entities").to_arrow().to_pylist()
            if e["paper_id"] == "alpha-paper"]
    assert ents == []


def test_query_ranks_matching_paper_first(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    lib.ingest(_make_run(tmp_path, "beta-paper", "beta"))
    with patch("llm.library._embed_texts", side_effect=_fake_embed):
        hits = lib.query("alpha dynamics", top_k=4)
    assert hits
    assert hits[0]["paper_id"] == "alpha-paper"
    assert {"gid", "paper_id", "doc_name", "char_start", "char_end",
            "score", "text"} <= set(hits[0])


def test_query_papers_filter(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    lib.ingest(_make_run(tmp_path, "beta-paper", "beta"))
    with patch("llm.library._embed_texts", side_effect=_fake_embed):
        hits = lib.query("alpha dynamics", top_k=4, papers=["beta-paper"])
    assert hits
    assert all(h["paper_id"] == "beta-paper" for h in hits)


def test_query_empty_library_returns_empty(tmp_path: Path):
    lib = Library(tmp_path / "library")
    hits = lib.query("anything")
    assert hits == []


def _const_embed(texts):
    return np.asarray([[0.5] * 8 for _ in texts], dtype=np.float32)


def test_query_sparse_leg_ranks_keyword_paper_first(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha", embed=_const_embed))
    lib.ingest(_make_run(tmp_path, "beta-paper", "beta", embed=_const_embed))
    with patch("llm.library._embed_texts", side_effect=_const_embed):
        hits = lib.query("alpha", top_k=8)
    assert hits
    assert hits[0]["paper_id"] == "alpha-paper"


def test_cli_ingest_papers_query_json(tmp_path: Path, capsys, monkeypatch):
    import json as _json
    import cli

    _make_run(tmp_path, "alpha-paper", "alpha")
    monkeypatch.setenv("LAZY_PAPER_LIBRARY_DIR", str(tmp_path / "library"))

    rc = cli.main(["ingest", "alpha-paper",
                   "--runs-dir", str(tmp_path / "runs")])
    assert rc == 0
    assert "ingested" in capsys.readouterr().out

    rc = cli.main(["papers"])
    assert rc == 0
    assert "alpha-paper" in capsys.readouterr().out

    with patch("llm.library._embed_texts", side_effect=_fake_embed):
        rc = cli.main(["query", "alpha dynamics", "--json", "--top-k", "3"])
    assert rc == 0
    hits = _json.loads(capsys.readouterr().out)
    assert hits and hits[0]["paper_id"] == "alpha-paper"


def test_query_survives_missing_bm25_ids(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    (lib.root / "bm25_ids.json").unlink()
    hits = lib.query("alpha dynamics")  # must not raise; no embed call needed
    assert hits == []


def test_readonly_papers_creates_no_dirs(tmp_path: Path):
    root = tmp_path / "fresh-library"
    lib = Library(root)
    assert lib.papers() == {}
    assert not root.exists()


def test_run_ingest_flag_calls_library(tmp_path: Path, monkeypatch):
    import cli

    monkeypatch.setattr(cli, "_run_one", lambda *a, **k: None)
    called = {}

    class FakeLib:
        def __init__(self, *a, **k):
            pass

        def ingest(self, run_dir, **k):
            called["run_dir"] = Path(run_dir)
            return {"n_chunks": 1, "n_entities": 0}

    monkeypatch.setattr("llm.library.Library", FakeLib)
    # _run_one is stubbed, so nothing creates runs/x/ — meta.yaml needs it.
    (tmp_path / "runs" / "x").mkdir(parents=True)
    rc = cli.main(["run", "--pdf", "a.pdf", "--template", "t.docx",
                   "--runs-dir", str(tmp_path / "runs"),
                   "--paper-id", "x", "--ingest"])
    assert rc == 0
    assert called["run_dir"].name == "x"


def test_ingest_builds_index_when_missing(tmp_path: Path):
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    (run / "s08_section_compose" / "retrieval.parquet").unlink()
    lib = Library(tmp_path / "library")
    with patch("llm.retriever._embed_texts", side_effect=_fake_embed):
        entry = lib.ingest(run)
    assert entry["n_chunks"] > 0
    assert (run / "s08_section_compose" / "retrieval.parquet").exists()


def _exp_bundle(tmp_path: Path, name: str = "exp-01") -> Path:
    b = tmp_path / name
    b.mkdir()
    dump_yaml(b / "exp.yaml", {"title": "alpha gait sweep",
                               "hyperparams": {"alpha_en": 1.0},
                               "papers": []})
    (b / "notes.md").write_text(
        "alpha experiment notes: run converged. " * 20, encoding="utf-8")
    return b


def test_query_papers_filter_isolates_experiment(tmp_path: Path):
    # Ingest one paper + one experiment; querying with papers=[exp_id] must
    # return only the experiment's chunks.
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha", embed=_const_embed))
    b = _exp_bundle(tmp_path)
    with patch("llm.library._embed_texts", side_effect=_const_embed):
        lib.ingest_experiment(b)
        hits = lib.query("alpha", top_k=8, papers=["exp-01"])
    assert hits
    assert all(h["paper_id"] == "exp-01" for h in hits)


def test_ingest_preserves_cjk_title_roundtrip(tmp_path: Path):
    # A CJK title survives manifest write/read exactly.
    run = _make_run(tmp_path, "alpha-paper", "alpha")
    dump_yaml(run / "s06_context" / "context.yaml",
              {"title": "能量正则化与四足步态", "keywords": ["alpha"]})
    lib = Library(tmp_path / "library")
    entry = lib.ingest(run)
    assert entry["title"] == "能量正则化与四足步态"
    assert lib.papers()["alpha-paper"]["title"] == "能量正则化与四足步态"


def test_cli_ingest_missing_run_names_path(tmp_path: Path, monkeypatch):
    import cli

    monkeypatch.setenv("LAZY_PAPER_LIBRARY_DIR", str(tmp_path / "library"))
    with pytest.raises(SystemExit, match="no-such-run"):
        cli.main(["ingest", "no-such-run", "--runs-dir", str(tmp_path / "runs")])


def test_remove_paper_cleans_everything(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    lib.ingest(_make_run(tmp_path, "beta-paper", "beta"))
    lib.remove("alpha-paper")
    assert "alpha-paper" not in lib.papers()
    rows = lib._db.open_table("chunks").to_arrow().to_pylist()
    assert all(r["paper_id"] != "alpha-paper" for r in rows)
    assert not (lib.root / "papers" / "alpha-paper").exists()
    with patch("llm.library._embed_texts", side_effect=_fake_embed):
        hits = lib.query("alpha dynamics")
    assert all(h["paper_id"] != "alpha-paper" for h in hits)


def test_remove_last_entry_empties_index(tmp_path: Path):
    lib = Library(tmp_path / "library")
    lib.ingest(_make_run(tmp_path, "alpha-paper", "alpha"))
    lib.remove("alpha-paper")
    assert lib.papers() == {}
    assert lib.query("anything") == []  # no crash, no stale bm25


def test_remove_unknown_raises(tmp_path: Path):
    lib = Library(tmp_path / "library")
    with pytest.raises(SystemExit, match="not in the library"):
        lib.remove("ghost")
