from pathlib import Path

from stages._common import slugify, stage_dir


def test_slugify_basic_ascii():
    assert slugify("Hello World") == "Hello_World"


def test_slugify_strips_punctuation():
    assert slugify("foo: bar?!") == "foo_bar"


def test_slugify_preserves_cjk():
    assert slugify("引言 1") == "引言_1"


def test_slugify_truncates_to_maxlen():
    assert slugify("a" * 100, maxlen=10) == "a" * 10


def test_slugify_empty_input_returns_untitled():
    assert slugify("   ") == "untitled"


def test_stage_dir_creates_nested_dirs(tmp_path: Path):
    d = stage_dir(tmp_path, "paper1", "s01_ocr")
    assert d.exists() and d.is_dir()
    assert d == tmp_path / "paper1" / "s01_ocr"
