# lazy-paper

> 一条命令，把科研 PDF 转成结构化的多格式深度分析：**DOCX · PDF · HTML · PPTX**。

<p>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <a href="CHANGELOG.md"><img alt="Release" src="https://img.shields.io/badge/release-v1.2.1-blue"></a>
  <a href="#tests"><img alt="Tests" src="https://img.shields.io/badge/tests-167%20passing-22c55e"></a>
  <a href="docs/AGENT_GUIDE.md"><img alt="Agent-friendly" src="https://img.shields.io/badge/agent--friendly-yes-7c3aed"></a>
</p>

<p>
  <img alt="DeepSeek" src="https://img.shields.io/badge/LLM-DeepSeek--Reasoner-1f6feb">
  <img alt="Qwen-VL" src="https://img.shields.io/badge/Vision-Qwen--VL-ff7a00">
  <img alt="MinerU" src="https://img.shields.io/badge/OCR-MinerU%20%7C%20PaddleOCR--VL-0ea5e9">
  <img alt="WeasyPrint" src="https://img.shields.io/badge/PDF-WeasyPrint-0b7285">
  <img alt="python-pptx" src="https://img.shields.io/badge/PPT-python--pptx-c2410c">
  <img alt="python-docx" src="https://img.shields.io/badge/DOCX-python--docx-2563eb">
  <img alt="Jinja2" src="https://img.shields.io/badge/HTML-Jinja2-b91c1c">
</p>

**[English](README.md) · [简体中文](README.zh.md)**

---

`lazy-paper` 是一条 9 阶段的 CLI 流水线。喂给它一篇科研 PDF + 一个章节大纲模板，得到一套中英双语深度分析文档。每个阶段独立、可审计、可断点续跑。

## 亮点

- **一个源，四种输出**：DOCX、PDF（WeasyPrint）、HTML（base64 内嵌图像，单文件可邮）、PPTX（学术答辩风，LLM 分组的 4–5 大节）
- **可插拔 OCR**：MinerU（默认，识图友好）或 PaddleOCR-VL
- **可插拔 LLM**：任意 OpenAI 兼容端点 — 默认视觉 Qwen-VL、文本 DeepSeek-Reasoner
- **可断点 + 可追溯**：每个阶段写 `done.yaml`，每个 LLM 调用持久化 prompt / response
- **软失败 + 精准重试**：单个 renderer 崩溃不会阻断其他格式；`--retry-failed` 只重跑失败的格式
- **一个 env 旋钮控制 LLM 花费**：`LLM_MAX_TOKENS_CEILING`
- **Docker 友好**：基于 Python 3.11 的精简镜像，Pango / Cairo / gdk-pixbuf 已预装

## 适用人群

- **科研人员**：做文献综述时，从 PDF 一次拿到讲稿 + 演讲稿
- **实验室管理者**：搭一条共享队列的论文摘要流水线
- **AI agent**：被指派维护或扩展此项目时 — 请先读 [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md)

如果你期望一个能"代你阅读"的工具，这不是它。`lazy-paper` 产出的是高质量初稿，你仍需复核。流水线对此诚实：所有 LLM 推断都留在 `*.response.json` 中可追溯，其余阶段是确定性算法。

## 技术栈

