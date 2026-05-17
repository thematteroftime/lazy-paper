"""paper2md CLI: orchestrates the 9 stages over (pdf, template) -> (bundle + preview)."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from stages._common import dump_yaml, slugify, stage_dir, is_done

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


def _run_one(args, name: str, run_root: Path, paper_id: str) -> None:
    out = stage_dir(run_root, paper_id, name)
    if is_done(out) and not args.force:
        print(f"[skip] {name} (already done)")
        return
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
        _s09.run(
            compose_dir=stage_dir(run_root, paper_id, "s08_section_compose"),
            fig_notes_dir=stage_dir(run_root, paper_id, "s07_figure_analyze"),
            out_dir=out,
            paper_title=args.paper_id or Path(args.pdf).stem,
            lang=args.lang,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paper2md")
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
    r.add_argument("--lang", choices=("en", "zh"), default="zh",
                   help="Output language for LLM stages and render")
    args = ap.parse_args(argv)

    if args.cmd != "run":
        ap.print_help()
        return 1

    load_dotenv(Path.cwd() / ".env", override=False)
    paper_id = args.paper_id or slugify(Path(args.pdf).stem)
    run_root = Path(args.runs_dir)
    run_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    for name in STAGE_ORDER:
        _run_one(args, name, run_root, paper_id)

    meta = {
        "paper_id": paper_id,
        "pdf": str(Path(args.pdf).resolve()),
        "template": str(Path(args.template).resolve()),
        "runs_dir": str(run_root.resolve()),
        "stages_completed": STAGE_ORDER,
        "duration_s": time.time() - t0,
    }
    dump_yaml(run_root / paper_id / "meta.yaml", meta)
    print(f"[done] {paper_id} in {meta['duration_s']:.1f}s → {run_root / paper_id / 's09_render' / 'preview.docx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
