"""lazy-paper CLI: orchestrates the 9 stages over (pdf, template) -> (bundle + preview)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _augment_dyld_for_macos_brew() -> None:
    """Help dyld find weasyprint's Homebrew-installed dependencies on macOS bare-metal.

    No-op on Linux (Docker) and Windows. See conftest.py for the test-time twin.
    """
    if sys.platform != "darwin":
        return
    candidates = ["/opt/homebrew/lib", "/usr/local/lib"]
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts: list[str] = []
    if existing:
        parts.append(existing)
    for path in candidates:
        if os.path.isdir(path) and path not in parts:
            parts.append(path)
    if parts:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


_augment_dyld_for_macos_brew()

from dotenv import load_dotenv

from stages._common import dump_yaml, load_yaml, slugify, stage_dir, is_done

import stages.s01_ocr.runner as _s01
import stages.s02_clean.runner as _s02
import stages.s03_chapter.runner as _s03
import stages.s04_figures.runner as _s04
import stages.s05_template.runner as _s05
import stages.s06_context.runner as _s06
import stages.s07_figure_analyze.runner as _s07
import stages.s08_section_compose.runner as _s08
import stages.s09_render.runner as _s09

STAGE_ORDER = [
    "s01_ocr", "s02_clean", "s03_chapter", "s04_figures",
    "s05_template", "s06_context", "s07_figure_analyze",
    "s08_section_compose", "s09_render",
]


def _parse_formats(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


def _load_done(path: Path) -> dict:
    try:
        result = load_yaml(path)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _is_partial_done(out: Path) -> bool:
    done = out / "done.yaml"
    return done.exists() and bool(_load_done(done).get("partial"))


def _print_done_summary(paper_id: str, duration_s: float, s09_dir: Path) -> None:
    done = s09_dir / "done.yaml"
    formats_str = "preview.docx (legacy fallback)"
    if done.exists():
        payload = _load_done(done)
        formats = payload.get("formats") or {}
        produced = [k for k, v in formats.items() if isinstance(v, str)]
        failed = [k for k, v in formats.items() if isinstance(v, dict) and "error" in v]
        parts = []
        if produced:
            parts.append("produced: " + ", ".join(sorted(produced)))
        if failed:
            parts.append("failed: " + ", ".join(sorted(failed)))
        if parts:
            formats_str = " | ".join(parts)
        if payload.get("partial"):
            formats_str = "[partial] " + formats_str
    print(f"[done] {paper_id} in {duration_s:.1f}s → {s09_dir} ({formats_str})")


def _resolve_formats_for_s09(args, out: Path) -> list[str] | None:
    if getattr(args, "retry_failed", False):
        done_path = out / "done.yaml"
        if done_path.exists():
            done = _load_done(done_path)
            failed = [k for k, v in (done.get("formats") or {}).items()
                      if isinstance(v, dict) and "error" in v]
            if failed:
                return failed
    return _parse_formats(args.formats)


def _run_one(args, name: str, run_root: Path, paper_id: str) -> None:
    out = stage_dir(run_root, paper_id, name)
    # s05_template: auto-invalidate cache when the source docx changes so an
    # edited template doesn't silently propagate as stale title text.
    stale_template = (
        name == "s05_template" and is_done(out) and not args.force
        and _s05.is_cache_stale(out, Path(args.template))
    )
    if stale_template:
        print(f"[s05_template] template content changed — invalidating cache", flush=True)
    if is_done(out) and not args.force and not stale_template \
            and not getattr(args, "retry_failed", False) \
            and not _is_partial_done(out):
        print(f"[skip] {name} (already done)")
        return
    if _is_partial_done(out) and not getattr(args, "retry_failed", False) and not args.force:
        print(f"[s09_render] WARNING: previous run was partial — rerunning to recover failed formats. "
              f"Use --retry-failed to rerun ONLY the failed ones.", file=sys.stderr, flush=True)
    print(f"[run]  {name}")
    if name == "s01_ocr":
        if args.skip_ocr:
            print("        --skip-ocr set; expecting upstream artifacts present")
            return
        backend = os.environ.get("OCR_BACKEND", "mineru").lower()
        if backend == "mineru":
            token = os.environ.get("MINERU_TOKEN")
            if not token:
                raise SystemExit("OCR_BACKEND=mineru but MINERU_TOKEN not set")
        else:
            token = os.environ.get("PADDLEOCR_TOKEN")
            if not token:
                raise SystemExit("OCR_BACKEND=paddleocr but PADDLEOCR_TOKEN not set")
        _s01.run(pdf=Path(args.pdf), out_dir=out, token=token, backend=backend,
                 ocr_lang=args.ocr_lang)
    elif name == "s02_clean":
        _s02.run(in_dir=stage_dir(run_root, paper_id, "s01_ocr"), out_dir=out)
    elif name == "s03_chapter":
        _s03.run(in_dir=stage_dir(run_root, paper_id, "s02_clean"), out_dir=out, min_chars=1)
    elif name == "s04_figures":
        _s04.run(
            docs_dir=stage_dir(run_root, paper_id, "s02_clean"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            out_dir=out,
            pdf=Path(args.pdf),
        )
        # v1.12 phase 1: PDFFigures 2 reconciliation (opt-in)
        if getattr(args, "pdffigures2", False):
            from scripts.pdffigures2_sidecar import run_sidecar, SidecarUnavailable
            from stages.s04_figures.runner import reconcile_with_pdffigures2
            try:
                pf2_payload = run_sidecar(Path(args.pdf))
                figures_path = out / "figures.yaml"
                if figures_path.exists():
                    figs = load_yaml(figures_path) or []
                    new_figs, report = reconcile_with_pdffigures2(figs, pf2_payload)
                    dump_yaml(figures_path, new_figs)
                    dump_yaml(out / "_pdffigures2.yaml", {"raw": pf2_payload, "report": report})
                    print(f"        [pdffigures2] renames={len(report['renames'])} "
                          f"keeps={len(report['keeps'])}", flush=True)
            except SidecarUnavailable as e:
                print(f"        [pdffigures2] skipped: {e}", file=sys.stderr, flush=True)
    elif name == "s05_template":
        _s05.run(template_docx=Path(args.template), out_dir=out)
    elif name == "s06_context":
        _s06.run(
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            out_dir=out,
        )
    elif name == "s07_figure_analyze":
        _s07.run(
            figures_dir=stage_dir(run_root, paper_id, "s04_figures"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            context_dir=stage_dir(run_root, paper_id, "s06_context"),
            out_dir=out,
            lang=args.lang,
        )
    elif name == "s08_section_compose":
        _s08.run(
            template_dir=stage_dir(run_root, paper_id, "s05_template"),
            chapters_dir=stage_dir(run_root, paper_id, "s03_chapter") / "chapters",
            context_dir=stage_dir(run_root, paper_id, "s06_context"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            figures_stage_dir=stage_dir(run_root, paper_id, "s04_figures"),
            out_dir=out,
            lang=args.lang,
        )
    elif name == "s09_render":
        from llm.citation import CitationMode
        formats = _resolve_formats_for_s09(args, out)
        _s09.run(
            compose_dir=stage_dir(run_root, paper_id, "s08_section_compose"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            context_dir=stage_dir(run_root, paper_id, "s06_context"),
            out_dir=out,
            paper_title=args.paper_id or Path(args.pdf).stem,
            lang=args.lang,
            formats=formats,
            pptx_bullets=args.pptx_bullets,
            pptx_template=getattr(args, "pptx_template", None),
            presenter=getattr(args, "presenter", None),
            affiliation=getattr(args, "affiliation", None),
            pptx_subtitle=getattr(args, "pptx_subtitle", None),
            # When --debug-citations is set, force KEEP everywhere (audit
            # trail mode). Otherwise pass None so the per-format default in
            # runner.py applies (html → HYPERLINK, others → REMOVE) — that
            # default was unreachable for CLI users before v1.9.2.1.
            citation_mode=(CitationMode.KEEP
                           if getattr(args, "debug_citations", False)
                           else None),
        )


def _cmd_ingest(args) -> int:
    from llm.library import Library
    lib = Library(args.library_dir)
    run_dir = Path(args.runs_dir) / slugify(args.paper_id)
    entry = lib.ingest(run_dir, kind=args.kind)
    print(f"[library] ingested {run_dir.name}: {entry['n_chunks']} chunks, "
          f"{entry['n_entities']} entities → {lib.root}")
    return 0


def _cmd_garden(args) -> int:
    from llm import garden
    from llm.library import Library

    lib = Library(args.library_dir)
    out_dir = Path(args.out) if args.out else lib.root / "garden"
    page = garden.build(lib, out_dir)
    manifest = lib.papers()
    n_papers = sum(1 for e in manifest.values() if e.get("kind", "paper") == "paper")
    n_exp = sum(1 for e in manifest.values() if e.get("kind") == "experiment")
    print(f"[garden] built {page} ({n_papers} papers, {n_exp} experiments)")
    if args.open:
        import webbrowser
        webbrowser.open(page.resolve().as_uri())
    return 0


def _cmd_advise(args) -> int:
    from llm import advise as adv
    from llm.library import Library
    from llm.synthesize import check_citations

    lib = Library(args.library_dir)
    if args.outcome:
        out = adv.record_outcome(lib, args.exp, args.outcome)
        print(f"[advise] outcome recorded → {out}")
        if not args.idea:
            return 0
    if not args.idea:
        raise SystemExit("advise: --idea is required (or use --outcome alone "
                         "to record a result)")
    evidence = adv.gather_evidence(lib, args.exp, idea=args.idea,
                                   top_k=args.top_k)
    round_dir = adv.next_round_dir(lib, args.exp)
    report_path = round_dir / "report.md"
    report, resp = adv.compose(idea=args.idea, evidence=evidence,
                               lang=args.lang, audit_base=report_path)
    # round_NN references are legitimate grounding alongside manifest ids
    known = set(lib.papers()) | {p.name for p in adv._rounds(lib, args.exp)}
    unknown = check_citations(report, known)
    round_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"[advise] {args.exp} {round_dir.name} → {report_path} "
          f"(model {resp.model})")
    if unknown:
        print(f"[advise] WARNING: [src:] markers not in library: "
              f"{', '.join(unknown)}")
    print()
    print(report)
    return 0


def _cmd_exp_ingest(args) -> int:
    from llm.experiment import analyze_curves, load_bundle
    from llm.library import Library

    bundle = Path(args.bundle)
    load_bundle(bundle)  # fail fast with a clear message
    if args.skip_vision:
        notes = []
        print("[exp] --skip-vision: curves not analyzed")
    else:
        notes = analyze_curves(bundle, lang=args.lang)
        print(f"[exp] analyzed {len(notes)} curve(s) "
              f"(cached in {bundle / 'exp_notes.yaml'})")
    lib = Library(args.library_dir)
    entry = lib.ingest_experiment(bundle, exp_id=args.id)
    print(f"[exp] ingested {args.id or bundle.name}: {entry['n_chunks']} chunks, "
          f"kind=experiment, linked papers: {', '.join(entry['papers']) or '—'} "
          f"→ {lib.root}")
    return 0


def _cmd_query(args) -> int:
    from llm.library import Library
    lib = Library(args.library_dir)
    raw = _parse_formats(args.papers)
    papers = [slugify(p) for p in raw] if raw else None
    hits = lib.query(args.text, top_k=args.top_k, papers=papers)
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("[library] no results (is anything ingested?)")
        return 0
    for h in hits:
        snippet = " ".join(h["text"].split())[:160]
        print(f"[{h['paper_id']}] {h['doc_name']} "
              f"chars {h['char_start']}-{h['char_end']} (score {h['score']})\n"
              f"    {snippet}")
    return 0


def _cmd_papers(args) -> int:
    from llm.library import Library
    manifest = Library(args.library_dir).papers()
    if not manifest:
        print("[library] empty")
        return 0
    for pid, e in manifest.items():
        print(f"{pid:32s} {e.get('kind', 'paper'):10s} "
              f"{e.get('n_chunks', 0):5d} chunks  {e.get('title', '')}")
    return 0


def _cmd_synthesize(args) -> int:
    from llm import synthesize as syn
    from llm.library import Library

    lib = Library(args.library_dir)
    raw = _parse_formats(args.papers)
    papers = [slugify(p) for p in raw] if raw else None
    evidence = syn.gather(lib, args.topic, papers=papers, top_k=args.top_k)

    out_dir = Path(args.out_dir) if args.out_dir else (
        lib.root / "synth" / slugify(args.topic, maxlen=40))
    report_path = out_dir / "report.md"
    if report_path.exists():
        print(f"[synthesize] overwriting existing {report_path}", flush=True)
    report, resp = syn.compose(topic=args.topic, evidence=evidence,
                               lang=args.lang, audit_base=report_path)
    unknown = syn.check_citations(report, set(lib.papers()))
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(f"[synthesize] wrote {report_path} "
          f"({len(report)} chars, model {resp.model})")
    if unknown:
        print(f"[synthesize] WARNING: [src:] markers not in library: "
              f"{', '.join(unknown)}")
    print()
    print(report)
    return 0


def _cmd_template(args) -> int:
    from llm import template_author as ta

    if args.run:
        digest = ta.prescan_run(Path(args.runs_dir) / slugify(args.run))
    else:
        pdf = Path(args.pdf)
        if not pdf.exists():
            raise SystemExit(f"--pdf {pdf} not found")
        digest = ta.prescan_pdf(pdf)

    lib_ctx = ""
    if args.use_library:
        from llm.library import Library
        lib_ctx = ta.library_context(Library(args.library_dir), args.idea)

    out = Path(args.out) if args.out else (
        Path("templates") / f"auto-{slugify(args.idea, maxlen=40)}.docx")
    if out.exists():
        print(f"[template] overwriting existing {out}", flush=True)
    # draft() persists <out>.prompt.md / <out>.response.json BEFORE validating,
    # so a rejected LLM response is always inspectable.
    sections, resp = ta.draft(idea=args.idea, paper_digest=digest,
                              library_context=lib_ctx, lang=args.lang,
                              n_sections=args.sections, audit_base=out)
    ta.write_docx(sections, out, idea=args.idea)
    nodes = ta.roundtrip_check(out, sections)

    print(f"[template] wrote {out} ({len(nodes)} sections, "
          f"{sum(len(s['questions']) for s in sections)} questions)")
    for i, sec in enumerate(sections, 1):
        print(f"  {i} {sec['title']}")
        for q in sec["questions"]:
            print(f"      · {q}")
    print(f"\n[template] review/edit the docx, then run:\n"
          f"  uv run python -m cli run --pdf <paper.pdf> --template \"{out}\" "
          f"--paper-id <id> --lang {args.lang}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lazy-paper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the full pipeline on one (pdf, template) pair")
    r.add_argument("--pdf", required=True)
    r.add_argument("--template", required=True)
    r.add_argument("--runs-dir", default="runs")
    r.add_argument("--paper-id", default=None)
    r.add_argument("--skip-ocr", action="store_true",
                   help="Assume s01_ocr outputs already exist in the run dir")
    r.add_argument("--force", action="store_true",
                   help="Re-run stages even if done.yaml is present")
    r.add_argument("--only", default=None,
                   help="Run only this single stage (e.g. s09_render) instead of all 9")
    r.add_argument("--lang", choices=("en", "zh"), default="zh",
                   help="Output language for LLM stages and render")
    r.add_argument("--ocr-lang", choices=("en", "zh"), default="en",
                   help="Source-document language sent to the OCR backend "
                        "(MinerU's `language` field). Default 'en' since "
                        "MinerU's English mode handles mixed-language papers "
                        "well; set 'zh' for CJK-heavy manuscripts where the "
                        "English pipeline drops characters. Independent of "
                        "--lang (which controls OUTPUT language).")
    r.add_argument("--formats", default=None,
                   help="Comma-separated subset of docx,pdf,html,pptx "
                        "(default: all four). PPTX uses extra LLM calls; "
                        "pass --formats docx,pdf,html to skip.")
    r.add_argument("--pptx-bullets", choices=("llm", "rule"), default="llm",
                   help="How PPT bullets are generated (llm = quality, rule = offline)")
    r.add_argument("--pptx-template", type=Path, default=None, metavar="PATH",
                   help="Optional .pptx file used as slide-master base for PPT output")
    r.add_argument("--presenter", default=None, metavar="STR",
                   help="Presenter name shown on the title slide")
    r.add_argument("--affiliation", default=None, metavar="STR",
                   help="Affiliation shown on the title slide")
    r.add_argument("--pptx-subtitle", default=None, metavar="STR",
                   help="Custom subtitle for title slide (default: derived from context.yaml keywords)")
    r.add_argument("--retry-failed", action="store_true",
                   help="In --only mode, re-run only the formats marked partial in done.yaml")
    r.add_argument("--debug-citations", action="store_true",
                   help="Keep [span:doc:start-end] citation markers in rendered output (default: strip)")
    r.add_argument("--pdffigures2", action="store_true",
                   help="v1.12: enable PDFFigures 2 sidecar for caption-anchored figure "
                        "renumbering (requires PDFFIGURES2_JAR=docker + a built "
                        "lazy-paper/pdffigures2:0.1.0 image). Off by default — opt-in until v1.13.")
    r.add_argument("--ingest", action="store_true",
                   help="v1.14: after the run, ingest results into the knowledge "
                        "library (see `lazy-paper ingest --help`). Opt-in.")

    li = sub.add_parser("ingest", help="Ingest a finished run into the knowledge library")
    li.add_argument("paper_id", help="Run name under --runs-dir (same as run --paper-id)")
    li.add_argument("--runs-dir", default="runs")
    li.add_argument("--kind", choices=("paper", "experiment"), default="paper",
                    help="'experiment' reserved for the v1.17 experiment loop")
    li.add_argument("--library-dir", default=None,
                    help="Library root (default: $LAZY_PAPER_LIBRARY_DIR or ./library)")

    lq = sub.add_parser("query", help="Hybrid search across all ingested papers")
    lq.add_argument("text")
    lq.add_argument("--top-k", type=int, default=8)
    lq.add_argument("--papers", default=None,
                    help="Comma-separated paper_id filter")
    lq.add_argument("--json", action="store_true",
                    help="Machine-readable output (for agents)")
    lq.add_argument("--library-dir", default=None)

    lp = sub.add_parser("papers", help="List ingested papers")
    lp.add_argument("--library-dir", default=None)

    lt = sub.add_parser("template",
                        help="Draft a question-template docx from your idea "
                             "(+ paper prescan, + optional library grounding)")
    lt.add_argument("--idea", required=True,
                    help="Your research lens — drives at least half the questions")
    src = lt.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", default=None,
                     help="New paper: cheap text-layer prescan (no OCR API)")
    src.add_argument("--run", default=None, metavar="PAPER_ID",
                     help="Existing run: reuse s02/s03/s04/s06 artifacts (richer)")
    lt.add_argument("--runs-dir", default="runs")
    lt.add_argument("--out", default=None,
                    help="Output docx (default templates/auto-<idea-slug>.docx)")
    lt.add_argument("--use-library", action="store_true",
                    help="Ground questions in the v1.14 knowledge library "
                         "(adds cross-paper comparison questions)")
    lt.add_argument("--library-dir", default=None)
    lt.add_argument("--lang", choices=("en", "zh"), default="zh")
    lt.add_argument("--sections", type=int, default=6)

    ls = sub.add_parser("synthesize",
                        help="Cross-paper synthesis: topic -> grounded "
                             "research-direction report from the library")
    ls.add_argument("--topic", required=True)
    ls.add_argument("--papers", default=None,
                    help="Comma-separated paper_id scope (default: whole library)")
    ls.add_argument("--top-k", type=int, default=18,
                    help="Topic-relevant excerpts pulled from the library")
    ls.add_argument("--out-dir", default=None,
                    help="Default <library>/synth/<topic-slug>/")
    ls.add_argument("--lang", choices=("en", "zh"), default="zh")
    ls.add_argument("--library-dir", default=None)

    le = sub.add_parser("exp-ingest",
                        help="v1.17: analyze + ingest an experiment bundle "
                             "(exp.yaml + curves + metrics + notes)")
    le.add_argument("bundle", help="Bundle directory (see docs: exp.yaml contract)")
    le.add_argument("--id", default=None, help="Override exp id (default: dir name)")
    le.add_argument("--lang", choices=("en", "zh"), default="zh")
    le.add_argument("--skip-vision", action="store_true",
                    help="Skip curve analysis (no vision LLM calls)")
    le.add_argument("--library-dir", default=None)

    la = sub.add_parser("advise",
                        help="v1.18: grounded next-iteration plan for an "
                             "ingested experiment (+ round memory)")
    la.add_argument("--exp", required=True, metavar="EXP_ID")
    la.add_argument("--idea", default=None,
                    help="Your current question / direction for this round")
    la.add_argument("--outcome", default=None,
                    help="Record what happened after the LAST round's advice "
                         "(stored as outcome.md; informs future rounds)")
    la.add_argument("--top-k", type=int, default=12)
    la.add_argument("--lang", choices=("en", "zh"), default="zh")
    la.add_argument("--library-dir", default=None)

    lg = sub.add_parser("garden",
                        help="v1.19: build the star-map knowledge garden "
                             "(static garden.html from the library)")
    lg.add_argument("--out", default=None,
                    help="Output dir (default <library>/garden/)")
    lg.add_argument("--open", action="store_true",
                    help="Open the built garden.html in the default browser")
    lg.add_argument("--library-dir", default=None)

    args = ap.parse_args(argv)

    load_dotenv(Path.cwd() / ".env", override=False)
    if args.cmd == "ingest":
        return _cmd_ingest(args)
    if args.cmd == "query":
        return _cmd_query(args)
    if args.cmd == "papers":
        return _cmd_papers(args)
    if args.cmd == "template":
        return _cmd_template(args)
    if args.cmd == "synthesize":
        return _cmd_synthesize(args)
    if args.cmd == "exp-ingest":
        return _cmd_exp_ingest(args)
    if args.cmd == "advise":
        return _cmd_advise(args)
    if args.cmd == "garden":
        return _cmd_garden(args)
    # Always slugify to prevent path traversal: --paper-id "../../tmp/x"
    # would otherwise let outputs land outside runs/.
    paper_id = slugify(args.paper_id) if args.paper_id else slugify(Path(args.pdf).stem)
    run_root = Path(args.runs_dir)
    run_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    stage_list = [s.strip() for s in args.only.split(",")] if args.only else STAGE_ORDER
    unknown = [s for s in stage_list if s not in STAGE_ORDER]
    if unknown:
        raise SystemExit(f"Unknown stage(s) in --only: {unknown}. Valid: {STAGE_ORDER}")
    for name in stage_list:
        _run_one(args, name, run_root, paper_id)

    meta = {
        "paper_id": paper_id,
        "pdf": str(Path(args.pdf).resolve()),
        "template": str(Path(args.template).resolve()),
        "runs_dir": str(run_root.resolve()),
        "stages_completed": STAGE_ORDER,
        "duration_s": time.time() - t0,
        # v1.11.1: persist `lang` so demo scripts and audits can verify
        # baseline language without re-reading every fig_notes.yaml.
        # Bug history: v1.10 baseline runs lacked this field, causing the
        # 7/15-paper bilingual contamination found in cycle 11.
        "lang": args.lang,
    }
    dump_yaml(run_root / paper_id / "meta.yaml", meta)
    if args.ingest:
        from llm.library import Library
        entry = Library().ingest(run_root / paper_id)
        print(f"[library] ingested {paper_id} ({entry['n_chunks']} chunks)")
    _print_done_summary(paper_id, meta["duration_s"], run_root / paper_id / "s09_render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
