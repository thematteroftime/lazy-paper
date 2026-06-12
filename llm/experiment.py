"""Experiment bundles (v1.17): validate, deep-read curves, build corpus.

A bundle is a user-authored directory (exp.yaml + curves + metrics CSV +
notes). `analyze_curves` runs the vision LLM once per plot (cached in
exp_notes.yaml inside the bundle, audit sidecars beside it); `build_corpus`
flattens everything into text for Library.ingest_experiment to chunk+embed.
Videos are deferred: planned path is ffmpeg keyframe sampling (Docker), the
frames then reuse exactly this curve pipeline.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from llm.client import LLM
from llm.template_author import _split_prompt  # same-package prompt helper
from stages._common import dump_yaml, load_yaml, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "exp_curve.md"

_LANG_INSTRUCTIONS = {
    "zh": "Respond in Chinese (keep axis labels / technical terms as-is).",
    "en": "Respond in English.",
}
_IMG_GLOBS = ("*.png", "*.jpg", "*.jpeg", "curves/*.png", "curves/*.jpg",
              "curves/*.jpeg")


def load_bundle(bundle_dir: Path) -> dict:
    p = Path(bundle_dir) / "exp.yaml"
    if not p.exists():
        raise SystemExit(f"{p} not found — an experiment bundle needs an "
                         f"exp.yaml manifest (title/env/software/hyperparams/"
                         f"papers/date)")
    meta = load_yaml(p)
    if not isinstance(meta, dict) or not meta.get("title"):
        raise SystemExit(f"{p}: needs at least a `title` field")
    return meta


def _images(bundle_dir: Path) -> list[Path]:
    seen: list[Path] = []
    for g in _IMG_GLOBS:
        seen.extend(sorted(Path(bundle_dir).glob(g)))
    return seen


def summarize_metrics(bundle_dir: Path) -> str:
    """Deterministic digest of every *.csv: per numeric column min/max/last."""
    out: list[str] = []
    for f in sorted(Path(bundle_dir).glob("*.csv")):
        try:
            rows = list(csv.DictReader(f.read_text(encoding="utf-8").splitlines()))
        except Exception:
            continue
        if not rows:
            continue
        cols: dict[str, list[float]] = {}
        for r in rows:
            for k, v in r.items():
                try:
                    cols.setdefault(k, []).append(float(v))
                except (TypeError, ValueError):
                    pass
        parts = [f"{f.name}: rows={len(rows)}"]
        for k, vals in cols.items():
            if vals:
                parts.append(f"{k}: min={min(vals):g} max={max(vals):g} "
                             f"last={vals[-1]:g}")
        out.append("; ".join(parts))
    return "\n".join(out)


def analyze_curves(bundle_dir: Path, *, lang: str = "zh") -> list[dict]:
    """Vision LLM per plot -> exp_notes.yaml (cache: skip if file exists)."""
    bundle_dir = Path(bundle_dir)
    notes_path = bundle_dir / "exp_notes.yaml"
    if notes_path.exists():
        return load_yaml(notes_path) or []
    images = _images(bundle_dir)
    if not images:
        return []
    meta = load_bundle(bundle_dir)
    exp_context = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    system = system_tpl.format(
        lang_instruction=_LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"]))
    user = user_tpl.format(exp_context=exp_context)
    llm = LLM(role="vision")
    notes: list[dict] = []
    for img in images:
        resp = llm.chat(system=system, user=user, images=[img],
                        temperature=0.2, max_tokens=1500)
        stem = img.stem
        (bundle_dir / f"exp_notes.{stem}.prompt.md").write_text(
            f"SYSTEM:\n{system}\n\nUSER:\n{user}\n\nIMAGE: {img.name}",
            encoding="utf-8")
        (bundle_dir / f"exp_notes.{stem}.response.json").write_text(
            json.dumps({"model": resp.model, "usage": resp.usage,
                        "content": resp.content}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        parsed = safe_parse_yaml(resp.content.strip()) or {}
        if not isinstance(parsed, dict):
            parsed = {}
        notes.append({
            "image": str(img.relative_to(bundle_dir)),
            "visual_summary": str(parsed.get("visual_summary", "")),
            "deep_observation": str(parsed.get("deep_observation", "")),
            "anomalies": parsed.get("anomalies") or [],
        })
    dump_yaml(notes_path, notes)
    return notes


def build_corpus(bundle_dir: Path) -> str:
    """Flatten the bundle into one text document for chunk+embed."""
    bundle_dir = Path(bundle_dir)
    meta = load_bundle(bundle_dir)
    parts = ["## EXPERIMENT MANIFEST",
             yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)]
    notes_md = sorted(bundle_dir.glob("*.md"))
    for n in notes_md:
        parts.append(f"## NOTES {n.name}\n" + n.read_text(encoding="utf-8"))
    digest = summarize_metrics(bundle_dir)
    if digest:
        parts.append("## METRICS DIGEST\n" + digest)
    for note in (load_yaml(bundle_dir / "exp_notes.yaml")
                 if (bundle_dir / "exp_notes.yaml").exists() else []) or []:
        if isinstance(note, dict):
            parts.append(
                f"## CURVE {note.get('image', '?')}\n"
                f"{note.get('visual_summary', '')}\n"
                f"{note.get('deep_observation', '')}\n"
                + "\n".join(f"anomaly: {a}" for a in (note.get("anomalies") or [])))
    return "\n\n".join(p for p in parts if p.strip())
