<h1 align="center">lazy-paper</h1>

<p align="center">
  <em>一条命令，把科研 PDF 转成结构化的多格式深度分析。</em>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <a href="CHANGELOG.md"><img alt="Release" src="https://img.shields.io/badge/release-v1.3.3-blue"></a>
  <a href="#测试"><img alt="Tests" src="https://img.shields.io/badge/tests-189%20passing-22c55e"></a>
  <a href="docs/AGENT_GUIDE.md"><img alt="Agent-friendly" src="https://img.shields.io/badge/agent--friendly-yes-7c3aed"></a>
</p>

<p align="center"><strong><a href="README.md">English</a> · <a href="README.zh.md">简体中文</a></strong></p>

<p align="center">
  <img src="docs/assets/showcase-outline.png" alt="LLM 分组目录" width="640">
  <br>
  <em>一份 PDF · 9 阶段（确定性+LLM 混合）· 四种精修产物。</em>
</p>

---

## 它做什么

喂入一篇科研 PDF + 一份 `.docx` 章节大纲模板，得到 **DOCX · PDF · HTML · PPTX** —— 中英双语深度分析，图表、量化锚点完整保留。

```
PDF  +  outline.docx                    ┌─▶ preview.docx
        │                               │
        ▼                               │
  OCR ▶ 清洗 ▶ 切章 ▶ 抠图 ▶ ───────────┼─▶ preview.pdf
  模板 ▶ 上下文 ▶ 图分析 LLM ▶ ─────────┼─▶ preview.html
  章节 LLM ▶ 渲染 ────────────────────┼─▶ preview.pptx
                                        │   （学术答辩风格）
                                        ▼
                                  runs/<paper-id>/s09_render/
```

每个阶段写 `done.yaml`、可断点续跑；每次 LLM 调用持久化 prompt 与 response 供追溯。

## 快速开始

```bash
# 安装
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/thematteroftime/lazy-paper && cd lazy-paper
uv python install 3.11 && uv venv --python 3.11
uv pip install -e ".[dev]"
brew install pango gdk-pixbuf libffi cairo   # macOS 必装（WeasyPrint）

# 配置
cp .env.example .env   # 填 MINERU_TOKEN + LLM_*_API_KEY

# 运行
uv run python -m cli run \
  --pdf "papers/your-paper.pdf" \
  --template "Table of Contents-Relaxor AFE-ZGY-HW.docx" \
  --paper-id mypaper --lang zh --formats docx,pdf,html,pptx
```

产物：`runs/<paper-id>/s09_render/preview.{docx,pdf,html,pptx}`。

> **Windows 用户**：建议走 Docker（`docker compose build && docker compose run --rm lazy-paper run …`） —— WeasyPrint 依赖 GTK runtime，Docker 已预装。

## 输出格式

<table>
  <tr>
    <th width="80">格式</th>
    <th>你拿到什么</th>
  </tr>
  <tr>
    <td><code>docx</code></td>
    <td>自包含 Word 文档；西文 Times New Roman、中文宋体</td>
  </tr>
  <tr>
    <td><code>pdf</code></td>
    <td>与 DOCX 同内容，通过 WeasyPrint 渲染共享 HTML 模板</td>
  </tr>
  <tr>
    <td><code>html</code></td>
    <td>单文件、图像 base64 内嵌——可邮件、可浏览器直接打开</td>
  </tr>
  <tr>
    <td><code>pptx</code></td>
    <td>学术答辩风：奶白+炭黑配色、LLM 分组的 4–5 大节目录、图左/右文混排、含定量结论的收尾页</td>
  </tr>
</table>

<p align="center">
  <img src="docs/assets/showcase-divider.png" alt="节分隔片 + KEY POINTS 卡" width="640">
  <br>
  <em>节分隔片。字号随要点密度自适应，autofit 兜底确保长 bullet 不溢出。</em>
</p>

## 技术栈

<p>
  <img alt="DeepSeek" src="https://img.shields.io/badge/LLM-DeepSeek--Reasoner-1f6feb">
  <img alt="Qwen-VL" src="https://img.shields.io/badge/Vision-Qwen--VL-ff7a00">
  <img alt="MinerU" src="https://img.shields.io/badge/OCR-MinerU%20%7C%20PaddleOCR--VL-0ea5e9">
  <img alt="WeasyPrint" src="https://img.shields.io/badge/PDF-WeasyPrint-0b7285">
  <img alt="python-pptx" src="https://img.shields.io/badge/PPT-python--pptx-c2410c">
  <img alt="python-docx" src="https://img.shields.io/badge/DOCX-python--docx-2563eb">
  <img alt="Jinja2" src="https://img.shields.io/badge/HTML-Jinja2-b91c1c">
</p>

