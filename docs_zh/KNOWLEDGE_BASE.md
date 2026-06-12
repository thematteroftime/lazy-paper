# 知识库（v1.14）

library 是一个持久化的跨论文存储层，由你已有的 run 产物直接构建。入库**零 LLM
调用**——知识图谱取自 `runs/<paper-id>/s06_context/`，chunk 索引（含向量）取自
`runs/<paper-id>/s08_section_compose/retrieval.parquet`；若 run 未跑到 s08，
入库时会构建一次索引（仅 embeddings 调用，无 LLM 调用）。入库后，论文数据不再
依赖 `runs/` 目录（清理 runs 也不丢），并且可以和库内所有其他论文一起被检索。

## 快速上手

```bash
# 对任何跑到 s08 的 run（新跑的或历史的；只跑到 s03 时入库会构建一次索引）：
uv run python -m cli ingest mypaper

# 或一条命令带入库：
uv run python -m cli run --pdf … --template … --paper-id mypaper --ingest

# 跨论文检索：
uv run python -m cli query "能量正则化如何影响步态切换" --top-k 5
uv run python -m cli query "…" --papers mypaper,otherpaper   # 限定范围
uv run python -m cli query "…" --json                        # 供 agent 消费
uv run python -m cli papers                                  # 查看库内容
```

## 目录结构

默认根目录 `./library`（用 `LAZY_PAPER_LIBRARY_DIR` 或 `--library-dir` 覆盖）。
属于用户数据，与 `runs/` 一样被 gitignore。

| 路径 | 内容 |
|---|---|
| `manifest.yaml` | 每篇论文一条：标题、kind、关键词、chunk/实体数、聚合 LLM token 数、来源 run |
| `lancedb/` | `chunks`（文本 + 向量，按 `paper_id` 区分）、`entities`、`relations`（合并后的逐篇 KG）表 |
| `bm25/` + `bm25_ids.json` | 全库稀疏索引，每次入库重建 |
| `papers/<id>/` | 归档的 `context.yaml`、`fig_notes.yaml`、`figures.yaml`、合成章节 `sections/`、OCR `imgs/` |

## 语义约定

- **幂等**：重复入库同一论文会替换其全部行，manifest 始终一条。
- **一个库只允许一个 embeddings 模型**：向量维度不一致会报错拒绝——混用模型会
  悄悄破坏排序质量。
- **query** 与 run 内检索器（`llm/retriever.py`）使用同一套 dense + BM25 + RRF
  融合方案，跨论文排序行为与你在单篇 run 里已经验证过的一致。
- **`kind: experiment`**：`ingest --kind` 已接受该值但属预留——实验闭环功能在
  后续版本落地。

## 跨论文综合（v1.16 Synthesize）

`lazy-paper synthesize` 针对一个研究方向问题，从整个库（或指定论文子集）中收集证据，
通过单次文本 LLM 调用生成一份有据可查的 Markdown 报告。

### 用途

给定一个主题（如"能量正则化与多技能架构在腿式机器人上的结合路径"），命令从 v1.14
库中收集证据（manifest 元数据、归档的 `context.yaml` / `fig_notes.yaml`、混合检索
的文本片段），然后合成一份五节式研究方向报告。每条从证据中得出的陈述都必须带有
`[src: paper_id]` 标记；确定性后检查会对任何不在库中的标记打印 WARNING。

### 快速上手

```bash
uv run python -m cli synthesize --topic "能量正则化与步态切换对比"
uv run python -m cli synthesize --topic "..." --papers paper-a,paper-b   # 限定范围
uv run python -m cli synthesize --topic "..." --lang en                  # 英文输出（默认：zh）
```

输出路径为 `<library>/synth/<topic-slug>/report.md`，同目录保存审计附件：
`.prompt.md` 和 `.response.json`（在引用检查前写入，保证被拒报告可追溯）。

### 报告结构

报告包含以下五个 `##` 节，顺序固定：

| 节 | 内容 |
|---|---|
| `## 主题综述` | 跨论文的主题总览与框架 |
| `## 方法对比` | Markdown 表格——每篇论文一行：方法、关键量化结果、局限性 |
| `## 证据与分歧` | 各论文间的共识与矛盾 |
| `## 研究空白` | 库内任何论文均未解决的开放性问题 |
| `## 下一步建议` | 3–5 条具体可证伪的下一步，每条至少引用一个 `[src: ...]`；超出证据范围的推断标注 `(推测)` |

### 溯源约定

- 每条从证据得出的陈述必须带 `[src: paper_id]`，使用库中的准确论文 id；多来源写
  法：`[src: id1][src: id2]`。
- 合成完成后，`check_citations` 做确定性扫描，对不在库 manifest 中的 id 打印
  `WARNING: [src:] markers not in library: ...`。
- 超出证据范围的内容必须标注 `(推测)`。
- 审计附件（`.prompt.md` / `.response.json`）在引用检查前写入；若首次结果完全不含
  `[src:]` 标记，则执行一次纠正重试。

### 证据来源

`gather()` 从三个层次构建证据块：

1. **Manifest** — 库内每篇论文的标题与关键词。
2. **归档 context/fig_notes** — 每篇论文的 `context.yaml`（最多 3 条
   `critical_questions`、4 条 `headline_metrics`）和 `fig_notes.yaml`（最多 4 条
   `deep_observation` / `visual_summary`）。
3. **混合检索片段** — 与 run 内检索器相同的 dense + BM25 + RRF 方案，以主题字符串
   为查询（默认 `--top-k 18`）。

### 设计说明：s08 运行时上下文暂不注入

`synthesize` 刻意不注入 s08 运行时库上下文。锚定引用验证器（anchored-quote
verifier）将带作者名的外部引用视为需要本地 `cited_quote` 的锚定声明；来自综合报告
的外部引用与这些规则的交互需要独立的溯源设计。s08 有 5 次反转审计历史，改动须
谨慎。此延迟属有意为之，已明确记录，不应以快速补丁绕过。
