from pathlib import Path

from stages.s02_clean.runner import (
    strip_running_headers,
    repair_chars,
    flag_corrupted_column_flow,
    run,
)


def test_strip_running_headers_journal_line():
    docs = [
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 1.",
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 2.",
        "L. He et al. Acta Materialia 249(2023) 118826\nReal body line 3.",
    ]
    cleaned = strip_running_headers(docs, min_repeat=3)
    for c in cleaned:
        assert "Acta Materialia" not in c
        assert "Real body" in c


def test_strip_running_headers_keeps_unique_lines():
    docs = ["unique header\nbody A", "another\nbody B"]
    cleaned = strip_running_headers(docs, min_repeat=3)
    assert cleaned[0].startswith("unique header")


def test_repair_cid_minus():
    assert repair_chars("ranging between 0.1 to (cid:0) 10^{-4}") == \
        "ranging between 0.1 to − 10^{-4}"


def test_repair_subscripted_oxide_formula():
    assert repair_chars("AgNbO 3 ceramic") == "AgNbO₃ ceramic"
    assert repair_chars("page 3 of 8") == "page 3 of 8"


def test_repair_squashed_ag_plus():
    assert repair_chars("translation mode (Ag + )") == "translation mode (Ag⁺)"


def test_flag_obvious_interleave():
    bad = "outs A t l a t n h d o i u n g g h en t e h r e g y cl s a to ra g e p e r f or m a n c e"
    flagged = flag_corrupted_column_flow(bad)
    assert flagged.startswith("<!-- corrupted-column-flow -->")
    assert bad in flagged


def test_keep_normal_line():
    ok = "we found a high polarization change and low hysteresis"
    assert flag_corrupted_column_flow(ok) == ok


def test_run_clean_pipeline(tmp_path: Path):
    in_dir = tmp_path / "in"; in_dir.mkdir()
    out_dir = tmp_path / "out"
    (in_dir / "doc_0.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nAgNbO 3 sample.",
        encoding="utf-8",
    )
    (in_dir / "doc_1.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nSecond page.",
        encoding="utf-8",
    )
    (in_dir / "doc_2.md").write_text(
        "L. He et al. Acta Materialia 249(2023) 118826\nThird page.",
        encoding="utf-8",
    )
    run(in_dir=in_dir, out_dir=out_dir)
    out0 = (out_dir / "doc_0.md").read_text(encoding="utf-8")
    assert "Acta Materialia" not in out0
    assert "AgNbO₃" in out0
