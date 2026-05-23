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

    Default is the 10-type closed schema (`paper_kg.md`). Strategy KL
    (v1.8.1 recommended) sets `LAZY_PAPER_KG_PROMPT=paper_kg_v3.md` to
    add an 11th `author` entity type linked to each `comparator` via the
    `cited_by_paper` relation — this is what lets the section composer
    introduce comparators as "<Author> et al." instead of bare chemical
    formulas.
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
        max_tokens=max_tokens(32000),
        temperature=0.0,
        max_retries=2,
    )


def extract_headline_metrics(kg: PaperKG) -> dict[str, str]:
    """Pick the flagship sample's key metrics out of the KG.

    Returns {'flagship': formula, 'W_rec': '5.00 J/cm^3', 'eta': '90.09 %', ...}
    or {} if no flagship material is identified.

    Why: v1.10 baseline had a meng2024 cross-chapter inconsistency where
    ch07/09/13/15 quoted three different W_rec values for the same flagship
    sample (5.00, 4.50, 2.94) because the section composer pulled numbers
    from neighbouring comparator citations. The KG already captures the
    correct `mat_main --has_W_rec--> 5.00` relation; piping it into
    `context.yaml` (consumed by the s08 prompt) gives the LLM a single
    source of truth instead of letting it scavenge values from chunks.
    """
    materials = [e for e in kg.entities if e.type == "material"]
    if not materials:
        return {}
    # Prefer the canonical `mat_main` id; otherwise fall back to the
    # first material entity. The prompt sets `mat_main` for the flagship.
    main = next((m for m in materials if m.id == "mat_main"), materials[0])
    val_by_id = {e.id: e for e in kg.entities if e.type == "value"}
    unit_by_id = {e.id: e for e in kg.entities if e.type == "unit"}
    val_to_unit_id = {r.subject: r.object for r in kg.relations
                      if r.predicate == "has_unit"}

    out: dict[str, str] = {"flagship": main.text}
    for r in kg.relations:
        if r.subject != main.id or not r.predicate.startswith("has_"):
            continue
        key = r.predicate.removeprefix("has_")
        val = val_by_id.get(r.object)
        if not val:
            continue
        unit = unit_by_id.get(val_to_unit_id.get(val.id, ""))
        out[key] = f"{val.text} {unit.text}".strip() if unit else val.text
    return out


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
