"""Throwaway smoke test — confirms ragas wiring before we build the harness."""
import pytest

pytestmark = pytest.mark.ragas


def test_ragas_imports():
    from ragas.metrics import faithfulness, context_recall, context_precision
    assert all(callable(m) or hasattr(m, "name") for m in [
        faithfulness, context_recall, context_precision,
    ])
