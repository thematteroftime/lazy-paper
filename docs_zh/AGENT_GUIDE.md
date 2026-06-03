# lazy-paper — AI Agent 指南

本文档面向被指派维护、扩展或调试本仓库的 AI 编码 agent（Claude Code、Cursor、Copilot 等）。前置阅读：`docs_zh/INTERNAL/HANDOFF.md` 和 `docs_zh/ARCHITECTURE.md`。

## 给 agent 的 TL;DR

1. **不要动 `runs/`**，除非用户明确要求清理。它是已验证的测试语料库。
2. **任何改动前后都要跑 `uv run pytest -q`**。如果弄坏了测试，要么修好要么回滚。应有 300 个用例通过（2 个 `-m live` 被 deselected）；live-LLM 测试通过 `-m live` 门控。
3. **用 `LLM_MAX_TOKENS_CEILING` 环境变量在测试运行中控成本**（例如冒烟测试用 `LLM_MAX_TOKENS_CEILING=4000`）。
4. **不要绕过 `llm.client.max_tokens()`**。所有 LLM 调用都经过它。直接把硬编码的 `max_tokens=N` 改大是倒退做法。
5. **改 prompt 必须同步升 `_PROMPT_VERSION`**（在 `stages/s09_render/pptx_summarizer.py` 中，或其他 LLM 阶段的对应常量）—— 否则缓存响应不会失效。
6. **推送前必须做端到端验证**。从 `runs/` 中已验证的 5 篇论文里至少挑 2 篇，清掉 `s09_render/`，用 `--only s09_render --force` 重跑。PPT 大纲应当生成 4-5 个带要点描述的分组节，而不是扁平的逐章列表。

---

## 工作流模式

### 何时使用 subagent

适合：
- **长耗时批处理**（5 篇论文重新渲染要 30-75 分钟）。派发为 subagent，主上下文不必盯着等。
- **只读代码审计**（找硬编码、重复代码、未使用的 import）。`subagent_type: Explore` 最合适 —— 把冗长的审计输出挡在主上下文之外。
- **目标清晰、验收标准明确的小范围重构**（如"抽出 MIME 辅助函数，更新 2 处调用点，跑测试"）。要给精确的 prompt 和具体的测试命令。

不适合：
- **主 agent 已经理解的快速编辑**。为了改 3 行而派发，纯属浪费启动 token。
- **需要快速用户反馈的任务**。subagent 运行期间不能中断；用户一旦改主意，subagent 的工作就白做了。

### 后台命令 vs subagent

- **批处理脚本**（重渲染脚本、长流水线）用 **`Bash` 加 `run_in_background: true`**。脚本结束时你会收到通知；可以用 `Read` 读取它的日志文件。
- **需要判断 + 工具调用、而不是仅仅执行脚本的任务**用 **`Agent`（subagent）**。

### 缓存失效的坑

四层缓存：
1. **Stage `done.yaml`**：`--force` 可绕过。
2. **`s05_template` 内容哈希**：自 v1.2.1 起，`done.yaml` 记录 `template_sha256_16`，CLI 在源 docx 变化时自动让 s05 失效 —— 不需要 `--force`。**然而**下游阶段（s08、s09）在 s05 刷新时并不会自动失效；它们仍需 `--force`（或直接删除目录）才能拾取新的章节标题。
3. **PPTX summarizer 的 LLM 缓存**（`s09_render/llm_cache/`）：键为 `_PROMPT_VERSION` + lang + 输入内容的 SHA-256。改动 prompt 语义时务必升版本常量。
4. **`s06`/`s07`/`s08` 的审计文件**：每次运行都会写，但阶段的 `done.yaml` 会让整个阶段被跳过。用 `--force` 或删除阶段目录。
5. **`runs/<paper_id>/meta.yaml`**（v1.11.1）：持久化该 run 的 `lang` 字段，外部 auditor / demo 脚本不必再 grep `fig_notes.yaml` 推断语言。不是缓存键，仅作单一信息源。

如果某篇论文产出错误输出且你怀疑是缓存陈旧，最粗暴的修复是 `rm -rf runs/<paper_id>/{s05_template,s08_section_compose,s09_render}` 然后重跑。

**常见坑**：论文已渲染完后又编辑了 `Table of Contents-*.docx`。v1.2.1+ 会自动让 s05 失效，但你还得手动清掉 s08/s09 才能把新标题传播下去。单篇论文最干净的重置流程：

