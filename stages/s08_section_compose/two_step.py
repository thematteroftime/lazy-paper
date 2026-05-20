"""Strategy B: two-step section composition — outline first, then expand
each point with its evidence (env-gated by LAZY_PAPER_TWO_STEP=1).

Step 1 (planning): LLM returns a structured outline binding each key claim
to specific evidence chunk indices.

Step 2 (expansion): each outline point is expanded into prose, with the
exact evidence chunks pinned to the prompt.

Trade-off: 2× LLM calls per section, but each call is shorter and more
focused than v1.4.x's single-shot compose. The forced planning step
should give better depth + structural coherence per section.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import instructor
from instructor import Mode
from pydantic import BaseModel, Field

from llm.client import max_tokens

if TYPE_CHECKING:
    from llm.client import LLM
    from llm.retriever import Chunk


class OutlinePoint(BaseModel):
    """One key claim the section should make + the chunks supporting it."""
    claim: str = Field(description="One sentence, the claim to make.")
    evidence_chunk_ids: list[int] = Field(
        default_factory=list,
        description="Indices into the retrieved chunks list (0-based).",
    )
    target_chars: int = Field(
        default=200,
        ge=80, le=600,
        description="Approximate Chinese character budget for the expansion.",
    )


class SectionOutline(BaseModel):
    """Structured plan of the section before any prose is written."""
    points: list[OutlinePoint] = Field(min_length=2, max_length=8)
    notes: str = Field(default="", description="One sentence on overall arc.")


_OUTLINE_SYS = """You plan one section of a research-paper deep analysis.
You will receive: section title + guidance + a numbered list of retrieved
source chunks. Produce a structured outline (3-6 points typically; up to 8
for rich sections, 2 minimum). For EACH point:
  - claim: one sentence (Chinese unless guidance says otherwise)
  - evidence_chunk_ids: 0-based indices into the chunks list that support
    this claim. Cite at least one when possible.
  - target_chars: ~100-500 char Chinese budget for the expansion.

Prefer points that surface concrete numerical/parametric content from the
chunks (e.g. specific J/cm³, kV/cm, °C values, chemical formulas). Avoid
generic motivational sentences."""


_EXPAND_SYS = """You expand one outlined point of a research-paper section.
You will receive: the section title + guidance, the specific claim to make,
and the specific evidence chunks pinned to it. Write a paragraph (target
chars given) that:
  - states the claim clearly
  - cites specific numbers / units / chemical formulas / figure refs from
    evidence (no rounding away precision; e.g. "5.00 J/cm³" not "~5 J/cm³")
  - stays in the section's language (Chinese unless explicitly English)

Return ONLY the prose; the orchestrator concatenates points with blank
lines."""


def compose_two_step(
    llm: "LLM",
    section_title: str,
    section_guidance: str,
    chunks: list["Chunk"],
    lang: str = "zh",
) -> str:
    """Run the outline → expand two-step pipeline. Returns concatenated prose."""
    # ---- Step 1: outline -----------------------------------------------------
    chunks_block = "\n".join(
        f"[{i}] ({c.doc_name}, chars {c.char_start}-{c.char_end})\n{c.text[:1200]}"
        for i, c in enumerate(chunks)
    )
    lang_hint = ("Chinese prose with embedded English technical terms"
                 if lang == "zh" else "English prose")
    outline_user = (
        f"Section title: {section_title}\n"
        f"Guidance: {section_guidance}\n\n"
        f"Source chunks (0-indexed):\n{chunks_block}\n\n"
        f"Target language: {lang_hint}.\n"
        f"Return the SectionOutline now."
    )
    client = instructor.from_openai(llm._client, mode=Mode.JSON)
    outline = client.chat.completions.create(
        model=llm.model,
        response_model=SectionOutline,
        messages=[
            {"role": "system", "content": _OUTLINE_SYS},
            {"role": "user", "content": outline_user},
        ],
        max_tokens=max_tokens(4000),
        temperature=0.2,
        max_retries=2,
    )

    # ---- Step 2: expand each point -----------------------------------------
    pieces: list[str] = []
    for pt in outline.points:
        pinned_chunks = [chunks[i].text for i in pt.evidence_chunk_ids
                         if 0 <= i < len(chunks)]
        evidence_block = ("\n---\n".join(pinned_chunks)[:8000]
                          if pinned_chunks else "(no pinned chunks; rely on prior context)")
        expand_user = (
            f"Section: {section_title}\n"
            f"Claim to develop: {pt.claim}\n"
            f"Target length: ~{pt.target_chars} characters.\n"
            f"Language: {lang_hint}.\n\n"
            f"Pinned evidence:\n{evidence_block}"
        )
        resp = llm.chat(
            system=_EXPAND_SYS,
            user=expand_user,
            max_tokens=max_tokens(2000),
            temperature=0.3,
        )
        prose = resp.content.strip()
        if prose:
            pieces.append(prose)

    return "\n\n".join(pieces)
