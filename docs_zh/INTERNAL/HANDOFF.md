# lazy-paper — 生产环境交接文档

> **状态：** 已发布 · **测试：** 253/253 通过 · **已在 13 篇语料库上端到端验证** · **最近发布：** v1.9.0 (2026-05-22)
>
> **v1.9.0 上线 informed-retry，把 meng2024 T1 的方差降到 0。**
> 之前的 retry-when-empty 用的是笼统的 "你漏了 required mentions" 提示。
> v1.9 现在为每个缺失的 required mention 生成包含具体锚点 token
> （作者姓氏 OR 关联数值）的逐实体诊断，LLM 拿到的是一份确定性
> 检查清单，而不是一句模糊的提醒。**meng2024 的三次独立 run 在 T1
> 基准恢复测试上全部拿到 9/17**——方差从 v1.8.1 的 stdev 2.6 降到
> v1.9 的 **stdev 0**。完整语料验证 + 分析见
> `docs_zh/v1_9_validation_results.md`。
>
> **v1.8.x 基础不变。** Strategy KL 仍是推荐的高质量默认方案。
> verifier 在子串匹配前对 LaTeX/OCR 形式做归一化（因此引用 comparator
> 的优质 claim 不再因为 `$W _ { \mathrm { rec } }$` 之类的空白差异被
> 错误拒绝）；retry-when-empty 触发条件在 verify 之后测量覆盖率，
> 因此 verifier 刚刚 drop 掉 comparator claim 时
> 它会触发，并允许一次加强版的 LLM 调用把这些 claim 恢复回来。
> 在 meng2024 ch01（标志性的 benchmark-recovery 测试）上：
> v1.8.1 KL 下限 12/17、均值 15.0、范围 12–17（v1.7 KL 是下限 1、均值 5.0）。
> yang2025/fu2020/chai2026 上无回归。完整分析见
> `docs/v1_8_validation_results.md`。
>
> v1.4.x 的基础设施（PaperDB / 两层 critic / Onyx 引用处理器）保持不变。
> 基于 pydantic-ai 的 section agent（`LAZY_PAPER_AGENT=1`）仍然是
> opt-in。完整的 v1.4.0 → v1.8.1 发布轨迹见 CHANGELOG.md。

如果你是冷启动接手本项目（无论是人类维护者还是 AI agent），请先读这份文档。它告诉你：项目中存在什么、什么能用、哪些已经验证过、以及在哪里做修改。

---

## 1. 本项目做什么

`lazy-paper` 是一个 9 阶段流水线，能把科研论文 PDF + 一份 Markdown 大纲模板（`.docx`）转换成一套多格式深度分析文档：DOCX、PDF、HTML、PPTX。每个阶段都会写入 `runs/<paper_id>/<stage>/`，并且可以独立重跑。

- **OCR**：MinerU（默认，对图片友好）或 PaddleOCR-VL
- **文本 LLM**：任何 OpenAI 兼容端点（默认 DeepSeek-Reasoner）
- **视觉 LLM**：任何 OpenAI 兼容端点（默认 Qwen-VL）
- **输出**：`runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`

---

## 2. 快速开始

```bash
# 安装
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"

# 配置
cp .env.example .env       # 然后填入 MINERU_TOKEN + LLM_*_API_KEY

# 端到端运行
uv run python -m cli run \
  --pdf "papers/he2023.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id he2023 --lang zh \
  --formats docx,pdf,html,pptx
```

WeasyPrint（PDF）需要系统库：

