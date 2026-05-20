# Content Optimization Roadmap — v1.4 → v2.0

> v1.3.x 关闭了所有可见的布局缺陷。内容缺陷需要换思路 —— 不是再调一两个 prompt，而是**把生成范式从"单次提示"升级为"检索-验证-迭代"循环**。本文给出可执行的 4 步路径，每步对齐一个成熟开源项目。

## 现状的内容三宗病

`docs/v1_4_roadmap.md` 第一次审计已记录，复述为机制语言：

1. **Hallucination on topic mismatch** —— LLM 用模板暗示的"应该写什么"覆盖了源论文的"实际是什么"。yang2025 是神经形态论文，s08 却补了能量存储数字（8.6 J/cm³ / 85%）。本质是 prompt 给 LLM 太多"应当"，留太少"必须基于源"。
2. **Quoted-symbol drift** —— LLM 在长上下文中弄混 E_b vs 测试场（340 vs 348 kV/cm）、单位（4 MV/cm vs 4000 kV/cm）。本质是没有事后核对环节。
3. **Missed source facts** —— meng2024 源中明明写了 "tape-casting"，composer 却说"不涉及合成方法"。本质是 keyword-matching 召回错过了关键段落。

三种病一个共同特征：**模型只看到了我们喂给它的子集，而不是源论文全貌；产生的内容没有被任何机制对照源验证。**

## 路线图：四阶段升级

### 阶段 1 — 检索增强生成（RAG over paper）·  对齐 [PaperQA2](https://github.com/Future-House/paper-qa)

**问题**：s08 现在给 LLM 8000–15000 字的"keyword 最相关章节摘录"。但 keyword 匹配会漏掉同义改写的关键句（"tape-casting" / "流延法" / "doctor blade method"），也会带入大量与本节无关的内容。

**做法**：用 embedding 检索替代 keyword 匹配。
- **离线**：把每篇论文的 cleaned chapters（`s02_clean/doc_*.md`）+ `s07_figure_analyze/fig_notes.yaml` 切成 200–400 字 chunks，跑 embedding（`text-embedding-3-small` 或开源 `bge-m3`），存到 `runs/<paper>/s06_context/index.parquet`。
- **生成时**：s08 写每节前，用该节的 `title + guidance + key_terms` 做 query，retrieve top-8 chunks，仅这 8 个作为"evidence pool"喂给 LLM。
- **prompt 加锁**：「ONLY use facts present in `<evidence>` block. If a fact you want to write is not in there, write 'this paper does not directly address X' instead of inventing.」

**参考**：PaperQA2 实现了"问题 → 检索 → 多 chunk 综合 → 引用回写"完整闭环；它的 `evidence_summary` / `final_answer` 两阶段思路可直接借鉴。

**预期效果**：解决病 1（topic mismatch）和病 3（missed facts）；不解决病 2。

**工作量**：~3 天。新增 `stages/s06_context/embed.py`、`llm/retriever.py`、s08 prompt 重写。LLM 成本下降（喂 LLM 的 token 减少 60%）。

### 阶段 2 — 自校验 critic 回路 ·  对齐 [Reflexion](https://github.com/noahshinn/reflexion) / [Self-Refine](https://github.com/madaan/self-refine)

**问题**：s08 一次性产出整章，没有"对完了答案再翻书"的步骤。

**做法**：在 s08 完成一章后，跑一个轻量 critic 模型。
- 输入：composed chapter 文本 + 该章对应的 retrieved evidence chunks。
- 任务：逐句标注  
  ① 此句中数字 / 化学式 / 命名实体是否在 evidence 中存在？  
  ② 此句中"Fig.N"是否在 `figures.yaml` 中？  
  ③ 是否有 evidence 之外的事实断言？
- 输出：若问题 ≥ 阈值，把 critic 的标注当 feedback 给 composer 重写一次（最多 2 轮）。

**参考**：Reflexion 的"trial → reflection → retry"循环最适合；Self-Refine 提供 critic prompt 模板。两者都是几百行实现，可直接借鉴。

**预期效果**：解决病 2（symbol drift）大半；同时大幅压低病 1 残留。

**工作量**：~3 天。需要 critic prompt + 1 额外 LLM call/chapter（成本 ≈ +30%）。

### 阶段 3 — 多 perspective 大纲驱动 ·  对齐 [STORM](https://github.com/stanford-oval/storm) / [Sakana AI Scientist](https://github.com/SakanaAI/AI-Scientist)

**问题**：s08 把"撰写本节"作为单一任务给 LLM。深度分析需要"多角度提问 → 回答 → 整合"。

