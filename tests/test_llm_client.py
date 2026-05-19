from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm.client import LLM, image_to_data_url, max_tokens


def test_image_to_data_url(tmp_path: Path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")  # minimal JPEG magic
    url = image_to_data_url(img)
    assert url.startswith("data:image/jpeg;base64,")
    assert "/9j" not in url[:23]  # base64 body comes after prefix


def test_llm_text_role_chat(monkeypatch):
    monkeypatch.setenv("LLM_TEXT_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_TEXT_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_TEXT_MODEL", "test-model")

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="hello"))]
    fake_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    with patch("llm.client.OpenAI") as oai_cls:
        oai_cls.return_value.chat.completions.create.return_value = fake_resp
        llm = LLM(role="text")
        out = llm.chat(system="be concise", user="hi")
    assert out.content == "hello"
    assert out.usage["total_tokens"] == 15
    assert out.model == "test-model"


def test_llm_vision_role_includes_images(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_VISION_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_VISION_BASE_URL", "https://x.example.com/v1")
    monkeypatch.setenv("LLM_VISION_MODEL", "qwen-vl")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="saw img"))]
    fake_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    with patch("llm.client.OpenAI") as oai_cls:
        oai_cls.return_value.chat.completions.create.return_value = fake_resp
        llm = LLM(role="vision")
        out = llm.chat(system="describe", user="what is this", images=[img])

    call_kwargs = oai_cls.return_value.chat.completions.create.call_args.kwargs
    user_msg = call_kwargs["messages"][1]
    # user content must be a list with text + image_url parts when images present
    assert isinstance(user_msg["content"], list)
    types = [p["type"] for p in user_msg["content"]]
    assert "text" in types and "image_url" in types
    assert out.content == "saw img"


def test_llm_vision_role_rejects_images_if_unsupported(monkeypatch):
    monkeypatch.setenv("LLM_TEXT_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_TEXT_MODEL", "deepseek-chat")
    llm = LLM(role="text")
    with pytest.raises(ValueError, match="does not support images"):
        llm.chat(system="x", user="y", images=[Path("/tmp/whatever.jpg")])


def test_max_tokens_returns_default_when_under_ceiling(monkeypatch):
    monkeypatch.delenv("LLM_MAX_TOKENS_CEILING", raising=False)
    assert max_tokens(8000) == 8000
    assert max_tokens(40000) == 40000


def test_max_tokens_clamps_to_env_ceiling(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS_CEILING", "5000")
    assert max_tokens(12000) == 5000
    assert max_tokens(2000) == 2000


def test_max_tokens_ignores_garbage_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS_CEILING", "not-a-number")
    # Falls back to the built-in 40000 ceiling.
    assert max_tokens(60000) == 40000
    assert max_tokens(8000) == 8000
