"""Stage 01: PDF -> PaddleOCR-VL -> doc_*.md + imgs/."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pypdfium2 as pdfium
import requests
from PIL import Image

from stages._common import DOC_PAGE, bbox_from_filename, mark_done
from stages.s01_ocr import mineru as _mineru

_IMG_TAG = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)

API = os.environ.get(
    "PADDLEOCR_BASE_URL", "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
)
MODEL = os.environ.get("PADDLEOCR_MODEL", "PaddleOCR-VL-1.5")
OPT = {k: False for k in ("useDocOrientationClassify", "useDocUnwarping", "useChartRecognition")}
_PADDLEOCR_TIMEOUT_S = int(os.environ.get("PADDLEOCR_TIMEOUT_S", "1800"))
_PADDLEOCR_POLL_S = int(os.environ.get("PADDLEOCR_POLL_S", "5"))


def upscale_images(*, pdf: Path, ocr_dir: Path, target_dpi: int = 300,
                   min_scale_factor: float = 1.5,
                   max_aspect_skew: float = 0.20,
                   jpeg_quality: int = 92) -> dict:
    """Re-render images at high DPI from the PDF.

    For each ``doc_N.md`` in *ocr_dir*, finds ``<img>`` tags whose filename
    encodes a bbox as ``…_X1_Y1_X2_Y2.jpg``, renders the corresponding PDF
    page at *target_dpi* via pypdfium2, maps the bbox into the rendered pixel
    space, crops, and overwrites the file.

    Coordinate mapping
    ------------------
    PaddleOCR outputs bbox coordinates in its own pixel space, which varies
    per page (it rescales each page to an internal DPI that differs from the
    PDF's native 72 pt/in).  We recover the page-level mapping by reading the
    existing image files: for images where PaddleOCR has upscaled the crop
    (existing_pixels / bbox_width > 1), we infer ``paddle_page_w`` as
    ``rendered_width / existing_scale_x``.  For pages where all images are at
    native scale (existing_scale ≈ 1), we fall back to the PDF page's natural
    point dimensions together with a ``paddle_dpi`` estimated from
    well-covered pages in the same document.

    Skips an image if the inferred improvement ratio is below
    *min_scale_factor*, or if the existing image has non-uniform scaling
    (x/y discrepancy > *max_aspect_skew*).

    Returns ``{"upscaled": N, "skipped": M, "pages": K}``.
    """
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    pdf_doc = pdfium.PdfDocument(str(pdf))
    n_pages = len(pdf_doc)

    # Collect (rel_path, bbox) per page index.
    page_to_items: dict[int, list[tuple[str, tuple[int, int, int, int]]]] = {}
    for doc_md in sorted(ocr_dir.glob("doc_*.md")):
        m = DOC_PAGE.search(doc_md.name)
        if not m:
            continue
        page_idx = int(m.group(1))
        if page_idx >= n_pages:
            continue
        text = doc_md.read_text(encoding="utf-8")
        for im in _IMG_TAG.finditer(text):
            rel = im.group(1)
            bbox = bbox_from_filename(rel)
            if bbox is None:
                continue
            page_to_items.setdefault(page_idx, []).append((rel, bbox))

    # --- Pass 1: for each page, infer paddle_page_w/h from existing images ---
    # paddle_page_w = rendered_w / ex_sx  for images where ex_sx > 1.
    # Collect these estimates and also a cross-page fallback.
    page_paddle_w: dict[int, float] = {}
    page_paddle_h: dict[int, float] = {}
    all_paddle_dpi_x: list[float] = []
    all_paddle_dpi_h: list[float] = []

    for page_idx, items in page_to_items.items():
        page = pdf_doc[page_idx]
        pts_w = page.get_width()
        pts_h = page.get_height()
        scale = target_dpi / 72.0
        rendered_w = round(pts_w * scale)
        rendered_h = round(pts_h * scale)

        sx_estimates: list[float] = []
        sy_estimates: list[float] = []
        for rel, (x1, y1, x2, y2) in items:
            bbox_w = x2 - x1
            bbox_h = y2 - y1
            if bbox_w <= 0 or bbox_h <= 0:
                continue
            existing_path = ocr_dir / rel
            try:
                with Image.open(existing_path) as ex_img:
                    ex_w, ex_h = ex_img.size
            except Exception:
                continue
            ex_sx = ex_w / bbox_w
            ex_sy = ex_h / bbox_h
            # Only trust images that PaddleOCR actually upscaled (ex_sx > 1.1)
            if ex_sx > 1.1:
                sx_estimates.append(rendered_w / ex_sx)
            if ex_sy > 1.1:
                sy_estimates.append(rendered_h / ex_sy)

        if sx_estimates:
            ppw = sum(sx_estimates) / len(sx_estimates)
            page_paddle_w[page_idx] = ppw
            all_paddle_dpi_x.append(ppw * 72.0 / pts_w)
        if sy_estimates:
            pph = sum(sy_estimates) / len(sy_estimates)
            page_paddle_h[page_idx] = pph
            all_paddle_dpi_h.append(pph * 72.0 / pts_h)

    # Cross-page fallback paddle DPI (median of well-covered pages).
    def _median(vals: list[float]) -> float:
        if not vals:
            return 130.0  # PaddleOCR default ~130 DPI as stated in issue
        s = sorted(vals)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    fallback_dpi_x = _median(all_paddle_dpi_x)
    fallback_dpi_y = _median(all_paddle_dpi_h)

    # --- Pass 2: render pages and upscale images ---
    upscaled = 0
    skipped = 0

    for page_idx, items in sorted(page_to_items.items()):
        page = pdf_doc[page_idx]
        pts_w = page.get_width()
        pts_h = page.get_height()
        scale = target_dpi / 72.0
        bitmap = page.render(scale=scale).to_pil()
        rendered_w, rendered_h = bitmap.size

        # Determine paddle coord space dimensions for this page.
        ppw = page_paddle_w.get(page_idx, pts_w * fallback_dpi_x / 72.0)
        pph = page_paddle_h.get(page_idx, pts_h * fallback_dpi_y / 72.0)
        rs_x = rendered_w / ppw  # rendered pixels per paddle coord unit
        rs_y = rendered_h / pph

        for rel, (x1, y1, x2, y2) in items:
            bbox_w = x2 - x1
            bbox_h = y2 - y1
            if bbox_w <= 0 or bbox_h <= 0:
                skipped += 1
                continue

            # Check existing image scale.
            existing_path = ocr_dir / rel
            try:
                with Image.open(existing_path) as ex_img:
                    ex_w, ex_h = ex_img.size
            except Exception:
                skipped += 1
                continue

            ex_sx = ex_w / bbox_w
            ex_sy = ex_h / bbox_h
            if max(ex_sx, ex_sy) > 0 and abs(ex_sx - ex_sy) / max(ex_sx, ex_sy) > max_aspect_skew:
                print(f"[upscale] {Path(rel).name}: aspect skew ex_sx={ex_sx:.2f} ex_sy={ex_sy:.2f}, skipping",
                      flush=True)
                skipped += 1
                continue

            # Improvement check: if the rendered crop won't be much larger, skip.
            effective_improvement = rs_x / max(ex_sx, 0.01)
            if effective_improvement < min_scale_factor:
                skipped += 1
                continue

            nx1 = max(0, int(x1 * rs_x))
            ny1 = max(0, int(y1 * rs_y))
            nx2 = min(rendered_w, int(x2 * rs_x))
            ny2 = min(rendered_h, int(y2 * rs_y))
            if nx2 - nx1 < 8 or ny2 - ny1 < 8:
                skipped += 1
                continue

            crop = bitmap.crop((nx1, ny1, nx2, ny2))
            # Ensure RGB (alpha channels from RGBA renders)
            if crop.mode not in ("RGB", "L"):
                crop = crop.convert("RGB")
            out_path = ocr_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(out_path, "JPEG", quality=jpeg_quality, optimize=True)
            upscaled += 1

    return {"upscaled": upscaled, "skipped": skipped, "pages": len(page_to_items)}


def _run_paddleocr(*, pdf: Path, out_dir: Path, token: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    h = {"Authorization": f"bearer {token}"}
    with pdf.open("rb") as f:
        r = s.post(API, headers=h,
                   data={"model": MODEL, "optionalPayload": json.dumps(OPT)},
                   files={"file": f}, timeout=600)
    if not r.ok:
        # Don't echo r.text — upstream gateways occasionally include
        # request headers/payload, which can leak the API token.
        raise SystemExit(f"paddleocr HTTP {r.status_code}")
    job_id = r.json()["data"]["jobId"]
    poll_url = f"{API}/{job_id}"
    deadline = time.monotonic() + _PADDLEOCR_TIMEOUT_S
    while True:
        if time.monotonic() > deadline:
            raise SystemExit(
                f"paddleocr poll timed out after {_PADDLEOCR_TIMEOUT_S}s "
                f"(set PADDLEOCR_TIMEOUT_S to extend)"
            )
        j = s.get(poll_url, headers=h, timeout=60).json()["data"]
        if j["state"] == "done":
            text = s.get(j["resultUrl"]["jsonUrl"], timeout=120).text
            break
        if j["state"] == "failed":
            raise SystemExit(j.get("errorMsg", j))
        print(j["state"], file=sys.stderr)
        time.sleep(_PADDLEOCR_POLL_S)
    n = 0
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        for res in json.loads(line)["result"]["layoutParsingResults"]:
            (out_dir / f"doc_{n}.md").write_text(res["markdown"]["text"], encoding="utf-8")
            for rel, url in res["markdown"]["images"].items():
                q = out_dir / rel
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(s.get(url, timeout=120).content)
            n += 1
    # Auto-upscale figure crops from PDF (PaddleOCR's crops are ~130 DPI; we want 300)
    try:
        upscale_stats = upscale_images(pdf=pdf, ocr_dir=out_dir, target_dpi=300)
    except Exception as e:
        upscale_stats = {"error": str(e)}
        print(f"[s01_ocr] upscale_images failed: {e}", file=sys.stderr)
    mark_done(out_dir, {"docs": n, "upscale": upscale_stats})
    return {"docs": n, "upscale": upscale_stats}


def run(*, pdf: Path, out_dir: Path, token: str, backend: str | None = None,
        ocr_lang: str = "en") -> dict:
    """Stage 01 entry. Selects backend:
    - OCR_BACKEND=mineru (or backend="mineru"): MinerU cloud
    - default: PaddleOCR-VL (existing behavior)
    `token` is the chosen backend's API token. For backward compat, when backend is
    paddleocr we treat `token` as PADDLEOCR_TOKEN; for mineru as MINERU_TOKEN.
    `ocr_lang` selects the source-language hint sent to the OCR backend
    (MinerU's `language` field; "en" / "zh"). Default "en" preserves
    pre-v1.11.5 behaviour for English-only papers.
    """
    chosen = backend or os.environ.get("OCR_BACKEND") or "mineru"
    chosen = chosen.lower()
    if chosen == "mineru":
        return _mineru.run(pdf=pdf, out_dir=out_dir, token=token, ocr_lang=ocr_lang)
    # paddleocr fallback (existing logic)
    return _run_paddleocr(pdf=pdf, out_dir=out_dir, token=token)
