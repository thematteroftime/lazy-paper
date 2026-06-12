"""Garden export: library -> window.GARDEN_EXPORT for frontend/garden.

The frontend computes ALL layout/links/indexes itself (see
frontend/garden/DATA_ADAPTER.md); this module only maps library data to the
documented shape and bakes it inline into garden.html (file:// fetch is
CORS-blocked, so build-time inlining — "方式 A" in the handoff doc).
Frontend assets are vendored pristine and never modified.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from stages._common import load_yaml

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend" / "garden"

_SCRIPT_MARKER = '<script src="garden-data.js"></script>'


def export_data(lib) -> dict:
    """Map library to GARDEN_EXPORT shape.  Never touches lib._db when manifest is empty."""
    manifest = lib.papers()  # safe: never creates dirs

    if not manifest:
        return {"manifest": {"papers": []}, "entities": {}, "relations": {}}

    papers_out = []
    for pid, entry in manifest.items():
        p: dict = {
            "id": pid,
            "title": entry.get("title") or pid,
            "lang": entry.get("lang") or "zh",
            "n_chunks": entry.get("n_chunks") or 0,
            "n_entities": entry.get("n_entities") or 0,
            "total_tokens": entry.get("total_tokens") or 0,
            "keywords": entry.get("keywords") or [],
            "kind": entry.get("kind") or "paper",
        }
        # ingested_at: epoch float -> ISO-8601 UTC string
        raw_ts = entry.get("ingested_at")
        if raw_ts is not None:
            p["ingested_at"] = (
                datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )

        # papers only: questions from context.yaml, figures from figures.yaml
        if entry.get("kind", "paper") == "paper":
            ctx_path = lib.root / "papers" / pid / "context.yaml"
            if ctx_path.exists():
                ctx = load_yaml(ctx_path) or {}
                p["questions"] = (ctx.get("critical_questions") or [])
            else:
                p["questions"] = []

            figs_path = lib.root / "papers" / pid / "figures.yaml"
            if figs_path.exists():
                raw_figs = load_yaml(figs_path) or []
                p["figures"] = [
                    {"id": f["fig_id"], "caption": f.get("caption", "")}
                    for f in raw_figs
                    if "fig_id" in f
                ][:20]
            else:
                p["figures"] = []
        else:
            p["questions"] = []
            p["figures"] = []

        papers_out.append(p)

    # entities and relations from LanceDB
    entities_out: dict[str, list] = {}
    relations_out: dict[str, list] = {}

    has_entities = "entities" in lib._db.table_names()
    has_relations = "relations" in lib._db.table_names()

    if has_entities:
        for row in lib._db.open_table("entities").to_arrow().to_pylist():
            pid = row["paper_id"]
            entities_out.setdefault(pid, []).append({
                "id": row["id"],
                "type": row["type"],
                "text": row["text"],
            })

    if has_relations:
        for row in lib._db.open_table("relations").to_arrow().to_pylist():
            pid = row["paper_id"]
            relations_out.setdefault(pid, []).append(
                [row["subject"], row["predicate"], row["object"]]
            )

    return {
        "manifest": {"papers": papers_out},
        "entities": entities_out,
        "relations": relations_out,
    }


def build(lib, out_dir: Path) -> Path:
    """Copy frontend/garden/ (minus DATA_ADAPTER.md) into out_dir, inject
    GARDEN_EXPORT inline, write garden-export.json. Return path to garden.html."""
    export = export_data(lib)
    if not export["manifest"]["papers"]:
        raise SystemExit("garden: library is empty — ingest something first")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy all frontend assets except DATA_ADAPTER.md
    for src in FRONTEND_DIR.iterdir():
        if src.name == "DATA_ADAPTER.md":
            continue
        shutil.copy2(src, out_dir / src.name)

    # Inject inline export into garden.html before <script src="garden-data.js">
    html_src = out_dir / "garden.html"
    html = html_src.read_text(encoding="utf-8")
    if _SCRIPT_MARKER not in html:
        raise SystemExit(
            f"garden: expected marker '{_SCRIPT_MARKER}' not found in garden.html "
            f"— frontend file may have changed shape"
        )
    inline_block = (
        f'<script>\nwindow.GARDEN_EXPORT = '
        f'{json.dumps(export, ensure_ascii=False)};\n</script>\n'
    )
    html = html.replace(_SCRIPT_MARKER, inline_block + _SCRIPT_MARKER)
    html_src.write_text(html, encoding="utf-8")

    # Also write the JSON for http-served users
    (out_dir / "garden-export.json").write_text(
        json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return html_src
