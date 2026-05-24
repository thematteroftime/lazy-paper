# v1.10 — External Reference Survey

> Date: 2026-05-22
> Spec: docs/superpowers/specs/2026-05-22-v1_10-variant-test-design.md §11.1

## Purpose

Avoid 闭门造车 (closed-door reinvention) — put v1.10 variant designs in
context with how 6 open-source systems handle the same problems
(figure citation / quote grounding / coverage / informed-retry).

---

## Per-system summaries

### STORM (Stanford OVAL)

- **Source**: https://github.com/stanford-oval/storm (MIT license)
- **Paper / design**: "Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models" — arXiv:2402.14207, NAACL 2024. Authors: Yijia Shao, Yucheng Jiang, Theodore A. Kanell, Peter Xu, Omar Khattab, Monica S. Lam.
- **What it does**: STORM generates long-form, Wikipedia-style articles on arbitrary topics. It first runs a multi-agent pre-writing stage that discovers diverse perspectives and simulates expert conversations grounded in web sources, then curates an outline, and finally writes a full article with citations. Human Wikipedia editors rated its output 25% more organized and 10% broader in coverage than outline-driven RAG baselines.
- **Mechanism**: Two-stage outline-then-write pipeline. Stage 1: perspective discovery (by examining similar existing articles) → simulated conversation between a writer-agent (from that perspective) and a topic-expert-agent (grounded in retrieved web pages) → structured outline. Stage 2: multi-LM system (cheaper fast models for conversation / query splitting, stronger model for the final cited article). Co-STORM extension adds a Moderator agent and a live human participant steering a "mind map" of hierarchically organized information.
- **Citation grounding**: Claims are tied back to sources at response-generation time inside the simulated conversations. The expert-agent's answers are directly anchored to retrieved web pages (not fabricated), so citations are inline from the start rather than added post-hoc. The DSPy framework is used to wire retrieval and generation together in a modular way.
- **Figure binding**: Not a primary concern — STORM targets text-only Wikipedia-style articles; no figure citation or image binding mechanism is described.
- **Informed-retry**: No explicit retry loop. Perspective diversity is the mechanism for coverage: multiple writer-agents with different viewpoints independently probe the topic expert, and the union of their conversations determines outline breadth.
- **What we can borrow**:
  - Multi-perspective probing as a coverage mechanism — parallels lazy-paper's best-of-N approach for `compose_structured`; variant B's per-comparator cap increase effectively expands the "perspective" each LLM call is allowed to cover.
  - Outline-first discipline: STORM's pre-writing outline corresponds directly to lazy-paper's s05_outline stage feeding s08_section_compose. The design principle (structure before prose) is well validated.
  - Cheaper-model / expensive-model split across pipeline stages — matches lazy-paper's architecture where OCR/context stages use smaller models and s08 uses the strongest available model.
- **Where we diverge**:
  - STORM targets general web topics; lazy-paper targets a single scientific PDF with rich internal structure (sections, figures, tables). The retrieval corpus is the paper itself, not the web.
  - STORM has no concept of figure binding or image citation — our variant C is entirely novel in this space relative to STORM.
  - STORM does not verify or score its own drafts; lazy-paper's `verify_section_draft` verifier + `retry-when-short` / `retry-when-empty` loops have no STORM equivalent.

---

### OpenScholar (AI2)

- **Source**: https://github.com/AkariAsai/OpenScholar (open-source; Llama 3.1 8B fine-tune + retrieval infrastructure)
- **Paper / design**: "OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs" — arXiv:2411.14199, November 2024. Authors: Akari Asai et al., Allen Institute for AI / UW.
- **What it does**: OpenScholar answers scientific questions by searching a 45-million open-access paper datastore, then generating synthesis responses with citation accuracy on par with human experts. It outperforms GPT-4o by 5% in correctness and PaperQA2 by 7% on ScholarQABench, while GPT-4o hallucinates citations 78–90% of the time vs OpenScholar's near-human rate.
- **Mechanism**: Three-stage pipeline:
  1. **Retrieval**: bi-encoder search over peS2o index (200M+ embeddings from 45M papers) + Semantic Scholar API + optional You.com web search; passages reranked by a BGE-based cross-encoder.
  2. **Iterative generation with self-feedback**: (a) Generate initial response y₀ with citations. (b) Generate up to 3 natural-language feedback sentences identifying gaps (e.g., "The answer only includes empirical results, not methodology"). (c) If feedback identifies missing content, generate a retrieval query and fetch additional passages. (d) Regenerate response yₖ incorporating new passages. (e) Repeat until no further feedback or max iterations.
  3. **Post-hoc citation attribution**: After generation, the system verifies that all "citation-worthy statements" (scientific claims requiring justification) are backed by retrieved passages; missing citations are inserted retroactively.
