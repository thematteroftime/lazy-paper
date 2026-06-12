# 知识库

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

## 跨论文综合

`lazy-paper synthesize` 针对一个研究方向问题，从整个库（或指定论文子集）中收集证据，
通过单次文本 LLM 调用生成一份有据可查的 Markdown 报告。

### 用途

给定一个主题（如"能量正则化与多技能架构在腿式机器人上的结合路径"），命令从
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
| `## 研究空白与新问题` | 开放空白 + 至少 3 个由交叉分析激发的新问题（刻意发散、各自锚定证据） |
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

## 实验数据

实验数据成为库的一等公民——经过验证、视觉深度解读，并与论文一起可被检索。入库后，
单次 `query` 调用即可同时跨论文与实验结果搜索，无需额外参数。

### 用途

`exp-ingest` 对实验 bundle（曲线图、指标 CSV、实验记录、`exp.yaml` 清单）施以与论文
相同的处理：每张曲线图进行视觉深度解读（缓存至 `exp_notes.yaml`），确定性指标摘要，
将语料 chunk+向量化后写入**共享** `chunks` 表（`kind="experiment"`）。manifest 记录
env/software/hyperparams/关联论文，以便 advise 顾问跨论文↔实验数据层进行推理。

### Bundle 约定

实验 bundle 是一个具有以下结构的目录：

| 文件 / 目录 | 必填？ | 说明 |
|---|---|---|
| `exp.yaml` | **必填** | 清单：`title`、`env`、`software`、`hyperparams: {...}`、`papers: [paper_id...]`、`date` |
| `*.md`（如 `notes.md`） | 可选 | 自由格式实验记录（任意 `*.md`） |
| `*.csv`（如 `metrics.csv`） | 可选 | 任何含表头行与数值列的 CSV |
| 顶层或 `curves/` 下的 `*.png` / `*.jpg` | 可选 | 实验曲线图 |

### 快速上手

```bash
uv run python -m cli exp-ingest my-exp-01/
uv run python -m cli exp-ingest my-exp-01/ --id custom-id   # 自定义实验 id
uv run python -m cli exp-ingest my-exp-01/ --skip-vision    # 跳过视觉 LLM 调用
uv run python -m cli exp-ingest my-exp-01/ --lang en        # 英文曲线分析（默认：zh）

# 入库后，query 同时跨论文与实验结果：
uv run python -m cli query "CoT 收敛"
```

### 处理流程

1. **验证** — 加载 `exp.yaml`；文件缺失或 `title` 为空时以清晰提示退出。
2. **视觉深度解读** — 每张曲线图调用一次视觉 LLM，返回严格 YAML
   （`visual_summary`、`deep_observation`、`anomalies`）。结果缓存至 bundle 内
   `exp_notes.yaml`，重复运行为空操作。审计附件写在同目录：
   `exp_notes.<stem>.prompt.md` 和 `exp_notes.<stem>.response.json`。
3. **指标摘要** — 确定性，无 LLM 调用：对每个 `*.csv` 的每个数值列计算
   `min/max/last` 及行数。
4. **语料构建** — 将 `exp.yaml` 内容 + 实验记录 + 指标摘要 + 曲线分析展平为一份文本，
   再通过 SentenceSplitter（chunk 400/overlap 80）分块并向量化，写入**共享** `chunks`
   表（`kind="experiment"`）。
5. **归档** — bundle 产物复制至 `<library>/experiments/<id>/`（bundle 删除后仍保留）：
   `exp.yaml`、`exp_notes.yaml`、`*.md`、`*.csv`、曲线图（位于 `curves/` 下）。
6. **Manifest** — 新增条目，包含 `kind: experiment`、`env`、`software`、
   `hyperparams` 键、`papers`（关联论文 id）、`n_chunks`、`embedding_dim`、
   `ingested_at`、`source_bundle`。

### 视频延迟说明

视频产物暂不支持。规划路径：通过 Docker 调用 ffmpeg 提取关键帧；提取的帧将复用
曲线视觉分析管线。

## AI 科学家顾问

