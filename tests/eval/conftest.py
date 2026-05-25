"""Shared fixtures for the ragas eval harness.

Reads runs from `<repo-root>/runs/` (symlinked into the worktree). Wires
RAGAS's LLM and embeddings to the project's own LLM_* env (DeepSeek + DashScope)
so the harness doesn't silently fall back to OpenAI keys we don't have.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
import yaml

# Load .env at conftest import time so LLM_TEXT_* / LLM_VISION_* fixtures
# see the project's keys without needing to be `source`d into the shell.
# Top-level cli.py does the same trick at runtime.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env", override=False)
except ImportError:
    pass


def patch_ragas_executor_for_py314() -> None:
    """py3.14 ragas-executor monkey-patch — called lazily from the harness.

    ragas 0.1.21's Executor calls asyncio.as_completed(coros) OUTSIDE a running
    loop (line 38 of ragas/executor.py); the result is iterated inside an
    asyncio.run() block downstream. This pattern relied on py3.11's implicit
    default event loop. Python 3.14 made get_event_loop() strict — the
    pre-scheduled coros never attach to the loop asyncio.run creates, so
    they're destroyed unawaited and evaluate() hangs at 0/N forever.

    Patch: replace ragas.executor.Executor.results with a py3.14-safe variant
    that creates Tasks INSIDE the running loop. Caller invokes this AFTER it
    has decided ragas is going to run (don't import ragas during pytest
    collection — it pulls in langchain etc. and slows the whole suite).
    """
    import ragas.executor as _re

    def safe_results(self):
        async def _aresults():
            from tqdm.auto import tqdm
            coros = [afunc(*args, **kwargs)
                     for afunc, args, kwargs, _ in self.jobs]
            tasks = [asyncio.create_task(c) for c in coros]
            results = []
            for fut in tqdm(asyncio.as_completed(tasks),
                            desc=self.desc,
                            total=len(self.jobs),
                            leave=self.keep_progress_bar):
                r = await fut
                results.append(r)
            return results

        results = asyncio.run(_aresults())
        sorted_results = sorted(results, key=lambda x: x[0])
        return [r[1] for r in sorted_results]

    _re.Executor.results = safe_results


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
