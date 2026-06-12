from pathlib import Path
from unittest.mock import patch

import pytest

from llm.synthesize import gather, compose, check_citations
from stages._common import dump_yaml


class _FakeLib:
    def __init__(self, root: Path, manifest: dict, hits: list[dict] | None = None):
        self.root = root
        self._manifest = manifest
        self._hits = hits or []
        self.last_query = None

    def papers(self):
        return self._manifest

    def query(self, topic, *, top_k=8, papers=None):
        self.last_query = {"topic": topic, "top_k": top_k, "papers": papers}
        return self._hits


def _lib(tmp_path: Path) -> _FakeLib:
    root = tmp_path / "library"
    manifest = {
        "paper-a": {"title": "Paper A", "keywords": ["energy"]},
        "paper-b": {"title": "Paper B", "keywords": ["skills"]},
    }
    for pid in manifest:
        d = root / "papers" / pid
        d.mkdir(parents=True)
        dump_yaml(d / "context.yaml",
                  {"title": manifest[pid]["title"],
                   "critical_questions": [f"What limits {pid}?"],
                   # real s06 schema: headline_metrics is a DICT, not a list
                   "headline_metrics": {"flagship": f"{pid}-platform"}})
        dump_yaml(d / "fig_notes.yaml",
                  [{"fig_id": "Fig. 1", "deep_observation": f"{pid} CoT drops 30%."}])
    hits = [{"gid": "paper-a::c0001", "paper_id": "paper-a", "doc_name": "d",
             "char_start": 0, "char_end": 9, "score": 0.03,
             "text": "energy regularization cuts CoT"}]
    return _FakeLib(root, manifest, hits)


def test_gather_includes_manifest_archives_excerpts(tmp_path: Path):
    lib = _lib(tmp_path)
    ev = gather(lib, "energy transfer")
    assert "PAPER paper-a" in ev and "PAPER paper-b" in ev
    assert "What limits paper-a?" in ev          # archived critical question
    assert "CoT drops 30%" in ev                  # archived fig deep_observation
    assert "paper-a-platform" in ev               # dict-shaped headline_metrics
    assert "energy regularization cuts CoT" in ev  # query excerpt
    assert lib.last_query["topic"] == "energy transfer"


def test_gather_requires_two_papers(tmp_path: Path):
    lib = _lib(tmp_path)
    lib._manifest = {"paper-a": lib._manifest["paper-a"]}
    with pytest.raises(SystemExit, match="at least 2"):
        gather(lib, "x")


def test_gather_papers_filter(tmp_path: Path):
    lib = _lib(tmp_path)
    with pytest.raises(SystemExit, match="at least 2"):
        gather(lib, "x", papers=["paper-a"])
    ev = gather(lib, "x", papers=["paper-a", "paper-b"])
    assert lib.last_query["papers"] == ["paper-a", "paper-b"]
    assert "PAPER paper-a" in ev


_GOOD_REPORT = """## 主题综述
能量正则化显著降低 CoT [src: paper-a]。

## 方法对比
| 论文 | 方法 | 结果 | 局限 |
|---|---|---|---|
| paper-a | 能量项 | CoT -30% [src: paper-a] | 高速失稳 |

## 证据与分歧
两文在权重选择上分歧 [src: paper-a][src: paper-b]。

## 研究空白
缺少双足验证。

## 下一步建议
1. 复现 α_en 扫描 (推测) [src: paper-a]。
"""


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.model = "fake"
        self.usage = {"total_tokens": 2}


def test_compose_retries_then_succeeds(tmp_path: Path):
    base = tmp_path / "synth" / "report.md"
    with patch("llm.synthesize.LLM") as M:
        M.return_value.chat.side_effect = [
            _FakeResp("no markers here"), _FakeResp(_GOOD_REPORT)]
        report, resp = compose(topic="t", evidence="e", lang="zh",
                               audit_base=base)
    assert "[src: paper-a]" in report
    assert M.return_value.chat.call_count == 2
    assert Path(str(base) + ".response.json").exists()
    assert Path(str(base) + ".prompt.md").exists()


def test_compose_no_markers_raises(tmp_path: Path):
    with patch("llm.synthesize.LLM") as M:
        M.return_value.chat.return_value = _FakeResp("still no markers")
        with pytest.raises(SystemExit, match="grounding markers"):
            compose(topic="t", evidence="e", lang="zh")


def test_check_citations_flags_unknown():
    unknown = check_citations(_GOOD_REPORT + "\n幽灵 [src: ghost-paper]。",
                              {"paper-a", "paper-b"})
    assert unknown == ["ghost-paper"]
    assert check_citations(_GOOD_REPORT, {"paper-a", "paper-b"}) == []


def test_cli_synthesize_e2e(tmp_path: Path, capsys, monkeypatch):
    import cli

    lib = _lib(tmp_path)

    class FakeLibCls:
        def __init__(self, *a, **k):
            self.root = lib.root
        papers = staticmethod(lib.papers)
        query = staticmethod(lambda topic, top_k=8, papers=None: lib._hits)

    monkeypatch.setattr("llm.library.Library", FakeLibCls)
    with patch("llm.synthesize.LLM") as M:
        M.return_value.chat.return_value = _FakeResp(_GOOD_REPORT)
        rc = cli.main(["synthesize", "--topic", "能量正则化迁移"])
    assert rc == 0
    out_dir = lib.root / "synth"
    reports = list(out_dir.rglob("report.md"))
    assert len(reports) == 1
    assert "[src: paper-a]" in reports[0].read_text(encoding="utf-8")
    captured = capsys.readouterr().out
    assert "[synthesize] wrote" in captured


def test_gather_recovers_fig_notes_from_raw_fallback(tmp_path: Path):
    # Real archives are 100% s07's defensive-parse-failed shape:
    # {error, fig_id, image_paths, raw} with the analysis inside fenced YAML.
    lib = _lib(tmp_path)
    raw = "```yaml\nfig_id: Fig. 9\nvisual_summary: |\n  raw-recovered CoT curve.\n```"
    dump_yaml(lib.root / "papers" / "paper-a" / "fig_notes.yaml",
              [{"error": "yaml-parse", "fig_id": "Fig. 9",
                "image_paths": [], "raw": raw}])
    ev = gather(lib, "x")
    assert "raw-recovered CoT curve" in ev


def test_check_citations_comma_variants():
    known = {"a", "b"}
    assert check_citations("x [src: a,b] y", known) == []
    assert check_citations("x [src: a, b] y", known) == []
    assert check_citations("x [src: a, ghost] y", known) == ["ghost"]


def test_check_citations_artifact_suffix():
    # advise (v1.18) emits [src: <id> <artifact>] — validate the id token only
    known = {"exp-01"}
    assert check_citations("x [src: exp-01 notes.md] y", known) == []
    assert check_citations("x [src: ghost notes.md] y", known) == ["ghost"]
