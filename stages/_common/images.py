"""Image helpers shared across stages and the LLM client."""
from __future__ import annotations

import base64
from pathlib import Path

_MIME_BY_SUFFIX = {
    "jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif",
}


def image_to_data_url(path: Path) -> str:
    """Encode an image as a base64 `data:image/<mime>;base64,…` URL."""
    mime = _MIME_BY_SUFFIX.get(path.suffix.lstrip(".").lower(), "jpeg")
    b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"
