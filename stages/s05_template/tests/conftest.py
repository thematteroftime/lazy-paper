"""Shared fixtures for s05_template tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    # stages/s05_template/tests/ -> stages/s05_template/ -> stages/ -> repo root
    return Path(__file__).resolve().parent.parent.parent.parent
