# v1.4 Roadmap — 内容质量升级

> 现状：v1.3.3 已发布（commit `f816795`），9-stage 流水线稳定，189 tests 全过。
> 目标：v1.4 解决三类内容缺陷——**模板驱动幻觉、符号上下文漂移、漏抓源事实**。

## 为什么需要 v1.4

v1.3 已经把布局做对了；剩下的问题都集中在 s08 LLM 章节合成阶段——**它的"证据源"太弱**：仅靠 OCR + 关键词打分挑出的片段，没有结构化的论文知识。

三个具体症状（来自 10 篇 corpus 实测）：

| 症状 | 例子 | 根因 |
|---|---|---|
| **模板驱动幻觉** | yang2025 ch01 编造 `Wrec=8.6 J/cm³ at η=85%`（源文无此数） | 模板域 ≠ 论文域时，prompt 里的 `{paper.system}` + `key_terms` 把模板默认领域的"常识数据"拉进生成 |
| **符号上下文漂移** | meng2024 把 "test field=340 kV/cm" 当成 "E_b=340 kV/cm"（源文 E_b 实际是 348） | LLM 看到的是孤立片段，不知道哪个符号绑定哪个值 |
| **漏抓源事实** | meng2024 ch10 声称"未提合成方法"+ 编造"presumably solid-state"，源文第 12 页明确写 "tape-casting" | 关键词检索没召回，LLM 也没工具去复查源文 |

**共同根因**：s08 没有「这篇论文里到底有哪些实体/数值/事实」的结构化记忆，也没有「写完再核对一次」的反思能力。

## 当前数据流（v1.3.3，提取部分维持）

```
┌─────────────────────────────────────────────────────────────────────┐
│  Input:  paper.pdf  +  outline.docx  +  .env(LLM/OCR tokens)        │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s01_ocr             │  MinerU  或  PaddleOCR-VL
                    │  (云端)              │  → doc_N.md + imgs/*.jpg
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s02_clean           │  Unicode 归一、噪声去除
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s03_chapter         │  按 PDF 内在节切分
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s04_figures         │  多面板图合并 + 标注
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s05_template        │  解析 outline.docx
                    │                      │  → 章节 + guidance
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s06_context         │  文本 LLM × 1
                    │                      │  → title / system / keywords
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s07_figure_analyze  │  视觉 LLM × N(图)
                    │                      │  → fig_notes.yaml
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s08_section_compose │  文本 LLM × M(章节)
                    │  ★ 内容质量瓶颈      │  关键词打分 → 片段 → 直接生成
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s09_render          │  无 LLM；模板渲染
                    └──────────┬───────────┘
                               ▼
              preview.docx / .pdf / .html / .pptx
```

**关键事实**：提取链路（s01–s05）**不动**——OCR 后端、清洗、切章、抠图、模板解析在 v1.3.3 已经稳定，v1.4 不改一行。所有变更集中在 **s06 末尾 + s08**。

## v1.4 设计：两个新层

```
                    ┌──────────────────────┐
                    │  s06_context (扩展)  │  现有: title/system/keywords
                    │                      │ +新增: PaperKG  (instructor)
                    │                      │ +新增: Retriever 索引
                    │                      │   (llama-index + bm25s)
                    └──────────┬───────────┘
                               │
                    ┌──────────┴───────────┐
                    │   PaperDB (新)       │  ── 单篇论文数据库 ──
                    │                      │
                    │  paper_kg.parquet    │  10 类闭包实体/关系图
                    │     (材料/掺杂/参    │  (instructor + Pydantic)
                    │      数/数值/单位    │
                    │      /图/表/论断     │
                    │      /方法/对比物)   │
                    │                      │
                    │  retrieval.parquet   │  父子分块 + BM25 + dense
                    │                      │  (RRF 融合, 12.5ms/500 chunks)
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  s08_section_compose │  文本 LLM × M(章节)
                    │  (重写)              │
                    │                      │  ┌─ Agent (pydantic-ai) ──┐
                    │                      │  │  tools:                │
                    │                      │  │   • query_kg()         │
                    │                      │  │   • retrieve()         │
                    │                      │  │   • check_source()     │
                    │                      │  │   • emit_section()     │
                    │                      │  └────────────────────────┘
                    │                      │  ┌─ Reviewer ─────────────┐
                    │                      │  │  T1: regex 校验 (免费) │
                    │                      │  │  T2: instructor 复检   │
                    │                      │  │       (仅在 T1 触发时) │
                    │                      │  └────────────────────────┘
                    │                      │  ┌─ Citation processor ───┐
                    │                      │  │  [span:doc_X:Y-Z] 渲染 │
                    │                      │  │  (vendored from Onyx)  │
                    │                      │  └────────────────────────┘
                    └──────────────────────┘
```

