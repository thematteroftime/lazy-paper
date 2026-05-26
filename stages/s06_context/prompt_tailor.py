"""Pre-stage prompt tailoring (v1.12 phase 4).

Reads the paper's already-extracted context.yaml + intro chunk and emits a
per-paper augmentation block (domain framing, terminology, metric patterns,
comparator style example FROM THIS PAPER). s08 prepends a render of this
block to _STRUCTURED_SYSTEM before each compose call.

Gated by LAZY_PAPER_PROMPT_TAILOR=1 in the caller (s06_context.runner);
this module just implements the LLM call + schema validation. Soft-degrade
is the caller's responsibility (catch PromptTailorError, drop a .failed
marker, let s08 fall back to vanilla _STRUCTURED_SYSTEM).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Callable

import yaml

PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "prompt_tailor.md"
VERSION = "prompt_tailor_v1"
_REQUIRED_KEYS = ("domain_framing", "terminology", "metric_patterns", "comparator_style")


class PromptTailorError(RuntimeError):
    """Raised when the pre-stage LLM response cannot be parsed/validated."""


def _read_intro_chunk(chapters_dir: Path, max_chars: int = 3000) -> str:
    """Return the first `max_chars` of chapter_001_INTRODUCTION.md, or ''."""
    intro_path = chapters_dir / "chapter_001_INTRODUCTION.md"
    if not intro_path.exists():
        return ""
    text = intro_path.read_text(encoding="utf-8")
    return text[:max_chars]


def _build_user_prompt(context: dict, intro: str) -> str:
    """Render the user message: <<<CONTEXT>>> + <<<INTRO>>> blocks."""
    ctx_yaml = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)
    return (
        "<<<CONTEXT>>>\n"
        f"{ctx_yaml}"
        "<<<INTRO>>>\n"
        f"{intro}\n"
    )


def _parse_and_validate(text: str) -> dict:
    """Parse JSON; ensure all required top-level keys are present."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PromptTailorError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise PromptTailorError(f"LLM JSON root is not an object: {type(obj).__name__}")
    missing = [k for k in _REQUIRED_KEYS if k not in obj]
    if missing:
        raise PromptTailorError(f"LLM JSON missing keys: {missing}")
    return obj


def generate_prompt_augment(
    *,
    context: dict,
    chapters_dir: Path,
    llm_chat: Callable[..., str] | None = None,
) -> dict:
    """Run the pre-stage LLM and return a validated augmentation dict.

    `llm_chat` is injectable for tests; in prod it wraps llm.client.LLM.chat.
    Raises PromptTailorError on parse/validation failure — caller decides
    whether to soft-degrade (drop a .failed marker and continue without
    augmentation).
    """
    if llm_chat is None:
        from llm.client import LLM
        client = LLM(role="text")

        def _real_chat(**kw):
            return client.chat(**kw).content

        llm_chat = _real_chat

    system = PROMPT_PATH.read_text(encoding="utf-8")
    intro = _read_intro_chunk(chapters_dir)
    user = _build_user_prompt(context, intro)
    resp = llm_chat(system=system, user=user, temperature=0.1, max_tokens=2000)
    out = _parse_and_validate(resp)
    out["generated_by"] = VERSION
    out["generated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    return out