`lazy-paper advise` 闭合 AI 科学家闭环：实验证据 + 关联论文 + 迭代记忆 → 有据可查
的下一轮迭代方案。每轮 advise 生成一份四节式 Markdown 报告，每条建议均需注明具体
改动、可证伪的量化预期，以及经 manifest 校验的 `[src: id]` 引用标记（论文 id 与实
验 id 均有效）。历轮结果（含用户记录的实验结论）积累于
`<library>/experiments/<id>/advice/round_NN/`，建议命中率因此可追溯审计。

### 用途

给定一个已入库的实验和当前问题（`--idea`），命令从四个层次收集证据：实验归档 bundle
（`exp.yaml`、`exp_notes.yaml`、`notes.md`、指标摘要）、关联论文的归档上下文
（`context.yaml` 中的核心指标与关键问题）、与 idea 相关的库检索片段（dense + BM25 +
RRF 混合检索，默认 `--top-k 12`），以及所有历轮 advise 报告与用户记录的实验结论。
随后以单次文本 LLM 调用（重试 + 审计附件，house 模式）生成有据可查的迭代方案。
下一轮自动读取当轮报告与记录的结论——且不得重复已失败的建议。

### 快速上手

```bash
# 第一轮——请求迭代方案
uv run python -m cli advise --exp my-exp-01 --idea "push stable speed to 2.2 m/s"

# ... 在实验室运行建议的迭代 ...

# 记录实际发生的情况（写入 round_01/outcome.md）
uv run python -m cli advise --exp my-exp-01 --outcome "alpha_en=0.8 held to 2.1 m/s, CoT +6%"

# 第二轮——证据中已包含 round_01 报告与结论
uv run python -m cli advise --exp my-exp-01 --idea "now reclaim the CoT regression"
```

其他参数：

```bash
uv run python -m cli advise --exp my-exp-01 --idea "..." --lang en   # 英文输出（默认：zh）
uv run python -m cli advise --exp my-exp-01 --idea "..." --top-k 20  # 更多库检索片段
```

报告输出至 `<library>/experiments/<id>/advice/round_NN/report.md`，同目录保存审计
附件：`report.md.prompt.md` 与 `report.md.response.json`（引用检查前写入，确保被
拒报告可追溯）。

### 报告结构

报告包含以下四个 `##` 节，顺序固定：

| 节 | 内容 |
|---|---|
| `## 现状诊断` | 基于归档指标与曲线分析对当前实验状态的诊断 |
| `## 下一轮迭代方案` | 3–5 条编号迭代建议；每条须注明 (a) 改什么——具体改动，(b) 预期——带区间的可证伪量化预期，(c) 依据——至少一个 `[src: id]` |
| `## 深度观察` | 跨论文、跨实验的观察，用于解读当前状态 |
| `## 风险与备选` | 风险与替代方案；超出证据范围的推断标注 `(推测)` |

### 溯源约定

- 每条从证据得出的陈述必须带 `[src: id]`，使用 manifest 中的准确 id；论文 id 与
  实验 id 均为合法来源——两者都是 manifest 条目。
- 合成完成后，`check_citations` 做确定性扫描，对不在 manifest 中的 id 打印
  `WARNING: [src:] markers not in library: ...`。
- 超出证据范围的内容必须标注 `(推测)`。
- 审计附件（`.prompt.md` / `.response.json`）在引用检查前写入；若首次结果完全
  不含 `[src:]` 标记，则执行一次纠正重试。

### 轮次记忆

历轮结果积累于 `<library>/experiments/<id>/advice/`：

```
advice/
  round_01/
    report.md          # 四节式迭代方案
    report.md.prompt.md
    report.md.response.json
    outcome.md         # 由 --outcome 写入（用户记录的实验结果）
  round_02/
    report.md          # 须引用 round_01 结论；不得重复已失败的建议
    ...
```

`--outcome "..."` 将 `outcome.md` 写入最近一轮的目录。后续轮次将接收所有历轮报告
与结论作为证据，建议命中率因此可被审计：若某建议失败，下一轮方案须予以说明并提
出不同方向。

### 证据来源

`gather_evidence()` 从四个层次构建证据块，按以下顺序：

1. **实验归档** — `exp.yaml`（标题、超参、环境、关联论文），`exp_notes.yaml` 曲线
   分析（每张图的 visual_summary / deep_observation），`*.md` 实验记录，确定性指
   标摘要（每个 CSV 列的 min/max/last）。
