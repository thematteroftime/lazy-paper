"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename
"""
from stages._common.paths import slugify, stage_dir
from stages._common.yaml_io import load_yaml, dump_yaml, safe_parse_yaml
from stages._common.done import mark_done, is_done

__all__ = [
    "slugify", "stage_dir",
    "load_yaml", "dump_yaml", "safe_parse_yaml",
    "mark_done", "is_done",
]
