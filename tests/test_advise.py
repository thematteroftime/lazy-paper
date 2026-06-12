from pathlib import Path
from unittest.mock import patch

import pytest

from llm.advise import gather_evidence, compose, next_round_dir, record_outcome
from stages._common import dump_yaml


class _FakeLib:
    def __init__(self, root: Path, manifest: dict, hits=None):
        self.root = root
        self._manifest = manifest
        self._hits = hits or []

    def papers(self):
        return self._manifest

    def query(self, topic, *, top_k=8, papers=None):
        return self._hits


def _lib(tmp_path: Path) -> _FakeLib:
    root = tmp_path / "library"
    manifest = {
        "paper-a": {"kind": "paper", "title": "Paper A", "keywords": ["energy"]},
        "exp-01": {"kind": "experiment", "title": "alpha sweep",
                   "papers": ["paper-a"], "env": "IsaacLab"},
    }
    pa_dir = root / "papers" / "paper-a"
    pa_dir.mkdir(parents=True)
    dump_yaml(pa_dir / "context.yaml",
              {"title": "Paper A", "critical_questions": ["What limits A?"],
               "headline_metrics": {"flagship": "Go1"}})
    ex = root / "experiments" / "exp-01"
    ex.mkdir(parents=True)
    dump_yaml(ex / "exp.yaml", {"title": "alpha sweep",
                                "hyperparams": {"alpha_en": 1.0},
                                "papers": ["paper-a"]})
    dump_yaml(ex / "exp_notes.yaml",
              [{"image": "curves/cot.png", "visual_summary": "CoT falls to 3.2",
                "deep_observation": "healthy convergence", "anomalies": []}])
    (ex / "notes.md").write_text("diverged above 1.9 m/s", encoding="utf-8")
    (ex / "metrics.csv").write_text("step,cot\n0,9.9\n200,3.2\n",
                                    encoding="utf-8")
    hits = [{"gid": "paper-a::c0001", "paper_id": "paper-a", "doc_name": "d",
             "char_start": 0, "char_end": 9, "score": 0.03,
             "text": "energy regularization cuts CoT by 67.4%"}]
    return _FakeLib(root, manifest, hits)


def test_gather_evidence_all_sources(tmp_path: Path):
    lib = _lib(tmp_path)
    ev = gather_evidence(lib, "exp-01", idea="push to 2.2 m/s")
    assert "alpha sweep" in ev                 # exp.yaml
    assert "alpha_en" in ev                    # hyperparams
    assert "CoT falls to 3.2" in ev            # exp_notes
    assert "diverged above 1.9" in ev          # notes.md
    assert "min=3.2" in ev                     # metrics digest
    assert "Paper A" in ev and "What limits A?" in ev  # linked paper context
    assert "67.4%" in ev                       # library excerpt


def test_gather_evidence_unknown_exp(tmp_path: Path):
    lib = _lib(tmp_path)
    with pytest.raises(SystemExit, match="not an ingested experiment"):
        gather_evidence(lib, "paper-a", idea="x")   # a paper, not an experiment
    with pytest.raises(SystemExit, match="not an ingested experiment"):
        gather_evidence(lib, "ghost", idea="x")


def test_round_dirs_increment(tmp_path: Path):
    lib = _lib(tmp_path)
    r1 = next_round_dir(lib, "exp-01")
    assert r1.name == "round_01"
    r1.mkdir(parents=True)
    (r1 / "report.md").write_text("r1", encoding="utf-8")
    r2 = next_round_dir(lib, "exp-01")
    assert r2.name == "round_02"


def test_prior_rounds_and_outcomes_in_evidence(tmp_path: Path):
    lib = _lib(tmp_path)
    r1 = next_round_dir(lib, "exp-01")
    r1.mkdir(parents=True)
    (r1 / "report.md").write_text("建议：将 alpha_en 提到 1.2", encoding="utf-8")
    record_outcome(lib, "exp-01", "alpha_en=1.2 导致 2.0 m/s 失稳，回退")
    assert (r1 / "outcome.md").exists()
    ev = gather_evidence(lib, "exp-01", idea="next")
    assert "PRIOR ROUND round_01" in ev
    assert "alpha_en 提到 1.2" in ev
    assert "失稳，回退" in ev


def test_record_outcome_requires_round(tmp_path: Path):
    lib = _lib(tmp_path)
    with pytest.raises(SystemExit, match="no advise rounds"):
        record_outcome(lib, "exp-01", "x")


_GOOD_ADVICE = """## 现状诊断
CoT 已收敛到 3.2 [src: exp-01]，但 1.9 m/s 以上失稳 [src: exp-01]。
上一轮结论仍然成立 [src: round_01 outcome]。

## 下一轮迭代方案
1. 改什么：alpha_en 降到 0.8；预期：2.0 m/s 跟踪误差 < 0.1（区间 0.05-0.1）；依据 [src: paper-a]。

## 深度观察
论文的 67.4% 节能 [src: paper-a] 与实验趋势一致 [src: exp-01]。

## 风险与备选
(推测) 课程式速度调度可能更稳 [src: paper-a]。
"""


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.model = "fake"
        self.usage = {"total_tokens": 2}


def test_compose_marker_contract_and_audit(tmp_path: Path):
    base = tmp_path / "r" / "report.md"
    with patch("llm.advise.LLM") as M:
        M.return_value.chat.side_effect = [
            _FakeResp("no markers"), _FakeResp(_GOOD_ADVICE)]
        report, resp = compose(idea="i", evidence="e", lang="zh",
                               audit_base=base)
    assert "[src: exp-01]" in report
    assert M.return_value.chat.call_count == 2
    assert Path(str(base) + ".response.json").exists()


def test_cli_advise_e2e_and_outcome(tmp_path: Path, capsys, monkeypatch):
    import cli

    lib = _lib(tmp_path)

    class FakeLibCls:
        def __init__(self, *a, **k):
            self.root = lib.root
        papers = staticmethod(lib.papers)
        query = staticmethod(lambda topic, top_k=8, papers=None: lib._hits)

    monkeypatch.setattr("llm.library.Library", FakeLibCls)
    with patch("llm.advise.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(_GOOD_ADVICE)
        rc = cli.main(["advise", "--exp", "exp-01", "--idea", "push to 2.2"])
    assert rc == 0
    r1 = lib.root / "experiments" / "exp-01" / "advice" / "round_01"
    assert (r1 / "report.md").exists()
    out = capsys.readouterr().out
    assert "round_01" in out

    rc = cli.main(["advise", "--exp", "exp-01", "--outcome", "回退了"])
    assert rc == 0
    assert (r1 / "outcome.md").read_text(encoding="utf-8") == "回退了"

    # round references ([src: round_01 ...]) are legitimate grounding —
    # they must not trigger an unknown-citation WARNING
    with patch("llm.advise.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(_GOOD_ADVICE)
        rc = cli.main(["advise", "--exp", "exp-01", "--idea", "round two"])
    assert rc == 0
    out2 = capsys.readouterr().out
    assert "WARNING" not in out2
    assert "round_02" in out2
