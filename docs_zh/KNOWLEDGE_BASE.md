# 知识库（v1.14）

library 是一个持久化的跨论文存储层，由你已有的 run 产物直接构建。入库**零 LLM
调用**——chunk 向量与知识图谱原样取自 `runs/<paper-id>/s06_context/`。入库后，
论文数据不再依赖 `runs/` 目录（清理 runs 也不丢），并且可以和库内所有其他论文
一起被检索。

## 快速上手

```bash
# 对任何跑到 s06 的 run（新跑的或历史的）：
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
