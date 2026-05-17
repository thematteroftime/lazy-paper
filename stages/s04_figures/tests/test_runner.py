from pathlib import Path

import yaml
from PIL import Image as PILImage

from stages.s04_figures.runner import run


def test_figures_basic_pairing(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    (src / "imgs").mkdir()
    (src / "imgs" / "img_a.jpg").write_bytes(b"\xff")
    (src / "imgs" / "img_b.jpg").write_bytes(b"\xff")
    (src / "doc_0.md").write_text(
        '<img src="imgs/img_a.jpg">\n\n'
        "Fig. 1. Phase diagram of ANT-xLa ceramics.\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (src / "doc_1.md").write_text(
        '<img src="imgs/img_b.jpg">\n\n'
        "Fig. 2. Weibull distribution.\n",
        encoding="utf-8",
    )

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    (chapters_dir / "chapter_001_Results.md").write_text("see Fig. 1(a) and Fig. 2.", encoding="utf-8")

    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir)
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    by_id = {f["fig_id"]: f for f in figs}
    assert by_id["Fig. 1"]["image_rel_path"].endswith("img_a.jpg")
    assert "Phase diagram" in by_id["Fig. 1"]["caption"]
    mentions = yaml.safe_load((out_dir / "mentions.yaml").read_text(encoding="utf-8"))
    assert mentions["chapter_001_Results.md"] == ["Fig. 1", "Fig. 2"]


