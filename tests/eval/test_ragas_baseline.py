"""RAGAS faithfulness / context_recall / context_precision against golden_qa.

Runs only when invoked explicitly:
    uv run pytest -m ragas tests/eval/test_ragas_baseline.py -v -s

Writes per-paper score JSON to tests/eval/_ragas_out/<paper_id>.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ragas


def _load_chapter_chunks(run_dir: Path, expected_chunks: list[str]) -> list[str]:
    """Each entry: 'chapter_xxx.md' or 'chapter_xxx.md:START-END' (char range)."""
    chapters_dir = run_dir / "s03_chapter" / "chapters"
    out = []
    for spec in expected_chunks:
        if ":" in spec:
            fname, span = spec.split(":")
            start, end = (int(x) for x in span.split("-"))
        else:
            fname, start, end = spec, None, None
        text = (chapters_dir / fname).read_text()
        out.append(text[start:end] if start is not None else text)
    return out


def _load_answer(run_dir: Path) -> str:
    """Concatenate s08 composed prose — what we score 'does it answer Q?' against."""
    compose_dir = run_dir / "s08_section_compose" / "chapters"
    return "\n\n".join(p.read_text() for p in sorted(compose_dir.glob("*.md")))


def test_ragas_scores(golden_papers, ragas_llm, ragas_embeddings):
    """For each golden paper compute faithfulness/context_recall/context_precision + dump JSON."""
    import asyncio

    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness, context_recall, context_precision

    # py3.14 + ragas-0.1.21 compatibility (see conftest docstring for the why).
    # We patch lazily from the test body — not at conftest load time — so the
    # rest of the suite doesn't pay the langchain import cost during
    # collection. ragas/langchain imports up there take ~4 minutes.
    from tests.eval._ragas_py314_patch import patch_ragas_executor_for_py314
    patch_ragas_executor_for_py314()
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    out_dir = Path(__file__).parent / "_ragas_out"
    out_dir.mkdir(exist_ok=True)

    # Cache the compose-stage output per paper; ragas asks 20 questions × same answer corpus.
    answer_corpus_cache: dict[str, str] = {
        p["paper_id"]: _load_answer(p["run_dir"]) for p in golden_papers
    }

    for paper in golden_papers:
        rows = []
        full_answer = answer_corpus_cache[paper["paper_id"]]
        for item in paper["items"]:
            rows.append({
                "question": item["question"].strip(),
                "answer": full_answer,
                "contexts": _load_chapter_chunks(paper["run_dir"], item["expected_chunks"]),
                "ground_truth": item["ground_truth"].strip(),
            })
        ds = Dataset.from_list(rows)
        result = evaluate(
            ds,
            metrics=[faithfulness, context_recall, context_precision],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )
        scores = {k: float(v) for k, v in result.to_pandas().mean(numeric_only=True).items()}
        payload = {
            "paper_id": paper["paper_id"],
            "n_questions": len(rows),
            "scores": scores,
        }
        (out_dir / f"{paper['paper_id']}.json").write_text(json.dumps(payload, indent=2))
        # Soft sanity guard — these are baseline, not pass/fail. Just assert non-zero so we
        # catch a totally broken run before downstream comparisons.
        assert scores.get("faithfulness", 0) > 0, (
            f"{paper['paper_id']} faithfulness == 0 — check ragas LLM wiring"
        )
