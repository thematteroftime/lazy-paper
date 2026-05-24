# lazy-paper — 生产环境交接文档

> **状态：** 已发布 · **测试：** 300/300 通过（2 个 deselected `-m live`） · **端到端验证：** 9-paper variant test + 18-paper v1.9.2 corpus + v1.11.1 sentence-level audit + cycle-14 4-spec+2-meta cross-check + cycle-15 3-spec+2-meta planning audit · **最近发布：** v1.11.4 (2026-05-24，2 个 drive-by literal 修复 + `docs/INTERNAL/audit_subagent_template.md`)
>
> **v1.11.3** 是针对 meng2024 ch06 "错绑电场 + 凭空 E_b" 幻觉与 ch07 thin-numerics 退化的 targeted pipeline hotfix。两个改动 (~15 LOC)：(a) `section_compose.md` 加 "NO MAKING UP NUMBERS" abstention 规则；(b) `structured.py` retry-when-short swap guard 现在接受 "numeric anchor 数严格增加" 的 retry，不只是 "verifier-accepted claim 数 >=" 这一条。已知 v1.12 issue：F2 在 ch06 触发过严 — LLM 完全放弃写 `5.00 J/cm³`（chars 4261→1234），尽管 chunks 实际有正确共现（c0023）。按项目原则 "不编 > 编错"，本 hotfix 接受 trade-off；v1.12 会加 same-chunk-pairing 规则让 composer 写对的而不是 abstain。
>
> **v1.11.2** 是 tooling/erratum 发布——pipeline 行为零变化 vs v1.11.1。cycle 12 audit #1 报告 ali2025_flash ch13 捏造三个 baseline 数值；2 个独立 meta auditor 然后推翻该报告（OCR LaTeX 间隔 `1 7 . 3` 形式 — plain `grep` 漏抓）。hotfix candidate 加了 prompt rule + numeric verifier advisory，在 commit 前被 revert，因为 spec 确认它在真章节引入真 regression。ship 的是：`scripts/audit_grep.py`（OCR-tolerant 替代品）+ TEST_FRAMEWORK 中"审计陷阱"节，避免 subagent audit 重蹈方法论错误。
>
> **已知 v1.11.3 候选**（defer 到独立 diagnostic cycle）：meng2024 ch06 把 `W_rec=5.00 J/cm³ / η=90.09%` 错绑 "180 kV/cm"（源论文：340 kV/cm）+ 捏造 `E_b=214 kV/cm`（源论文无此值）；meng2024 ch07 在 v1.10 → v1.11.1 之间丢掉了 `5.00 J/cm³` 引用。单行 cap fix attempt（retriever cap 12→24）试了被 revert（ch06 没修 + 章节字数塌缩 -60%）。真因是 v1.10→v1.11.1 STRUCTURED 路径迁移的结构性问题，需要独立 audit cycle 而不是一行 patch。
>
> **v1.11.1** 落地 4 个 HIGH bug 修复，来自 cycle-11 sentence-level audit（3 个 subagent 交叉验证 output vs 源论文）。v1.11.0 通过了 architecture-review ship gate 但未 push；v1.11.1 是 v1.11 线第一个 stable。
>
> - **Bug #1+#2（flagship 数值跨章节漂移）** — meng2024 ch07/09/13/15 对同一 flagship sample 给出 3 个不同 W_rec 值。修复：从 KG（`mat_main --has_W_rec-->`）抽 `headline_metrics` 注入 `context.yaml` 作为硬 ground-truth；prompt 强约束 composer 用准值。
> - **Bug #3（author misattribution）** — meng2024 ch13 把 Ma et al. 的结果错归到 Cao et al.。修复：post-verify advisory `author_not_in_chunk_advisory`，默认 advisory，`LAZY_PAPER_AUTHOR_HARDREJECT=1` 升级为硬拒。
> - **Bug #4（OCR text-prompt 被当物理图）** — hif_2 ch15 对 "图 43" 捏造物理 critique，实际该图是 unCLIP appendix 的 generation prompt 字面 `(a) A high quality photo of a dog…`。修复：双层 caption-stub 过滤（`is_generation_prompt_caption`）于 s04 + s07 defense-in-depth。
> - **双语回归防护** — `cli.py` 写 `meta.yaml.lang`；s07 在 `lang=zh` 但前 5 条 `visual_summary` CJK 字符 < 30% 时打 stderr WARNING；s09 builder 把 Untitled 兜底标题本地化为 "未命名章节"。
>
> **v1.11.0** 是一次 first-principles refactor（commit `a4d90ab`），从 v1.10 主动**删掉**了 3 个 over-engineered 模块：cross-citation reject（~40 LOC）、figure-retry pass（~85 LOC）、headline-metric prompt rule。理由记录见 `docs/ARCHITECTURE.md` §11。
>
> **v1.10.0** 上线 **Variant C — figure_ids 硬约束**：schema-level figure citation + figure-retry pass + env-gated whitelist。从 3-variant × 9-paper × 3-audit-cycle 测试（33 LLM run、9 specialist auditor）里选出。在多图论文上跑出真 100% figure embed（ali2025_flash 26/26、hif_1 20/20、hif_2 17/17），保住 meng2024 T1 = 9/9/9 零方差，在 ali2025_flash T4 上破基线（4→5）。同时上线 `normalize_ocr_latex` BS3+BS4（LaTeX escape 折叠 + Unicode NFKD）提升所有 variant 的 verifier 精度。完整验证见 `docs/v1_10_variant_comparison.md`。
>
> **v1.9.2** 在 v1.9.0 informed-retry 之上落地 8 个 high-impact bug 修复（2-auditor + 3-reviewer + 2-confirmation 循环）。在 18 篇语料（13 corpus + 5 newly OCR'd）的验证下保持 meng2024 T1 = 9/9/9 零方差。HTML 可点击引用成为终端用户默认。完整报告见 `docs_zh/archive/v1_9_2_20_paper_validation.md`。
>
> **v1.9.0 上线 informed-retry，把 meng2024 T1 的方差降到 0。** 之前的 retry-when-empty 用的是笼统的 "你漏了 required mentions" 提示。v1.9 现在为每个缺失的 required mention 生成包含具体锚点 token（作者姓氏 OR 关联数值）的逐实体诊断，LLM 拿到的是一份确定性检查清单。**meng2024 三次独立 run 在 T1 上全部 9/17** —— 方差从 v1.8.1 的 stdev 2.6 降到 v1.9 的 **stdev 0**。完整分析见 `docs_zh/archive/v1_9_validation_results.md`。
>
> **v1.8.x 基础不变。** Strategy KL 仍是推荐的高质量默认方案。verifier 在子串匹配前对 LaTeX/OCR 形式做归一化；retry-when-empty 在 verify 之后测量覆盖率，verifier 刚 drop comparator claim 时会触发，一次加强 LLM 调用可恢复。
>
> v1.4.x 基础设施（PaperKG / 两层 reviewer / Onyx 引用处理器）保持不变。基于 pydantic-ai 的 section agent（`LAZY_PAPER_AGENT=1`）仍 opt-in。完整 v1.4.0 → v1.11.1 release 轨迹见 CHANGELOG.md。

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
| `LAZY_PAPER_FIGURE_ID_WHITELIST` | 否 | `1`（开启） | v1.10。verifier 把未知 `fig_id` 从 accepted claim 剥除，并把正文里的 `Fig. N` / `图N` 替换为按 lang 的 `UNKNOWN_FIGURE_LABEL`。设 `0` 退回 advisory-only |
| `LAZY_PAPER_AUTHOR_HARDREJECT` | 否 | `0`（advisory） | v1.11.1。`1` 时 post-verify 丢掉那些作者姓氏没出现在任何 cited chunk 文本里的 claim。默认 advisory（在 `critic_flags.yaml` 记 `author_not_in_chunk_advisory`）；只在你的语料上确认精度后才升级为硬拒 |
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

