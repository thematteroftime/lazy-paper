import os
from pathlib import Path
from unittest.mock import patch

from stages.s01_ocr import runner as s01_runner


def test_dispatch_default_is_mineru(monkeypatch, tmp_path: Path):
    """Default backend is mineru (changed in v0.5 after empirical quality wins)."""
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    called = {}
    def fake_mineru(*, pdf, out_dir, token, ocr_lang="en"):
        called["mineru"] = True
        called["ocr_lang"] = ocr_lang
        return {"docs": 0}
    monkeypatch.setattr(s01_runner._mineru, "run", fake_mineru)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out", token="t")
    assert called.get("mineru") is True
    # v1.11.5: default ocr_lang flows through as "en"
    assert called.get("ocr_lang") == "en"


def test_dispatch_env_var_picks_mineru(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OCR_BACKEND", "mineru")
    called = {}
    def fake_mineru(*, pdf, out_dir, token, ocr_lang="en"):
        called["mineru"] = True
        return {"docs": 0}
    monkeypatch.setattr(s01_runner._mineru, "run", fake_mineru)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out", token="t")
    assert called.get("mineru") is True


def test_dispatch_ocr_lang_zh_threads_through(monkeypatch, tmp_path: Path):
    """v1.11.5: `--ocr-lang zh` reaches MinerU's `language` field.
    Independent of --lang (output language)."""
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    captured = {}
    def fake_mineru(*, pdf, out_dir, token, ocr_lang="en"):
        captured["ocr_lang"] = ocr_lang
        return {"docs": 0}
    monkeypatch.setattr(s01_runner._mineru, "run", fake_mineru)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out",
                   token="t", ocr_lang="zh")
    assert captured["ocr_lang"] == "zh"


def test_dispatch_explicit_arg_overrides_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OCR_BACKEND", "mineru")
    called = {}
    def fake_paddle(*, pdf, out_dir, token):
        called["paddle"] = True
        return {"docs": 0}
    monkeypatch.setattr(s01_runner, "_run_paddleocr", fake_paddle)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out",
                   token="t", backend="paddleocr")
    assert called.get("paddle") is True
