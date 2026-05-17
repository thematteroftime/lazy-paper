import json
from pathlib import Path

import pytest

from stages.s01_ocr.mineru import _content_list_to_docs, MinerUError


def test_content_list_to_docs_per_page(tmp_path: Path):
    """Items with different page_idx produce separate doc_N.md files."""
    staged_imgs = tmp_path / "_raw" / "images"; staged_imgs.mkdir(parents=True)
    dest_imgs = tmp_path / "imgs"
    out_dir = tmp_path / "out"; out_dir.mkdir()
    # Create dummy image
    (staged_imgs / "abc.jpg").write_bytes(b"\xff\xd8\xff\xe0")

    content_list = [
        {"type": "title", "text": "Intro", "page_idx": 0},
        {"type": "text", "text": "First page body.", "page_idx": 0},
        {"type": "image", "img_path": "images/abc.jpg",
         "image_caption": ["Figure 1. Test figure."], "page_idx": 0},
        {"type": "text", "text": "Page 1 body.", "page_idx": 1},
    ]
    n = _content_list_to_docs(content_list, staged_imgs, dest_imgs, out_dir)
    assert n == 2
    d0 = (out_dir / "doc_0.md").read_text(encoding="utf-8")
    d1 = (out_dir / "doc_1.md").read_text(encoding="utf-8")
    assert "First page body" in d0
    assert "Figure 1. Test figure" in d0
    assert "img_mineru_001" in d0
    assert (dest_imgs / "img_mineru_001.jpg").exists()
    assert "Page 1 body" in d1


def test_content_list_skips_empty_pages(tmp_path: Path):
    """A page with no usable items is not written."""
    staged_imgs = tmp_path / "_raw" / "images"; staged_imgs.mkdir(parents=True)
    dest_imgs = tmp_path / "imgs"
    out_dir = tmp_path / "out"; out_dir.mkdir()
    content_list = [
        {"type": "text", "text": "", "page_idx": 0},  # empty
        {"type": "text", "text": "real", "page_idx": 1},
    ]
    n = _content_list_to_docs(content_list, staged_imgs, dest_imgs, out_dir)
    # Page 0 produces no body and is skipped; page 1 produces doc_1.md
    assert not (out_dir / "doc_0.md").exists()
    assert (out_dir / "doc_1.md").exists()


def test_image_count_correct(tmp_path: Path):
    """Multiple image items produce sequentially-numbered jpg files."""
    staged_imgs = tmp_path / "_raw" / "images"; staged_imgs.mkdir(parents=True)
    dest_imgs = tmp_path / "imgs"
    out_dir = tmp_path / "out"; out_dir.mkdir()
    for h in ("h1.jpg", "h2.jpg", "h3.jpg"):
        (staged_imgs / h).write_bytes(b"\xff\xd8\xff\xe0")
    content_list = [
        {"type": "image", "img_path": f"images/{h}", "image_caption": [f"Figure {i}."], "page_idx": i}
        for i, h in enumerate(("h1.jpg", "h2.jpg", "h3.jpg"))
    ]
    _content_list_to_docs(content_list, staged_imgs, dest_imgs, out_dir)
    extracted = sorted(dest_imgs.glob("*.jpg"))
    assert len(extracted) == 3
    assert {p.name for p in extracted} == {"img_mineru_001.jpg", "img_mineru_002.jpg", "img_mineru_003.jpg"}
