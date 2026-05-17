"""Stage 04: figure & table index + chapter mention map."""
from __future__ import annotations

import re
import statistics
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from stages._common import BBOX_FROM_NAME, DOC_PAGE, bbox_from_filename, dump_yaml, mark_done, slugify

IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)
FIG_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*(Fig(?:ure)?\.?\s*\d+[A-Za-z]?)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
TAB_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*(Table\s*\d+)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
FIG_MENTION_RE = re.compile(r"Fig(?:ure)?\.?\s*(\d+)([a-z])?", re.IGNORECASE)


def _normalize_fig_id(raw: str) -> str:
    m = re.match(r"Fig(?:ure)?\.?\s*(\d+)([A-Za-z]?)", raw, re.IGNORECASE)
    if not m:
        return raw.strip()
    return f"Fig. {m.group(1)}{m.group(2).lower() if m.group(2) else ''}"


def _calibrate_scale(entries: list[dict]) -> tuple[float, float] | None:
    """From upscaled image dimensions vs bbox dimensions, compute paddle_coord → 300 DPI pixel scale.
    Returns None if no usable pairs."""
    rx, ry = [], []
    for e in entries:
        bbox = bbox_from_filename(e["image_rel_path"])
        if bbox is None:
            continue
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if bw < 5 or bh < 5:
            continue
        p = Path(e["image_abs_path"])
        if not p.exists():
            continue
        try:
            with Image.open(p) as im:
                iw, ih = im.size
        except Exception:
            continue
        if iw < 5 or ih < 5:
            continue
        rx.append(iw / bw)
        ry.append(ih / bh)
    if not rx or not ry:
        return None
    return statistics.median(rx), statistics.median(ry)


def _other_figs_y_extents_on_page(
    by_fig: dict[str, list[dict]],
    current_fid: str,
    page_idx: int,
) -> list[tuple[int, int]]:
    """Return [(y_min, y_max), ...] of all OTHER figures' bbox unions on the same page."""
    extents = []
    for fid, entries in by_fig.items():
        if fid == current_fid:
            continue
        same_page = [e for e in entries
                     if DOC_PAGE.search(e.get("source_doc", ""))
                     and int(DOC_PAGE.search(e["source_doc"]).group(1)) == page_idx]
        if not same_page:
            continue
        bboxes = [bbox_from_filename(e["image_rel_path"]) for e in same_page]
        bboxes = [b for b in bboxes if b is not None]
        if not bboxes:
            continue
        extents.append((min(b[1] for b in bboxes), max(b[3] for b in bboxes)))
    return extents


def _expand_to_neighbors(
    cur_bbox: tuple[int, int, int, int],
    same_page_other_extents: list[tuple[int, int]],
    *,
    gap_threshold: int = 200,
    safety_margin: int = 30,
    enabled: bool = False,
) -> tuple[int, int, int, int]:
    """DISABLED BY DEFAULT.

    The original design tried to expand a figure's y-range to fill suspicious
    whitespace gaps between adjacent figures on the same page, on the theory
    that PaddleOCR missed parts of the figure. In practice the "gap" is almost
    always paragraph body text that PaddleOCR correctly excluded — expanding
    into it just imports paragraph text into the figure crop. Kept as a knob
    (`enabled=True`) for future experiments but defaulted off.
    """
    if not enabled:
        return cur_bbox

    x1, y1, x2, y2 = cur_bbox
    if not same_page_other_extents:
        return cur_bbox  # No neighbors on this page → never expand

    cur_center_y = (y1 + y2) / 2
    above_y_max: int | None = None
    below_y_min: int | None = None
    for o_y_min, o_y_max in same_page_other_extents:
        o_center = (o_y_min + o_y_max) / 2
        if o_center < cur_center_y:
            if above_y_max is None or o_y_max > above_y_max:
                above_y_max = o_y_max
        elif o_center > cur_center_y:
            if below_y_min is None or o_y_min < below_y_min:
                below_y_min = o_y_min

    # Expand UP only if an above-neighbor exists and the gap is suspicious
    if above_y_max is not None and (y1 - above_y_max) > gap_threshold:
        midpoint = (above_y_max + y1) / 2
        y1 = int(midpoint + safety_margin)
    # Expand DOWN only if a below-neighbor exists and the gap is suspicious
    if below_y_min is not None and (below_y_min - y2) > gap_threshold:
        midpoint = (y2 + below_y_min) / 2
        y2 = int(midpoint - safety_margin)
    return (x1, y1, x2, y2)


