"""Tests for reconcile_with_pdffigures2 — caption-anchored figure renumbering."""
from __future__ import annotations


def test_reconcile_renames_skipped_figure():
    """MinerU outputs Fig.1, Fig.2; pdffigures2 reports Fig.1, Fig.3 (gap at 2).
    Expected: our entry currently labeled 'Fig. 2' is RENAMED to 'Fig. 3'
    so downstream mentions.yaml aligns with the paper's actual numbering.
    """
    from stages.s04_figures.runner import reconcile_with_pdffigures2

    mineru_figs = [
        {"fig_id": "Fig. 1", "caption": "Schematic of synergistic optimization",
         "image_rel_path": "imgs/a.jpg"},
        {"fig_id": "Fig. 2", "caption": "P-E loops at various temperatures",
         "image_rel_path": "imgs/b.jpg"},
    ]
    pf2 = {
        "figures": [
            {"fig_id": "Fig. 1", "caption": "Schematic of the synergistic optimization strategy",
             "page": 0, "region": (0, 0, 0, 0)},
            {"fig_id": "Fig. 3", "caption": "P-E loops at various temperatures",
             "page": 4, "region": (0, 0, 0, 0)},
        ],
        "tables": [],
    }
    out, report = reconcile_with_pdffigures2(mineru_figs, pf2)
    assert out[0]["fig_id"] == "Fig. 1"
    assert out[1]["fig_id"] == "Fig. 3"
    assert any(r["from"] == "Fig. 2" and r["to"] == "Fig. 3" for r in report["renames"])


def test_reconcile_keeps_when_pdffigures2_disagrees():
    """If captions don't match, keep MinerU's numbering and log a 'keep' entry."""
    from stages.s04_figures.runner import reconcile_with_pdffigures2

    mineru_figs = [{"fig_id": "Fig. 1", "caption": "Total miss",
                    "image_rel_path": "x.jpg"}]
    pf2 = {
        "figures": [{"fig_id": "Fig. 5",
                     "caption": "Completely different content",
                     "page": 0, "region": (0, 0, 0, 0)}],
        "tables": [],
    }
    out, report = reconcile_with_pdffigures2(mineru_figs, pf2)
    assert out[0]["fig_id"] == "Fig. 1"
    assert any(r["fig_id"] == "Fig. 1" and r["reason"] == "no_caption_match"
               for r in report["keeps"])


def test_reconcile_handles_empty_pdffigures2():
    """If pdffigures2 returns no figures (e.g. parse error), MinerU output is unchanged."""
    from stages.s04_figures.runner import reconcile_with_pdffigures2

    mineru_figs = [{"fig_id": "Fig. 1", "caption": "x", "image_rel_path": "a.jpg"}]
    out, report = reconcile_with_pdffigures2(mineru_figs, {"figures": [], "tables": []})
    assert out == mineru_figs
    assert len(report["keeps"]) == 1
    assert len(report["renames"]) == 0
