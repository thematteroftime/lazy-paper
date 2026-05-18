"""Repo-level pytest config: make weasyprint loadable on macOS bare-metal.

WeasyPrint needs Pango/Cairo/gdk-pixbuf libraries. On macOS they're installed
to /opt/homebrew/lib via `brew install pango gdk-pixbuf libffi cairo`, but the
system dyld doesn't search there by default. We append Homebrew lib paths to
DYLD_FALLBACK_LIBRARY_PATH so pytest subprocesses (and tests that import
weasyprint) can find the .dylibs.

This is a no-op on Linux (used in Docker) since system libs live at standard
paths the dynamic linker already searches.
"""
from __future__ import annotations

import os
import sys


def _augment_dyld_for_macos_brew() -> None:
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