def _merge_figure_subpanels(
    figures: list[dict],
    *,
    docs_dir: Path,
    pdf: Path,
    target_dpi: int = 300,
    margin_paddle_units: int = 0,  # default 0 to avoid bleed into adjacent text columns
    jpeg_quality: int = 92,
    min_sub_panels: int = 1,
) -> list[dict]:
    """Group sub-panel crops by fig_id; for groups with >=1 entry, render the union bbox
    from the PDF at target_dpi and replace the cluster with one merged entry.

    Scale is calibrated PER PAGE from existing post-upscale image dimensions:
    sx, sy = median(image_w / bbox_w, image_h / bbox_h) across all images on that page.
    """
    if not pdf.exists():
        return figures

    by_fig: dict[str, list[dict]] = {}
    others: list[dict] = []
    for f in figures:
        fid = f.get("fig_id", "")
        if fid.startswith("Fig.") and bbox_from_filename(f.get("image_rel_path", "")):
            by_fig.setdefault(fid, []).append(f)
        else:
            others.append(f)

    # Per-page calibration: scale derived from ALL images on the page (not just one fig's cluster)
    page_to_calibration: dict[int, tuple[float, float]] = {}
    pdf_doc = pdfium.PdfDocument(str(pdf))
    n_pages = len(pdf_doc)
    for entries in by_fig.values():
        for e in entries:
            m = DOC_PAGE.search(e["source_doc"])
            if not m:
                continue
            page_idx = int(m.group(1))
            if page_idx in page_to_calibration:
                continue
            page_entries = [
                x for x in figures
                if x.get("source_doc") == e["source_doc"]
                and bbox_from_filename(x.get("image_rel_path", "")) is not None
            ]
            cal = _calibrate_scale(page_entries)
            if cal is not None:
                page_to_calibration[page_idx] = cal

    merged_imgs_dir = docs_dir / "imgs"
    merged_imgs_dir.mkdir(exist_ok=True)
    out_figures: list[dict] = list(others)

    for fid, entries in by_fig.items():
        page_counts: dict[int, int] = {}
        for e in entries:
            m = DOC_PAGE.search(e["source_doc"])
            if m:
                pi = int(m.group(1))
                page_counts[pi] = page_counts.get(pi, 0) + 1
        if not page_counts:
            out_figures.extend(entries)
            continue
        page_idx = max(page_counts, key=page_counts.get)
        if page_idx >= n_pages:
            out_figures.extend(entries)
            continue
        cal = page_to_calibration.get(page_idx)
        if cal is None:
            out_figures.extend(entries)
            continue
        # Use UNIFORM scale (min of x/y ratios) to avoid non-uniform stretching that
        # bleeds into adjacent regions. PaddleOCR's coord system doesn't preserve PDF
        # aspect exactly, but using the smaller axis ratio gives a conservative crop
        # that stays within the figure's actual visible area.
        sx_per, sy_per = cal
        s_uniform = min(sx_per, sy_per)
        sx = sy = s_uniform

        bboxes = [bbox_from_filename(e["image_rel_path"]) for e in entries]
        bboxes = [b for b in bboxes if b is not None]
        if not bboxes:
            out_figures.extend(entries)
            continue
        # First compute the raw union with bbox margin
        ux1 = max(0, min(b[0] for b in bboxes) - margin_paddle_units)
        uy1 = max(0, min(b[1] for b in bboxes) - margin_paddle_units)
        ux2 = max(b[2] for b in bboxes) + margin_paddle_units
        uy2 = max(b[3] for b in bboxes) + margin_paddle_units

        # Gap-fill expansion: if there's significant whitespace between this figure
        # and its neighbors on the same page (>200 paddle units), it usually means
        # PaddleOCR missed the top or bottom of the figure. Expand to fill.
        other_extents = _other_figs_y_extents_on_page(by_fig, fid, page_idx)
        ux1, uy1, ux2, uy2 = _expand_to_neighbors(
            (ux1, uy1, ux2, uy2),
            other_extents,
            gap_threshold=200,
            safety_margin=30,
        )

        # Clamp y range to avoid bleeding into adjacent figures on the same page.
        # Use our figure's centroid to decide which side a neighbor is on, so that
        # a rogue bbox that already extends into a neighbor's territory still gets
        # correctly clamped (its own y_max is not a reliable boundary marker).
        cur_y_min, cur_y_max = min(b[1] for b in bboxes), max(b[3] for b in bboxes)
        cur_y_center = (cur_y_min + cur_y_max) / 2
        for o_y_min, o_y_max in other_extents:
            o_y_center = (o_y_min + o_y_max) / 2
            if o_y_center > cur_y_center:
                # Other figure is below current: clamp our bottom to just above it
                uy2 = min(uy2, o_y_min - 1)
            else:
                # Other figure is above current: clamp our top to just below it
                uy1 = max(uy1, o_y_max + 1)
        # Safety: ensure positive height
        if uy2 <= uy1:
            uy1, uy2 = min(b[1] for b in bboxes), max(b[3] for b in bboxes)

        page = pdf_doc[page_idx]
        bitmap = page.render(scale=target_dpi / 72.0).to_pil()
        rw, rh = bitmap.size

        nx1 = max(0, int(ux1 * sx))
        ny1 = max(0, int(uy1 * sy))
        nx2 = min(rw, int(ux2 * sx))
        ny2 = min(rh, int(uy2 * sy))
        if nx2 - nx1 < 32 or ny2 - ny1 < 32:
            out_figures.extend(entries)
            continue
        crop = bitmap.crop((nx1, ny1, nx2, ny2))
        if crop.mode not in ("RGB", "L"):
            crop = crop.convert("RGB")
        slug = slugify(fid, maxlen=30)
        merged_rel = f"imgs/{slug}_merged.jpg"
        merged_abs = merged_imgs_dir / f"{slug}_merged.jpg"
        crop.save(merged_abs, "JPEG", quality=jpeg_quality, optimize=True)
        captions = [e.get("caption", "") for e in entries]
        cleanest_caption = max(captions, key=len) if captions else ""
        source_doc = entries[0]["source_doc"]
        out_figures.append({
            "fig_id": fid,
            "image_rel_path": merged_rel,
            "image_abs_path": str(merged_abs.resolve()),
            "caption": cleanest_caption,
            "source_doc": source_doc,
            "merged_from": [e["image_rel_path"] for e in entries],
        })
    out_figures.sort(key=lambda f: (f.get("fig_id", "_zzz"), f.get("source_doc", "")))
    return out_figures


