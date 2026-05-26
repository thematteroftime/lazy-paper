"""Wrapper around PDFFigures 2 (AI2) for caption-anchored figure numbering.

Used by stages/s04_figures when `--pdffigures2` is set. Subprocess-only;
never imported into the main pipeline's hot path. Docker-only by design
(project policy: no host JVM install).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


class SidecarUnavailable(RuntimeError):
    """Raised when the pdffigures2 docker image is not callable."""


# Match e.g. "Figure 3.", "Fig. 3a:", "Table 1 -" — strip from the start of a caption.
_CAPTION_PREFIX_RE = re.compile(
    r"^(?:Figure|Fig\.?|Table)\s*\d+[A-Za-z]?\.?\s*[:.\-]?\s*",
    re.IGNORECASE,
)


def parse_pdffigures2_output(raw: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Convert pdffigures2's JSON list into a {figures: [...], tables: [...]} split.

    Each entry gains:
      - figures: fig_id ('Fig. 1' canonical), caption (prefix stripped),
                 caption_raw, page, region (x1, y1, x2, y2)
      - tables: same shape with table_id ('Table 1')
    """
    figures: list[dict] = []
    tables: list[dict] = []
    for entry in raw:
        kind = entry.get("figType", "Figure")
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        caption_raw = str(entry.get("caption", "")).strip()
        caption_clean = _CAPTION_PREFIX_RE.sub("", caption_raw).strip()
        region = entry.get("regionBoundary", {})
        rec = {
            "page": entry.get("page", 0),
            "caption": caption_clean,
            "caption_raw": caption_raw,
            "region": (region.get("x1"), region.get("y1"),
                       region.get("x2"), region.get("y2")),
        }
        if kind == "Table":
            tables.append({**rec, "table_id": f"Table {name}"})
        else:
            figures.append({**rec, "fig_id": f"Fig. {name}"})
    return {"figures": figures, "tables": tables}


def _invoke_jar(pdf: Path) -> str:
    """Run PDFFigures 2 via the docker wrapper; return its JSON-array stdout.

    Docker-only by design. Set PDFFIGURES2_JAR=docker in .env after building
    the image once:
        docker build -f Dockerfile.pdffigures2 -t lazy-paper/pdffigures2:0.1.0 .
    """
    target = os.environ.get("PDFFIGURES2_JAR", "").strip()
    if target != "docker":
        raise SidecarUnavailable(
            "PDFFIGURES2_JAR must be 'docker' (no other paths supported); "
            "build the image with `docker build -f Dockerfile.pdffigures2 "
            "-t lazy-paper/pdffigures2:0.1.0 .` then set PDFFIGURES2_JAR=docker"
        )
    wrapper = Path(__file__).resolve().parent.parent / "vendor" / "pdffigures2.sh"
    if not wrapper.exists():
        raise SidecarUnavailable(f"missing wrapper: {wrapper}")
    try:
        cp = subprocess.run([str(wrapper), str(pdf.resolve())],
                            check=True, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:  # docker binary not in PATH
        raise SidecarUnavailable(f"docker not available: {e}") from e
    except subprocess.CalledProcessError as e:
        raise SidecarUnavailable(
            f"docker run exited {e.returncode}: {e.stderr[:200] if e.stderr else ''}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise SidecarUnavailable(f"docker run timed out after {e.timeout}s") from e
    return cp.stdout


def run_sidecar(pdf: Path) -> dict[str, list[dict]]:
    """End-to-end: invoke pdffigures2 and parse its output.

    Raises SidecarUnavailable if docker/image not callable — caller can
    decide to skip silently or warn.
    """
    raw_json = _invoke_jar(pdf)
    raw = json.loads(raw_json) if raw_json.strip() else []
    return parse_pdffigures2_output(raw)