```bash
# macOS
brew install pango gdk-pixbuf libffi cairo

# Linux/Docker
# Dockerfile 已经包含；裸机 Linux：apt install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

Docker 用户：`docker compose build && docker compose run --rm lazy-paper run --pdf ...`

---

## 3. 环境变量

| 变量 | 是否必填 | 默认值 | 用途 |
|---|---|---|---|
| `OCR_BACKEND` | 否 | `mineru` | `mineru` 或 `paddleocr` |
| `MINERU_TOKEN` | 当 `OCR_BACKEND=mineru` 时 | — | 来自 https://mineru.net/ 的 API token |
| `PADDLEOCR_TOKEN` | 当 `OCR_BACKEND=paddleocr` 时 | — | 来自百度 AI Studio 的 token |
| `LLM_VISION_BASE_URL` | 是 | DashScope | 视觉 LLM 的 OpenAI 兼容 base URL |
| `LLM_VISION_API_KEY` | 是 | — | 视觉 LLM 的 key |
| `LLM_VISION_MODEL` | 否 | `qwen-vl-max-latest` | 视觉模型名 |
| `LLM_TEXT_BASE_URL` | 是 | DeepSeek | 文本 LLM 的 OpenAI 兼容 base URL |
| `LLM_TEXT_API_KEY` | 是 | — | 文本 LLM 的 key |
| `LLM_TEXT_MODEL` | 否 | `deepseek-reasoner` | 文本模型名 |
| `LLM_MAX_TOKENS_CEILING` | 否 | `40000` | 对每一次 LLM 调用的 `max_tokens` 设上限（用一个旋钮约束花费或配额） |
| `LLM_EMBEDDINGS_BATCH_SIZE` | 否 | `10` | retriever 对 chunk 做 embedding 时的单批大小（`llm/retriever.py`） |
| `LAZY_PAPER_STRUCTURED` | 否 | 未设置 | `1` 启用基于 instructor 的结构化 compose + verifier（v1.8.1+ 推荐） |
| `LAZY_PAPER_KG_PROMPT` | 否 | `paper_kg.md` | KG 抽取所用的 prompt 文件。Strategy L 使用 `paper_kg_v3.md` 抽取作者实体 |
| `LAZY_PAPER_BEST_OF_N` | 否 | `1` | 每个 section 独立 draft 的样本数。`2` 启用 Strategy K 的 best-of-N 合并 |
| `LAZY_PAPER_VERIFIER_THRESHOLD` | 否 | `0.85` | quote vs chunk 子串/模糊匹配分数的最低阈值 |
| `LAZY_PAPER_RETRY_THRESHOLD` | 否 | `0.5` | 当 verify 之后覆盖率小于等于该值时触发 retry-when-empty。`0` 表示仅在**所有** required mention 缺失时才重试 |
| `LAZY_PAPER_MIN_SECTION_CHARS` | 否 | `500` | 若 verified 章节短于此值，额外触发一次让 LLM 把章节写厚。`0` 关闭长度触发重试 |
| `LAZY_PAPER_MIN_SECTION_CLAIMS` | 否 | `4` | 同上但针对 claim 数量。两条件任一满足即触发 |
| `LAZY_PAPER_HTML_CITATIONS` | 否 | `hyperlink` | HTML 引用渲染模式：`hyperlink`（可点击逐 claim 锚点 + 文末 sources 段）、`keep`、`remove` |
| `LAZY_PAPER_FIGURE_BIND` | 否 | unset | `1` 启用图-章节绑定：每个 section 在 compose prompt 里附带 top-4 主题相关的图，避免 LLM 引用偏题图。默认关闭；在 meng2024 T1 上发现回归，所以选择性使用 |
| `LAZY_PAPER_AGENT` | 否 | 未设置 | `1` 启用实验性的 pydantic-ai tool-calling agent compose 路径 |
| `LAZY_PAPER_TWO_STEP` | 否 | 未设置 | `1` 启用实验性的 outline→expand 两步 compose 路径 |
| `LAZY_PAPER_WHOLE_PAPER` | 否 | 未设置 | `1` 在每个 section compose 中注入整篇论文文本（成本很高） |
| `LAZY_PAPER_COVERAGE` | 否 | 未设置 | `1` 给 `critic_flags.yaml` 增加实体覆盖率标记 |
| `LAZY_PAPER_CHUNK_SIZE` | 否 | `400` | Retriever 的 chunk 大小（字符数） |
| `LAZY_PAPER_CHUNK_OVERLAP` | 否 | 自动推导 | Retriever 的 chunk overlap |
| `LAZY_PAPER_HIERARCHICAL` | 否 | 未设置 | `1` 启用 parent-child 分层检索 |
| `LAZY_PAPER_PARENT_SIZE` | 否 | `2000` | 启用分层检索时的 parent chunk 大小 |
| `LAZY_PAPER_PARENT_OVERLAP` | 否 | `200` | parent chunk overlap |
| `MINERU_BASE_URL` | 否 | `https://mineru.net/api/v4` | MinerU API base URL（用于自建/代理时覆盖） |
| `MINERU_TIMEOUT_S` | 否 | `1800` | MinerU 轮询的硬截止时间（大 PDF 可能需要调大） |
| `MINERU_POLL_S` | 否 | `10` | MinerU 轮询间隔 |
| `PADDLEOCR_BASE_URL` | 否 | `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs` | PaddleOCR API 端点 |
| `PADDLEOCR_MODEL` | 否 | `PaddleOCR-VL-1.5` | PaddleOCR 模型名 |
| `PADDLEOCR_TIMEOUT_S` | 否 | `1800` | PaddleOCR 轮询的硬截止时间 |
| `PADDLEOCR_POLL_S` | 否 | `5` | PaddleOCR 轮询间隔 |

