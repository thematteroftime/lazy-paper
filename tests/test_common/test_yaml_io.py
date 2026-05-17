from pathlib import Path

import pytest

from stages._common import load_yaml, dump_yaml, safe_parse_yaml


def test_dump_then_load_roundtrip(tmp_path: Path):
    target = tmp_path / "x.yaml"
    obj = {"name": "测试", "items": [1, 2, 3]}
    dump_yaml(target, obj)
    assert load_yaml(target) == obj


def test_dump_yaml_preserves_unicode(tmp_path: Path):
    target = tmp_path / "u.yaml"
    dump_yaml(target, {"k": "中文"})
    text = target.read_text(encoding="utf-8")
    assert "中文" in text  # not escaped to \uXXXX


def test_safe_parse_valid():
    assert safe_parse_yaml("a: 1\nb: 2") == {"a": 1, "b": 2}


def test_safe_parse_empty():
    assert safe_parse_yaml("") is None
    assert safe_parse_yaml("   ") is None


def test_safe_parse_flow_sequence_with_question_mark():
    """[What is X?] is invalid YAML flow context; safe parser should quote it."""
    text = "items: [What is X?, Yes or No?]"
    result = safe_parse_yaml(text)
    assert result == {"items": ["What is X?", "Yes or No?"]}


def test_safe_parse_unrecoverable():
    bad = ": : : foo\nbar\n  baz: : :"
    assert safe_parse_yaml(bad) is None


def test_safe_parse_scalar_with_inner_colon():
    text = (
        "visual_summary: Panels show a strong inverse correlation: "
        "Eb increases from 12 to 41 kV/mm\nfig_id: Fig. 3"
    )
    result = safe_parse_yaml(text)
    assert result is not None
    assert result["fig_id"] == "Fig. 3"
    assert "inverse correlation" in result["visual_summary"]


def test_safe_parse_real_qwen_failure_excerpt():
    text = (
        "fig_id: Fig. 3\n"
        "visual_summary: Panels (a-d) show micrographs, revealing a strong correlation: Eb increases\n"
        "text_claim_check:\n"
        "  - claim: trivial\n"
        "    verdict: supported\n"
        "    note: ok\n"
        "caption: Test caption\n"
    )
    result = safe_parse_yaml(text)
    assert result is not None
    assert "correlation" in result["visual_summary"]
    assert result["caption"] == "Test caption"