- **Citation grounding**: Passage-level provenance tracking throughout. `--min_citation` flag enforces minimum citation density. The post-hoc step specifically finds unsupported claims and links them to passages — directly analogous to the concept behind variant C's verifier figure check.
- **Figure binding**: Not addressed — OpenScholar targets text-only question answering over paper corpora; no figure or image binding mechanism exists.
- **Informed-retry**: The self-feedback loop IS the informed-retry pattern: the model explicitly identifies what is missing, formulates a retrieval query to fill that gap, then regenerates. This is the closest open-source analog to lazy-paper's `retry-when-short` logic, but implemented at a higher level (natural-language gap identification vs. character-count threshold).
- **What we can borrow**:
  - Natural-language gap identification as a retry trigger: instead of (or in addition to) `len(draft) < MIN_SECTION_CHARS`, consider having the verifier produce a one-sentence description of what is missing — this could power a more targeted retry prompt (not planned for v1.10 but a strong v1.11 candidate).
  - Post-hoc citation insertion: analogous to s09's literal-mention binding pass; the design principle (citation verification as a separate post-generation step) validates our two-stage s08→s09 architecture.
  - `--max_per_paper` passage constraint: analogous to `select_top_required(cap=N)` — OpenScholar also throttles how many passages per source paper enter the context, preventing dominance by any single source.
- **Where we diverge**:
  - OpenScholar uses a purpose-trained retriever + reranker on a 45M-paper corpus; lazy-paper's "retrieval" is internal to a single PDF (section context + figure notes), no external datastore.
  - Feedback loop operates at the full-response level; lazy-paper's retry operates at the section level — the granularity is appropriate to each problem.
  - OpenScholar is a Q&A system; lazy-paper is a document-to-document synthesis (PDF → structured Markdown). The output contract is different.

---

### LitLLM

- **Source**: https://github.com/LitLLM/LitLLM (Apache-2.0) and TMLR 2025 version at https://github.com/LitLLM/litllms-for-literature-review-tmlr
- **Paper / design**: (1) "LitLLM: A Toolkit for Scientific Literature Review" — arXiv:2402.01788. (2) "LitLLMs, LLMs for Literature Review: Are we there yet?" — arXiv:2412.15249, TMLR 2025. Authors: Shubham Agarwal et al.
- **What it does**: LitLLM automates the "related works" section of a research paper. Given a user's abstract, it extracts keywords via LLM, retrieves relevant papers via Semantic Scholar and embedding search, re-ranks results, and generates a coherent related-work narrative. Claims to reduce related-work writing from hours to minutes.
- **Mechanism**: Four steps: (1) LLM-based keyword extraction from user abstract. (2) Hybrid retrieval (keyword + embedding). (3) LLM-based attribution re-ranking ("re-ranking doubles normalized recall vs. naive search"). (4) Two-step generation: first produce a structural plan, then generate the actual text following that plan. Optional user-supplied plan: `"Generate {num_sentences} sentences. Cite {cite_x} at line {line_x}."` — a template-driven citation placement system.
- **Citation grounding**: RAG-based; citations are placed at LLM-specified sentence positions using a template directive system. No per-paper intermediate summaries; the full re-ranked paper set is in the prompt and the LLM is told which references to place where. No post-hoc verification.
- **Per-comparator drafting**: LitLLM does NOT do per-paper/per-comparator drafting. It generates a single-pass unified narrative with all retrieved papers in context. This is the key difference from lazy-paper variant B's per-comparator cap increase — our approach acknowledges that the per-section context window is already structured around individual comparators (required mentions), which is architecturally closer to "per-comparator allocation" than LitLLM's flat RAG approach.
- **Informed-retry**: No iterative loop or coverage check. Generation is single-pass; users must adjust templates and regenerate manually.
- **What we can borrow**:
  - Attribution re-ranking as a retrieval quality signal: lazy-paper currently ranks figures by `relevance_score` from s07_figure_analyze; LitLLM's "attribution re-ranking" framing (re-rank by whether the LLM would actually cite this source) is a possible v1.11 improvement for figure selection.
  - Plan-first / template-driven citation placement: validates our outline (s05) → compose (s08) split. The "plan" is the section outline + required-mention list; the "template" is the structured prompt in `_STRUCTURED_SYSTEM`.
