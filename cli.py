"""lazy-paper CLI: orchestrates the 9 stages over (pdf, template) -> (bundle + preview)."""
from __future__ import annotations

import argparse
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
        _s01.run(pdf=Path(args.pdf), out_dir=out, token=token, backend=backend)
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
    args = ap.parse_args(argv)

    if args.cmd != "run":
        ap.print_help()
        return 1

    load_dotenv(Path.cwd() / ".env", override=False)
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
    _print_done_summary(paper_id, meta["duration_s"], run_root / paper_id / "s09_render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
