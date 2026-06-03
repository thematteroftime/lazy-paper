<h1 align="center">lazy-paper</h1>

<p align="center">
  <em>一条命令，把科研 PDF 变成结构化的多格式深度解读。</em>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <a href="CHANGELOG.md"><img alt="Release" src="https://img.shields.io/badge/release-v1.13--render-blue"></a>
  <a href="docs_zh/AGENT_GUIDE.md"><img alt="Agent-friendly" src="https://img.shields.io/badge/agent--friendly-yes-7c3aed"></a>
</p>

<p align="center"><strong><a href="README.md">English</a> · <a href="README.zh.md">简体中文</a></strong></p>

<p align="center">
  <img src="docs/assets/showcase-outline.png" alt="LLM 分组大纲" width="640">
</p>

---

## 它做什么

喂进一份科研 PDF + 一份章节大纲 `.docx`，吐出 **DOCX · PDF · HTML · PPTX** 四格式的双语深度解读——图、表、量化锚点全部保留。一条命令、9 阶段、每步可断点续跑。

```mermaid
flowchart LR
    PDF[PDF] --> S01[s01_ocr] --> S02[s02_clean] --> S03[s03_chapter] --> S04[s04_figures]
    TPL[outline.docx] --> S05[s05_template]
    S03 --> S06[s06_context<br/>+ KG]
    S04 --> S06
    S04 --> S07[s07_figure_analyze]
    S05 --> S08
    S06 --> S08
    S07 --> S08[s08_section_compose]
    S08 --> S09[s09_render]
    S09 --> OUT[preview.docx · pdf · html · pptx]
```

每个 stage 都写 `done.yaml` 独立可重跑，每次 LLM 调用都把 prompt + response 落盘。逐阶段详解在 [`docs_zh/ARCHITECTURE.md`](docs_zh/ARCHITECTURE.md)。

## 输出长什么样

<p align="center">
  <img src="docs/assets/v113-pdf-p01.png" alt="封面页" width="270">
  <img src="docs/assets/v113-pdf-p03.png" alt="图块 + 深度观察" width="270">
  <img src="docs/assets/v113-pdf-p05.png" alt="带行内公式的章节" width="270">
</p>

<p align="center"><em><code>preview.pdf</code> 三张真实截图——封面+章节、多面板图+深度观察块、含公式的章节。</em></p>

## 快速开始

```bash
# 安装
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
uv python install 3.11 && uv venv --python 3.11
uv pip install -e ".[dev]"
brew install pango gdk-pixbuf libffi cairo   # macOS · WeasyPrint 依赖

# 配置
cp .env.example .env   # 填 token，见下表

# 运行
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "templates/Table of Contents-CV-IMRaD.docx" \
  --paper-id mypaper --lang zh --formats docx,pdf,html,pptx
```

产物在 `runs/<paper-id>/s09_render/preview.{docx,pdf,html,pptx}`。

> **Windows 用户**：建议走 Docker（`docker compose run --rm lazy-paper run …`），WeasyPrint 依赖 GTK runtime。

## 申请 API key

每个角色注册一次，把 key 填进 `.env` 就行。

| 角色 | 服务商 | 注册链接 | `.env` 字段 |
|---|---|---|---|
| **OCR**（默认） | MinerU 云 | <https://mineru.net> · 账户 → API tokens | `MINERU_TOKEN` |
| **OCR**（备选） | 百度 AI Studio · PaddleOCR-VL | <https://aistudio.baidu.com/paddleocr> | `PADDLEOCR_TOKEN` |
| **文本 LLM** | DeepSeek-Reasoner | <https://platform.deepseek.com> · API keys | `LLM_TEXT_API_KEY` |
| **视觉 LLM** | 阿里云百炼 · Qwen-VL | <https://bailian.console.aliyun.com/> · API-KEY | `LLM_VISION_API_KEY` |

