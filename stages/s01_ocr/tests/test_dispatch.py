import os
from pathlib import Path
from unittest.mock import patch

from stages.s01_ocr import runner as s01_runner


def test_dispatch_default_is_mineru(monkeypatch, tmp_path: Path):
    """Default backend is mineru (changed in v0.5 after empirical quality wins)."""
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    called = {}
    def fake_mineru(*, pdf, out_dir, token):
        called["mineru"] = True
        return {"docs": 0}
    monkeypatch.setattr(s01_runner._mineru, "run", fake_mineru)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out", token="t")
    assert called.get("mineru") is True


def test_dispatch_env_var_picks_mineru(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OCR_BACKEND", "mineru")
    called = {}
    def fake_mineru(*, pdf, out_dir, token):
        called["mineru"] = True
        return {"docs": 0}
    monkeypatch.setattr(s01_runner._mineru, "run", fake_mineru)
    s01_runner.run(pdf=tmp_path / "x.pdf", out_dir=tmp_path / "out", token="t")
    assert called.get("mineru") is True


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
