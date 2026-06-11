from pathlib import Path
from unittest.mock import patch

import pytest

from llm.template_author import prescan_run, prescan_pdf
from stages._common import dump_yaml


def _make_run(tmp_path: Path) -> Path:
    run = tmp_path / "runs" / "demo-paper"
    (run / "s02_clean").mkdir(parents=True)
    (run / "s02_clean" / "doc_0.md").write_text(
        "Adaptive Energy Regularization\n\nAbstract — We propose an adaptive "
        "energy term E_t that scales with velocity.", encoding="utf-8")
    (run / "s03_chapter").mkdir()
    # Real s03 schema: top-level LIST of {chapter_no, title, file, sources, chars}
    dump_yaml(run / "s03_chapter" / "chapter_index.yaml",
              [{"chapter_no": 0, "title": "INTRODUCTION",
                "file": "chapter_000_INTRODUCTION.md", "sources": [], "chars": 100},
               {"chapter_no": 1, "title": "ENERGY REGULARIZATION",
                "file": "chapter_001_ENERGY.md", "sources": [], "chars": 200}])
    (run / "s04_figures").mkdir()
    dump_yaml(run / "s04_figures" / "figures.yaml",
              [{"fig_id": "Fig. 1", "caption": "Gait transition vs commanded velocity."}])
    (run / "s06_context").mkdir()
    dump_yaml(run / "s06_context" / "context.yaml",
              {"title": "Adaptive Energy Regularization",
               "keywords": ["energy", "gait"],
               "critical_questions": ["How does E_t scale?"]})
    return run


def test_prescan_run_includes_all_sources(tmp_path: Path):
    run = _make_run(tmp_path)
    digest = prescan_run(run)
    assert "Adaptive Energy Regularization" in digest      # context title
    assert "ENERGY REGULARIZATION" in digest               # chapter title
    assert "Gait transition vs commanded velocity" in digest  # caption
    assert "adaptive" in digest or "Abstract" in digest    # s02 head text


def test_prescan_run_partial_artifacts(tmp_path: Path):
    run = tmp_path / "runs" / "bare"
    (run / "s02_clean").mkdir(parents=True)
    (run / "s02_clean" / "doc_0.md").write_text("Only OCR text here.", encoding="utf-8")
    digest = prescan_run(run)
    assert "Only OCR text here." in digest


def test_prescan_run_nothing_usable(tmp_path: Path):
    run = tmp_path / "runs" / "empty"
    run.mkdir(parents=True)
    with pytest.raises(SystemExit, match="prescan"):
        prescan_run(run)