四项都是 OpenAI 兼容协议；换 OpenAI / vLLM / Ollama / Anthropic 网关只需改 `LLM_*_BASE_URL` + `LLM_*_MODEL`。

## 选对模板——整个流程最关键的一步

**模板的章节标题会原文塞进 compose prompt。** 拿"Dielectric Properties of Relaxor AFE"去跑 unCLIP 图像生成论文，LLM 要么写一段越界声明、要么把 unCLIP 内容硬塞进错误标题之下。同一篇论文、同一模型、同一 prompt：**一个错模板能把 RAGAS faithfulness 从 0.81 拉到 0.10。** 这不是可选项。

| 模板（`templates/<文件>`） | 适用领域 |
|---|---|
| `Table of Contents-CV-IMRaD.docx` | 通用 CV / ML / IMRaD（Intro → Method → Experiments → Results → Discussion） |
| `Table of Contents-Relaxor AFE-ZGY-HW.docx` | 材料科学（铁电、储能） |
| `Table of Contents-ATEC-B2w-Reward-ZGY.docx` | 腿足/轮足机器人 RL 奖励设计（ATEC2026 B2w 能耗正则化） |
| `Table of Contents-ATEC-B2w-MUJICA-v2-ZGY.docx` | 多技能统一 RL（能耗 + 技能选择器 + DC 电机约束） |

新领域复制最近邻的一份，改章节标题。**没有"通用够用"的模板**——错模板会安静地拖垮下游每个阶段。

## 输出格式一览

| 格式 | 要点 |
|---|---|
| `docx` | Word 文档，宋体 + Times New Roman。v1.13 design tokens：accent `#D97757` 章节编号 + 左侧竖条、次级灰图说、accent 边深度观察块 |
| `pdf` | WeasyPrint 渲染同套 HTML；`@media print` 屏蔽 topbar / TOC；公式 italic serif Unicode 兜底 |
| `html` | 单文件、图像 base64 内嵌。Sticky topbar + 右侧 TOC + 3 套强调色主题 + KaTeX 公式 + 点击复制 TeX。设 `LAZY_PAPER_INLINE_KATEX=1` 全离线（~1.08 MB） |
| `pptx` | 学术答辩风：奶白 / 炭黑、LLM 分组 4–5 节目录、图文并排、含定量结论 |

## 文档地图

| 文件 | 受众 |
|---|---|
| [`docs_zh/USER_GUIDE.md`](docs_zh/USER_GUIDE.md) · [`docs/`](docs/USER_GUIDE.md) | 终端用户 —— 配置、迭代、排障 |
| [`docs_zh/ARCHITECTURE.md`](docs_zh/ARCHITECTURE.md) · [`docs/`](docs/ARCHITECTURE.md) | 维护者 —— 9 阶段契约、检索器、verifier |
| [`docs_zh/AGENT_GUIDE.md`](docs_zh/AGENT_GUIDE.md) · [`docs/`](docs/AGENT_GUIDE.md) | AI 编程 agent —— 工作流与反模式 |
| [`templates/`](templates/) | 4 份现成 outline 模板 |
| [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) | 版本变更 · 贡献约定 |

## 许可证

MIT —— 见 [`LICENSE`](LICENSE)。基于 [MinerU](https://github.com/opendatalab/MinerU)、[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)、[DeepSeek](https://www.deepseek.com/)、[Qwen](https://github.com/QwenLM/Qwen)、[WeasyPrint](https://github.com/Kozea/WeasyPrint)、[python-pptx](https://github.com/scanny/python-pptx)、[python-docx](https://github.com/python-openxml/python-docx) 构建。

```bibtex
@software{lazy_paper,
  author  = {thematteroftime},
  title   = {lazy-paper: PDF research papers to multi-format deep analysis},
  url     = {https://github.com/thematteroftime/lazy-paper},
  version = {1.13-render},
  year    = {2026}
}
```
