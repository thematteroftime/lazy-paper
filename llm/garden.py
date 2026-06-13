"""Garden export: library -> window.GARDEN_EXPORT for frontend/garden.

The frontend computes ALL layout/links/indexes itself (see
frontend/garden/DATA_ADAPTER.md); this module only maps library data to the
documented shape and bakes it inline into garden.html (file:// fetch is
CORS-blocked, so build-time inlining — "方式 A" in the handoff doc).
Frontend assets are vendored pristine and never modified.
"""
from __future__ import annotations

import json
import re
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
            p["figures"] = []
            if figs_path.exists():
                for f in (load_yaml(figs_path) or [])[:20]:
                    if "fig_id" not in f:
                        continue
                    fig = {"id": f["fig_id"], "caption": f.get("caption", "")}
                    # archived image -> export-relative src (build() copies it)
                    rel = f.get("image_rel_path")
                    if rel:
                        img = lib.root / "papers" / pid / "imgs" / Path(rel).name
                        if img.exists():
                            fig["src"] = f"imgs/{pid}/{img.name}"
                    p["figures"].append(fig)

            # Copy the self-contained preview into the garden tree at build
            # time; the field is a RELATIVE path because browsers block file://
            # navigation outside the page's own directory.
            run_dir = entry.get("source_run")
            if run_dir and (Path(run_dir) / "s09_render" / "preview.html").exists():
                p["preview"] = f"previews/{pid}.html"
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

    out = {
        "manifest": {"papers": papers_out},
        "entities": entities_out,
        "relations": relations_out,
    }
    clusters = _domain_clusters(lib, papers_out)
    if clusters:
        out["clusters"] = clusters
    sections = {}
    for p in papers_out:
        s = _real_sections(lib, p["id"])
        if s:
            sections[p["id"]] = s
    if sections:
        out["sections"] = sections
    return out


def _chapter_index(lib, pid: str, source_run: str | None):
    """Real chapter list — prefer the archived copy (survives runs/ cleanup),
    fall back to the source run."""
    archived = lib.root / "papers" / pid / "chapter_index.yaml"
    if archived.exists():
        return load_yaml(archived) or []
    if source_run:
        p = Path(source_run) / "s03_chapter" / "chapter_index.yaml"
        if p.exists():
            return load_yaml(p) or []
    return []


def _real_sections(lib, pid: str) -> list[dict] | None:
    """Sections from the real chapter structure: titles from chapter_index,
    chunk counts from chunks.doc_name, entity ids from entities.doc — no
    fabricated IMRaD split. Returns None when chapter data is unavailable so
    the frontend keeps its heuristic fallback."""
    from collections import Counter

    entry = lib.papers().get(pid) or {}
    chapters = _chapter_index(lib, pid, entry.get("source_run"))
    if not chapters:
        return None

    chunk_n = Counter(
        r["doc_name"] for r in lib._db.open_table("chunks").to_arrow()
        .select(["paper_id", "doc_name", "is_parent"]).to_pylist()
        if r["paper_id"] == pid and not r["is_parent"])

    ent_by_doc: dict[str, list] = {}
    if "entities" in lib._db.table_names():
        for r in (lib._db.open_table("entities").to_arrow()
                  .select(["paper_id", "id", "doc"]).to_pylist()):
            if r["paper_id"] == pid:
                ent_by_doc.setdefault(r["doc"], []).append(r["id"])

    out = []
    for ch in chapters:
        if not isinstance(ch, dict) or not ch.get("file"):
            continue
        title = str(ch.get("title") or ch["file"])
        out.append({
            "num": str(ch.get("chapter_no", len(out))),
            "zh": title,   # no Chinese chapter title archived; English is real
            "en": title,
            "chunks": chunk_n.get(ch["file"], 0),
            "ents": ent_by_doc.get(ch["file"], []),
            "q": None,     # no per-chapter question is stored anywhere
        })
    return out or None


_KW_STOP = {"of", "and", "the", "for", "in", "with", "via", "to", "on",
            "based", "using", "a", "an", "from", "by", "multi"}


def _kw_tokens(keywords) -> set:
    toks = set()
    for k in keywords or []:
        for w in re.split(r"[^a-z0-9]+", str(k).lower()):
            if len(w) > 2 and w not in _KW_STOP:
                toks.add(w)
    return toks


def _domain_clusters(lib, papers: list[dict]) -> list[dict]:
    """Group papers by SHARED KEYWORD TOKENS — real domain descriptors the LLM
    extracted per paper. Two papers join when they share >=2 significant tokens
    (single union-find pass), so robotics / vision / LLM / each physics subfield
    separate cleanly; mean-pooled embeddings lump all of ML/CS together, which
    is why keywords are the better domain signal here. Cluster label = the
    members' most common token. Never leaves a paper unassigned (the frontend's
    only fallback is random)."""
    from collections import Counter

    tok = {p["id"]: _kw_tokens(p.get("keywords")) for p in papers}
    ids = [p["id"] for p in papers if tok[p["id"]]]
    if len(ids) < 2:
        return []

    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if len(tok[ids[i]] & tok[ids[j]]) >= 2:
                parent[find(ids[i])] = find(ids[j])

    groups: dict[str, list] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)

    kw_phrases = {p["id"]: (p.get("keywords") or []) for p in papers}
    clusters: list[dict] = []
    for members in sorted(groups.values(), key=len, reverse=True):
        c = Counter(w for m in members for w in tok[m])
        top, n = c.most_common(1)[0] if c else ("domain", 0)
        # a token shared by 2+ members names the domain; a lone paper is better
        # labelled by its own primary keyword phrase than a random token
        if n >= 2:
            label = top
        else:
            phrases = kw_phrases.get(members[0]) or [top]
            label = phrases[0]
        clusters.append({"key": label, "en": label, "zh": label,
                         "paper_ids": list(members)})

    # cap at 6 (frontend palette): fold any overflow into the largest cluster
    if len(clusters) > 6:
        for cl in clusters[6:]:
            clusters[0]["paper_ids"].extend(cl["paper_ids"])
        clusters = clusters[:6]

    # papers with no keyword tokens join the largest cluster, so the frontend
    # never falls back to random assignment
    placed = {m for cl in clusters for m in cl["paper_ids"]}
    rest = [p["id"] for p in papers if p["id"] not in placed]
    if rest and clusters:
        clusters[0]["paper_ids"].extend(rest)
    return clusters


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

    # Copy referenced figure images next to the page (src = imgs/<pid>/<name>)
    for paper in export["manifest"]["papers"]:
        for fig in paper.get("figures", []):
            src = fig.get("src")
            if not src:
                continue
            target = out_dir / src
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lib.root / "papers" / paper["id"] / "imgs" / Path(src).name,
                         target)

    # Copy each paper's self-contained preview.html into the garden tree, so
    # the panel's "open preview" link stays a same-directory navigation.
    manifest = lib.papers()
    for paper in export["manifest"]["papers"]:
        if "preview" not in paper:
            continue
        run_dir = (manifest.get(paper["id"]) or {}).get("source_run")
        src = Path(run_dir) / "s09_render" / "preview.html"
        if src.exists():
            target = out_dir / paper["preview"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    return html_src
