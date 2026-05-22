"""Tests for variant-test metrics collector."""
from pathlib import Path
import yaml
import pytest

from scripts.collect_variant_metrics import (
    collect_chars_per_section,
    collect_figure_embed_ratio,
    parse_coverage_from_log,
    count_retry_fires,
    collect_run_metrics,
)


def test_collect_chars_per_section(tmp_path):
    chapters = tmp_path / "s08_section_compose" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "01_intro.md").write_text("a" * 1500, encoding="utf-8")
    (chapters / "02_methods.md").write_text("b" * 800, encoding="utf-8")
    result = collect_chars_per_section(tmp_path)
    assert result == {"01_intro": 1500, "02_methods": 800}


def test_collect_figure_embed_ratio(tmp_path):
    s09 = tmp_path / "s09_render"
    s09.mkdir(parents=True)
    (s09 / "preview.html").write_text(
        "<p><img src='a'><img src='b'></p>", encoding="utf-8"
    )
    s07 = tmp_path / "s07_figure_analyze"
    s07.mkdir(parents=True)
    (s07 / "fig_notes.yaml").write_text(
        yaml.safe_dump([
            {"fig_id": "Fig. 1"},
            {"fig_id": "Fig. 2"},
            {"fig_id": "Fig. 3"},
            {"fig_id": "Fig. 4"},
        ]),
        encoding="utf-8",
    )
    embedded, available, ratio = collect_figure_embed_ratio(tmp_path)
    assert embedded == 2
    assert available == 4
    assert ratio == 0.5


def test_parse_coverage_from_log():
    log = (
        "[s08] structured-compose: required=12 "
        "pre-verify-missing=5 (58%) post-verify-missing=3 (75%)\n"
        "[s08] structured-compose: required=8 "
        "pre-verify-missing=2 (75%) post-verify-missing=1 (88%)\n"
    )
    result = parse_coverage_from_log(log)
    assert result == [
        {"required": 12, "pre_missing": 5, "post_missing": 3},
        {"required": 8, "pre_missing": 2, "post_missing": 1},
    ]


def test_count_retry_fires():
    log = (
        "[s08] retry-when-empty: lifted post-verify coverage from 2/5 to 4/5\n"
        "[s08] retry-when-empty: lifted post-verify coverage from 1/3 to 2/3\n"
        "[s08] retry-when-short: lifted 3->5 claims, 600->1200 chars\n"
    )
    assert count_retry_fires(log, "retry-when-empty") == 2
    assert count_retry_fires(log, "retry-when-short") == 1
