"""Cross-paper synthesis: topic -> grounded research-direction report.

Evidence comes from the library (manifest, archived context/fig_notes,
hybrid-retrieved chunks); one text-LLM call composes a markdown report whose
claims carry [src: paper_id] markers; a deterministic post-check flags markers
that don't resolve to library papers. Reports land in library/synth/<slug>/
with the standard audit sidecars.

s08 in-run library context is deliberately NOT part of this module — external
citations interact with the anchored-quote verifier and need their own design.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import LLM
from llm.template_author import _split_prompt  # same-package prompt helper
from stages._common import load_yaml, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "synthesize.md"
_SRC_RE = re.compile(r"\[src:\s*([^\]]+?)\s*\]")
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")

_LANG_INSTRUCTIONS = {
    "zh": "Write the report in Chinese (keep established English technical terms as-is).",
    "en": "Write the report in English (you may keep the five section headings bilingual).",
}


def _archived(lib, pid: str, name: str):
    p = lib.root / "papers" / pid / name
    return load_yaml(p) if p.exists() else None


def gather(lib, topic: str, *, papers: list[str] | None = None,
           top_k: int = 18) -> str:
    """Evidence block: manifest + archived context/fig notes + topic chunks."""
    manifest = lib.papers()
    if papers:
        scope = set(papers)
        manifest = {pid: e for pid, e in manifest.items() if pid in scope}
    if len(manifest) < 2:
        raise SystemExit(
            "synthesize: needs at least 2 ingested papers in scope "
            f"(have {len(manifest)}) — run `lazy-paper ingest` first")
    parts: list[str] = []
    for pid, e in manifest.items():
        lines = [f"## PAPER {pid}",
                 f"title: {e.get('title', '')}",
                 f"keywords: {', '.join(e.get('keywords') or [])}"]
        ctx = _archived(lib, pid, "context.yaml") or {}
        for q in (ctx.get("critical_questions") or [])[:3]:
            lines.append(f"critical question: {q}")
        # Real s06 schema: headline_metrics is a dict ({name: value});
        # tolerate a list for forward compatibility.
        hm = ctx.get("headline_metrics") or {}
        hm_items = ([f"{k}: {v}" for k, v in hm.items()]
                    if isinstance(hm, dict) else [str(x) for x in hm])
        for mtr in hm_items[:4]:
            lines.append(f"headline metric: {mtr}")
        fig_notes = _archived(lib, pid, "fig_notes.yaml") or []
        if not isinstance(fig_notes, list):
            fig_notes = []
        for n in fig_notes[:4]:
            if not isinstance(n, dict):
                continue
            obs = n.get("deep_observation") or n.get("visual_summary")
            if not obs and n.get("raw"):
                # s07's defensive-parse-failed shape ({error, fig_id, raw}):
                # the analysis lives in a fenced YAML string under `raw` —
                # 100% of current real archives look like this.
                inner = safe_parse_yaml(_FENCE_RE.sub("", str(n["raw"]).strip()))
                if isinstance(inner, dict):
                    obs = (inner.get("deep_observation")
                           or inner.get("visual_summary"))
            if obs:
                lines.append(f"figure {n.get('fig_id', '?')}: "
                             + " ".join(str(obs).split())[:300])
        parts.append("\n".join(lines))
    hits = lib.query(topic, top_k=top_k, papers=sorted(manifest))
    if hits:
        lines = ["## TOPIC-RELEVANT EXCERPTS"]
        for h in hits:
            snippet = " ".join(h["text"].split())[:400]
            lines.append(f"- [{h['paper_id']}] {snippet}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def compose(*, topic: str, evidence: str, lang: str = "zh",
            audit_base: Path | None = None):
    """Text-LLM call (1 corrective retry) -> (report_markdown, LLMResponse).

    Audit sidecars are persisted BEFORE the marker check, so a rejected
    report is always inspectable.
    """
    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    system = system_tpl.format(
        lang_instruction=_LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"]))
    user = user_tpl.format(topic=topic, evidence=evidence)
    llm = LLM(role="text")
    for attempt in range(2):
        attempt_user = user if attempt == 0 else (
            user + "\n\nYour previous report was missing the required "
                   "[src: paper_id] grounding markers. Add one to every "
                   "evidence-drawn claim.")
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
        "synthesize: LLM produced a report without any [src: paper_id] "
        "grounding markers twice (see the saved .response.json)")


def check_citations(report: str, known: set[str]) -> list[str]:
    """Paper ids referenced by [src: ...] that are NOT in the library."""
    cited: set[str] = set()
    for m in _SRC_RE.finditer(report):
        for part in m.group(1).split(","):
            # advise emits "[src: <id> <artifact>]" — the id is the first token
            tokens = part.strip().split()
            if tokens:
                cited.add(tokens[0])
    return sorted(c for c in cited if c not in known)