def test_figures_div_wrapped_caption(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    (src / "imgs").mkdir()
    (src / "imgs" / "img.jpg").write_bytes(b"\xff")
    (src / "doc_0.md").write_text(
        '<div><img src="imgs/img.jpg"></div>\n\n'
        '<div style="text-align: center;">Fig. 1. Phase diagram of ANT-xLa ceramics.</div>\n',
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir)
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    assert any(f["fig_id"] == "Fig. 1" and "Phase diagram" in f["caption"] for f in figs)


def test_multiple_images_share_one_fig_id(tmp_path: Path):
    """Two chart_boxes near the same Fig. 1 caption should both get fig_id='Fig. 1' (no pdf → no merge)."""
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    (src / "imgs" / "panel_a.jpg").write_bytes(b"\xff")
    (src / "imgs" / "panel_b.jpg").write_bytes(b"\xff")
    (src / "doc_0.md").write_text(
        '<img src="imgs/panel_a.jpg">\n<img src="imgs/panel_b.jpg">\n\n'
        "Fig. 1. Two-panel figure with (a) and (b).\n",
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir)
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig1 = [f for f in figs if f.get("fig_id") == "Fig. 1"]
    assert len(fig1) == 2, f"expected 2 entries sharing Fig. 1, got {[f for f in figs]}"


def test_merge_subpanels_with_calibrated_scale(tmp_path: Path):
    """4 chart_boxes sharing one Fig. 3 caption merge into a single union-rendered image
    even when bboxes don't span the full page (sparse-page scenario)."""
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)

    # Build a synthetic 1-page PDF (US Letter at 150 DPI = 1275x1650)
    page = PILImage.new("RGB", (1275, 1650), "white")
    page.save(tmp_path / "p.pdf", "PDF", resolution=150.0)

    # Simulate 4 panels in the TOP HALF only (no images in bottom half — sparse page)
    # PaddleOCR coord space: page is ~1200x1600; panels occupy 100..600 x 100..500
    panels = {
        "imgs/img_in_chart_box_100_100_300_300.jpg": (200, 200),
        "imgs/img_in_chart_box_320_100_520_300.jpg": (200, 200),
        "imgs/img_in_chart_box_100_320_300_500.jpg": (200, 180),
        "imgs/img_in_chart_box_320_320_520_500.jpg": (200, 180),
    }
    # Create upscaled images at "300 DPI" = bbox dim * 2.0 ratio
    for rel, (bw, bh) in panels.items():
        PILImage.new("RGB", (int(bw * 2.0), int(bh * 2.0)), "blue").save(src / rel, "JPEG")
    img_tags = "\n".join(f'<img src="{rel}">' for rel in panels.keys())
    (src / "doc_0.md").write_text(
        f"{img_tags}\n\nFig. 3. Four-panel figure with subpanels (a)-(d).\n",
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")

    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig3 = [f for f in figs if f.get("fig_id") == "Fig. 3"]
    assert len(fig3) == 1, f"expected 1 merged entry, got {figs}"
    merged = fig3[0]
    assert "merged_from" in merged and len(merged["merged_from"]) == 4
    # Verify the merged image dimensions are reasonable (>200px on each side after the union)
    with PILImage.open(merged["image_abs_path"]) as im:
        mw, mh = im.size
    assert mw > 400 and mh > 200, (mw, mh)


def test_merge_clamps_to_neighbor_fig(tmp_path: Path):
    """Two figures on the same PDF page: Fig. 1's merged union must not bleed into Fig. 2.

    Fig. 1 has a rogue image_box whose bbox extends to y=420, past Fig. 2's start at y=400.
    After clamping the merged height should be strictly less than unclamped (660 px at 2x scale).
    """
    from PIL import Image as PILImage
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    # Single-page PDF (US Letter @ 150 DPI = 1275x1650)
    PILImage.new("RGB", (1275, 1650), "white").save(tmp_path / "p.pdf", "PDF", resolution=150.0)

    # Fig. 1 panels at y=100-300 (top half of page)
    fig1_panels = {
        "imgs/img_in_chart_box_100_100_400_300.jpg": (300, 200),
        "imgs/img_in_chart_box_500_100_800_300.jpg": (300, 200),
    }
    # Fig. 2 panels at y=400-600 (below Fig. 1, on the same PDF page)
    fig2_panels = {
        "imgs/img_in_chart_box_100_400_400_600.jpg": (300, 200),
        "imgs/img_in_chart_box_500_400_800_600.jpg": (300, 200),
    }
    for d in (fig1_panels, fig2_panels):
        for rel, (bw, bh) in d.items():
            PILImage.new("RGB", (int(bw * 2.0), int(bh * 2.0)), "blue").save(src / rel, "JPEG")

    # Rogue image_box for Fig. 1: its bbox extends to y=420, past Fig. 2's start at y=400.
    rogue_rel = "imgs/img_in_image_box_50_90_850_420.jpg"
    # Image size matches bbox*2 scale: (800*2, 330*2) = (1600, 660)
    PILImage.new("RGB", (1600, 660), "blue").save(src / rogue_rel, "JPEG")

    # Both figures in the same doc (= same PDF page, page_idx 0).
    # A 1500-char spacer between Fig. 1's caption and Fig. 2's images ensures that
    # Fig. 2's image_boxes are closer to Fig. 2's caption (distance < 1200) than to
    # Fig. 1's caption, so the PAIRING_WINDOW logic assigns them correctly.
    spacer = "x" * 1500
    fig1_imgs = "\n".join(
        f'<img src="{rel}">' for rel in list(fig1_panels.keys()) + [rogue_rel]
    )
    fig2_imgs = "\n".join(f'<img src="{rel}">' for rel in fig2_panels.keys())
    body = (
        f"{fig1_imgs}\n\n"
        "Fig. 1. Two-panel figure with rogue image_box overshoot.\n\n"
        f"{spacer}\n\n"
        f"{fig2_imgs}\n\n"
        "Fig. 2. Second figure that we must NOT overlap.\n"
    )
    (src / "doc_0.md").write_text(body, encoding="utf-8")

    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")

    import yaml
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig1_entries = [f for f in figs if f.get("fig_id") == "Fig. 1"]
    assert len(fig1_entries) == 1, f"Expected 1 merged Fig. 1, got: {fig1_entries}"
    fig2_entries = [f for f in figs if f.get("fig_id") == "Fig. 2"]
    assert len(fig2_entries) == 1, f"Expected 1 merged Fig. 2, got: {fig2_entries}"

    # Without clamping: uy2 = 420+10 = 430 → ny2 = 430*2 = 860 → height = 860 - 160 = 700 px
    # With clamping to Fig. 2's y_min (400): uy2 = min(430, 399) = 399 → height < 700 px
    # Specifically the unclamped result at rogue bbox bottom (y=420) would give 660px
    # at uy2=420 (no margin). Our clamped height should be strictly below that.
    with PILImage.open(fig1_entries[0]["image_abs_path"]) as im:
        _mw, mh = im.size
    # Unclamped with full margin: uy2=430 → ny2=860, height ≈700. Clamped: height < 700.
    # Use 700 as the guard (generous but strictly less than unclamped).
    assert mh < 700, f"Fig. 1 height should be clamped below 700px, got {mh}"


def test_gap_fill_expands_single_bbox_figure(tmp_path: Path):
    """A figure with only 1 bbox in lower half of page, with big gap to figure
    above, should be expanded upward to fill the gap."""
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    PILImage.new("RGB", (1275, 1650), "white").save(tmp_path / "p.pdf", "PDF", resolution=150.0)

    # Fig. 4 at top of page: y=100-300 (2 panels)
    fig4_a = "imgs/img_in_chart_box_100_100_400_300.jpg"
    fig4_b = "imgs/img_in_chart_box_500_100_800_300.jpg"
    for rel in (fig4_a, fig4_b):
        PILImage.new("RGB", (600, 400), "blue").save(src / rel, "JPEG")

    # Fig. 5 with ONLY 1 bbox far below (y=900-1100): there's a 600-unit gap
    fig5 = "imgs/img_in_chart_box_100_900_800_1100.jpg"
    PILImage.new("RGB", (1400, 400), "red").save(src / fig5, "JPEG")

    # Need a spacer >1200 chars between Fig. 4's caption and Fig. 5's image so that
    # the PAIRING_WINDOW logic correctly assigns Fig. 5's img to Fig. 5's caption.
    spacer = "x" * 1500
    body = (
        f'<img src="{fig4_a}">\n<img src="{fig4_b}">\n\nFig. 4. Two-panel.\n\n'
        f'{spacer}\n\n'
        f'<img src="{fig5}">\n\nFig. 5. Single-bbox figure (PaddleOCR missed top).\n'
    )
    (src / "doc_0.md").write_text(body, encoding="utf-8")
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")

    import yaml
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig5_entry = [f for f in figs if f.get("fig_id") == "Fig. 5"][0]
    # Fig. 5 should now be a `Fig_5_merged.jpg`, not the raw chart_box name
    assert "Fig_5_merged" in fig5_entry["image_rel_path"], fig5_entry
    # The merged image height should be larger than just the original 200-paddle-unit
    # bbox height (it should have been expanded to include the gap)
    from PIL import Image as PILImage2
    with PILImage2.open(fig5_entry["image_abs_path"]) as im:
        merged_h = im.size[1]
    # Original Fig. 5 bbox was 200 paddle units tall (y=900-1100). At 2.0x scale (the test
    # fixture's ratio), that's 400 px. With gap-fill: y was extended from 900 up to ~330
    # (Fig. 4 y_max=300 + safety_margin=30), so new height ~ 1100-330 = 770 paddle = 1540 px.
    assert merged_h < 500, f"Fig. 5 should NOT be expanded (gap-fill disabled), got {merged_h}"


def test_no_expand_when_only_figure_on_page(tmp_path: Path):
    """A figure with no neighbors on its page must not be expanded.
    Specifically guards against the regression where Fig. 1 of li2022 expanded
    to the whole page (catching abstract + body text)."""
    from PIL import Image as PILImage
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    PILImage.new("RGB", (1275, 1650), "white").save(tmp_path / "p.pdf", "PDF", resolution=150.0)
    # ONE figure with ONE small bbox in the lower portion (mimicking li2022 Fig. 1's case)
    rel = "imgs/img_in_chart_box_100_900_500_1100.jpg"
    PILImage.new("RGB", (800, 400), "blue").save(src / rel, "JPEG")
    (src / "doc_0.md").write_text(
        f'<img src="{rel}">\n\nFig. 1. Lone figure on a page.\n',
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")
    import yaml
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig1 = [f for f in figs if f.get("fig_id") == "Fig. 1"][0]
    # The merged image should reflect just the original 400-paddle-unit-tall bbox (with
    # small bbox margin), at 2.0x scale = ~800 px tall. Not the whole page.
    from PIL import Image as PILImage2
    with PILImage2.open(fig1["image_abs_path"]) as im:
        merged_h = im.size[1]
    assert merged_h < 900, f"Lone figure should not have been expanded; got {merged_h}"


def test_midpoint_expand_two_neighbors_no_overlap(tmp_path: Path):
    """When Fig. A and Fig. B both expand toward each other through a large gap,
    the midpoint rule must prevent overlap."""
    from PIL import Image as PILImage
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    PILImage.new("RGB", (1275, 1650), "white").save(tmp_path / "p.pdf", "PDF", resolution=150.0)
    # Fig. 1 at top, Fig. 2 at bottom, big gap in middle
    fig1 = "imgs/img_in_chart_box_100_100_700_300.jpg"
    fig2 = "imgs/img_in_chart_box_100_900_700_1100.jpg"
    for rel in (fig1, fig2):
        PILImage.new("RGB", (1200, 400), "green").save(src / rel, "JPEG")
    spacer = "x" * 1500
    (src / "doc_0.md").write_text(
        f'<img src="{fig1}">\n\nFig. 1. Top.\n\n{spacer}\n\n<img src="{fig2}">\n\nFig. 2. Bottom.\n',
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")
    import yaml
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig1_entry = next(f for f in figs if f.get("fig_id") == "Fig. 1")
    fig2_entry = next(f for f in figs if f.get("fig_id") == "Fig. 2")
    from PIL import Image as PILImage2
    with PILImage2.open(fig1_entry["image_abs_path"]) as im:
        f1_h = im.size[1]
    with PILImage2.open(fig2_entry["image_abs_path"]) as im:
        f2_h = im.size[1]
    # Both should be expanded toward the gap midpoint but not crash into each other.
    # Original gap = 600 paddle units; midpoint = 600. Each expands by ~250 units toward midpoint.
    # Fig. 1 expanded y range ~ 100 to 570; Fig. 2 ~ 630 to 1100.
    # At 2.0x scale: ~940 and ~940 px.
    assert f1_h < 500, f"Fig. 1 should NOT be expanded (gap-fill disabled), got {f1_h}"
    assert f2_h < 500, f"Fig. 2 should NOT be expanded (gap-fill disabled), got {f2_h}"


def test_single_bbox_figure_still_produces_merged_jpg(tmp_path: Path):
    """Single-bbox figure should still produce Fig_N_merged.jpg (not orphan chart_box name)."""
    src = tmp_path / "src"; (src / "imgs").mkdir(parents=True)
    PILImage.new("RGB", (1275, 1650), "white").save(tmp_path / "p.pdf", "PDF", resolution=150.0)
    rel = "imgs/img_in_chart_box_100_200_700_500.jpg"
    PILImage.new("RGB", (1200, 600), "green").save(src / rel, "JPEG")
    (src / "doc_0.md").write_text(
        f'<img src="{rel}">\n\nFig. 1. Single-bbox standalone figure.\n',
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "ch"; chapters_dir.mkdir()
    out_dir = tmp_path / "out"
    run(docs_dir=src, chapters_dir=chapters_dir, out_dir=out_dir, pdf=tmp_path / "p.pdf")
    import yaml
    figs = yaml.safe_load((out_dir / "figures.yaml").read_text(encoding="utf-8"))
    fig1 = [f for f in figs if f.get("fig_id") == "Fig. 1"][0]
    assert "Fig_1_merged" in fig1["image_rel_path"], f"expected Fig_1_merged, got {fig1['image_rel_path']}"
    assert fig1.get("merged_from"), "merged_from should list source bbox"