```bash
rm -rf runs/<paper_id>/{s05_template,s08_section_compose,s09_render}
uv run python -m cli run --pdf <pdf> --template <docx> --paper-id <pid> \
  --only s05_template,s08_section_compose,s09_render --force --formats docx,pdf,html,pptx
```

### 需要注意的常见失败模式

| 症状 | 根因 | 修复 |
|---|---|---|
| PPT 大纲为空（扁平 15 行列表、没有分组描述） | DeepSeek-Reasoner 的 reasoning token 可能吃掉 `max_tokens` 预算让正式内容没有 token 可用 | 大纲调用使用 `max_tokens(16000)` + 显式空响应检查；改 outline 时不要调低预算。 |
| 章节标题前后段编号不一致 | 模板的 `number` 字段稀疏（部分为 `''`、其它为 `'12'..'17'`），把它拼进标题会得到混杂形式 | s08 不能嵌入模板的 `number`；编号由 PPT 渲染器按位置加 01–N 前缀。如果改 `cli.py`，保留这一约定。 |
| `--only s08,s09` 静默地什么也不跑 | `--only` 解析器对逗号拆分有 bug | CLI 按逗号拆分并对未知阶段抛 `SystemExit`，改 `cli.py` 时保留这两条行为。 |
| 派发了 subagent 但从未完成 | 多半是上下文超限、会话超时，或 agent 静默撞上权限拒绝 | 用 `TaskOutput` 或读 subagent 跑过脚本写入的日志文件来核实。不要假定"subagent 结束 == 工作完成"。 |

### 应避免的反模式

- **通过在解析逻辑里硬编码特例来"修"docx 模板。** 如果模板解析错了，去修解析器（`stages/s05_template/runner.py`），不要改模板。模板是用户数据；解析器才是你的代码。
- **为了修一篇论文而加针对该论文的硬编码逻辑。** `he2023` 失败了就修通用代码路径，让它不再可能失败。如果实在必须特例化（比如已知的坏 PDF），用 flag 门控。
- **改完之后挂掉的测试不要直接删。** 先诊断：是你的改动错了，还是测试已经过时？只有当断言不再反映原意时才更新测试。
- **不重渲已验证论文就升 prompt 版本。** 一次版本提升会让所有缓存失效 → 下一次用户运行会全量重跑 LLM → 产生意料之外的成本。
- **构建通过就把任务标记为完成。** 对于渲染器变更，"完成"包括对实际产物做一次肉眼检查。把 PPT 转成 PNG 看一眼。

### 视觉验证

渲染器的 bug 通常是视觉性的（字体过小、重叠、语言错误、KaTeX 没加载到）。务必渲染为 PNG 检查。

**PPTX：**

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice \
  --headless --convert-to pdf --outdir /tmp/preview \
  runs/<paper_id>/s09_render/preview.pptx

uv run --with pymupdf python -c "
import fitz
doc = fitz.open('/tmp/preview/preview.pdf')
for i in [0, 1, 4, 7]:
    if i < len(doc):
        doc[i].get_pixmap(dpi=120).save(f'/tmp/preview/s{i+1:02d}.png')
"
```

**HTML（v1.13）** —— KaTeX 在客户端渲染，文件里只能看到 Unicode 兜底。验证真渲染结果要走浏览器：
- 在真实浏览器打开 `preview.html`，确认 `<span data-tex>` / `<figure class="formula-block">` 显示出 KaTeX 排版的数学，而不是兜底文本。
- 如果用了 `LAZY_PAPER_INLINE_KATEX=1`，文件应该 ~1 MB 且 grep 不到 `cdn.jsdelivr.net`。
- PDF（同套 HTML 走 WeasyPrint），打开后应看到公式以 italic serif 兜底显示 —— KaTeX **不**会跑。

然后通过 Read 工具读取 PNG / HTML / PDF 来检查。

### 与用户沟通

- **简洁**。用户已经在 PPT 布局上反复调了几个小时，不想看长篇叙述。
- **直接说结果和决策**。"通过 Y 修了 X。5 篇论文已验证。已推送。" 比 "我已完成工作。让我解释我做了什么。" 要好。
- **低风险可逆操作不用请示**（如跑测试、读文件）。但推送前、执行破坏性 `rm` 前、`git push --force` 前必须征求同意。
- **输出路径很重要**。完成渲染时，把产物的绝对路径告诉用户，方便他们打开。

---

## PaperDB + 检索器工作流模式

### 何时重跑 KG 抽取，何时复用

`paper_kg.parquet` 由 s06 写一次，**按设计即使 s06 加 `--force` 也会保留**。KG 抽取是一次针对整篇论文的 LLM 调用；重跑每篇论文约消耗 1 次 API 调用、耗时 15-30 秒。要强制重抽，必须显式删除该文件：

```bash
rm runs/<paper_id>/s06_context/paper_kg.parquet
uv run python -m cli run ... --only s06_context --force
```

需要重抽的情况：
- `kg_extract.py` 的 prompt 或 schema 变化了（同步升 schema 版本）。
- 某篇论文产生了 `kg_extract.failed` 标记但你认为是误判（如瞬时 API 错误）。
- 你手工编辑了章节文本，想让 KG 反映该编辑。

不必重抽的情况：
- 用 `--force` 重跑 s08（KG 不变；只有证据检索和组合会刷新）。
- 在 pptx_summarizer 里升 `_CHAPTER_PROMPT_VERSION`（那只会让 s09 缓存失效，与 KG 无关）。

`retrieval.parquet` 遵循同样的规则：除非显式删除或存在 `retrieval.failed`，否则在 s08 的 `--force` 下也会保留。

### 调试 retriever 质量

要在不跑完整流水线的前提下查看某一节将接收到的证据：

```python
uv run python -c "
from llm.retriever import Retriever
r = Retriever.load('runs/<paper_id>/s08_section_compose/retrieval.parquet')
hits = r.retrieve('your query here', top_k=8)
for h in hits:
    print(h.score, h.text[:120])