- **Where we diverge**:
  - LitLLM targets the "related works" section of a new paper; lazy-paper synthesizes an entire paper into a comprehensive reading document. Different output scope entirely.
  - LitLLM has no figure handling; no verifier; no retry. Lazy-paper's quality-assurance stack (verifier + retry-when-short + best-of-N merge) is more sophisticated.
  - LitLLM's "per-comparator" design is implicit (cite paper X at line Y) vs. lazy-paper variant B's explicit per-comparator mention allocation with a typed cap.

---

### gpt-researcher

- **Source**: https://github.com/assafelovic/gpt-researcher (open-source, actively maintained)
- **Homepage**: https://gptr.dev/
- **Design**: Assaf Elovic, 2023–present. No single canonical paper; documented via README and blog posts. Ranked #1 on Carnegie Mellon's DeepResearchGym benchmark.
- **What it does**: Autonomous deep-research agent that produces multi-source research reports with inline citations. Given a research question, it spawns sub-agents to crawl, scrape, validate, and synthesize across 10–30+ sources, producing long-form reports in ~3 minutes at ~$0.005/query. Supports multiple LLM backends (GPT, Claude, Gemini, Mistral, Ollama) and retrieval backends (Tavily, DuckDuckGo, Bing, arXiv, Exa, etc.).
- **Mechanism**: Two-mode operation:
  - **Deep Research (planner-executor)**: Planner agent generates comprehensive research questions; executor sub-agents (crawler + scraper + validator) run in parallel, each gathering information for one question; planner agent filters + aggregates + writes the final report. Multi-agent LangGraph / AG2 variant mirrors STORM's team-based design more closely.
  - **Quick Search**: Single-agent low-latency variant for embedded use cases.
  - Scope is bounded by `max_iterations`, `max_subtopics`, `max_search_results_per_query`.
- **Citation grounding**: All output includes source URLs; inline citations in Markdown/HTML format. The system explicitly aggregates across 20+ sources to reduce reliance on any single site, using "information frequency across sites" as a reliability signal — an ensemble approach to citation confidence.
- **Figure binding**: No figure citation or image binding mechanism. Web-sourced images may appear but are not systematically tracked.
- **Informed-retry**: No explicit retry; the planner-executor split is the reliability mechanism — multiple independent sub-agents provide redundancy rather than iterative self-correction. Coverage is addressed by generating many sub-questions upfront rather than by detecting gaps post-hoc.
- **What we can borrow**:
  - Ensemble citation confidence (frequency across sources) — a design principle applicable when lazy-paper eventually adds multi-document synthesis (e.g., combining multiple related papers). Not applicable to single-PDF mode.
  - Planner-executor pattern validates the s05 (outline/planner) → s08 (composer/executor) split. Separate planning and execution agents is a widely validated architecture.
- **Where we diverge**:
  - gpt-researcher targets web research; lazy-paper targets a single scientific PDF. The retrieval corpus, scale, and noise level are completely different.
  - gpt-researcher has no concept of figure/table binding, structured schema validation, or post-hoc verifier — it produces free-form Markdown.
  - No concept of "retry-when-short" or length quality control; output length is implicitly governed by the number of sub-questions and sources.

---

### PaperQA2 (Future House)

- **Source**: https://github.com/Future-House/paper-qa (open-source, MIT-ish)
- **Paper / design**: (1) "PaperQA: Retrieval-Augmented Generative Agent for Scientific Research" — arXiv:2312.07559. (2) "Language agents achieve superhuman synthesis of scientific knowledge" — arXiv:2409.13740 (PaperQA2, 2024). Authors: Jakub Lála et al., Future House.
- **What it does**: High-accuracy RAG for scientific documents. PaperQA2 answers questions from a user's PDF library with in-text citations (e.g., "(Qian2011Neural pages 1-2)"). It exceeds human expert performance on scientific QA, summarization, and contradiction detection (finding 2.34 ± 1.99 contradictions per paper with 70% expert-validated accuracy).
- **Mechanism**: Three-phase pipeline:
  1. **Paper Search**: LLM generates keyword queries → candidate papers retrieved → chunks embedded into vector index.
  2. **Gather Evidence**: Retrieved chunks ranked by embedding similarity; top candidates undergo **LLM-powered Retrieval with Contextual Summarization (RCS)** — the LLM scores and summarizes each chunk in the context of the specific query, dramatically improving signal quality before the final prompt.
  3. **Generate Answer**: Top RCS-scored summaries feed the final LLM call → grounded, cited response.
  - Agentic variant: iterative refinement of queries and answers over multiple rounds.
