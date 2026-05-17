import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from stages._common import is_done
from stages.s01_ocr.runner import run as run_ocr


def test_ocr_runner_writes_docs_and_images(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    job_response = {"data": {"jobId": "job-xyz"}}
    done_state = {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://x/result.json"}}}
    result_text = json.dumps({
        "result": {
            "layoutParsingResults": [
                {
                    "markdown": {
                        "text": '# page 1\n<img src="imgs/img_a.jpg">\n',
                        "images": {"imgs/img_a.jpg": "https://x/img_a.jpg"},
                    },
                    "outputImages": {},
                }
            ]
        }
    })

    def fake_post(url, **kwargs):
        r = MagicMock(); r.ok = True; r.json.return_value = job_response
        return r

    def fake_get(url, **kwargs):
        r = MagicMock(); r.ok = True
        if url.endswith("/job-xyz"):
            r.json.return_value = done_state
        elif url.endswith("result.json"):
            r.text = result_text
        else:
            r.content = b"\xff\xd8\xff\xe0FAKE-JPEG"
        return r

    with patch("stages.s01_ocr.runner.requests.Session") as sess_cls:
        sess = sess_cls.return_value
        sess.post.side_effect = fake_post
        sess.get.side_effect = fake_get
        run_dir = tmp_path / "runs" / "paper" / "01_ocr"
        run_ocr(pdf=pdf, out_dir=run_dir, token="t", backend="paddleocr")

    assert (run_dir / "doc_0.md").exists()
    assert (run_dir / "imgs" / "img_a.jpg").exists()
    assert is_done(run_dir)


from PIL import Image as PILImage
import pypdfium2 as pdfium


def test_upscale_images_replaces_lowres_with_pdf_render(tmp_path: Path):
    """Build a synthetic PDF, place a low-res JPEG with a bbox-coded name in imgs/,
    and verify upscale_images replaces it with a higher-res crop from the PDF."""
    from stages.s01_ocr.runner import upscale_images

    # Make a small PDF (1 page) using PIL → PDF
    page_img = PILImage.new("RGB", (1200, 1600), "white")
    # Draw a recognizable feature so we can spot the high-res crop
    for x in range(100, 500):
        for y in range(100, 500):
            page_img.putpixel((x, y), (255, 0, 0))
    pdf_path = tmp_path / "p.pdf"
    page_img.save(pdf_path, "PDF", resolution=150.0)

    ocr_dir = tmp_path / "ocr"
    (ocr_dir / "imgs").mkdir(parents=True)
    # Simulate PaddleOCR coord space: page is 600x800 in their coords; bbox 50-250, 50-250
    rel = "imgs/img_in_chart_box_50_50_250_250.jpg"
    low_res = PILImage.new("RGB", (200, 200), "blue")
    low_res.save(ocr_dir / rel, "JPEG")
    # doc_0.md references the image (so page_idx=0)
    (ocr_dir / "doc_0.md").write_text(f'<img src="{rel}">', encoding="utf-8")
    # Add a footer-like image to set the page's paddle_w/paddle_h max coords
    rel2 = "imgs/img_in_footer_box_0_780_600_800.jpg"
    PILImage.new("RGB", (600, 20), "gray").save(ocr_dir / rel2, "JPEG")
    (ocr_dir / "doc_0.md").write_text(
        f'<img src="{rel}">\n<img src="{rel2}">', encoding="utf-8",
    )

    stats = upscale_images(pdf=pdf_path, ocr_dir=ocr_dir, target_dpi=300)
    assert stats["upscaled"] >= 1, stats

    with PILImage.open(ocr_dir / rel) as new_img:
        new_w, new_h = new_img.size
    # The new crop should be substantially larger than the old 200x200
    assert new_w > 300, (new_w, new_h)
    assert new_h > 300, (new_w, new_h)
