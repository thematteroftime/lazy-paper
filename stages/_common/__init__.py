"""Shared stage helpers — backwards-compatible re-exports.

Modules:
- paths    : slugify, stage_dir
- yaml_io  : load_yaml, dump_yaml, safe_parse_yaml
- done     : mark_done, is_done
- bbox     : bbox_from_filename
"""
from stages._common.paths import slugify, stage_dir

__all__ = ["slugify", "stage_dir"]
