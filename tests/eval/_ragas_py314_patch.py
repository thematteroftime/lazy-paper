"""py3.14 ragas-executor compatibility shim.

Called lazily from the test body (after ragas has been decided to run) to
avoid pulling in langchain/ragas during pytest collection.
"""
from __future__ import annotations

import asyncio


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