最近一次大规模验证：**v1.10 — 3-variant × 9-paper × 3-audit-cycle 测试（2026-05-23）**，完整报告 `docs/v1_10_variant_comparison.md`；v1.11.1 又做了 cycle-11 sentence-level audit 修了 4 个 HIGH bug（见 banner）。

**Variant C**（v1.10 默认，配 `LAZY_PAPER_FIGURE_BIND=1`）的关键数字：

| 论文 | 流水线 | M2 fig embed | M4 TestCase |
|---|---|---|---|
| meng2024（3 次 run）| 各 15/15 | 7/7（100%）| T1 = 9/9/9（stdev 0）✓ 地板；T3 = 4/4/4 |
| yang2025 | 15/15 | 5/5 | T2 = 3/3 ✓ |
| fu2020 | 15/15 | （仅 baseline）| T5 = 3/4 ✓ |
| chai2026 | 15/15 | 2/2 | T6 = 4/4 ✓ |
| ali2025_flash | 15/15 | **26/26（100%）** | T4 = **5/5 🏆（破基线 4）** |
| gaur2022 | 15/15 | 1/1 | 通用 ✓ |
| he2023 | 15/15 | 8/8（100%）| 通用 ✓ |
| pan2025 | 15/15 | 4/4 | 通用 ✓ |
| hif_1（Adv Mat 综述, 62 页, v1.10+）| 15/15 | **20/20（100%）** | （跨域）|
| hif_2（DALL-E 2, 17 图, v1.10+）| 15/15 | **17/17（100%）** | （跨域）|

