"""Stage 01 alternative backend: MinerU cloud API.

Produces the same on-disk contract as the PaddleOCR backend (doc_<N>.md per page +
imgs/<filename>.jpg) so downstream stages don't care which OCR was used.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from stages._common import mark_done

_BASE = os.environ.get("MINERU_BASE_URL", "https://mineru.net/api/v4")
BATCH_URL = f"{_BASE}/file-urls/batch"
RESULTS_URL = f"{_BASE}/extract-results/batch/{{batch_id}}"
POLL_INTERVAL_S = int(os.environ.get("MINERU_POLL_S", "10"))
MAX_POLL_S = int(os.environ.get("MINERU_TIMEOUT_S", "1800"))


class MinerUError(RuntimeError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _post_batch(token: str, pdf_name: str, data_id: str,
                language: str = "en") -> tuple[str, str]:
    # Defaults force layout-OCR so figure-rich text-PDFs return their
    # vector-graphics figures (the cloud's text-layer fast path skipped them).
    is_ocr = _env_bool("MINERU_FORCE_OCR", True)
    enable_table = _env_bool("MINERU_ENABLE_TABLE", True)
    enable_formula = _env_bool("MINERU_ENABLE_FORMULA", True)
    model_version = os.environ.get("MINERU_MODEL_VERSION", "").strip()
    payload: dict[str, object] = {
        "enable_formula": enable_formula,
        "enable_table": enable_table,
        "language": language,
        "files": [{"name": pdf_name, "is_ocr": is_ocr, "data_id": data_id}],
    }
    if model_version:
        payload["model_version"] = model_version
    r = requests.post(
        BATCH_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if not r.ok:
        raise MinerUError(f"batch URL request failed: {r.status_code} {r.text[:200]}")
    j = r.json()
    if j.get("code") != 0:
        raise MinerUError(f"batch URL error: {j}")
    return j["data"]["batch_id"], j["data"]["file_urls"][0]


def _upload(upload_url: str, pdf: Path) -> None:
    with pdf.open("rb") as f:
        r = requests.put(upload_url, data=f, timeout=600)
    if not r.ok:
        raise MinerUError(f"upload failed: {r.status_code}")


def _poll(token: str, batch_id: str) -> dict:
    deadline = time.time() + MAX_POLL_S
    while time.time() < deadline:
        r = requests.get(
            RESULTS_URL.format(batch_id=batch_id),
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if not r.ok:
            raise MinerUError(f"poll failed: {r.status_code} {r.text[:200]}")
        j = r.json()
        results = j.get("data", {}).get("extract_result", [])
        if not results:
            time.sleep(POLL_INTERVAL_S)
            continue
        first = results[0]
        state = first.get("state")
        print(f"[mineru] state={state}", file=sys.stderr)
        if state == "done":
            return first
        if state == "failed":
            raise MinerUError(f"extraction failed: {first.get('err_msg')}")
        time.sleep(POLL_INTERVAL_S)
    raise MinerUError("polling timeout")


def _download_and_extract(zip_url: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "mineru.zip"
    with requests.get(zip_url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    # Zip-slip guard: refuse absolute paths or '..' segments. Without this,
    # a malicious or MITM'd zip could write outside `dest`.
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            try:
                target.relative_to(dest_resolved)
            except ValueError as exc:
                raise MinerUError(
                    f"refusing unsafe zip entry: {member!r}"
                ) from exc
        zf.extractall(dest)
    return dest


_FIG_NUM_RE = re.compile(r"^Fig(?:ure)?\.?\s*(\d+)", re.IGNORECASE)
# Sub-panel labels like "(a) Straight Line Walking" must not be promoted to
# standalone "Figure N." headers — s04's nearest-caption pairing groups them
# under the real caption that sits a few lines below.
_SUBPANEL_RE = re.compile(r"^\s*\(?[a-zA-Z]\)?\.?\s+\S", re.IGNORECASE)


def _ensure_figure_number(caption_text: str, expected_n: int) -> str:
    """Inject ``Figure <expected_n>`` if the caption lacks a leading figure
    number, so downstream `FIG_CAP_RE` matches. Sub-panel labels and properly
    numbered captions pass through untouched.
    """
    if not caption_text:
        return f"Figure {expected_n}. (caption missing)"
    if _FIG_NUM_RE.match(caption_text):
        return caption_text
    if _SUBPANEL_RE.match(caption_text):
        return caption_text
    stripped = re.sub(r"^Fig(?:ure)?\.?\s*[.\$]*\s*", "", caption_text, count=1,
                      flags=re.IGNORECASE)
    return f"Figure {expected_n}. {stripped}"


def _content_list_to_docs(content_list: list[dict], staged_imgs: Path,
                          dest_imgs: Path, out_dir: Path) -> int:
    """Convert MinerU's content_list.json items into per-page doc_<N>.md files.

    Returns the number of pages written.

    Strategy: group items by page_idx. For each page, emit markdown in document order.
    For 'image' items, copy the source image to dest_imgs/img_mineru_NNN.jpg and emit an
    <img> tag plus the original image caption text as a paragraph below.

    For 'text' items, emit the text (or markdown_header for headings).
    For 'table' items, emit either table HTML/markdown if available, else a placeholder.

    Missing-field handling:
    - Items missing 'type' are treated as type '' and skipped.
    - Image items missing 'img_path' are skipped silently.
    - Image source files that don't exist on disk are skipped silently (img tag omitted).
    - text/title items with empty/whitespace text are skipped.
    - equation items with empty text are skipped.
    - table items with no table_body and no table_caption produce nothing.
    """
    by_page: dict[int, list[dict]] = {}
    for item in content_list:
        pi = item.get("page_idx", 0)
        by_page.setdefault(pi, []).append(item)

    dest_imgs.mkdir(parents=True, exist_ok=True)
    img_counter = 0
    img_map: dict[str, str] = {}  # source img_path → new relative path

    pages_written = 0
    for page_idx in sorted(by_page.keys()):
        page_md_lines: list[str] = []
        for item in by_page[page_idx]:
            t = item.get("type", "")
            if t == "text":
                txt = (item.get("text") or "").strip()
                if not txt:
                    continue
                level = item.get("text_level")
                if level:
                    page_md_lines.append(f"{'#' * level} {txt}")
                else:
                    page_md_lines.append(txt)
            elif t in ("image", "chart"):
                # MinerU types scientific plots as `chart` and photos /
                # diagrams as `image`; both are figures for our purposes.
                src_path = item.get("img_path") or ""
                if not src_path:
                    continue
                if src_path not in img_map:
                    img_counter += 1
                    new_name = f"img_mineru_{img_counter:03d}.jpg"
                    src_abs = staged_imgs / Path(src_path).name
                    if not src_abs.exists():
                        src_abs = staged_imgs.parent / src_path
                    if src_abs.exists():
                        shutil.copy2(src_abs, dest_imgs / new_name)
                        img_map[src_path] = f"imgs/{new_name}"
                    else:
                        img_map[src_path] = ""  # mark missing, skip tag emit
                rel = img_map[src_path]
                if not rel:
                    continue
                page_md_lines.append(f'<img src="{rel}">')
                caps = item.get("image_caption") or item.get("chart_caption") or []
                for cap in caps:
                    cap_clean = _ensure_figure_number(
                        (cap or "").strip(), expected_n=img_counter,
                    )
                    if cap_clean:
                        page_md_lines.append(cap_clean)
            elif t == "table":
                tbl_body = item.get("table_body") or item.get("table_caption", [""])[0] or ""
                if tbl_body:
                    page_md_lines.append(str(tbl_body))
            elif t == "equation":
                eq = item.get("text") or ""
                if eq:
                    page_md_lines.append(f"$${eq}$$")
            elif t == "title":
                txt = item.get("text", "")
                if txt:
                    page_md_lines.append(f"# {txt}")
        body = "\n\n".join(page_md_lines).strip()
        if not body:
            continue
        (out_dir / f"doc_{page_idx}.md").write_text(body + "\n", encoding="utf-8")
        pages_written += 1
    return pages_written


def run(*, pdf: Path, out_dir: Path, token: str, ocr_lang: str = "en") -> dict:
    """Submit `pdf` to MinerU, download the result, and produce lazy-paper-compatible
    artifacts under `out_dir`.

    `ocr_lang` is forwarded to MinerU's `language` field. Default "en"
    matches pre-v1.11.5 behaviour; pass "zh" for CJK-heavy manuscripts.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    data_id = pdf.stem[:50] or "paper"
    print(f"[mineru] submitting {pdf.name} (lang={ocr_lang})", file=sys.stderr)
    batch_id, upload_url = _post_batch(token, pdf.name, data_id, language=ocr_lang)
    print(f"[mineru] batch_id={batch_id}", file=sys.stderr)
    _upload(upload_url, pdf)
    print(f"[mineru] uploaded; polling...", file=sys.stderr)
    result = _poll(token, batch_id)
    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise MinerUError("no full_zip_url in done result")

    stage_dir = out_dir / "_mineru_raw"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    _download_and_extract(zip_url, stage_dir)
    # find content_list.json
    cl_candidates = list(stage_dir.glob("*_content_list.json"))
    if not cl_candidates:
        raise MinerUError(f"no *_content_list.json in {stage_dir}")
    content_list = json.loads(cl_candidates[0].read_text(encoding="utf-8"))
    # images live under stage_dir/images/
    staged_imgs = stage_dir / "images"
    dest_imgs = out_dir / "imgs"
    n_pages = _content_list_to_docs(content_list, staged_imgs, dest_imgs, out_dir)

    mark_done(out_dir, {
        "backend": "mineru",
        "docs": n_pages,
        "images_extracted": len(list(dest_imgs.glob("*.jpg"))),
    })
    # Clean up extracted raw zip dir to save space, unless caller wants to
    # diagnose figure-recall regressions (MINERU_KEEP_RAW=1 preserves the zip
    # extraction so you can inspect *_content_list.json directly).
    if not _env_bool("MINERU_KEEP_RAW", False):
        shutil.rmtree(stage_dir, ignore_errors=True)
    return {"backend": "mineru", "docs": n_pages,
            "images": len(list(dest_imgs.glob("*.jpg")))}
