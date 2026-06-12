from pathlib import Path
from unittest.mock import patch

import pytest

from llm.experiment import load_bundle, summarize_metrics, analyze_curves, build_corpus
from stages._common import dump_yaml, load_yaml


def _bundle(tmp_path: Path) -> Path:
    b = tmp_path / "exp-01"
    (b / "curves").mkdir(parents=True)
    dump_yaml(b / "exp.yaml", {
        "title": "alpha gait sweep",
        "env": "IsaacLab 2.1 / Go2",
        "software": "lazy-rl v0.3",
        "hyperparams": {"alpha_en": 1.0, "lr": 3e-4},
        "papers": ["atec-b2w-energy-rl"],
        "date": "2026-06-10",
    })
    (b / "notes.md").write_text("Run diverged above 1.9 m/s as predicted.",
                                encoding="utf-8")
    (b / "metrics.csv").write_text(
        "step,cot,reward\n0,9.9,0.1\n100,5.0,0.6\n200,3.2,0.9\n",
        encoding="utf-8")
    # vision is mocked so content doesn't matter
    (b / "curves" / "cot.png").write_bytes(b"\x89PNG fake")
    return b


def test_load_bundle_validates(tmp_path: Path):
    b = _bundle(tmp_path)
    meta = load_bundle(b)
    assert meta["title"] == "alpha gait sweep"
    assert meta["papers"] == ["atec-b2w-energy-rl"]


def test_load_bundle_requires_exp_yaml(tmp_path: Path):
    empty = tmp_path / "nope"
    empty.mkdir()
    with pytest.raises(SystemExit, match="exp.yaml"):
        load_bundle(empty)


def test_summarize_metrics_digest(tmp_path: Path):
    b = _bundle(tmp_path)
    digest = summarize_metrics(b)
    assert "metrics.csv" in digest
    assert "cot" in digest and "min=3.2" in digest and "max=9.9" in digest
    assert "last=3.2" in digest
    assert "rows=3" in digest


def test_summarize_metrics_no_csv(tmp_path: Path):
    b = tmp_path / "x"
    b.mkdir()
    assert summarize_metrics(b) == ""


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.model = "fake-vl"
        self.usage = {"total_tokens": 3}


_CURVE_YAML = ("visual_summary: CoT falls from 9.9 to 3.2 over 200 steps.\n"
               "deep_observation: convergence healthy, no plateau.\n"
               "anomalies: []\n")


def test_analyze_curves_writes_notes_and_caches(tmp_path: Path):
    b = _bundle(tmp_path)
    with patch("llm.experiment.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(_CURVE_YAML)
        notes = analyze_curves(b, lang="zh")
        assert M.return_value.chat.call_count == 1
        # second call hits the exp_notes.yaml cache — no new LLM calls
        notes2 = analyze_curves(b, lang="zh")
        assert M.return_value.chat.call_count == 1
    assert notes == notes2
    assert notes[0]["image"] == "curves/cot.png"
    assert "CoT falls" in notes[0]["visual_summary"]
    assert (b / "exp_notes.yaml").exists()
    assert (b / "exp_notes.cot.prompt.md").exists()
    assert (b / "exp_notes.cot.response.json").exists()


def test_analyze_curves_no_images(tmp_path: Path):
    b = tmp_path / "noimg"
    b.mkdir()
    dump_yaml(b / "exp.yaml", {"title": "t"})
    assert analyze_curves(b, lang="zh") == []


def test_build_corpus_combines_everything(tmp_path: Path):
    b = _bundle(tmp_path)
    dump_yaml(b / "exp_notes.yaml",
              [{"image": "curves/cot.png",
                "visual_summary": "CoT falls.", "deep_observation": "ok",
                "anomalies": []}])
    corpus = build_corpus(b)
    assert "alpha gait sweep" in corpus            # exp.yaml
    assert "alpha_en" in corpus                    # hyperparams
    assert "diverged above 1.9" in corpus          # notes.md
    assert "min=3.2" in corpus                     # metrics digest
    assert "CoT falls." in corpus                  # curve analysis


def test_ingest_experiment_into_library(tmp_path: Path):
    import numpy as np
    from llm.library import Library

    b = _bundle(tmp_path)
    dump_yaml(b / "exp_notes.yaml",
              [{"image": "curves/cot.png", "visual_summary": "CoT falls.",
                "deep_observation": "ok", "anomalies": []}])

    def fake_embed(texts):
        return np.asarray([[0.5] * 8 for _ in texts], dtype=np.float32)

    lib = Library(tmp_path / "library")
    with patch("llm.library._embed_texts", side_effect=fake_embed):
        entry = lib.ingest_experiment(b)
    assert entry["kind"] == "experiment"
    assert entry["n_chunks"] > 0
    assert entry["papers"] == ["atec-b2w-energy-rl"]
    assert lib.papers()["exp-01"]["kind"] == "experiment"
    rows = lib._db.open_table("chunks").to_arrow().to_pylist()
    assert any(r["paper_id"] == "exp-01" for r in rows)
    # archived copy survives bundle deletion
    assert (lib.root / "experiments" / "exp-01" / "exp.yaml").exists()
    assert (lib.root / "experiments" / "exp-01" / "exp_notes.yaml").exists()
    # idempotent
    with patch("llm.library._embed_texts", side_effect=fake_embed):
        lib.ingest_experiment(b)
    rows2 = lib._db.open_table("chunks").to_arrow().to_pylist()
    assert len(rows2) == len(rows)


def test_cli_exp_ingest_e2e(tmp_path: Path, capsys, monkeypatch):
    import numpy as np
    import cli

    b = _bundle(tmp_path)
    monkeypatch.setenv("LAZY_PAPER_LIBRARY_DIR", str(tmp_path / "library"))

    def fake_embed(texts):
        return np.asarray([[0.5] * 8 for _ in texts], dtype=np.float32)

    with patch("llm.experiment.LLM") as M, \
         patch("llm.library._embed_texts", side_effect=fake_embed):
        M.return_value.chat.return_value = _FakeResp(_CURVE_YAML)
        rc = cli.main(["exp-ingest", str(b)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[exp] analyzed 1 curve" in out
    assert "[exp] ingested exp-01" in out


def test_analyze_curves_strips_markdown_fence(tmp_path: Path):
    # Qwen-VL wraps YAML in ```yaml fences (observed live) — must be stripped.
    b = _bundle(tmp_path)
    with patch("llm.experiment.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(
            "```yaml\n" + _CURVE_YAML + "```")
        notes = analyze_curves(b, lang="zh")
    assert "CoT falls" in notes[0]["visual_summary"]


def test_analyze_curves_analyzes_new_images_added_later(tmp_path: Path):
    b = _bundle(tmp_path)
    with patch("llm.experiment.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(_CURVE_YAML)
        analyze_curves(b, lang="zh")
        (b / "curves" / "reward.png").write_bytes(b"\x89PNG fake2")
        notes = analyze_curves(b, lang="zh")
        # only the newly added image triggers an LLM call
        assert M.return_value.chat.call_count == 2
    assert {n["image"] for n in notes} == {"curves/cot.png",
                                           "curves/reward.png"}


def test_ingest_experiment_refuses_paper_id_collision(tmp_path: Path):
    from llm.library import Library

    lib = Library(tmp_path / "library")
    lib.root.mkdir(parents=True, exist_ok=True)
    dump_yaml(lib.manifest_path, {"exp-01": {"kind": "paper", "title": "P"}})
    b = _bundle(tmp_path)  # dir name is exp-01
    with pytest.raises(SystemExit, match="collide"):
        lib.ingest_experiment(b)