| 层 | 库 / 服务 | 用途 |
|---|---|---|
| 运行时 | **Python 3.11+** | 推荐 uv 管理虚拟环境 |
| PDF I/O | `pdfplumber`、`pypdfium2`、`Pillow` | 抽文本、栅格化、图像处理 |
| OCR | [MinerU](https://mineru.net/)（默认）或 [PaddleOCR-VL](https://ai.baidu.com/ai-doc/AISTUDIO) | 云端 OCR |
| LLM 客户端 | `openai>=1.50`（OpenAI 兼容协议） | 文本 + 视觉调用统一接口 |
| 默认文本 LLM | [DeepSeek-Reasoner](https://api-docs.deepseek.com/) | 思维链推理质量 |
| 默认视觉 LLM | [Qwen-VL-Max](https://help.aliyun.com/zh/dashscope/)（阿里云 DashScope） | 图像理解 |
| 模板 | `python-docx`、`jinja2` | 解析 `.docx` 大纲、渲染 HTML |
| 渲染器 | `python-docx`、`python-pptx`、`weasyprint`、`jinja2` | 每种输出格式一个 renderer |
| 配置 | `pyyaml`、`python-dotenv` | YAML 工件 + `.env` 凭证 |
| HTTP | `requests` | OCR API 调用 |
| 开发 | `pytest>=8` | 167 个测试 |

## 快速开始

### 本地安装（Python 3.11+，使用 uv）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"

# WeasyPrint 在 macOS 需要系统图形库：
brew install pango gdk-pixbuf libffi cairo
```

### Docker（推荐 Windows 用户或共享服务器）

```bash
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
docker compose build
```

### 配置

```bash
cp .env.example .env
# 编辑 .env：
#   OCR_BACKEND + MINERU_TOKEN 或 PADDLEOCR_TOKEN
#   LLM_VISION_API_KEY（DashScope 的 Qwen-VL）
#   LLM_TEXT_API_KEY（DeepSeek）
```

### 运行

```bash
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper \
  --formats docx,pdf,html,pptx \
  --lang zh
```

产物：`runs/<paper-id>/s09_render/preview.{docx,pdf,html,pptx}`。

## 输出格式

| 格式 | 说明 |
|---|---|
| `docx` | 自包含 Word 文档；西文 Times New Roman，中文宋体 |
| `pdf` | 与 DOCX 同内容，通过 WeasyPrint 渲染同一 HTML 模板 |
| `html` | 单文件，图像 base64 内嵌 — 可邮件、可浏览器直接打开 |
| `pptx` | 学术答辩风：奶白 + 炭黑配色、衬线标题、LLM 分组的 4–5 大节目录、图左/右文混排、含定量结论的收尾页 |

`--formats docx,pptx` 选子集（默认 `docx,pdf,html`）。

### PPTX 定制

```bash
uv run python -m cli run --pdf x.pdf --template t.docx \
  --presenter "张博士" --affiliation "某大学" \
  --pptx-subtitle "能量存储材料" \
  --pptx-template "my-slide-master.pptx"
```

## 流水线

```
PDF ──┬─ s01_ocr（MinerU | PaddleOCR-VL）
      │  ↓
      │  s02_clean → s03_chapter → s04_figures
template.docx → s05_template
                 ↓
              s06_context        （文本 LLM：标题、体系、关键词）
              s07_figure_analyze （视觉 LLM，逐图）
              s08_section_compose（文本 LLM，逐节）
              s09_render → preview.{docx,pdf,html,pptx}
```

详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## CLI 参考

```
lazy-paper run --pdf PATH --template PATH [options]

必填
  --pdf PATH                源 PDF
  --template PATH           章节大纲 .docx

可选
  --paper-id ID             每篇的运行目录 slug（默认从 PDF 文件名推断）
  --runs-dir PATH           产物根目录（默认 ./runs）
  --lang {zh,en}            输出语言（默认 zh）
  --skip-ocr                假定 s01_ocr 产物已存在
  --force                   即使 done.yaml 存在也强制重跑
  --only STAGE[,STAGE...]   只跑指定阶段（逗号分隔；必须是 STAGE_ORDER 中的名字）
  --formats LIST            逗号列表：docx,pdf,html,pptx（默认 docx,pdf,html）
  --pptx-bullets {llm,rule} PPT 要点生成策略（默认 llm）
  --pptx-template PATH      自定义 .pptx 母版（可选）
  --pptx-subtitle TEXT      覆盖 PPT 副标题
  --presenter TEXT          PPT 标题页演讲人
  --affiliation TEXT        PPT 标题页所属机构
  --retry-failed            配合 --only s09_render，只重跑 done.yaml 中标记为 partial 的格式
```

## 切换 LLM 提供方

任意 OpenAI 兼容的视觉 / 文本端点都可用。改 `LLM_*_BASE_URL`、`LLM_*_API_KEY`、`LLM_*_MODEL` 三组环境变量即可。已实测：Qwen-VL（DashScope）+ DeepSeek-Reasoner。理论上 OpenAI、Anthropic 兼容网关、自托管 vLLM / Ollama 都能跑。

OCR 选择：`OCR_BACKEND=mineru`（推荐识图密集的论文）或 `OCR_BACKEND=paddleocr`。

`LLM_MAX_TOKENS_CEILING`（默认 `40000`）通过共享 helper 给所有 LLM 调用点上限。各阶段默认值已经放得比较宽（8K–16K），让 DeepSeek-Reasoner 的思维链 token 不至于把最终 JSON 内容挤掉。要省钱或贴合更严格的配额，把这个值调低即可。

## 测试

```bash
uv run pytest -q          # 167 个测试
uv run pytest -m live     # 真 LLM 烟测（需要真实 key）
```

## 已知问题

当前无。[`docs/PPT_KNOWN_ISSUES.md`](docs/PPT_KNOWN_ISSUES.md) 中分诊的两个 PPT 视觉问题（数学下标字体回退、≥6 条要点卡片重叠）均在 v1.2.1 修复完成 — 详见 [`CHANGELOG.md`](CHANGELOG.md)。

## 引用

学术工作中使用本项目时：

```bibtex
@software{lazy_paper,
  author  = {thematteroftime},
  title   = {lazy-paper: PDF research papers to multi-format deep analysis},
  url     = {https://github.com/thematteroftime/lazy-paper},
  version = {1.1.0},
  year    = {2026}
}
```

## 致谢

- [MinerU](https://github.com/opendatalab/MinerU) — 识图友好的 PDF 版面分析
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — 备选 OCR
- [DeepSeek](https://www.deepseek.com/) — 文本推理 LLM
- [Qwen](https://github.com/QwenLM/Qwen) — 视觉 LLM
- [WeasyPrint](https://github.com/Kozea/WeasyPrint)、[python-pptx](https://github.com/scanny/python-pptx)、[python-docx](https://github.com/python-openxml/python-docx) — 渲染栈

## 文档地图

| 文件 | 受众 | 用途 |
|---|---|---|
| [`README.md`](README.md) | 英文用户 | 安装 + 运行 + 格式选择 |
| [`README.zh.md`](README.zh.md) | 中文用户（你在这里） | 安装 + 运行 + 格式选择 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 维护者 / 扩展者 | 9 阶段数据契约、如何加阶段或格式 |
| [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) | AI 编程 agent | 工作流模式、缓存陷阱、反模式 |
| [`docs/PPT_KNOWN_ISSUES.md`](docs/PPT_KNOWN_ISSUES.md) | v1.2 实施者 | 已分诊的 PPT 缺陷与修法 |
| [`docs/INTERNAL/HANDOFF.md`](docs/INTERNAL/HANDOFF.md) | 下一任维护者 | 已验证状态、改动入口表、已知局限 |
| [`CHANGELOG.md`](CHANGELOG.md) | 任何人 | 版本之间的差异 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 外部贡献者 | 分支 / 测试 / PR 约定 |

## 许可证

MIT — 见 [`LICENSE`](LICENSE)。