---

## 4. 架构（一段话）

PDF → 9 个阶段 → 4 种输出格式。s01–s04 做 OCR / 清洗 / 分章 / 图片提取（确定性，不调 LLM）。s05 解析大纲模板。s06–s08 是三个 LLM 驱动的阶段（论文上下文、单图分析、单章 compose）。s09 构造一个不可变的 `Document` 模型并分发给 4 个渲染器（docx/html/pdf/pptx），每个渲染器都是 `Renderer` 的无状态子类。PPTX 渲染器额外会调用 `PptxSummarizer` 来做 4–5 组分组（`summarize_outline`）、单章 bullet（`summarize`）和收尾页（`summarize_paper`）；这些都用 input-hash 做了缓存，所以输入不变时重跑零 LLM 调用。每次 LLM 调用都会把 prompt + response 写到磁盘以便审计。每个阶段都会写 `done.yaml`，重跑时若没加 `--force` 会被跳过。完整的逐阶段说明见 `docs/ARCHITECTURE.md`。

```
PDF ──┬─ s01_ocr → s02_clean → s03_chapter → s04_figures ──┐
      │                                                     │
template.docx ── s05_template ─────────────────────────── ──┤
                                                            │
                                          s06_context       │ (text LLM)
                                          s07_figure_analyze│ (vision LLM)
                                          s08_section_compose│(text LLM)
                                          s09_render ───────┘
                                              │
                       runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}
```

---

## 5. 已验证状态

在 13 篇论文 corpus 上以 Strategy KL（v1.8.1+）端到端验证通过。最近一次完整 run：2026-05-21，详情见 `docs_zh/v1_8_2_corpus_validation.md`。

| 论文 | 流水线 | 重点得分 |
|---|---|---|
| meng2024（3 次 run）| 各 15/15 章节 | T1 基准恢复 12 / 17 / 16（均值 15.0、地板 12）|
| yang2025 | 15/15 | T2 不杜撰储能数据 3/3 ✓ |
| fu2020 | 15/15 | T5 基础 3/4 ✓ |
| chai2026 | 15/15 | T6 基础 4/4 ✓ |
| ali2025_flash | 15/15 | T4 比较深度 0/5 ⚠（LLM 采样方差；corpus 报告有分析）|
| gaur2022 | 15/15 | 通用 ✓（retry-when-empty 触发 2 次）|
| ge2025 | 15/15 | 通用 ✓（retry 2 次）|
| he2023 | 15/15 | 通用 ✓ |
| liu2022 | 15/15 | 通用 ✓ |
| pamula2025 | 15/15 | 通用 ✓（retry 3 次）|
| pan2025 | 15/15 | 通用 ✓（retry 2 次）|
| randall2021 | 15/15 | 通用 ✓ |
| yao2022 | 15/15 | 通用 ✓ |

DOCX 与 HTML 总是会被产出；PDF / PPTX 只在 `--formats` 包含它们时才产出（上面 v181 corpus run 只产了 docx+html）。输出路径：`runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`。

**测试**：253 个（2 个标记 `-m live` 被默认跳过）。运行命令：`uv run pytest -q`。

---

## 6. 在哪里做修改

| 目标 | 文件 / 操作 |
|---|---|
| 添加新的大纲模板 | 传 `--template <new>.docx`（无需改代码） |
| 切换 LLM 供应商 | 在 `.env` 改 `LLM_*_BASE_URL` / `LLM_*_MODEL`（任意 OpenAI 兼容端点） |
| 切换输出语言 | 传 `--lang en` 或 `--lang zh` |
| 选择输出格式 | 传 `--formats docx,pdf,html,pptx`（是 `docx,pdf,html,pptx` 的子集） |
| 重跑失败的格式 | 传 `--only s09_render --retry-failed` |
| 新增一个流水线阶段 | 见 `docs/ARCHITECTURE.md` 的 "Adding a new LLM stage" |
| 调整图片合并 | `stages/s04_figures/runner.py::_merge_figure_subpanels()` |
| 调整 LLM prompt | `llm/prompts/{paper_context,figure_analyze,section_compose,pptx_outline,pptx_summarize,pptx_paper_summary}.md` |
| 自定义 PPT 标题/副标题 | `--presenter`、`--affiliation`、`--pptx-subtitle` |
| 自定义 PPT 母版 | `--pptx-template <file.pptx>` |
| 切换 PPT bullet 模式 | `--pptx-bullets {llm,rule}` |
| 约束 LLM 成本 | 设置 `LLM_MAX_TOKENS_CEILING`（例如设成 `8000` 控制在配额内） |