- **Citation grounding**: In-text citations reference document, page range, and sometimes line range — `(Author Year pages X-Y)`. Citation markers are tracked from chunk retrieval through summarization to final output. This is closer to lazy-paper's `[span:doc:start-end]` marker scheme than any other system surveyed.
- **Figure / multimodal binding**: PaperQA2 performs **media enrichment during ingestion**: an LLM generates synthetic captions for figures and tables embedded in PDFs, shifting their embedding vectors to be semantically richer without altering source text. This allows evidence gathering to retrieve relevant visual content that terse original captions would miss. This is the closest parallel to lazy-paper's figure binding concept — and it is more architecturally complete: figure metadata enrichment at ingestion time, then retrieval-time inclusion in the evidence pool.
- **Verifier / retry**: Retries `Context` creation on invalid JSON (robustness). Agentic mode iteratively refines queries when initial answers are unsatisfactory. The RCS step is itself a quality filter: chunks that score poorly are excluded from the final prompt even if retrieved.
- **What we can borrow**:
  - **RCS (Retrieval with Contextual Summarization)** as a quality-filter before the final generation call — directly applicable to lazy-paper's figure selection in s07_figure_analyze: instead of a static `relevance_score`, an RCS-style call could score each figure's relevance to the specific section being composed (not just to the paper topic overall). Strong v1.11 candidate.
  - **Figure enrichment at ingestion time**: generating richer captions during s07_figure_analyze (we already do a version of this via `figure_notes.yaml`) validates the approach. We could improve description quality with a dedicated enrichment prompt.
  - **In-text citation with page range**: our `[span:doc:start-end]` marker format is already conceptually equivalent; the design is well-validated by PaperQA2.
  - **Span-level citation markers** vs. document-level: PaperQA2's `(Author Year pages X-Y)` maps cleanly to our `[span:doc:start-end]` format — both are granular, traceable, and verifiable.
- **Where we diverge**:
  - PaperQA2 answers individual questions from a multi-paper library; lazy-paper synthesizes a complete structured reading document from one paper. Different task structure.
  - PaperQA2's figure enrichment is at ingestion/indexing time; lazy-paper's figure analysis (s07) is per-paper at run time — the functional outcome is similar, but our approach is more tightly coupled to the specific paper being processed.
  - Variant C's `figure_ids` schema field + verifier check is more prescriptive than PaperQA2's approach: we enforce that specific figures ARE cited, not just that figures are retrievable. This is a harder constraint and arguably more appropriate for the single-paper synthesis use case.

---

### Onyx citation_processor

- **Source**: https://github.com/onyx-dot-app/onyx (MIT license; formerly Danswer)
- **Referenced file (upstream)**: `backend/onyx/chat/citation_processor.py` — a streaming `DynamicCitationProcessor` class for real-time citation marker substitution in chat responses.
- **What it does (upstream)**: Enterprise AI platform with RAG-based document Q&A. The `citation_processor.py` component transforms `[span:doc:start-end]` markers in streamed LLM output into hyperlinks or stripped text in real time, synchronized with the streaming token buffer.

#### Audit of our current usage

**Files involved:**
- `llm/citation/__init__.py` — `process_text(text, mode, sources)` — the in-tree adapter (non-streaming).
- `llm/citation/models.py` — three types: `SearchDoc`, `CitationInfo`, `STOP_STREAM_PAT` — re-exported for downstream parity with upstream Onyx shape.
- `THIRD_PARTY_NOTICES.md` — full attribution and history.

**How we use it:**
`process_text` is called from `stages/s09_render/renderers/base.py::Renderer._process_text(text)`. Every renderer (HTML, DOCX, PDF) inherits `_process_text` from `Renderer`. The `CitationMode` is set at renderer instantiation time (CLI flag `--citation-mode`, default `REMOVE`). Three modes:
- `REMOVE`: strips all `[span:doc:start-end]` markers from text before rendering — the default and most-used path.
- `KEEP`: passes text verbatim (markers remain visible in output).
- `HYPERLINK`: converts markers to `{"text": ..., "href": link#Lstart-Lend}` segments. The base renderer falls back to REMOVE behavior for HYPERLINK when `sources=[]` (which is always the case — see below).

