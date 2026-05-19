"""Stage 07: per-figure visual analysis using vision LLM. Outputs fig_notes.yaml."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from llm.client import LLM, max_tokens
from stages._common import dump_yaml, mark_done, safe_parse_yaml

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "figure_analyze.md"
FIG_NUM_RE = re.compile(r"Fig\.\s*(\d+)([a-z]?)")


def _excerpts(chapters_dir: Path, mentions: dict[str, list[str]], fig_id: str) -> str:
    m = FIG_NUM_RE.match(fig_id)
    if not m:
        return ""
    fig_num = m.group(1)
    pattern = re.compile(rf"\bFig(?:ure)?\.?\s*{fig_num}(?![0-9])", re.IGNORECASE)
    pieces: list[str] = []
    for ch_name, ids in mentions.items():
        if fig_id not in ids:
            continue
        ch_path = chapters_dir / ch_name
        if not ch_path.exists():
            continue
        paragraphs = re.split(r"\n\s*\n", ch_path.read_text(encoding="utf-8"))
        for i, p in enumerate(paragraphs):
            if pattern.search(p):
                start = max(0, i - 1)
                end = min(len(paragraphs), i + 2)
                pieces.append("\n\n".join(paragraphs[start:end]))
    return "\n\n---\n\n".join(pieces)[:6000]


def _split_prompt(template: str) -> tuple[str, str]:
    sys_idx = template.index("SYSTEM:") + len("SYSTEM:")
    usr_idx = template.index("USER:")
    return template[sys_idx:usr_idx].strip(), template[usr_idx + len("USER:"):].strip()


def _fid_to_filename(fig_id: str) -> str:
    return re.sub(r"[^\w-]+", "_", fig_id).strip("_")


LANG_INSTRUCTIONS = {
    "zh": "Write all free-form text fields (visual_summary, claim notes, deep_observation, caption) in Chinese (with English technical terms in parentheses where helpful). Keep field names exactly as listed.",
    "en": "Write all free-form text fields (visual_summary, claim notes, deep_observation, caption) in English. Keep field names exactly as listed.",
}


def run(*, figures_dir: Path, chapters_dir: Path, context_dir: Path, out_dir: Path,
        lang: str = "zh") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = yaml.safe_load((figures_dir / "figures.yaml").read_text(encoding="utf-8"))
    mentions = yaml.safe_load((figures_dir / "mentions.yaml").read_text(encoding="utf-8")) or {}
    context = yaml.safe_load((context_dir / "context.yaml").read_text(encoding="utf-8")) or {}

    system_tpl, user_tpl = _split_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    lang_text = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["zh"])
    system_tpl = system_tpl.replace("{lang_instruction}", lang_text)
    user_tpl = user_tpl.replace("{lang_instruction}", lang_text)
    paper_context_str = yaml.safe_dump(context, allow_unicode=True, sort_keys=False)

    # Group figures by fig_id (sub-panels of the same figure are kept together)
    by_fig: dict[str, list[dict]] = {}
    for f in figures:
        fid = f.get("fig_id", "")
        if not fid.startswith("Fig."):
            continue
        by_fig.setdefault(fid, []).append(f)

    llm = LLM(role="vision")
    notes: list[dict] = []

    # Stable order by fig number
    def _fig_sort_key(fid: str) -> tuple:
        m = re.match(r"Fig\.\s*(\d+)([a-z]?)", fid)
        return (int(m.group(1)) if m else 999, m.group(2) if m else "")

    for fid in sorted(by_fig.keys(), key=_fig_sort_key):
        entries = by_fig[fid]
        # Use the longest caption among the entries as canonical
        caption = max((e.get("caption", "") for e in entries), key=len, default="")
        excerpts = _excerpts(chapters_dir, mentions, fid)
        # Collect all image paths (sub-panels)
        img_paths: list[Path] = []
        for e in entries:
            p = Path(e.get("image_abs_path", ""))
            if not p.exists():
                p = figures_dir / e.get("image_rel_path", "")
            if p.exists():
                img_paths.append(p)
        # Note in prompt if multiple sub-panels exist
        panel_note = ""
        if len(img_paths) > 1:
            panel_note = (
                f"\n\nNote: This figure has {len(img_paths)} sub-panels. "
                "Treat them collectively as ONE figure; refer to them as panel (a), (b), etc. "
                "based on their visible labels.\n"
            )
        user_msg = (user_tpl
                    .replace("{paper_context}", paper_context_str)
                    .replace("{fig_id}", fid)
                    .replace("{caption}", caption + panel_note)
                    .replace("{chapter_excerpts}", excerpts))
        fname = _fid_to_filename(fid)
        (out_dir / f"{fname}.prompt.md").write_text(
            f"# SYSTEM\n{system_tpl}\n\n# USER\n{user_msg}\n\n# IMAGES\n" +
            "\n".join(str(p) for p in img_paths),
            encoding="utf-8",
        )
        response = llm.chat(
            system=system_tpl, user=user_msg,
            images=img_paths if img_paths else [],
            max_tokens=max_tokens(4000),
        )
        (out_dir / f"{fname}.response.json").write_text(
            json.dumps({"model": response.model, "latency_ms": response.latency_ms,
                        "usage": response.usage, "content": response.content,
                        "n_images_sent": len(img_paths)},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parsed = safe_parse_yaml(response.content)
        if parsed is None:
            notes.append({"fig_id": fid, "error": "yaml-parse: defensive parse failed",
                          "image_paths": [str(p) for p in img_paths],
                          "raw": response.content})
        else:
            parsed.setdefault("fig_id", fid)
            # Keep ALL image paths so s09 can render them as a block
            parsed["image_paths"] = [str(p) for p in img_paths]
            # Backward-compat: image_abs_path = first path
            parsed["image_abs_path"] = str(img_paths[0]) if img_paths else ""
            notes.append(parsed)

    dump_yaml(out_dir / "fig_notes.yaml", notes)
    mark_done(out_dir, {"figures": len(notes)})
    return {"figures": len(notes)}