---

## 7. 已知限制

- **s08 的 LLM 复述倾向**：section composer 可能产出略带复述的总结，而非紧凑的分析性散文。可针对你的领域词汇调整 `llm/prompts/section_compose.md`。
- **图片–caption 配对**：s04 把 caption 配对到 OCR 出来的 Markdown 中最近的前面那张图。对标准学术排版很稳；多栏论文里 caption 离图很远时可能错位。
- **caption 中的 LaTeX**：`_math.py::normalize_math()` 覆盖希腊字母 + 常见上下标。重度嵌套的 LaTeX 可能会原样透传。
- **PPT 密度**：每行都是公式的论文（重理论型）可能产出过长的单条 bullet，建议手动编辑。
- **Windows 上的 WeasyPrint**：需要 GTK runtime（Pango/Cairo）。建议用 Docker；或者只用 docx/html/pptx（不依赖 GTK）。
- **同模板论文的大纲分组可能重复**：如果 18 篇论文共享同一个 `template.docx`，它们的 s09 大纲分组可能在结构上很相似，因为章节标题一致。`llm/prompts/pptx_outline.md` 中注入论文特定关键词可以缓解；若不为每篇论文单独写模板就无法完全消除。

---

## 8. 可以安全删除的文件

| 路径 | 说明 |
|---|---|
| `runs/<paper_id>/s01_ocr/` | 体积较大的原始 OCR 输出。可用 `--force` 重新生成。想跳过重 OCR 就保留它。 |
| `runs/<paper_id>/*/*.prompt.md` 和 `*.response.json` | LLM 审计踪迹。可以删；重跑时会自动重建。 |
| `lazy_paper.egg-info/` | editable install 的元信息。`uv pip install -e .` 会重建。 |
| 任何位置的 `__pycache__/` | Python 自动重建。 |
| `runs/<paper_id>/s09_render/llm_cache/` | PPT LLM 调用的缓存。删掉会让下次运行重新做全量 summarization。 |

**不要**删 `runs/<paper_id>/s09_render/preview.*` — 那是最终产物。

---

## 9. AI agent 快速上手

如果你是接手本仓库的 LLM 编码 agent：

1. 先读本文件。
2. 读 `docs/ARCHITECTURE.md` 了解逐阶段契约。
3. 读 `docs/AGENT_GUIDE.md` 了解 AI 专属的工作流（subagent 模式、何时分派、v1.0–v1.1 开发期观察到的反模式）。
4. 任何改动前后都先跑 `uv run pytest -q`。
5. 扩展流水线时，遵循阶段目录结构：`stages/sNN_<name>/runner.py` + `stages/sNN_<name>/tests/`。在 `cli.py::STAGE_ORDER` 中注册。
6. 扩展 PPT 排版时，改 `stages/s09_render/renderers/pptx.py`；如果改动会影响 LLM prompt，请在 `pptx_summarizer.py` 中把对应的 `_PROMPT_VERSION` 加一（用于失效缓存）。
7. 推送前至少做 2 篇论文的端到端验证。可使用 `runs/` 中那 5 篇已验证论文。

---

## 10. 发布历史

