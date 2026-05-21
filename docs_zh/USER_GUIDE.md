# lazy-paper — 用户指南

## 适用读者

你是一位研究者（或他/她的助手），手头有一篇科研 PDF，想要把它转换成结构化的多格式分析文档 —— 而且不想自己写代码。本指南会带你完成环境配置、首次运行，以及如何对输出结果进行迭代调优。

如果你是维护本仓库的 AI coding agent，请改读 `docs/AGENT_GUIDE.md`。

---

## 首次配置

### 1. 安装 uv 与 Python

lazy-paper 使用 [uv](https://github.com/astral-sh/uv) 管理 Python 环境。除了 uv 自带的 Python，你**不**需要额外的系统 Python。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

然后克隆仓库并初始化环境：

```bash
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"
```

### 2. 系统依赖（仅 macOS）

WeasyPrint（用于生成 PDF）需要原生系统库：

```bash
brew install pango gdk-pixbuf libffi cairo
```

在 Linux 或 Windows 上，请改用 Docker：

```bash
docker compose build
# 然后把 "uv run python -m cli run ..." 替换为：
docker compose run --rm lazy-paper run ...
```

### 3. 创建 .env 文件

```bash
cp .env.example .env
```

用文本编辑器打开 `.env`，填入必需的 token：

| 变量 | 含义 | 申请地址 |
|---|---|---|
| `MINERU_TOKEN` | MinerU 云端 OCR API key | [mineru.net](https://mineru.net/) — 有免费额度 |
| `LLM_TEXT_API_KEY` | 文本 LLM 的 API key | [platform.deepseek.com](https://platform.deepseek.com/) 或任意 OpenAI 兼容服务商 |
| `LLM_VISION_API_KEY` | 视觉 LLM 的 API key | [dashscope.aliyun.com](https://dashscope.aliyun.com/)（Qwen-VL） |
| `LLM_EMBEDDINGS_API_KEY` | embeddings 的 API key（v1.4+） | **可选** — 若不设置则自动沿用 `LLM_VISION_API_KEY` |

如果你的视觉服务商支持 `text-embedding-3-small`，就不需要单独的 embeddings key。DashScope（Qwen-VL 的服务商）支持，所以默认的 `.env.example` 把 `LLM_EMBEDDINGS_API_KEY` 留空。

---

## 五分钟快速开始

`.env` 配置好之后，运行：

```bash
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --lang zh \
  --formats docx,pdf,html,pptx
```

把 `papers/your-paper.pdf` 替换为你的 PDF 路径。`--template` 后面填入你的章节大纲 `.docx` 文件（在 `templates/` 目录下有示例）。

输出会落在：

```
runs/mypaper/s09_render/
  preview.docx
  preview.pdf
  preview.html
  preview.pptx
```

整个 run 大约耗时 5–20 分钟，取决于论文长度和 API 延迟。每个 stage 会写入一个 `done.yaml` 标记，所以如果运行中断，直接再跑同一条命令就能从中断处继续。

---

## 选择 OCR 后端

| 后端 | 配置 | 适用场景 | 备注 |
|---|---|---|---|
| **MinerU** | `OCR_BACKEND=mineru` | 图多的论文；多栏排版 | 云端 API；需要 `MINERU_TOKEN`；略慢 |
| **PaddleOCR-VL** | `OCR_BACKEND=paddleocr` | 纯文本论文；周转快 | 云端 API；需要 `PADDLEOCR_TOKEN`；`.env.example` 默认 |

可以在 `.env` 里配置，也可以在单次运行时覆盖：

```bash
OCR_BACKEND=mineru uv run python -m cli run ...
```

如果你的论文图较多、默认的 PaddleOCR 漏识别了图像边界框，请切换到 MinerU。

---

## 选择 LLM 服务商

lazy-paper 支持任意 OpenAI 兼容端点。`.env.example` 的默认配置是：

- **文本 LLM**：DeepSeek-Reasoner（带 chain-of-thought；适合分析性写作）
- **视觉 LLM**：DashScope 上的 Qwen-VL-Max（图像理解能力强）

要切换服务商，在 `.env` 里修改这些变量：

```
LLM_TEXT_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-reasoner
LLM_TEXT_API_KEY=sk-...

LLM_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_VISION_MODEL=qwen-vl-max
LLM_VISION_API_KEY=sk-...
```

已测试过的替代方案：
- OpenAI：`LLM_TEXT_BASE_URL=https://api.openai.com/v1`，`LLM_TEXT_MODEL=gpt-4o`
- 自托管的 vLLM 或 Ollama：`LLM_TEXT_BASE_URL=http://localhost:8000/v1`

视觉 LLM 必须支持 OpenAI messages 格式的图像输入。文本 LLM 必须支持 JSON-mode 输出。

---

## 推荐的高质量模式：Strategy KL（v1.8.1+）

如果想要 benchmark 级别的章节生成质量、并能稳定 recover 文献引用，请启用 **Strategy KL**。该模式组合了：基于 instructor 的结构化 composer + verifier、v3 版 KG prompt（抽取 author / comparator / cited-by-paper 实体）、以及 best-of-N 样本合并。该组合已在 v1.8.2 的 10 篇论文 corpus 上验证；在 meng2024 benchmark 上平均覆盖率 15.0/17（下限 12，区间 12–17）。

在 `.env` 中加入以下几行：

```
LAZY_PAPER_STRUCTURED=1             # 启用 instructor 结构化 compose + verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md # 抽取 author + comparator + cited_by_paper 实体
LAZY_PAPER_BEST_OF_N=2              # 每个 section 跑 2 份样本，轮询合并
LAZY_PAPER_VERIFIER_THRESHOLD=0.85  # quote vs. chunk 的最小匹配分数
LAZY_PAPER_RETRY_THRESHOLD=0.5      # post-verify 覆盖率 ≤ X 时触发一次 retry
```

取舍：
- **成本**：best-of-N=2 大致让 s08 的 LLM 开销翻倍（s08 是最贵的 stage）。单篇论文总成本从约 \$0.60–1.20 上升到约 \$0.90–1.80。
- **延迟**：s08 大约慢 1.7–2 倍（多份草稿在能并行时会并行执行）。
- **质量**：verifier 会拒掉缺乏依据的 claim；retry-when-empty 触发器会用一次强化的 LLM 调用，把 v1.7 之前会丢掉的 comparator 引用救回来。

如果只想跑快速/低成本的基线，把上面这些变量保持不设置（即默认值）即可 —— Strategy J 仍是 v1.7 起被记录的默认行为，对大多数论文效果也很好。

---

## 对输出进行迭代

调整结果不需要重跑整个 pipeline。每个 stage 都可以独立重跑。

### 查看中间产物

| 产物 | 能告诉你什么 |
|---|---|
| `runs/<id>/s03_chapter/chapters/` | PDF 是怎么被切成章节的 —— 检查章节边界是否识别错误 |
| `runs/<id>/s06_context/context.yaml` | 论文的标题、研究体系、关键词与缩写，这些都会注入下游所有 prompt |
| `runs/<id>/s07_figure_analyze/fig_notes.yaml` | 视觉 LLM 对每张图的结构化观察 |
| `runs/<id>/s08_section_compose/chapters/` | LLM 生成的各章节正文 —— 也是 DOCX/PDF/HTML 的主要内容来源 |
| `runs/<id>/s08_section_compose/critic_flags.yaml` | 正则 critic 抛出的质量 flag（v1.4+） |

### 重跑单个 stage

用 `--only` 配合 `--force` 可以只重跑某一个 stage：

```bash
# 重新生成章节内容，不动 OCR 和图像分析
uv run python -m cli run \
  --pdf papers/mypaper.pdf \
  --template template.docx \
  --paper-id mypaper \
  --only s08_section_compose \
  --force

# 用已经生成好的章节，重新渲染所有输出格式
uv run python -m cli run \
  --pdf papers/mypaper.pdf \
  --template template.docx \
  --paper-id mypaper \
  --only s09_render \
  --force \
  --formats docx,pdf,html,pptx
```

### 重跑一组 stage

```bash
--only s08_section_compose,s09_render
```

用逗号分隔 stage 名。当你修改了 template，想重新 compose + 渲染而不想再跑 OCR 时很有用。

### 单篇论文完全重置

```bash
rm -rf runs/mypaper/{s05_template,s08_section_compose,s09_render}
uv run python -m cli run ... --paper-id mypaper
```

---

## 故障排查

### OCR 漏识别了某张图

图像确实在 PDF 里，但输出里没有出现。

1. 检查 `runs/<id>/s04_figures/figures.yaml` —— 这张图的 ID 在里面吗？
2. 不在：切换 OCR 后端（`OCR_BACKEND=mineru` 在密集排版下更擅长识别图像）。删除 `s01_ocr/done.yaml` 并重跑：
   ```bash
   rm runs/<id>/s01_ocr/done.yaml
   OCR_BACKEND=mineru uv run python -m cli run ... --paper-id <id>
   ```
3. 在 `figures.yaml` 里有、但输出里没有：检查 `s07_figure_analyze/fig_notes.yaml` —— 视觉 LLM 分析了它吗？没有的话删掉 `s07_figure_analyze/done.yaml` 并重跑：
   ```bash
   rm runs/<id>/s07_figure_analyze/done.yaml
   uv run python -m cli run ... --paper-id <id> --only s07_figure_analyze,s08_section_compose,s09_render
   ```

### 某一章看起来像在胡编

输出的某节出现了原文里找不到的事实。

1. 检查 `runs/<id>/s08_section_compose/critic_flags.yaml` —— 在该节中找 `numeric_not_in_source` 这类 flag。
2. 阅读对应的 `<slug>.prompt.md`，看看喂给 LLM 的依据是什么。
3. 检查 `runs/<id>/s06_context/context.yaml` —— 如果论文的研究体系/关键词字段错了，会带偏整个生成。删掉 `s06_context/done.yaml` 重新跑 context 抽取。
4. 删掉该节的缓存输出，用 `--force` 重跑 s08：
   ```bash
   rm runs/<id>/s08_section_compose/chapters/<slug>.md
   uv run python -m cli run ... --paper-id <id> --only s08_section_compose --force
   ```

### PPT 排版出错（bullet 溢出或重叠）

通常是 bullet 文字过长导致的渲染瑕疵。

1. 检查 `runs/<id>/s09_render/preview.pptx` —— 用 LibreOffice 转成 PDF 后查看：
   ```bash
   /Applications/LibreOffice.app/Contents/MacOS/soffice \
     --headless --convert-to pdf --outdir /tmp/ \
     runs/<id>/s09_render/preview.pptx
   ```
2. 如果 bullet 过长，可能是 `s08_section_compose/chapters/` 里某节的句子太长。用 `--force` 重跑 s08（LLM 本身有随机性，新的一次调用往往会产出更短的 bullet）。
3. 参见 `docs/PPT_KNOWN_ISSUES.md` 了解已知排版限制和绕过办法。

### macOS 上 WeasyPrint 段错误

通常是 Homebrew 的原生库没找到。

1. 确认库已安装：`brew list | grep -E "pango|cairo|gdk"`。
2. 装了仍然崩，请改用 Docker 镜像：
   ```bash
   docker compose build
   docker compose run --rm lazy-paper run \
     --pdf papers/mypaper.pdf --template template.docx \
     --paper-id mypaper --formats docx,pdf,html,pptx
   ```
3. 一定要本机跑的话，请确保用的是 `uv run`（不是系统 Python）。macOS 系统自带的 Python 3.9 + WeasyPrint 组合会稳定触发段错误；uv 的隔离 Python 3.11 不会。

---

## 成本说明

### 单篇论文的粗略成本

对于一篇典型的 12 页材料科学论文、8 张图，采用 DeepSeek-Reasoner（文本） + Qwen-VL-Max（视觉） + DashScope embeddings：

| Stage | LLM 调用 | 大致费用 |
|---|---|---|
| s06_context（context + KG） | 2 次文本调用 | ~\$0.02 |
| s07_figure_analyze | 8 次视觉调用 | ~\$0.10–0.20 |
| s08_section_compose（15 节） | 15 次文本调用 + 1 次 embedding | ~\$0.30–0.60 |
| s09_render（PPTX summarizer） | 17 次文本调用（outline + 15 + paper） | ~\$0.20–0.40 |
| **合计** | | **~\$0.60–1.20 / 篇** |

成本会随论文长度、图数量和章节数显著浮动。Embeddings（用于混合检索）非常便宜（一篇论文全部 chunk 大约只要 ~\$0.001）。启用 Strategy KL（`LAZY_PAPER_BEST_OF_N=2`）后，s08 成本约翻倍，单篇总成本约为 \$0.90–1.80。

### 用 LLM_MAX_TOKENS_CEILING 控制开销

在 `.env` 里设置 `LLM_MAX_TOKENS_CEILING`，可以给每一次 LLM 调用都加上一个 token 上限：

```
LLM_MAX_TOKENS_CEILING=8000   # 保守
LLM_MAX_TOKENS_CEILING=40000  # 默认（对 DeepSeek-Reasoner 的 CoT 来说是宽松值）
```

把这个值压得太低，会导致分析性 stage（s08、s09）输出截断的 JSON。如果你看到空输出或格式损坏的输出，把上限调回 40000 附近。

### 复用缓存结果

因为每个 stage 都会写 `done.yaml`，所以同一篇论文第一次完整跑完后再跑几乎是零成本 —— 所有 stage 都会被跳过。只有在以下情况你才会再次产生 LLM 调用：

- 显式传了 `--force`。
- 你删掉了某个 stage 的 `done.yaml` 或输出目录。
- PPTX summarizer 的输入 hash 变了（比如你换了 template，章节标题随之变化，被喂给 outline LLM 的内容也就变了）。