def test_prescan_pdf_reads_first_pages(tmp_path: Path):
    class FakePage:
        def __init__(self, text): self._t = text
        def extract_text(self): return self._t

    class FakePDF:
        pages = [FakePage("Page one title"), FakePage("Page two"), FakePage(None)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("pdfplumber.open", return_value=FakePDF()):
        digest = prescan_pdf(Path("whatever.pdf"))
    assert "Page one title" in digest and "Page two" in digest


_CANNED_YAML = """\
sections:
  - title: "1. 研究背景与能量正则化动机?"
    questions:
      - 论文中 E_t 项的数学形式是什么，单位是什么?
      - 3 个速度区间各自的步态是什么?
  - title: 方法核心
    questions:
      - Fig. 1 中转换速度点的数值是多少?
"""


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.model = "fake"
        self.usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


def test_draft_parses_and_sanitizes(tmp_path: Path):
    from llm.template_author import draft
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp(
            "```yaml\n" + _CANNED_YAML + "```")
        sections, resp = draft(idea="迁移到双足", paper_digest="digest",
                               library_context="", lang="zh", n_sections=2)
    assert len(sections) == 2
    # title sanitized: leading numbering stripped, trailing '?' stripped
    assert sections[0]["title"] == "研究背景与能量正则化动机"
    # question that starts with a digit got a guidance prefix so s05 can
    # never promote it to a heading
    qs = sections[0]["questions"]
    assert any(q.startswith("- 3 个速度区间") for q in qs)
    assert any(q.endswith("?") for q in qs)


def test_draft_invalid_yaml_raises(tmp_path: Path):
    from llm.template_author import draft
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp("not: [valid")
        with pytest.raises(SystemExit, match="template draft"):
            draft(idea="x", paper_digest="d", library_context="",
                  lang="zh", n_sections=2)


def test_draft_prompt_contains_inputs():
    from llm.template_author import draft
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp(_CANNED_YAML)
        draft(idea="MY-IDEA", paper_digest="MY-DIGEST",
              library_context="MY-LIB", lang="en", n_sections=3)
        kwargs = MockLLM.return_value.chat.call_args.kwargs
    assert "MY-IDEA" in kwargs["user"]
    assert "MY-DIGEST" in kwargs["user"]
    assert "MY-LIB" in kwargs["user"]
    assert "3" in kwargs["system"]


def test_write_docx_roundtrips_through_s05(tmp_path: Path):
    from llm.template_author import write_docx
    from stages.s05_template.runner import parse_template

    sections = [
        {"title": "研究背景与动机",
         "questions": ["论文要解决的核心矛盾是什么?",
                       "- 3 个基线各自的缺陷是什么?"]},
        {"title": "方法核心",
         "questions": ["Fig. 1 的转换速度数值是多少?"]},
    ]
    out = tmp_path / "auto-test.docx"
    write_docx(sections, out, idea="迁移到双足")

    nodes = parse_template(out)
    assert len(nodes) == 2
    assert nodes[0]["title"] == "研究背景与动机"
    assert nodes[0]["level"] == 1 and nodes[0]["number"] == "1"
    # every question landed in guidance, none was promoted to a heading
    assert "核心矛盾" in nodes[0]["guidance"]
    assert "3 个基线" in nodes[0]["guidance"]
    assert "转换速度" in nodes[1]["guidance"]


def test_write_docx_adversarial_titles_still_roundtrip(tmp_path: Path):
    from llm.template_author import write_docx, _clean_title
    from stages.s05_template.runner import parse_template

    # titles that would trip s05's guidance heuristics if unsanitized
    sections = [
        {"title": _clean_title("2.1 Why does it work?"),
         "questions": ["Q one?"]},
        {"title": _clean_title("(draft) comparison"),
         "questions": ["Q two?"]},
    ]
    out = tmp_path / "adv.docx"
    write_docx(sections, out, idea="x")
    nodes = parse_template(out)
    assert len(nodes) == 2


def test_cli_template_from_run(tmp_path: Path, capsys, monkeypatch):
    import cli

    run = _make_run(tmp_path)
    out = tmp_path / "templates" / "auto-demo.docx"
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp(_CANNED_YAML)
        rc = cli.main(["template", "--idea", "迁移到双足",
                       "--run", "demo-paper",
                       "--runs-dir", str(tmp_path / "runs"),
                       "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert Path(str(out) + ".prompt.md").exists()
    assert Path(str(out) + ".response.json").exists()
    captured = capsys.readouterr().out
    assert "研究背景与能量正则化动机" in captured
    assert "--template" in captured  # next-step hint


def test_cli_template_use_library(tmp_path: Path, monkeypatch):
    import cli

    run = _make_run(tmp_path)
    seen = {}

    class FakeLib:
        def __init__(self, *a, **k): pass
        def papers(self):
            return {"other-paper": {"title": "Other Paper", "keywords": ["foo"]}}
        def query(self, idea, top_k=5):
            return [{"paper_id": "other-paper", "text": "relevant excerpt",
                     "doc_name": "d", "char_start": 0, "char_end": 10,
                     "score": 0.1, "gid": "other-paper::c0001"}]

    monkeypatch.setattr("llm.library.Library", FakeLib)
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp(_CANNED_YAML)
        rc = cli.main(["template", "--idea", "compare-me",
                       "--run", "demo-paper",
                       "--runs-dir", str(tmp_path / "runs"),
                       "--out", str(tmp_path / "t.docx"),
                       "--use-library"])
        seen["user"] = MockLLM.return_value.chat.call_args.kwargs["user"]
    assert rc == 0
    assert "Other Paper" in seen["user"]
    assert "relevant excerpt" in seen["user"]


def test_draft_retries_once_then_succeeds(tmp_path: Path):
    from llm.template_author import draft
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.side_effect = [
            _FakeResp("not: [valid"), _FakeResp(_CANNED_YAML)]
        sections, resp = draft(idea="x", paper_digest="d", library_context="",
                               lang="zh", n_sections=2)
    assert len(sections) == 2
    assert MockLLM.return_value.chat.call_count == 2
    second_user = MockLLM.return_value.chat.call_args.kwargs["user"]
    assert "valid YAML" in second_user


def test_draft_failure_writes_audit_sidecars(tmp_path: Path):
    from llm.template_author import draft
    base = tmp_path / "tpl" / "auto-x.docx"
    with patch("llm.template_author.LLM") as MockLLM:
        MockLLM.return_value.chat.return_value = _FakeResp("garbage: [")
        with pytest.raises(SystemExit, match="template draft"):
            draft(idea="x", paper_digest="d", library_context="",
                  lang="zh", n_sections=2, audit_base=base)
    assert Path(str(base) + ".response.json").exists()
    assert Path(str(base) + ".prompt.md").exists()
