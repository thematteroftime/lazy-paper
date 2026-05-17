"""Stage completion marker (done.yaml)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from stages._common.yaml_io import dump_yaml


def mark_done(stage_path: Path, extra: dict[str, Any] | None = None) -> None:
    dump_yaml(stage_path / "done.yaml", {"finished_at": time.time(), **(extra or {})})


def is_done(stage_path: Path) -> bool:
    return (stage_path / "done.yaml").exists()
