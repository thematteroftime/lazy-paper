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
    dump_yaml(run / "s03_chapter" / "chapter_index.yaml",
              {"chapters": [{"num": 0, "slug": "intro", "title": "INTRODUCTION"},
                            {"num": 1, "slug": "method", "title": "ENERGY REGULARIZATION"}]})
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