- **v1.4 规划**（规划阶段，2026-05-20，经过第 2 轮研究后重写）：研究验证过的 **4 步**路线图，见 `docs/v1_4_content_roadmap.md`。类别正确的锚点项目：**Microsoft GraphRAG**（实体/KG grounding）+ **ByteDance DeerFlow**（scoped sub-agent 模式）+ **OpenScholar / AllenAI**（科研型自反思引用 grounded 生成）+ **agentic-rag-for-dummies**（LangGraph 形态的参考实现）。架构：(1) PaperKG 抽取器（每篇论文一次 LLM pass，GraphRAG 精简成单文档模式）；(2) 分层 parent-child 混合 retriever（约 200 LOC）；(3) 15 个 section sub-agent 配 retrieve-or-commit 自反思 gate；(4) 两层 critic — 先 Python 正则（数字 / Fig.N / 化学式 → grep 源文），仅在正则触发标记时调 LLM critic。**LangGraph 仍被拒绝** — 抽取其 node-shape 语义约 150 LOC；不引入框架依赖。每篇论文成本 +50%（正则那一层免费完成大部分校验）。约 9 天；可拆为 v1.3.4（步骤 1+2+4a，5 天）→ v1.4.0（步骤 3+4b，4 天）。初稿（PaperQA2 / STORM / Sakana / DSPy）**已废弃** — 类别不对。等待维护者放行。
- **v1.3.3**（2026-05-20）：动态 section-divider 布局。按估算的换行数测量每个 bullet 的高度；bullet 以恒定 0.18" 间距累计排布；卡片需要时从 4.5" 拉伸到 5.4";只在万不得已时才缩字号。同时 `_read_fig_notes` 在 s07 YAML 防御性解析失败时通过正则从 `raw` 字段恢复 caption/deep_observation（修复 ali2025_flash Fig. 28 看似空白的幻灯片）。
- **v1.3.2**（2026-05-20）：留白 vs 截断审计。`_BULLET_CAP_TABLE` 重新校准，使得任意密度都允许多行 wrap（每条 bullet 2-3 行）而不是 1 行 + 省略号。10 篇语料库的 section-divider 省略率从 42% 降到 2.9%，同时仍保住 4.5" 的卡片高度 — bullet 现在用内容填满可用纵向空间，而不是留白。
- **v1.3.1**（2026-05-20）：加固性发布。逐页审计中发现的 8 个 PPT 缺陷已修：`_combined` 观察重叠、稀疏卡片 autofit 裁剪、单一观察空间浪费、caption-header 50/55 字符截断、7-bullet 上限过紧、量化校验失败时的 soft-accept（对英文论文是灾难性的）、Priority-3 fallback `[:60]` 词中截断、章节 prompt 语言指令、fallback 观察 200 字截断、异形 Unicode 标点。语料库从 4 篇扩到 10 篇（新增 fu2020 / ge2025 / chai2026 / pamula2025 / meng2024 / gaur2022）。新增 `scripts/audit_pptx.py` 逐页校验器。189 个测试。
- **v1.3.0**（2026-05-19）：质量发布。LLM 后的**量化内容校验**（章节 ≥1 量化 bullet；论文 ≥3 + 比较性结论；全描述性的图片观察会被拒）。**自适应 PPT 排版**：大纲行按 wrap 数自适应，KEY POINTS 卡片按密度自适应（16→13pt），图片观察纵向 guard。3 个 summarizer 方法处都加了**显式失败日志**。s08 能看到更多上下文：图片观察 100→400 字、caption 120→300、章节摘录 8000→15000（≤8 章的论文用全文）。跨渲染器的表格样式统一。README + README.zh 用真实的 PPT 截图重做。178 个测试。在覆盖 EN+ZH、单晶/综述/理论/薄膜主题的 4 篇论文上完成端到端验证。
- **v1.2.2**（2026-05-19）：PPT 大纲现在尊重 `--lang en`（之前无论如何都产出中文分组名）。`_lang_directive` 注入到 `pptx_outline.md`；`_OUTLINE_PROMPT_VERSION` v12→v13。`_is_low_diversity` 重构为按语言区分（CJK 子串 vs 英文 word token），并把 "每个分组都出现" 的阈值收紧 — 消除英文误报。
- **v1.2.1**（2026-05-19）：s05_template 在源 docx 变化时自动失效缓存（在 `done.yaml` 里存 docx 的 SHA-256）；自动重跑时 CLI 会打印 "[s05_template] template content changed — invalidating cache"。修复一类 bug：早于 v15 的旧版中文前缀标题会传染给那些在模板英化前就 OCR 完的论文输出。
- **v1.2.0**（2026-05-19）：两个 PPT 视觉 bug（Unicode 下标 font fallback、≥6 bullet 时 KEY POINTS 卡片重叠）— 已解决。`_math.py` 把拉丁系 Unicode 下标折叠为 `_<plain>`；`_section_divider` 在 n_bullets≥6 时缩小字号；`SlidePlanner._truncate_bullet` 对长度设上限。164 个测试。
- **v1.1.0**（2026-05-19）：大纲 LLM 调用的 max_tokens 提升 + 环境上限；章节标题编号统一；deep-observation 字号 11→13pt；CLI `--only` 支持逗号分隔 + 未知阶段校验;image-data-url helper 合并到一处；158 个测试。
- **v1.0.0**（2026-05-18）：首次公开发布。4 种输出格式、9 阶段流水线、docker + 裸机两种安装路径。
