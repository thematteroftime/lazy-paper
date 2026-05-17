"""Renderer registry. Subclasses register themselves by file extension."""
from __future__ import annotations

from stages.s09_render.renderers.base import Renderer

# Populated as each renderer module is added (docx → M2, html/pdf → M3, pptx → M4).
RENDERERS: dict[str, type[Renderer]] = {}

__all__ = ["Renderer", "RENDERERS"]
