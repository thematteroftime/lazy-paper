"""Unit tests for the pdffigures2 sidecar parser. Subprocess is mocked."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


SAMPLE_OUTPUT = [
    {"name": "1", "page": 0, "caption": "Schematic of the synergistic optimization strategy.",
     "regionBoundary": {"x1": 100, "y1": 100, "x2": 500, "y2": 400}, "figType": "Figure"},
    {"name": "2", "page": 2, "caption": "P-E loops at various temperatures.",
     "regionBoundary": {"x1": 80, "y1": 200, "x2": 520, "y2": 600}, "figType": "Figure"},
    {"name": "1", "page": 5, "caption": "Lattice parameters from XRD refinement.",
     "regionBoundary": {"x1": 60, "y1": 300, "x2": 540, "y2": 500}, "figType": "Table"},
]


def test_parse_figures_only():
    from scripts.pdffigures2_sidecar import parse_pdffigures2_output
    parsed = parse_pdffigures2_output(SAMPLE_OUTPUT)
    assert len(parsed["figures"]) == 2
    assert parsed["figures"][0]["fig_id"] == "Fig. 1"
    assert parsed["figures"][1]["fig_id"] == "Fig. 2"
    assert len(parsed["tables"]) == 1
    assert parsed["tables"][0]["table_id"] == "Table 1"


def test_canonical_caption_strip():
    """The 'Figure 3.' prefix in the raw caption should be stripped from the parsed caption."""
    from scripts.pdffigures2_sidecar import parse_pdffigures2_output
    parsed = parse_pdffigures2_output([
        {"name": "3", "page": 0, "caption": "Figure 3. P-E loops.", "figType": "Figure",
         "regionBoundary": {"x1": 0, "y1": 0, "x2": 0, "y2": 0}},
    ])
    assert parsed["figures"][0]["caption"] == "P-E loops."
    # Raw is preserved so downstream auditing can still see the original.
    assert parsed["figures"][0]["caption_raw"] == "Figure 3. P-E loops."


def test_run_sidecar_subprocess_returns_dict():
    from scripts.pdffigures2_sidecar import run_sidecar
    fake_json = json.dumps(SAMPLE_OUTPUT)
    with patch("scripts.pdffigures2_sidecar._invoke_jar", return_value=fake_json):
        result = run_sidecar(Path("/fake.pdf"))
    assert "figures" in result and len(result["figures"]) == 2
    assert "tables" in result and len(result["tables"]) == 1


def test_run_sidecar_propagates_unavailable():
    """When _invoke_jar raises SidecarUnavailable, run_sidecar lets it through so
    callers (cli.py) decide whether to warn or abort."""
    from scripts.pdffigures2_sidecar import run_sidecar, SidecarUnavailable
    with patch("scripts.pdffigures2_sidecar._invoke_jar",
               side_effect=SidecarUnavailable("docker not available")):
        with pytest.raises(SidecarUnavailable):
            run_sidecar(Path("/fake.pdf"))