**做法**：把每节拆成 3 阶段：
1. **Outliner agent**：「按这个 guidance，我应该回答 5 个具体子问题：Q1…Q5」  
2. **Researcher agent**（每个 Q）：从 evidence chunks 中检索 → 用 evidence 回答 → 引用 chunk id
3. **Synthesizer agent**：把 5 个 Q&A 写成 1 段连贯叙述

**参考**：STORM 是 Wikipedia 文章生成的 SOTA，思路就是「perspective generation → grounded outline → writing」。AI Scientist 的 ideator/experimenter/reviewer 三角色也可借鉴。

**预期效果**：从"paraphrase"变成"genuine synthesis"。yang2025 ch14 / ali2025 ch14 已经偶尔展现这种品质 —— 多 agent 化可以稳定复现。

**工作量**：~5 天。重构 s08 为 mini-pipeline。LLM 成本 +200%（3 次调用/section），但用 retrieval 减下来的 token 数能抵消一半。

### 阶段 4 — 编译式 prompt 程序化 ·  对齐 [DSPy](https://github.com/stanfordnlp/dspy)

**问题**：现在我们用字符串模板手写 prompt。每次改 prompt 都靠人眼试错；prompt 间没有结构。

**做法**：用 DSPy 把每个 LLM 调用声明为「Signature（输入字段→输出字段）+ ChainOfThought / Predict」。DSPy 把 prompt 工程变成「编译目标」—— 你写 spec，它自动调 prompt。

```python
class ComposeSection(dspy.Signature):
    """Compose a presentation section grounded in source evidence."""
    section_title: str = dspy.InputField()
    section_guidance: str = dspy.InputField()
    evidence_chunks: list[str] = dspy.InputField()
    section_body: str = dspy.OutputField(desc="≥80% facts traceable to evidence")

composer = dspy.ChainOfThought(ComposeSection)
result = composer(section_title=..., evidence_chunks=...)
```

**参考**：DSPy 文档的 "Optimizing prompts with DSPy" 教程。已经在生产中被 PaperQA、TextGrad 等用作底层。

**预期效果**：可维护性 +50%；prompt 自动优化器（BootstrapFewShot）能挖掘出比人手调更好的 prompt；测试每个 signature 比测试整个 stage 容易。

**工作量**：~5 天，分散在 v1.4–v2.0 中渐进迁移（不必一次重写）。

## 优先级与里程碑

| 版本 | 包含阶段 | 关键能力 | 工作量 |
|---|---|---|---|
| **v1.4** | 阶段 1 (RAG) + 阶段 2 (critic loop) | 病 1/2/3 大半被堵；同时 LLM 成本下降 | ~6 天 |
| **v1.5** | 阶段 3 (multi-agent outline) | 内容从 paraphrase → 真综合 | ~5 天 |
| **v2.0** | 阶段 4 (DSPy 编译化) + 全 prompt 迁移 | 工程可维护性跃迁 | ~5 天分散 |

v1.4 是性价比最高的一步 —— 6 天投入消除 ~70% 内容缺陷。如果只能做一阶段，做阶段 1+2。

## 相邻借鉴的若干小点

- **Anthropic Citations API**：原生 grounding，输出时附带源 span 引用。可作为阶段 1 的轻量等价方案（不用自建 embedding 索引）。
- **Instructor** + **Pydantic** 强 schema：现在我们已经用 `_normalize_chapter_summary` 防御性补字段，迁到 Pydantic schema 后可以编译期就拒掉错 payload。
- **GPT Researcher** / **AutoGen GroupChat**：多 agent debate 模式的开源参考，适合做阶段 3 的 prototype。
- **LlamaIndex Knowledge Graph Index**：把论文的 entities（材料、参数、单位、设备）抽成 KG 后，再生成时可以用 KG 约束 "Pb₀.₉₈La₀.₀₂" 等命名实体 —— 解决病 2 的另一条路径。
- **Sakana AI Scientist** 的 reviewer prompt：直接复用其 review checklist（novelty / soundness / clarity / contribution）作为阶段 3 的 critic 角色 baseline。

## 决定点

v1.3.x 已经在布局上做到了"无可见 bug"。内容优化是更深的、更值得投入的方向。建议下一轮投入 v1.4（阶段 1+2 ≈ 6 天）后回到 corpus 全量审，看是否能把内容审计的 3 类病一次降到 < 10% 出现率。

如果时间紧，**只做阶段 1 也是一次重大升级** —— 整个生成范式从"模板填空"变成"基于源回答"。