**Critical finding — HYPERLINK mode is effectively dead code:**
`Renderer._process_text` always calls `process_text(..., sources=[])`. With an empty sources list, `docs_by_id` is empty, so every marker in HYPERLINK mode falls through to `segments.append(m.group(0))` (the raw marker string), and the caller's `"".join(...)` produces the same output as KEEP mode, not actual hyperlinks. No caller currently passes a populated `sources` list. The HTML renderer (`renderers/html.py`) uses `CitationMode` from the CLI but does not override `_process_text` to supply sources. Result: `--citation-mode hyperlink` produces output identical to `--citation-mode keep`.

**Streaming variant status:** The upstream `DynamicCitationProcessor` (streaming, token-by-token marker detection) was vendored as `llm/citation/stream_processor.py` in v1.4.0–v1.7 but was never wired into the runtime. It was removed in v1.8.x. Only the three support types (`SearchDoc`, `CitationInfo`, `STOP_STREAM_PAT`) survive in `models.py`. The streaming variant is completely absent from the codebase and is dead code.

**What we can fix / borrow (v1.10+ candidate):**
- If HYPERLINK mode is ever made functional, `Renderer._process_text` must accept a `sources` parameter and pass it down. The `process_text` logic is already correct — only the call site is broken.
- The `STOP_STREAM_PAT` sentinel in `models.py` is technically unreachable dead code (no streaming path exists); it can be removed or kept as documentation of the upstream design.

---

## Comparative table — v1.10 三变体 vs 业界设计图谱

| 设计点 | STORM | OpenScholar | LitLLM | gpt-researcher | PaperQA2 | Onyx | v1.10 A | v1.10 B | v1.10 C |
|---|---|---|---|---|---|---|---|---|---|
| **informed-retry** (检测缺失后触发再检索/再生成) | — | ✓ (self-feedback loop, NL gap ID + retrieval query) | — | — | ✓ (agentic iterative query refinement) | — | — | — | ✓ (figure-retry: ≥50% figures missing → hard-prompt retry) |
| **per-comparator drafting** (为每个比较对象单独起草再合并) | — (per-perspective conversation, conceptually similar) | — | — (flat RAG, no per-paper split) | — | — | — | — | ✓ (cap=12 for survey sections, ensures each comparator gets mention budget) | — |
| **figure_ids 硬约束** (schema字段+verifier强制图引用) | — | — | — | — | ? (figure enriched at ingestion; not a hard cite constraint) | — | — | — | ✓ (SectionDraft.figure_ids + verifier advisory + figure-retry) |
| **coverage 兜底** (字数/引用不足时强制重试) | — (perspective diversity is the coverage mechanism) | ✓ (max 3 feedback rounds) | — | — (sub-question count governs coverage) | ✓ (RCS quality filter; agentic retry) | — | ✓ (MIN_SECTION_CHARS=1200 env; BEST_OF_N=3) | — | — |
| **quote grounding / verbatim citation** (原文引用追溯到页/行) | ✓ (response anchored to retrieved web pages) | ✓ (passage-level provenance; post-hoc citation insertion) | ✓ (cite paper X at line Y template) | ✓ (source URL tracking) | ✓ (page-range in-text citations; RCS chunk tracking) | ✓ (span-marker → hyperlink) | (existing v1.8 [span:doc:start-end] markers) | (same) | (same + figure_ids) |
| **multi-perspective / best-of-N** (多视角or多次采样后合并) | ✓ (multiple writer-agents with different perspectives) | — | — | — (parallel sub-agents but single planner) | — | — | ✓ (BEST_OF_N=3 → _merge_drafts) | — | — |
| **outline-first 结构先行** (先确定纲要再写散文) | ✓ (perspective→outline→article) | — | ✓ (plan → generate) | ✓ (questions → sub-reports → final) | — | — | ✓ (s05→s08) | ✓ (same) | ✓ (same) |
| **post-hoc verifier** (生成后独立验证通过率) | — | ✓ (citation-worthy claims check) | — | — | ✓ (RCS score; JSON retry) | — | ✓ (verify_section_draft ratio=0.85) | ✓ (same) | ✓ (same + figure check) |
| **figure / multimodal binding** (图表引用绑定到具体图号) | — | — | — | — | ✓ (media enrichment + synthetic captions at ingestion) | — | — | — | ✓ (figure_ids schema field) |
| **streaming citation** (流式token时实时替换引用标记) | — | — | — | — | — | ✓ (upstream DynamicCitationProcessor) | — (dead code removed v1.8) | — | — |

