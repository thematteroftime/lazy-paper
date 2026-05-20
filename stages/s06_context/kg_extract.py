"""KG extraction sub-step of s06_context (one LLM call per paper)."""
from __future__ import annotations

import os
from pathlib import Path

import instructor
from instructor import Mode

from llm.client import LLM, max_tokens
from llm.paper_kg import PaperKG

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "llm" / "prompts"
_MAX_CHARS = 30_000


def _prompt_path() -> Path:
    """Allow env override of the KG-extraction prompt.

    Set LAZY_PAPER_KG_PROMPT=paper_kg_v2.md to try the more aggressive
    comparator-extraction prompt that explicitly handles literature
    benchmark patterns ('X et al. reported …').
    """
    return _PROMPTS_DIR / os.environ.get("LAZY_PAPER_KG_PROMPT", "paper_kg.md")


def _gather_source(chapters_dir: Path) -> str:
    parts: list[str] = []
    for p in sorted(chapters_dir.glob("chapter_*.md")):
        parts.append(f"=== {p.name} ===\n" + p.read_text(encoding="utf-8"))
    return "\n\n".join(parts)[:_MAX_CHARS]


def _split_prompt(template_text: str, paper_text: str) -> tuple[str, str]:
    sys_idx = template_text.index("SYSTEM:") + len("SYSTEM:")
    usr_idx = template_text.index("USER:")
    system = template_text[sys_idx:usr_idx].strip()
    user = template_text[usr_idx + len("USER:"):].strip().replace("{paper_text}", paper_text)
    return system, user


def _extract_via_llm(system: str, user: str) -> PaperKG:
    llm = LLM(role="text")
    client = instructor.from_openai(llm._client, mode=Mode.JSON)
    return client.chat.completions.create(
        model=llm.model,
        response_model=PaperKG,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens(16000),
        temperature=0.0,
        max_retries=2,
    )


def build_paper_kg(*, chapters_dir: Path, out_dir: Path) -> PaperKG | None:
    """Returns the KG on success, None on failure (writes `kg_extract.failed`).

    All failure modes — empty input, prompt-template malformation, LLM error,
    parquet write error — are caught and recorded in the marker file. The
    s06 runner must never abort because of a KG failure.
    """
    paper_text = _gather_source(chapters_dir)
    if not paper_text.strip():
        (out_dir / "kg_extract.failed").write_text("no source chapters", encoding="utf-8")
        return None
    try:
        template_text = _prompt_path().read_text(encoding="utf-8")
        system, user = _split_prompt(template_text, paper_text)
        kg = _extract_via_llm(system, user)
        kg.to_parquet(out_dir / "paper_kg.parquet")
        return kg
    except Exception as exc:  # template parse, LLM, pyarrow — any failure
        (out_dir / "kg_extract.failed").write_text(repr(exc), encoding="utf-8")
        return None
