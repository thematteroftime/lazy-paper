from pathlib import Path

import yaml

from stages.s03_chapter.runner import run, detect_science_anchor


def test_detect_anchor_named_section():
    assert detect_science_anchor("References") == "References"
    assert detect_science_anchor("## Introduction") == "Introduction"
    assert detect_science_anchor("Random body text that doesn't anchor") is None


def test_detect_anchor_numbered_subsection():
    assert detect_science_anchor("2.1. Sample preparation").startswith("2.1")


def test_run_splits_imrad(tmp_path: Path):
    in_dir = tmp_path / "in"; in_dir.mkdir()
    (in_dir / "doc_0.md").write_text(
        "## Abstract\nWe report...\n\n"
        "1. Introduction\nIntro body.\n\n"
        "2. Experimental\nMethod body.\n\n"
        "3. Results and discussion\nResults body.\n\n"
        "4. Conclusion\nConcl body.\n\n"
        "References\n[1] foo.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    summary = run(in_dir=in_dir, out_dir=out_dir, min_chars=1)
    idx = yaml.safe_load((out_dir / "chapter_index.yaml").read_text(encoding="utf-8"))
    titles = [c["title"] for c in idx]
    assert any("Introduction" in t for t in titles)
    assert any("Experimental" in t for t in titles)
    assert any("Results" in t for t in titles)
    assert any("Conclusion" in t for t in titles)
    assert any("References" in t for t in titles)
    assert summary["count"] == len(titles)
