"""Advise: experiment + library -> grounded next-iteration plan.

The AI-scientist closing loop. Evidence = the experiment's archived bundle +
its linked papers' archived context + idea-relevant library excerpts + ALL
prior advise rounds (reports + user-recorded outcomes). One text-LLM call
(retry + audit sidecars, house pattern) composes a four-section plan whose
claims carry [src: id] markers — validated against the manifest via
synthesize.check_citations (experiment ids are manifest entries too).
Rounds live at <library>/experiments/<exp_id>/advice/round_NN/.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from llm.client import LLM
from llm.experiment import summarize_metrics
from llm.template_author import _split_prompt
from stages._common import load_yaml

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "advise.md"

_LANG_INSTRUCTIONS = {
    "zh": "Write in Chinese (keep technical terms as-is).",
    "en": "Write in English.",
}


def _advice_root(lib, exp_id: str) -> Path:
    return lib.root / "experiments" / exp_id / "advice"


def _rounds(lib, exp_id: str) -> list[Path]:
    root = _advice_root(lib, exp_id)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("round_"))


def next_round_dir(lib, exp_id: str) -> Path:
    # Use max existing index + 1 (not a count) so a gap — e.g. a manually
    # deleted round_02 — never re-issues an already-used round number.
    rounds = _rounds(lib, exp_id)
    last = 0
    for rd in rounds:
        try:
            last = max(last, int(rd.name.removeprefix("round_")))
        except ValueError:
            continue
    return _advice_root(lib, exp_id) / f"round_{last + 1:02d}"


def record_outcome(lib, exp_id: str, outcome: str) -> Path:
    rounds = _rounds(lib, exp_id)
    if not rounds:
        raise SystemExit(f"{exp_id}: no advise rounds yet — nothing to "
                         f"record an outcome against")
    out = rounds[-1] / "outcome.md"
    out.write_text(outcome, encoding="utf-8")
    return out


def gather_evidence(lib, exp_id: str, *, idea: str, top_k: int = 12) -> str:
    manifest = lib.papers()
    entry = manifest.get(exp_id)
    if not entry or entry.get("kind") != "experiment":
        raise SystemExit(f"'{exp_id}' is not an ingested experiment — run "
                         f"`lazy-paper exp-ingest` first (see `papers`)")
    ex = lib.root / "experiments" / exp_id
    parts: list[str] = [f"## EXPERIMENT {exp_id}"]
    if (ex / "exp.yaml").exists():
        parts.append(yaml.safe_dump(load_yaml(ex / "exp.yaml"),
                                    allow_unicode=True, sort_keys=False))
    for note in (load_yaml(ex / "exp_notes.yaml")
                 if (ex / "exp_notes.yaml").exists() else []) or []:
        if isinstance(note, dict):
            parts.append(f"curve {note.get('image', '?')}: "
                         f"{note.get('visual_summary', '')} | "
                         f"{note.get('deep_observation', '')}")
    for md in sorted(ex.glob("*.md")):
        parts.append(f"notes {md.name}: " + md.read_text(encoding="utf-8")[:1500])
    digest = summarize_metrics(ex)
    if digest:
        parts.append("metrics: " + digest)

    for pid in entry.get("papers") or []:
        pctx_path = lib.root / "papers" / pid / "context.yaml"
        pmeta = manifest.get(pid) or {}
        lines = [f"## LINKED PAPER {pid}", f"title: {pmeta.get('title', '')}"]
        if pctx_path.exists():
            pctx = load_yaml(pctx_path) or {}
            for q in (pctx.get("critical_questions") or [])[:3]:
                lines.append(f"critical question: {q}")
            hm = pctx.get("headline_metrics") or {}
            items = ([f"{k}: {v}" for k, v in hm.items()]
                     if isinstance(hm, dict) else [str(x) for x in hm])
            for m in items[:4]:
                lines.append(f"headline metric: {m}")
        parts.append("\n".join(lines))

    hits = lib.query(f"{idea} {entry.get('title', '')}", top_k=top_k)
    if hits:
        lines = ["## LIBRARY EXCERPTS"]
        for h in hits:
            snippet = " ".join(h["text"].split())[:400]
            lines.append(f"- [{h['paper_id']}] {snippet}")
        parts.append("\n".join(lines))

    for rd in _rounds(lib, exp_id):
        report = rd / "report.md"
        if report.exists():
            parts.append(f"## PRIOR ROUND {rd.name}\n"
                         + report.read_text(encoding="utf-8")[:2000])
        outcome = rd / "outcome.md"
        if outcome.exists():
            parts.append(f"## OUTCOME of {rd.name} (user-recorded)\n"
                         + outcome.read_text(encoding="utf-8")[:1000])

    return "\n\n".join(p for p in parts if p.strip())


def compose(*, idea: str, evidence: str, lang: str = "zh",
            audit_base: Path | None = None):
    """House drafting loop: 1 corrective retry, sidecars before validation."""
    from llm.synthesize import _SRC_RE  # same marker contract

    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    system = system_tpl.format(
        lang_instruction=_LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"]))
    user = user_tpl.format(idea=idea, evidence=evidence)
    llm = LLM(role="text")
    for attempt in range(2):
        attempt_user = user if attempt == 0 else (
            user + "\n\nYour previous plan was missing the required [src: id] "
                   "grounding markers. Add one to every evidence-drawn claim.")
        resp = llm.chat(system=system, user=attempt_user,
                        temperature=0.4, max_tokens=4096)
        if audit_base is not None:
            base = Path(audit_base)
            base.parent.mkdir(parents=True, exist_ok=True)
            Path(str(base) + ".prompt.md").write_text(
                f"SYSTEM:\n{system}\n\nUSER:\n{attempt_user}", encoding="utf-8")
            Path(str(base) + ".response.json").write_text(
                json.dumps({"model": resp.model, "usage": resp.usage,
                            "content": resp.content},
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        report = resp.content.strip()
        if _SRC_RE.search(report):
            return report, resp
    raise SystemExit(
        "advise: LLM produced a plan without any [src: id] grounding "
        "markers twice (see the saved .response.json)")
