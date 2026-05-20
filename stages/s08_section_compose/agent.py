"""Section composer agent — pydantic-ai with 4 tools.

Tools:
  - query_kg     : list entities by type, optionally filtered
  - retrieve     : hybrid retrieval with optional entity-span boost
  - check_source : substring + unit-normalized lookup
  - emit_section : terminal call; returns the draft
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from llm.client import LLM
from llm.paper_kg import PaperKG
from llm.retriever import Retriever


_CITATION_PAT = re.compile(r"\[span:[^\]]+:\d+-\d+\]")


_SECTION_SYS_PROMPT = """You are composing one section of a research-paper deep analysis.

Available tools:
- query_kg(entity_type, filter): list paper entities of a closed type.
- retrieve(query, top_k, entity_boost): get relevant source chunks.
- check_source(claim, expected_value): verify a quote/value is in source.
- emit_section(draft): terminal — return the final draft.

Workflow per section:
1. Use query_kg + retrieve to gather evidence relevant to this section's guidance.
2. For each numeric/quoted claim you plan to write, call check_source first.
3. Compose the draft, attaching [span:doc_name:start-end] markers to claims.
4. Call emit_section with the final draft. At least one [span:...] marker is required.

Never invent numbers, units, or claims not in the evidence.
"""


@dataclass
class SectionContext:
    kg: PaperKG
    retriever: Retriever


def _validate_emit(draft: str) -> None:
    if not _CITATION_PAT.search(draft):
        raise ValueError("draft must contain at least one [span:doc:start-end] marker")


def _build_agent() -> Agent:
    llm = LLM(role="text")
    provider = OpenAIProvider(
        base_url=str(llm._client.base_url),
        api_key=llm._client.api_key,
    )
    model = OpenAIChatModel(llm.model, provider=provider)
    agent: Agent[SectionContext, str] = Agent(
        model,
        deps_type=SectionContext,
        output_type=str,
        system_prompt=_SECTION_SYS_PROMPT,
    )

    @agent.tool
    async def query_kg(ctx: RunContext[SectionContext], entity_type: str,
                       filter: dict | None = None) -> list[dict]:
        return [e.model_dump() for e in ctx.deps.kg.query(entity_type, filter)]

    @agent.tool
    async def retrieve(ctx: RunContext[SectionContext], query: str,
                       top_k: int = 8,
                       entity_boost: list[str] | None = None) -> list[dict]:
        spans = []
        if entity_boost:
            ids = set(entity_boost)
            spans = [e.source_span for e in ctx.deps.kg.entities if e.id in ids]
        chunks = ctx.deps.retriever.retrieve(query, top_k=top_k, entity_spans=spans)
        return [c.to_dict() for c in chunks]

    @agent.tool
    async def check_source(ctx: RunContext[SectionContext], claim: str,
                           expected_value: str | None = None) -> dict:
        return ctx.deps.retriever.check_claim(claim, expected_value)

    @agent.tool
    async def emit_section(ctx: RunContext[SectionContext], draft: str) -> str:
        _validate_emit(draft)
        return draft

    return agent


def run_section_agent(*, section: dict, kg: PaperKG, retriever: Retriever,
                      prior_bullet: str, max_iters: int = 8) -> str:
    agent = _build_agent()
    ctx = SectionContext(kg=kg, retriever=retriever)
    user_msg = (
        f"Section title: {section['title']}\n"
        f"Guidance: {section.get('guidance', '')}\n"
        f"Prior section's lead bullet: {prior_bullet or '(none)'}\n\n"
        "Compose this section, then call emit_section."
    )
    result = agent.run_sync(user_msg, deps=ctx)
    return result.output