variant A/B 的 M2/M4 对比 + 零方差 stdev 表见 `docs/v1_10_variant_comparison.md` §3。

**重要 — 环境变量解锁 M2 figure binding**：100% 那一列依赖 `LAZY_PAPER_FIGURE_BIND=1`。不开 variant C 仍受益（LLM 在 schema + base prompt 下会主动引图），但比率更低 — 见 `.env.example` 推荐 env 组合 + `docs/v1_10_variant_comparison.md §7` 的 env-on vs env-off 对比。

DOCX + HTML 总是会被产出；PDF / PPTX 只在 `--formats` 包含它们时才产出。输出路径：`runs/<paper_id>/s09_render/preview.{docx,pdf,html,pptx}`。

**测试**：300 个（2 个标记 `-m live` 被默认跳过）。运行命令：`uv run pytest -q`。

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
3. 读 `docs/AGENT_GUIDE.md`（或中文版 `docs_zh/AGENT_GUIDE.md`）了解 AI 专属工作流（subagent 模式、何时分派、当前最佳实践 — 从 v1.0 → v1.11 release 周期总结）。
4. 任何改动前后都先跑 `uv run pytest -q`。
5. 扩展流水线时，遵循阶段目录结构：`stages/sNN_<name>/runner.py` + `stages/sNN_<name>/tests/`。在 `cli.py::STAGE_ORDER` 中注册。
6. 扩展 PPT 排版时，改 `stages/s09_render/renderers/pptx.py`；如果改动会影响 LLM prompt，请在 `pptx_summarizer.py` 中把对应的 `_PROMPT_VERSION` 加一（用于失效缓存）。
7. 推送前至少做 2 篇论文的端到端验证。可使用 `runs/` 中那 5 篇已验证论文。

---

## 10. 发布历史

完整每版本细节见 `CHANGELOG.md`。要点：

- **v1.11.1**（2026-05-24）：cycle-11 sentence-level audit 出的 4 个 HIGH bug 修复（flagship 数值漂移、author 误归属、OCR-prompt 当物理图、双语回归防护）。300 tests。
- **v1.11.0**（2026-05-23，未 push）：first-principles refactor（`a4d90ab`）— 删 cross-citation reject、figure-retry pass、headline-metric prompt rule（3 个 over-engineered 模块）。297 tests。
- **v1.10.0**（2026-05-23）：Variant C — figure_ids 硬约束，从 3-variant × 9-paper × 3-audit-cycle 测试选出。多图论文 100% embed；meng2024 T1 = 9/9/9 零方差。
- **v1.9.2**（2026-05-22）：8 个 high-impact bug 修复（2-auditor + 3-reviewer + 2-confirmation 循环）；HTML 可点击引用成默认。
- **v1.9.0**（2026-05-22）：informed-retry — 逐实体诊断带 anchor token；meng2024 T1 stdev 2.6 → **0**。
- **v1.8.x**（2026-05-21）：Strategy KL 升为推荐默认（verifier 内 LaTeX/OCR 归一化，retry-when-empty post-verify）；meng2024 T1 地板 1 → 12。
- **v1.7 / v1.6 / v1.5**（2026-05-20 / 19）：KL → J → strategy-matrix 评测 harness（`scripts/evaluate.py`），v1.4 的 4 步规划落地。
- **v1.4 规划**（2026-05-20，第 2 轮研究后重写）：4 步路线图（归档 `docs/archive/v1_4_roadmap.md`）。锚点项目：Microsoft GraphRAG + ByteDance DeerFlow + OpenScholar/AllenAI + agentic-rag-for-dummies。架构：PaperKG 抽取器 + 分层 parent-child 混合 retriever + 15× section sub-agent + 两层 critic。

---

## 11. 历次审计取证 trail（cycle 10 → 12）

| 周期 | 时间 | 类型 | 主要发现 |
|---|---|---|---|
| cycle 10 | 2026-05-22 | 5-paper variance check | v1.9.1 |
| cycle 10b | 2026-05-22 | 18-paper validation | v1.9.2，8 bug fix |
| cycle 11 | 2026-05-23 | 3-variant × 9-paper variant matrix | v1.10.0 Variant C 选出 |
| cycle 11b | 2026-05-23 | architecture review | v1.11.0 cut 3 模块 |
| cycle 11c | 2026-05-24 | sentence-level audit（3 subagent） | v1.11.1 4 个 HIGH 修复 |
| cycle 12 | 2026-05-24 | Audit A/B/C/D 文档审计 | 删 stale scripts/tests、archive 历史文档、同步 v1.11.1 doc |