def run(*, docs_dir: Path, chapters_dir: Path, out_dir: Path,
        pdf: Path | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures: list[dict] = []
    tables: list[dict] = []
    for doc in sorted(docs_dir.glob("doc_*.md")):
        text = doc.read_text(encoding="utf-8")
        img_positions = [(m.start(), m.group(1)) for m in IMG_RE.finditer(text)]
        cap_positions = [
            (m.start(), _normalize_fig_id(m.group(1)), m.group(2).strip())
            for m in FIG_CAP_RE.finditer(text)
        ]
        # For each image, find the closest caption within PAIRING_WINDOW chars
        # (allow multiple images to share one caption — those are sub-panels)
        PAIRING_WINDOW = 1200
        for img_start, rel in img_positions:
            best_fid, best_cap, best_dist = None, "", PAIRING_WINDOW
            for cap_start, fid, cap in cap_positions:
                # Scholarly papers place the caption AFTER the figure. Require
                # cap_start > img_start so a figure's panels don't get stolen
                # by the previous figure's caption.
                if cap_start <= img_start:
                    continue
                dist = cap_start - img_start
                if dist < best_dist:
                    best_dist = dist
                    best_fid = fid
                    best_cap = cap
            figures.append({
                "fig_id": best_fid or f"_unmatched_{Path(rel).stem}",
                "image_rel_path": rel,
                "image_abs_path": str((docs_dir / rel).resolve()),
                "caption": best_cap,
                "source_doc": doc.name,
            })
        for m in TAB_CAP_RE.finditer(text):
            tables.append({"table_id": m.group(1).strip(), "caption": m.group(2).strip(),
                           "source_doc": doc.name})

    if pdf is not None and pdf.exists():
        figures = _merge_figure_subpanels(figures, docs_dir=docs_dir, pdf=pdf)

    mentions: dict[str, list[str]] = {}
    for ch in sorted(chapters_dir.glob("chapter_*.md")):
        ids = sorted({f"Fig. {m.group(1)}{(m.group(2) or '').lower()}"
                      for m in FIG_MENTION_RE.finditer(ch.read_text(encoding='utf-8'))})
        mentions[ch.name] = ids

    dump_yaml(out_dir / "figures.yaml", figures)
    dump_yaml(out_dir / "tables.yaml", tables)
    dump_yaml(out_dir / "mentions.yaml", mentions)
    mark_done(out_dir, {"figures": len(figures), "tables": len(tables)})
    return {"figures": len(figures), "tables": len(tables)}