| 层 | 库 / 服务 | 用途 |
|---|---|---|
| 运行时 | **Python 3.11+** | 推荐 uv 管理虚拟环境 |
| PDF I/O | `pdfplumber`、`pypdfium2`、`Pillow` | 抽文本、栅格化、图像处理 |
| OCR | [MinerU](https://mineru.net/) · [PaddleOCR-VL](https://ai.baidu.com/ai-doc/AISTUDIO) | 云端 OCR（识图友好） |
| LLM 客户端 | `openai>=1.50` | OpenAI 兼容协议 —— 一份配置，任意提供方 |
| 默认文本 LLM | [DeepSeek-Reasoner](https://api-docs.deepseek.com/) | 思维链推理质量 |
| 默认视觉 LLM | [Qwen-VL-Max](https://help.aliyun.com/zh/dashscope/) | 图像理解 |
| 模板 | `python-docx`、`jinja2` | 解析 `.docx` 大纲、渲染 HTML |
| 渲染器 | `python-docx`、`python-pptx`、`weasyprint`、`jinja2` | 每种格式一个无状态渲染器 |
| 配置 | `pyyaml`、`python-dotenv` | YAML 工件 + `.env` 凭证 |
| HTTP | `requests` | OCR API 调用 |
| 开发 | `pytest>=8` | 189 个测试 |

## 质量守护（v1.3）

- **量化内容校验**：PPT 每条章节 bullet 必含 ≥1 个数字锚点；收尾页 ≥3 条量化 bullet + 含比较的 takeaway。LLM 后正则强制，违规触发重试。
- **批判 vs 描述**：figure 观察若全为描述性动词（"shows / depicts"）且无批判标记（"limitation / missing / should"）则拒绝。
- **布局鲁棒**：目录行高按 takeaway 换行数动态计算；KEY POINTS 字号与截断阈值随密度变化（16pt ↔ 13pt）；figure 观察块超界时缩字号而非溢出。
- **一个 env 旋钮控 LLM 花费**：`LLM_MAX_TOKENS_CEILING`（默认 40000）给所有调用点上限。

## CLI 参考

```
lazy-paper run --pdf PATH --template PATH [options]

可选
  --paper-id ID             运行目录 slug（默认从 PDF 推断）
  --runs-dir PATH           产物根目录（默认 ./runs）
  --lang {zh,en}            输出语言（默认 zh）
  --skip-ocr                假定 s01_ocr 产物已存在
  --force                   即使 done.yaml 存在也强制重跑
  --only STAGE[,STAGE...]   只跑指定阶段（逗号分隔）
  --formats LIST            docx,pdf,html,pptx（默认 docx,pdf,html）
  --pptx-bullets {llm,rule} PPT 要点策略（默认 llm）
  --pptx-template PATH      自定义 .pptx 母版
  --pptx-subtitle TEXT      覆盖 PPT 副标题
  --presenter TEXT          PPT 标题页演讲人
  --affiliation TEXT        PPT 标题页所属机构
  --retry-failed            配合 --only s09_render，只重跑 done.yaml 中 partial 的格式
```

## 切换 LLM / OCR 提供方

任意 OpenAI 兼容的视觉 / 文本端点都可用。改 `.env` 中 `LLM_*_BASE_URL`、`LLM_*_API_KEY`、`LLM_*_MODEL`。已实测：Qwen-VL（DashScope）+ DeepSeek-Reasoner。OpenAI、Anthropic 兼容网关、vLLM / Ollama 都能跑。

OCR：`OCR_BACKEND=mineru`（推荐识图密集）或 `OCR_BACKEND=paddleocr`。

## 测试

```bash
uv run pytest -q          # 189 个测试
uv run pytest -m live     # 真 LLM 烟测（需要真实 key）
```

## 引用

```bibtex
@software{lazy_paper,
  author  = {thematteroftime},
  title   = {lazy-paper: PDF research papers to multi-format deep analysis},
  url     = {https://github.com/thematteroftime/lazy-paper},
  version = {1.3.0},
  year    = {2026}
}
```

## 致谢

[MinerU](https://github.com/opendatalab/MinerU) · [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) · [DeepSeek](https://www.deepseek.com/) · [Qwen](https://github.com/QwenLM/Qwen) · [WeasyPrint](https://github.com/Kozea/WeasyPrint) · [python-pptx](https://github.com/scanny/python-pptx) · [python-docx](https://github.com/python-openxml/python-docx)

## 文档地图

| 文件 | 受众 |
|---|---|
| [`README.md`](README.md) · [`README.zh.md`](README.zh.md) | 一手用户（英 / 中） |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 维护者 —— 9 阶段契约 |
| [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) | AI 编程 agent —— 工作流与反模式 |
| [`docs/INTERNAL/HANDOFF.md`](docs/INTERNAL/HANDOFF.md) | 下一任维护者 —— 验证态 + 改动入口 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本差异 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 外部贡献者约定 |

## 许可证

MIT —— 见 [`LICENSE`](LICENSE)。
