from stages.s08_section_compose._units import normalize, equal


def test_kvcm_canonical():
    assert normalize("340 kV/cm") == (340.0, "kV/cm")


def test_mvcm_to_kvcm():
    assert normalize("4 MV/cm") == (4000.0, "kV/cm")


def test_jcm3_canonical():
    assert normalize("8.6 J/cm3") == (8.6, "J/cm3")
    assert normalize("8.6 J/cm³") == (8.6, "J/cm3")


def test_equal_within_tolerance():
    assert equal("4 MV/cm", "4000 kV/cm")
    assert equal("340 kV/cm", "0.34 MV/cm")
    assert not equal("4 MV/cm", "5000 kV/cm")


def test_percent_normalize():
    assert normalize("85%") == (85.0, "%")
    assert normalize("0.85") == (0.85, "")


def test_unparseable_returns_none():
    assert normalize("blah") is None