"
```

如果命中结果看起来不相关，检查：
1. `retrieval.parquet` 是基于正确的章节集合构建的吗？（看 s08 的 `done.yaml` 中的 `retriever` 字段）
2. query 文本是否贴近实际的节指导？逐字使用模板的 guidance 字符串。
3. KG entity boost 是在帮忙还是在帮倒忙？试试 `entity_boost=[]` 隔离出 dense+BM25 的基线。

若存在 `retrieval.failed`，s08 已记录 `[degraded] keyword fallback for <paper>` —— 检查 embedding API key（`LLM_EMBEDDINGS_API_KEY`，未设置时自动继承 `LLM_VISION_API_KEY`）是否有效。

### 解读 critic_flags.yaml

`s08_section_compose/critic_flags.yaml` 由 `reviewer.regex_check()` 在每节组合完成后产出。格式：

```yaml
- section: "Introduction"
  flags:
    - span: [42, 55]
      claim: "8.6 J/cm³"
      problem: numeric_not_in_source
      evidence: null
    - span: [120, 132]
      claim: "Fig. 99"
      problem: fig_not_in_yaml
      evidence: null
```

**当前行为**：regex 层为 LLM 层把关 —— 只有当 `regex_check()` 返回 ≥1 个 flag 时，`reviewer.llm_review()` 才会运行。查 `critic_flags.yaml` 可以了解某次 LLM critic 重写为何被触发，或在没有 LLM critic 介入时事后审计 s08 输出质量。

problem code 含义对照表：

| 代码 | 含义 |
|---|---|
| `numeric_not_in_source` | 草稿里的某个数值（带单位）在做完单位归一化后，仍未出现在任何源 chunk 中。 |
| `fig_not_in_yaml` | 草稿中的某条 `Fig. N` 或 `Table N` 引用与 `figures.yaml` 中的任何条目都不匹配。 |
| `formula_not_in_kg` | 草稿中的某个化学式或符号绑定与任何 KG entity 都不匹配。 |
| `unit_mismatch` | 两个值指向同一物理量但单位不兼容（如 kV/cm vs MV/cm，归一化未通过）。 |

### 开启实验性 pydantic-ai agent

Section agent（`stages/s08_section_compose/agent.py`）通过 `LAZY_PAPER_AGENT=1` 门控。开启方式：

```bash
LAZY_PAPER_AGENT=1 uv run python -m cli run ... --only s08_section_compose --force
```

agent 每节最多跑 8 次工具循环（`query_kg`、`retrieve`、`check_source`，最后是 `emit_section`）。每次工具调用都会打到 stderr。需要留意：

- `[degraded] agent fallback for <section>` —— agent 撞到错误或达到迭代上限；该节是通过 legacy 路径组合的。
- 草稿出现 meta-评论的章节（如"I will now synthesize…"）—— agent 返回的是关于"如何写"的散文，而非实际的节文本。这就是为什么有这个 flag；默认路径才是稳定的。

CI 或自动化批跑中不要启用 `LAZY_PAPER_AGENT=1`，除非已在你自己的论文语料上审计过 agent 输出。

### 开启 author-hardreject（v1.11.1）

v1.11.1 新增的 author-not-in-chunk 检查（`stages/s08_section_compose/structured.py:470-497`）**默认是 advisory** —— 在 `critic_flags.yaml` 记录 `author_not_in_chunk_advisory`，claim 保留。要升级为硬拒（claim 引的作者姓氏没出现在任何 cited chunk 文本里就丢掉整条 claim）：

```bash
LAZY_PAPER_AUTHOR_HARDREJECT=1 uv run python -m cli run ...
```

只在你的语料上确认精度后才开启。默认 advisory 的原因是：v1.11.1 首轮 18 篇语料发现一些合法的转述情况（比如 "Ma 等人" 出现在 quote 里，但不在逐字 chunk 切片里）。如果你的语料对作者引用要求严格，再开启。

### 引用渲染模式与 --debug-citations

默认情况下，`[span:doc_X:Y-Z]` 引用标记会从 DOCX 和 HTML 输出中剥除（模式：`REMOVE`）。要保留它们做调试：

```bash
uv run python -m cli run ... --debug-citations
```

这会把 citation adapter 切到 `KEEP` 模式，让标记作为字面文本保留。适用场景：

- 审计被检索到的 chunk 是否在最终散文中被引用。
- 检查 `emit_section` 是否正确地在接受草稿前要求了 ≥1 处引用。
- 把幻觉追溯回应当负责的检索 chunk（或缺失的 chunk）。

PPTX 演讲者备注无论 `--debug-citations` 与否始终保留标记。

---

## 用于熟悉项目的文件地图

```
cli.py                          # 入口；argparse + 阶段派发
conftest.py                     # 全局 pytest fixture；macOS DYLD shim

