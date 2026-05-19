"""OpenAI-compatible client for vision (Qwen-VL) and text (DeepSeek) roles."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

_MODELS_YAML = Path(__file__).resolve().parent / "models.yaml"

_MAX_TOKENS_CEILING_DEFAULT = 40000


def _load_roles() -> dict:
    return yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))


def max_tokens(default: int) -> int:
    """Clamp a requested max_tokens to the env-configured ceiling.

    Output quality and information density are favored: per-stage defaults are
    generous (multiple-K each). Set LLM_MAX_TOKENS_CEILING to constrain (e.g.
    to control cost or stay under a stricter API quota). Default ceiling 40000.
    """
    raw = os.environ.get("LLM_MAX_TOKENS_CEILING")
    ceiling = int(raw) if raw and raw.strip().isdigit() else _MAX_TOKENS_CEILING_DEFAULT
    return min(default, max(1, ceiling))


def image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict
    latency_ms: float


class LLM:
    def __init__(self, role: str, dotenv_path: Path | None = None):
        load_dotenv(dotenv_path or Path.cwd() / ".env", override=False)
        roles = _load_roles()
        if role not in roles:
            raise ValueError(f"unknown role {role!r}; expected one of {list(roles)}")
        cfg = roles[role]
        prefix = cfg["env_prefix"]
        api_key = os.environ.get(f"{prefix}_API_KEY")
        if not api_key:
            raise RuntimeError(f"missing env var {prefix}_API_KEY")
        base_url = os.environ.get(f"{prefix}_BASE_URL", cfg["default_base_url"])
        self.model = os.environ.get(f"{prefix}_MODEL", cfg["default_model"])
        self.supports_images = bool(cfg.get("supports_images", False))
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        *,
        system: str,
        user: str,
        images: list[Path] = (),
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        if images and not self.supports_images:
            raise ValueError(f"role/model {self.model} does not support images")
        messages = [{"role": "system", "content": system}]
        if images:
            user_parts: list[dict] = [{"type": "text", "text": user}]
            for img in images:
                user_parts.append(
                    {"type": "image_url", "image_url": {"url": image_to_data_url(Path(img))}}
                )
            messages.append({"role": "user", "content": user_parts})
        else:
            messages.append({"role": "user", "content": user})

        t0 = time.time()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency_ms = (time.time() - t0) * 1000
        u = getattr(resp, "usage", None)
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", None),
            "completion_tokens": getattr(u, "completion_tokens", None),
            "total_tokens": getattr(u, "total_tokens", None),
        }
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=self.model,
            usage=usage,
            latency_ms=latency_ms,
        )
