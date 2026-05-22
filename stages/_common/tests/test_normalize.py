"""Tests for normalize_ocr_latex — substring/fuzzy match preparation."""
from stages._common.normalize import normalize_ocr_latex


def test_latex_command_strip():
    assert normalize_ocr_latex(r"$W _ { \mathrm { rec } }$").replace(" ", "") == "w_rec"


def test_ocr_digit_space_fold():
    assert "5.00" in normalize_ocr_latex("5 . 0 0 j/cm")


def test_lowercase_default():
    assert normalize_ocr_latex("WdIs") == "wdis"


def test_lowercase_off():
    assert normalize_ocr_latex("WdIs", lowercase=False) == "WdIs"


# v1.10 BS3: LaTeX escape sequences (`\%`, `\&`, `\_`, `\^`)
def test_bs3_percent_escape():
    """`\\%` → `%` so the LLM's `91.04%` matches the source's `91.04\\%`."""
    assert normalize_ocr_latex(r"eta = 91.04\%") == "eta = 91.04%"


def test_bs3_other_escapes():
    """`\\&`, `\\_`, `\\$` all lose their leading backslash."""
    assert normalize_ocr_latex(r"A \& B") == "a & b"
    assert normalize_ocr_latex(r"W\_rec") == "w_rec"
    # `$` is a LaTeX math delimiter — also stripped by _LATEX_DELIM. So
    # both `\$5` and `$5` collapse to `5`. This is intentional: math
    # delimiters carry no semantic content for substring match.
    assert normalize_ocr_latex(r"\$5") == "5"


# v1.10 BS4: Unicode super/subscripts (NFKD)
def test_bs4_unicode_superscript():
    """`J/cm³` → `J/cm3` so the LLM's plain-ASCII quote matches OCR."""
    assert "2.94 j/cm3" in normalize_ocr_latex("2.94 J/cm³")


def test_bs4_unicode_subscript():
    assert "tio2" in normalize_ocr_latex("TiO₂")
    assert "h2o" in normalize_ocr_latex("H₂O")


def test_bs4_unicode_mixed():
    """Multi unit with mixed scripts."""
    assert "1.5 m s-1" in normalize_ocr_latex("1.5 m s⁻¹")


def test_bs4_greek_preserved():
    """NFKD must NOT touch Greek letters (α/β/π are not decomposable)."""
    out = normalize_ocr_latex("α-phase β-phase π=3.14")
    assert "α" in out
    assert "β" in out
    assert "π" in out


def test_bs3_bs4_combined():
    """Combined real-world example from corpus papers."""
    src = r"$W _ { \mathrm { rec } } = 2.94$ J/cm³, $\eta = 91.04\%$"
    out = normalize_ocr_latex(src)
    # both anchors recoverable
    assert "2.94" in out
    assert "j/cm3" in out
    assert "91.04%" in out