llm/
  client.py                     # LLM 类（OpenAI 兼容） + max_tokens() 辅助
  models.yaml                   # role -> env_prefix + 默认模型
  prompts/*.md                  # 每个 LLM 调用点对应一个 prompt
  retriever.py                  # Retriever：build_index() + retrieve()（llama-index + bm25s + RRF）
  citation/
    models.py                   # SearchDoc / CitationInfo 辅助类型
    __init__.py                 # CitationAdapter；--debug-citations 的模式开关

stages/_common/                 # 共享辅助函数（yaml、路径、done 标记、图像、bbox）
stages/sNN_<name>/runner.py     # 阶段入口；由 cli._run_one 调用
stages/sNN_<name>/tests/        # 每个阶段的单元测试

stages/s06_context/
  runner.py                     # context.yaml + 触发 kg_extract
  kg_extract.py                 # instructor 驱动的 10 类 KG → paper_kg.parquet

stages/s08_section_compose/
  runner.py                     # retriever 驱动的组合 + reviewer 编排
  agent.py                      # pydantic-ai agent（LAZY_PAPER_AGENT=1）
  reviewer.py                   # regex_check() + llm_review()（CritiqueRevision）
  _units.py                     # 单位归一化（kV/cm ↔ MV/cm 等）

stages/s09_render/
  builder.py                    # markdown 章节 -> 不可变 Document
  model.py                      # Document / Chapter / Block 数据类
  slide_planner.py              # Document -> SlideDeck（确定性）
  pptx_summarizer.py            # LLM 驱动的 summarize_outline / summarize / summarize_paper（带缓存）
  renderers/{base,docx,html,pdf,pptx}.py
  templates/                    # html/pdf 渲染器的 Jinja2 模板

docs/
  ARCHITECTURE.md               # 每个阶段的契约（读完本文后看）
  AGENT_GUIDE.md                # 你正在看的文件
  USER_GUIDE.md                 # 终端用户手册（安装、快速上手、迭代、排错）
  INTERNAL/HANDOFF.md           # 生产交接摘要
  INTERNAL/superpowers/         # 历史规格 + 计划

tests/                          # 跨切面测试（cli、llm client 等）
runs/                           # 已 gitignore —— 每篇论文的产物（本地提交了 5 篇已验证论文）

CHANGELOG.md                    # Keep-a-Changelog 格式
README.md                       # 面向人类的快速入门
CONTRIBUTING.md                 # 贡献规范
```

---

## 工作完成后

1. `uv run pytest -q` → 300 个通过，2 个 deselected。
2. 至少 2 篇论文的端到端冒烟测试（用 `--only s09_render --force` 重跑）。
3. 更新 `CHANGELOG.md` 的 Unreleased 小节。
4. 用清晰的 commit message 提交（解释 *why*，而不只是 *what*）。
5. 只有在用户确认后才 `git push origin main`。
6. 如果改动对用户可见，请在最后的消息里给出产物路径。
