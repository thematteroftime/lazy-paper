import time
from pathlib import Path

import yaml

from stages._common import mark_done, is_done


def test_is_done_false_when_marker_missing(tmp_path: Path):
    assert is_done(tmp_path) is False


def test_mark_done_creates_yaml_with_timestamp(tmp_path: Path):
    before = time.time()
    mark_done(tmp_path)
    after = time.time()
    payload = yaml.safe_load((tmp_path / "done.yaml").read_text(encoding="utf-8"))
    assert isinstance(payload["finished_at"], float)
    assert before <= payload["finished_at"] <= after


def test_mark_done_merges_extra_keys(tmp_path: Path):
    mark_done(tmp_path, {"files": 3, "bytes": 1024})
    payload = yaml.safe_load((tmp_path / "done.yaml").read_text(encoding="utf-8"))
    assert payload["files"] == 3
    assert payload["bytes"] == 1024
    assert "finished_at" in payload


def test_is_done_true_after_mark(tmp_path: Path):
    assert is_done(tmp_path) is False
    mark_done(tmp_path)
    assert is_done(tmp_path) is True
