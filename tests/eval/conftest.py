"""Shared fixtures for the ragas eval harness.

Reads runs from `<repo-root>/runs/` (symlinked into the worktree). Wires
RAGAS's LLM and embeddings to the project's own LLM_* env (DeepSeek + DashScope)
so the harness doesn't silently fall back to OpenAI keys we don't have.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


GOLDEN_DIR = Path(__file__).parent / "golden_qa"
RUNS_ROOT = Path(__file__).parent.parent.parent / "runs"
OUT_DIR = Path(__file__).parent / "_ragas_out"


@pytest.fixture(scope="session")
def golden_papers() -> list[dict]:
    """Yield {paper_id, items[], run_dir} for each golden_qa/*.yaml with a matching runs/ dir."""
    out = []
    for yml in sorted(GOLDEN_DIR.glob("*.yaml")):
        if yml.name.startswith("_"):
            continue
        data = yaml.safe_load(yml.read_text())
        run_dir = RUNS_ROOT / data["paper_id"]
        if not run_dir.exists():
            pytest.skip(f"runs/{data['paper_id']} not present — run the pipeline first")
        out.append({**data, "run_dir": run_dir})
    if not out:
        pytest.skip("no golden_qa/*.yaml found with matching runs/")
    return out


@pytest.fixture(scope="session")
def ragas_llm():
    """LangChain ChatOpenAI pointed at the project's text LLM (DeepSeek by default).

    RAGAS defaults to OpenAI; we override so the judge calls run through the
    same provider lazy-paper uses everywhere else.
    """
    base_url = os.environ.get("LLM_TEXT_BASE_URL")
    api_key = os.environ.get("LLM_TEXT_API_KEY")
    model = os.environ.get("LLM_TEXT_MODEL", "deepseek-chat")
    if not (base_url and api_key):
        pytest.skip("LLM_TEXT_BASE_URL / LLM_TEXT_API_KEY not set — ragas needs a live LLM judge")
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper
    chat = ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0.0,
        timeout=120,
    )
    return LangchainLLMWrapper(chat)


@pytest.fixture(scope="session")
def ragas_embeddings():
    """LangChain embeddings — reuse DashScope's text-embedding-v3 (LLM_VISION_* by fallback).

    Mirrors the `fallback_env_prefix: LLM_VISION` pattern in llm/models.yaml.
    """
    prefix = "LLM_EMBEDDINGS" if os.environ.get("LLM_EMBEDDINGS_API_KEY") else "LLM_VISION"
    base_url = os.environ.get(f"{prefix}_BASE_URL")
    api_key = os.environ.get(f"{prefix}_API_KEY")
    model = os.environ.get(f"{prefix}_EMBEDDING_MODEL", "text-embedding-v3")
    if not (base_url and api_key):
        pytest.skip(f"{prefix}_* embedding credentials not present")
    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    emb = OpenAIEmbeddings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        check_embedding_ctx_length=False,
    )
    return LangchainEmbeddingsWrapper(emb)