---

## 决策影响

### 1. v1.10 变体与业界最佳实践的对齐程度 → 强 ship 信号

**变体 A（纯 env 调优）** 在最佳实践层面有充分支撑：`MIN_SECTION_CHARS=1200` 阈值触发更多 `retry-when-short` 与 OpenScholar 的 self-feedback loop 和 PaperQA2 的 agentic refinement 属于同一设计哲学——「先生成，检测质量，不足则重试」；`BEST_OF_N=3` 的多样性 merge 与 STORM 的多视角 writer-agents 如出一辙。两者都是零代码改动的调参变体，风险极低，且有理论基础。strong ship signal。

**变体 C（figure_ids 硬约束）** 在业界无直接先例，但 PaperQA2 的 media enrichment 验证了「在流水线中专门处理图表」的必要性；OpenScholar 的 post-hoc citation insertion 验证了「独立验证 + 缺失则修补」这一双阶段架构。Variant C 是这两个思路的结合——把图引用从软提示升级为 schema/verifier 硬约束——属于合理外推，不是孤立创新。medium-strong ship signal（取决于实验数据）。

### 2. v1.10 变体的 contrarian 设计 → 是否站得住脚？

**变体 B（per-comparator cap 分级）** 是本次最 contrarian 的设计：6 个系统里没有一个做了严格意义上的「per-comparator 分级上限」——LitLLM 做 flat RAG，OpenScholar 做 `max_per_paper` passage throttling，STORM 做 per-perspective conversation。变体 B 的理论依据是：survey 类节（多个 comparator 并列）需要更多 required mention 槽位才能不被截断，这是 lazy-paper 特有的 section-type-aware 架构决策。该设计在业界无直接对标，但可以在第一原则上自洽辩护——survey 节的信息密度客观上更高，cap=5 是针对正文节设计的，直接复用是误用。实验数据（M1 字数 + M3 缺失率）是最终裁判。

### 3. v1.10 未覆盖、可列入 v1.11 候选的设计点

以下来自本调研，均不在当前 spec scope 内：

1. **RCS（Retrieval with Contextual Summarization，来自 PaperQA2）**: 在 s07_figure_analyze 里对每个图片做「context-aware relevance scoring」——不只是静态 relevance_score，而是在 s08 compose 时针对当前节的具体 prompt 动态打分。预期能大幅提升 section-figure 匹配精度。
2. **NL gap identification（来自 OpenScholar）**: 让 verifier 输出一句自然语言描述「本节缺少什么」，而不只是 `post_verify_missing=X/Y`。该 NL gap 可以作为 retry prompt 的 targeted hint，使 retry 更有方向性（而非盲目重跑完整 prompt）。
3. **HYPERLINK citation mode 修复（Onyx 审计发现）**: 当前 `Renderer._process_text` 传 `sources=[]` 导致 HYPERLINK 模式退化为 KEEP。修复只需在调用链传 sources，但需要从 run dir 读取 source 元数据，涉及 s09 runner 改动。低风险，高用户价值（可导出带超链接的 HTML 报告）。
4. **Streaming citation 复活（Onyx 遗产）**: 上游 `DynamicCitationProcessor` 完整实现了流式 token-by-token marker substitution；我们 v1.4–1.7 曾有 vendored 版本但从未接入。若未来加实时预览功能（如 web UI streaming），可从 upstream 重新引入。

---

## References

- STORM: https://github.com/stanford-oval/storm — arXiv:2402.14207 — https://storm-project.stanford.edu/research/storm/
- OpenScholar: https://github.com/AkariAsai/OpenScholar — arXiv:2411.14199 — https://arxiv.org/html/2411.14199v1
- LitLLM: https://github.com/LitLLM/LitLLM — arXiv:2402.01788 — arXiv:2412.15249 (TMLR 2025) — https://litllm.github.io/
- gpt-researcher: https://github.com/assafelovic/gpt-researcher — https://gptr.dev/
- PaperQA2: https://github.com/Future-House/paper-qa — arXiv:2409.13740 — arXiv:2312.07559
- Onyx (formerly Danswer): https://github.com/onyx-dot-app/onyx — local vendored adaptation at `llm/citation/__init__.py`, attribution in `THIRD_PARTY_NOTICES.md`