## 分阶段交付

### v1.3.4（5 天）— **加 PaperDB，不动 s08 行为**

| 改动 | 文件 | LOC |
|---|---|---|
| KG 提取 | `stages/s06_context/kg_extract.py` | ~40 |
| 检索器 | `llm/retriever.py` (llama-index + bm25s 适配) | ~15 |
| s08 改用 `retriever.retrieve()` 代替关键词打分 | `stages/s08_section_compose/compose.py` | ~20 改 |
| reviewer regex 层（observe-only，只记录到 `critic_flags.yaml`） | `stages/s08_section_compose/reviewer.py` | ~40 |

**用户可见效果**：检索质量提升（top-8 父子块代替关键词 top-N），但生成行为不变；`critic_flags.yaml` 为下一步提供数据。

### v1.4.0（4 天）— **s08 升级为工具调用 agent + LLM 复检**

| 改动 | 文件 | LOC |
|---|---|---|
| Section agent | `stages/s08_section_compose/agent.py` | ~30 |
| reviewer LLM 层（instructor + Pydantic） | `stages/s08_section_compose/reviewer.py` | ~15 |
| 单位归一 helper | `stages/s08_section_compose/_units.py` | ~25 |
| Citation 流处理（MIT vendoring） | `llm/citation/stream_processor.py` | ~516 (vendored) |
| Citation 适配 | `llm/citation/__init__.py` | ~20 |

**用户可见效果**：每章生成是 agent 循环（最多 8 步）+ 一次 reviewer 复检 + 必要时一次重写；citation marker 可在三种模式（隐藏/numeric/inline）渲染。

## 库账单（mature OSS first）

| 库 | 用途 | 来源 |
|---|---|---|
| `instructor` | 强类型 Pydantic LLM 输出 | pip |
| `pydantic-ai-slim[openai]` | typed agent + 工具调用循环 | pip（5 依赖） |
| `llama-index-core` | 分块 + VectorStoreIndex + TextNode | pip |
| `llama-index-retrievers-bm25` | 桥接 bm25s | pip |
| `bm25s` | 纯 numpy BM25（500 块 12.5ms） | pip |
| Onyx `citation_processor.py` | 流式 citation 解析 | vendored (MIT) |

**自写代码总量**：~185 LOC（不含 vendored 516）。其余全部由成熟库承担。

## 回滚

任何节点失败：`git checkout v1.3.3` 即恢复到 v1.3.3 稳定态。每篇论文的 PaperDB 失败时**软降级**（不写 KG，不索引，但 s08 仍能用旧逻辑跑出基础结果），保证流水线不因单篇论文中断。

## v1.5 预留

`findings.yaml`（跨章节一致性证据，由 reviewer 输出）会在 v1.5 被一个跨章节 coherence agent 消费。v1.4 只产出不消费。

---

详细工程契约见 [`docs/superpowers/specs/2026-05-20-v1.4-content-quality-design.md`](superpowers/specs/2026-05-20-v1.4-content-quality-design.md)。