2. **关联论文上下文** — 对 `exp.yaml.papers` 中每篇论文：来自 manifest 的标题，
   归档 `context.yaml` 中最多 3 条 `critical_questions` 与 4 条 `headline_metrics`。
3. **库检索片段** — 对整库执行 dense + BM25 + RRF 混合检索，查询串为
   `<idea> <exp title>`（默认 `--top-k 12`）。
4. **历轮 advise 记录** — 所有 `round_NN/report.md` 与 `round_NN/outcome.md`，
   以 `## PRIOR ROUND round_NN` / `## OUTCOME of round_NN` 为前缀注入证据。

### 延迟说明

- **`--template-guided advise`**：模板约束式迭代建议（由结构化问题模板引导方案形
  态）暂缓。当前以 `--idea` 字符串为透镜。
- **视频证据**：实验 bundle 中的视频产物尚不处理。曲线视觉管线处理静态图像；视频
  支持将沿 exp-ingest 规划的 ffmpeg 关键帧路径实现。

## 知识花园

### 用途

`lazy-paper garden` 为整个库构建一张静态星图。论文**与**实验均以星体形式呈现，
让知识库的增长一目了然。无需服务进程，无需动态数据拉取——HTML 文件完全自包含，
可像普通文档一样分享或归档。

### 快速上手

```bash
uv run python -m cli garden            # 输出至 <library>/garden/garden.html
uv run python -m cli garden --open     # 同上，构建后用默认浏览器打开
uv run python -m cli garden --out DIR  # 自定义输出目录
```

直接双击 `garden.html` 即可在浏览器中打开——无需服务器。

### 工作原理

构建时 `llm/garden.py` 执行以下步骤：

1. 读取库 manifest 及逐篇归档（`context.yaml`、`figures.yaml`），组装
   `GARDEN_EXPORT`。
2. 将 `frontend/garden/` 下的所有资源（`DATA_ADAPTER.md` 除外）原封不动地复制
   到输出目录——**资源文件从不被修改**。
3. 将 `window.GARDEN_EXPORT = {...};` 作为内联 `<script>` 块注入 `garden.html`，
   位置在 `<script src="garden-data.js">` 标记之前。内联注入是必须的：因为浏览器
   的 CORS 策略会阻止 `file://` URL 下的 `fetch('garden-export.json')` 请求，
   所以运行时拉取在本地文件打开场景下无法使用。
4. 在 HTML 旁同时写出 `garden-export.json`，供 HTTP 服务场景使用。

前端（`frontend/garden/`）自行计算**所有**布局、星体坐标、星座连线和索引——导出
器无需提供任何布局数据。前端资源以原始状态入库，可通过直接替换整个 `frontend/garden/`
目录来升级，无需改动任何 Python 代码。

### 离线说明

主画布为纯 JavaScript 实现，完全支持离线使用。调节面板（Tweaks Panel）从 CDN
加载 React 和 Babel，需要网络连接；离线时主星图仍可正常渲染。

### 数据映射

| `GARDEN_EXPORT` 字段 | 来源 |
|---|---|
| `manifest.papers[*]` | `manifest.yaml` — 每篇论文/实验一条 |
| `manifest.papers[*].kind` | `"paper"` 或 `"experiment"`（来自 manifest） |
| `manifest.papers[*].questions` | `papers/<id>/context.yaml` → `critical_questions`（仅论文） |
| `manifest.papers[*].figures` | `papers/<id>/figures.yaml` → `fig_id` + `caption`（仅论文，最多 20 条） |
| `entities` | LanceDB `entities` 表，按 `paper_id` 分组 |
| `relations` | LanceDB `relations` 表，按 `paper_id` 分组 |

### 已知缺口

以下限制记录于 `frontend/garden/DATA_ADAPTER.md`，将在后续版本中跟进：

- **模拟 ingest 按钮**：在真实数据模式下仍生成假论文；应改为重新拉取导出数据
  或隐藏该按钮（可通过 `data.fromExport === true` 判断真实数据模式）。
- **打开 preview.html 按钮**：目前为占位提示；真实产物应跳转到论文的合成输出
  页面或 garden 构建的轻量阅读页。
- **聚类**：在前端实体亲和度聚类功能落地之前，默认随机分配；导出器也可直接
  提供 `clusters` 数组来覆盖默认行为。
