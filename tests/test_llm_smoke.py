"""Live smoke tests. Require .env with real keys. Run explicitly:

    .venv/bin/python -m pytest tests/test_llm_smoke.py -v -m live
"""
import os
import pytest
from pathlib import Path

from llm.client import LLM

pytestmark = pytest.mark.live


def _have_keys() -> bool:
    return bool(os.environ.get("LLM_VISION_API_KEY")) and bool(os.environ.get("LLM_TEXT_API_KEY"))


@pytest.mark.skipif(not _have_keys(), reason="LLM keys not set")
def test_text_llm_returns_nonempty():
    llm = LLM(role="text")
    out = llm.chat(system="Reply with one word: ok", user="say ok", max_tokens=10)
    assert out.content.strip(), "empty content"
    assert out.usage["total_tokens"] is not None


@pytest.mark.skipif(not _have_keys(), reason="LLM keys not set")
def test_vision_llm_describes_image(tmp_path: Path):
    from PIL import Image
    img = tmp_path / "red.png"
    Image.new("RGB", (32, 32), "red").save(img)
    llm = LLM(role="vision")
    out = llm.chat(
        system="Describe the dominant color of the image in one English word.",
        user="What color?",
        images=[img],
        max_tokens=20,
    )
    assert "red" in out.content.lower(), f"unexpected response: {out.content!r}"
