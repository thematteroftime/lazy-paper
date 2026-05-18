# Spec — s09_render 多格式重构 + _common 整理

- **Date:** 2026-05-18
- **Author:** brainstorming session（zhangjiedong + Claude）
- **Status:** Approved by stakeholder, ready for implementation plan
- **Scope:** 1 个 stage 重构（`stages/s09_render/`）+ 1 个基础设施整理（`stages/_common.py` → `_common/` 包）
- **Out of scope:** s04 figures 重构、s05 template 重构、s01 ocr 重构、LLM 阶段调优、OCR/图表算法改进、表格渲染（待 s04 表格提取修好再加 TableBlock）

---

## 1. 目标

把 `s09_render` 从「单文件 docx 渲染器」升级为「多格式渲染器」，新增 **PDF / HTML / PPTX** 三种输出，保留现有 `preview.docx` + `mypaper_bundle/` 不破坏。同时按用户代码风格偏好把散乱模块（`_common.py`）按职责拆模块。

**驱动原则**（来自用户偏好）：
- 质量 > 速度；通用 > 特例；完善 > 轻量
- 代码简洁美观，相关函数归类成类，避免散乱过程式 API
- 部署走 uv + Docker，不污染本机
- 适配 agent 工具链，CLI 是默认入口形态

## 2. 用户与场景

- **主用户**：项目作者（科研论文深度分析自动化），开源项目准备公开
- **典型工作流**：跑完前 8 个 stage 后，`s09_render` 一次输出 4 种格式：
  - `preview.docx`：交付物，可继续 Word 内编辑
  - `preview.pdf`：打印、邮件、归档分发
  - `preview.html`：单文件自包含（图 base64 嵌入），浏览器/邮件分享
  - `preview.pptx`：组会汇报、论文讲解（图为主、20-40 页）
- **agent 用法**：CLI 子命令调用，所有功能开关都通过参数暴露

## 3. 架构

### 3.1 目录布局

```
stages/s09_render/
├── __init__.py
├── runner.py               # def run(...) 仅协调，~35 行
├── model.py                # 4 个 dataclass + Block union 别名
├── builder.py              # class DocumentBuilder
├── slide_planner.py        # class SlidePlanner（纯切分逻辑，无 LLM）
├── pptx_summarizer.py      # class PptxSummarizer（LLM 摘要 + 双轨缓存）
├── renderers/
│   ├── __init__.py         # RENDERERS = {"docx": ..., "html": ..., "pdf": ..., "pptx": ...}
│   ├── base.py             # class Renderer(ABC)
│   ├── docx.py             # class DocxRenderer
│   ├── html.py             # class HtmlRenderer
│   ├── pdf.py              # class PdfRenderer（内部调用 HtmlRenderer 拿 HTML 字符串 → weasyprint）
│   └── pptx.py             # class PptxRenderer
├── templates/
│   ├── preview.html.j2     # HTML / PDF 共用 jinja2 模板
│   └── styles.css          # 单一样式源
└── tests/
    ├── unit/
    │   ├── test_document_builder.py
    │   ├── test_slide_planner.py
    │   └── test_pptx_summarizer.py
    └── integration/
        ├── test_s09_render_smoke.py
        ├── test_s09_render_partial.py
        └── test_s09_render_cache.py
```

预估总行数约 680，分布在 10 个源文件，比当前 157 行单文件增长约 4×，但承载功能从「1 格式」扩到「4 格式 + PPT 切分 + 缓存」，量级合理。

### 3.2 数据流

```
compose_dir/chapters/*.md ─┐
                           ├─► DocumentBuilder.build() ─► Document
fig_notes_dir/fig_notes.yaml ┘                              │
                                                            ├─► DocxRenderer ─► preview.docx
                                                            ├─► HtmlRenderer ─► preview.html
                                                            │         │
                                                            │         └─► PdfRenderer 复用 ─► preview.pdf
                                                            │
                                                            └─► PptxSummarizer ─► summaries
                                                                        │
                                                                        ▼
                                                                  SlidePlanner.plan(doc, summaries)
                                                                        │
                                                                        ▼
                                                                  PptxRenderer ─► preview.pptx

并行：compose_dir/chapters + fig_notes 图 ─► _copy_bundle() ─► mypaper_bundle/
```

### 3.3 输出目录

```
runs/<paper_id>/s09_render/
├── preview.docx
├── preview.pdf            # 默认开
├── preview.html           # 默认开
├── preview.pptx           # 显式开 (--formats 包含 pptx 时)
├── mypaper_bundle/        # 现有行为，向后兼容
│   ├── chapters/
│   ├── figures/
│   └── README.md
├── llm_cache/             # PPT 摘要双轨缓存（仅 PPT 启用时）
│   ├── <chapter_slug>.input_hash.json
│   ├── <chapter_slug>.json
│   ├── <chapter_slug>.prompt.md
│   └── <chapter_slug>.response.json
└── done.yaml              # 含 formats 字段、partial 字段
```

## 4. 数据模型

```python
# stages/s09_render/model.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

@dataclass(frozen=True)
class Paragraph:
    text: str

@dataclass(frozen=True)
class FigureBlock:
    fig_id: str                       # "Fig. 5"
    label: str                        # "Fig. 5" or "图 5"（builder 阶段按 lang 选好）
    image_paths: tuple[Path, ...]     # 多面板时多张
    caption: str
    deep_observation: str             # 可空字符串

Block: TypeAlias = Paragraph | FigureBlock   # 未来加 TableBlock 在这里扩

@dataclass(frozen=True)
class Chapter:
    heading: str
    level: int                        # 1=H1, 2=H2 ...
    blocks: tuple[Block, ...]

@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                         # "zh" | "en"
    chapters: tuple[Chapter, ...]
```

**设计说明**：
- 全部 `frozen=True`，强制 builder 后不可变，避免 renderer 误改
- `Block` 用 union 别名，renderer 用 `isinstance` 静态分派
- `label` 在 builder 阶段就计算好（`"Fig. 5"` 或 `"图 5"`），renderer 不重复实现 label 逻辑
- 字段单语，因为 `fig_notes.yaml` 只持单语（由 s07 `--lang` 决定）
- 暂不引入 `TableBlock`（s04 表格提取目前几乎不工作，46 篇里 45 篇空数组）

## 5. 核心类设计

### 5.1 `DocumentBuilder`

```python
class DocumentBuilder:
    """从 markdown + fig_notes 构造 Document。纯转换，无 IO。"""

    def __init__(self, lang: str, paper_title: str):
        self.lang = lang
        self.paper_title = paper_title

    def build(self,
              chapters_md: dict[str, str],     # {file_name: markdown_text}
              fig_notes: list[dict]) -> Document:
        ...

    # 私有
    def _split_paragraphs(self, body: str) -> list[Paragraph]: ...
    def _find_referenced_figures(self, body: str,
                                  fig_notes: list[dict],
                                  embedded: set[str]) -> list[FigureBlock]: ...
    def _make_label(self, fig_id: str) -> str: ...   # "Fig. 5" → "图 5" if lang == "zh"
```

**关键行为**：等价于现 `_render_preview_docx:82-114` 的图引匹配（中英文 `Fig. 5` / `图5` / `图 5` 三模式），保证零行为改变。一个 figure 全局只插一次（保留 `embedded: set` 语义）。

### 5.2 `SlidePlanner`

```python
@dataclass(frozen=True)
class Slide:
    kind: str                         # "title" | "outline" | "divider" | "bullets" | "figure" | "closing"
    title: str
    bullets: tuple[str, ...] = ()
    image_paths: tuple[Path, ...] = ()
    caption: str = ""
    deep_observation: str = ""
    notes: str = ""                   # 演讲者备注：塞章节原文 / figure 原始 deep_obs 全文

@dataclass(frozen=True)
class SlideDeck:
    slides: tuple[Slide, ...]
    lang: str

class SlidePlanner:
    """Document + summaries → SlideDeck（汇报式、图为主、20-40 页）"""

    MAX_BULLETS_PER_SLIDE = 5
    MIN_PARAGRAPHS_FOR_DIVIDER = 2

    def __init__(self, lang: str):
        self.lang = lang

    def plan(self, doc: Document, summaries: dict | None) -> SlideDeck:
        ...

    # 私有
    def _plan_title(self, doc) -> Slide: ...
    def _plan_outline(self, doc) -> Slide: ...
    def _plan_chapter(self, ch: Chapter, summary: dict | None) -> list[Slide]: ...
    def _extract_bullets_fallback(self, paragraphs) -> list[list[str]]: ...   # 当 summaries 为 None 时的规则提取
    def _figure_to_slide(self, fb: FigureBlock, one_liner: str, notes: str) -> Slide: ...
    def _plan_closing(self, doc) -> Slide: ...
```

**Slide 结构**（每个 deck 包含）：
```
[1]   title    — 论文标题
[2]   outline  — 全部章节 heading
[3..] N × chapter cluster：
        ├── divider (可选，章节段落 ≥2 时插)
        ├── bullets × M (摘要 ≤5 条/页)
        └── figure × K (每图一页：图 70% + caption + 一句话 deep_obs，原文进 notes)
[末]  closing  — Conclusion bullets
```

### 5.3 `PptxSummarizer`

```python
class PptxSummarizer:
    """为 PPT 生成 bullets + 图 1 句话精炼。双轨缓存：input_hash 命中即复用。"""

    def __init__(self, llm: LLM, cache_dir: Path, lang: str):
        self.llm = llm
        self.cache_dir = cache_dir
        self.lang = lang

    def summarize(self, doc: Document) -> dict:
        """返回 {chapter_heading: {"bullets": [...], "figure_one_liners": {fig_id: str}}}"""
        ...

    # 私有
    def _input_hash(self, chapter: Chapter) -> str: ...
    def _try_cache(self, slug: str, input_hash: str) -> dict | None: ...
    def _write_cache(self, slug: str, input_hash: str, output: dict,
                     prompt: str, response: dict) -> None: ...
    def _call_llm(self, chapter: Chapter) -> tuple[dict, str, dict]: ...
```

**缓存协议**：
- 命中条件：`<slug>.input_hash.json` 内容 == 当前 chapter 的 sha256
- 命中：直接读 `<slug>.json` 作为结果
- 未命中：调 LLM，覆盖 `<slug>.{input_hash.json, json, prompt.md, response.json}` 四个文件
- 失败降级：同一 chapter 连续 3 次 LLM 调用失败（含每次单独重试），整体 `summarize()` 返回 `None`，`SlidePlanner` 走规则 fallback；done.yaml 标记 `pptx_summarizer="degraded"`

**LLM prompt 契约**（输出 JSON）：
```json
{
  "bullets": ["bullet1", "bullet2", "..."],
  "figure_one_liners": {"Fig. 1": "一句话精炼", "Fig. 2": "..."}
}
```

约束：bullets ≤5 条；每条 zh ≤30 字 / en ≤15 词；figure 一句话 zh ≤40 字 / en ≤20 词。

### 5.4 `Renderer` 类层级

```python
# renderers/base.py
class Renderer(ABC):
    extension: ClassVar[str]

    @abstractmethod
    def render(self, doc: Document, out_path: Path) -> None: ...

# renderers/docx.py  ~120 行（迁移现有逻辑）
class DocxRenderer(Renderer):
    extension = "docx"
    def render(self, doc, out_path): ...
    # 私有：_apply_cn_font / _write_paragraph / _write_figure_block

# renderers/html.py  ~80 行
class HtmlRenderer(Renderer):
    extension = "html"
    def render(self, doc, out_path): ...
    def render_to_string(self, doc) -> str:  # 公开给 PdfRenderer 复用
        ...
    # 私有：_image_to_base64 / _load_template

# renderers/pdf.py  ~30 行
class PdfRenderer(Renderer):
    extension = "pdf"
    def render(self, doc, out_path):
        html_str = HtmlRenderer().render_to_string(doc)
        weasyprint.HTML(string=html_str).write_pdf(out_path)

# renderers/pptx.py  ~150 行
class PptxRenderer(Renderer):
    extension = "pptx"
    def __init__(self, summaries: dict | None = None):
        self.summaries = summaries
    def render(self, doc, out_path):
        deck = SlidePlanner(doc.lang).plan(doc, self.summaries)
        self._build_pptx(deck, out_path)
    # 私有：_build_pptx / _layout_<kind> 系列（每个 slide.kind 一个 layout 方法）
```

## 6. CLI 与默认行为

**新增参数**（透传到 `s09_render.run`）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--formats` | `docx,pdf,html` | 逗号分隔；可任选 `docx/pdf/html/pptx` 组合 |
| `--pptx-bullets` | `llm` | `llm` 或 `rule`；仅 `--formats` 含 `pptx` 时生效 |
| `--pdf-engine` | `weasyprint` | 预留，目前只支持 weasyprint |
| `--html-self-contained` | `true` | 单文件 base64 嵌入图片 |
| `--retry-failed` | （flag） | 仅重跑 done.yaml 中 partial 标记的失败格式 |

**默认行为说明**（按用户「常用+质量保证」原则）：
- 默认 `docx,pdf,html`：三种「被阅读/分发」的稳态格式，无 LLM 调用、跑得快
- PPT **不在默认**：它是「汇报场景」按需开，且需 LLM 摘要（多花钱、多花时间、有失败概率）
- 一旦开 PPT，质量优先（`--pptx-bullets=llm`）

**示例**：
```bash
paper2md run --paper hu2025                                      # docx + pdf + html
paper2md run --paper hu2025 --formats docx,pdf,html,pptx         # 全开
paper2md run --paper hu2025 --formats pptx --pptx-bullets rule   # 只 PPT，规则模式（离线）
paper2md run --paper hu2025 --only s09_render --retry-failed     # 仅补跑上次失败的格式
```

## 7. 错误处理

**软/硬失败边界原则**：
- 用户可恢复的（装依赖、改配置） → 硬失败（fail fast）
- 非用户过错的（某 renderer 在边界 case 翻车） → 软失败（其他格式继续 + warning + done.yaml.partial=true）

**全场景表**：

| 场景 | 处理 | 用户感知 |
|---|---|---|
| 单 renderer 失败 | 异常入 `done.yaml.formats[fmt]`，其他格式继续 | stderr 红字 warning + `done.yaml.partial=true` |
| LLM 摘要调用失败 | 缓存命中用旧的；否则降级到规则提取，PPT 仍能出 | warning + `done.yaml.pptx_summarizer="degraded"` |
| 图片文件缺失 | 该 FigureBlock 跳过，不抛 | warning + `done.yaml.missing_figures=[...]` |
| jinja2 模板语法错 | 仅本格式 fail | stderr 定位到 template 文件名+行号 |
| `weasyprint` import 失败 | 启动时探测；pdf 不进 RENDERERS 注册表 | 立即提示 Docker 路径优先：`docker run paper2md ...` |
| `python-pptx` 缺失 | 启动时探测；pptx 不进注册表 | 提示 `uv pip install -U python-pptx` |
| `out_dir` 无写权限 | fail fast | stderr 红字 |

**告知机制**：所有 warning 走 stderr，主流程返回非 0 退出码仅在「所有格式都失败」时；部分失败返回 0 + `done.yaml.partial=true`，agent 可据此判断。

## 8. 依赖与部署

**新增 Python 依赖**（`pyproject.toml`）：
```toml
[project.dependencies]
jinja2 = ">=3.1"
weasyprint = ">=62"
python-pptx = ">=0.6.23"
```

**系统级依赖（仅 weasyprint 需要）**：Pango / Cairo / gdk-pixbuf / libffi。

**部署策略**（按用户偏好：uv + Docker 优先，不污染本机）：

1. **推荐路径 — Docker**（默认）：
   - `Dockerfile` 加一行 `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8`
   - 用户：`docker run paper2md run --paper hu2025`，零本机配置
   - `docker-compose.yml` 提供完整开发环境

2. **可选路径 — 本机直跑**：
   - README 注明系统依赖的 brew / apt 命令，仅作为「高级用户兜底」
   - Windows 本机 PDF 麻烦，README 明示：「PDF on Windows 需额外 GTK 步骤；HTML/DOCX/PPTX 开箱即用；推荐 Windows 用户走 Docker」

3. **uv 虚拟环境**（不论本机或 Docker 内部）：
   - 所有 Python 包通过 `uv add weasyprint python-pptx jinja2` 加入 `pyproject.toml`
   - `uv.lock` 锁定，保证可复现

## 9. `stages/_common` 重构

**现状**：单文件 `_common.py` 138 行 10 散函数，混 4 类职责。

**重构后**（按职责拆模块，不强行成类——这些是无状态 utility，按用户偏好「模块级函数 ≤3 个 + 无共享状态」不需成类）：

```
stages/_common/
├── __init__.py        # re-export 全部，保持 `from stages._common import slugify` 兼容
├── paths.py           # slugify, stage_dir                       (2 funcs)
├── yaml_io.py         # load_yaml, dump_yaml, safe_parse_yaml + 私有 _quote_*  (3 public)
├── done.py            # mark_done, is_done                       (2 funcs)
└── bbox.py            # bbox_from_filename                       (1 func)
```

**向后兼容**：`__init__.py` 用显式 re-export，所有现有 `from stages._common import xxx` 不动；所有 stage 不需改 import。

**新增测试**：`tests/unit/test_common/` 4 个文件做单元测试——顺手把「基础设施零单测」的债还了。

## 10. 测试策略

```
tests/
├── unit/
│   ├── test_document_builder.py        # 固定 fixtures (mock markdown + mock fig_notes) → assert Document 结构
│   ├── test_slide_planner.py           # mock Document → 检 SlideDeck 结构、slide kind 序列、页数 ∈ [15, 50]
│   ├── test_pptx_summarizer.py         # mock LLM client，验缓存命中 / 未命中 / input_hash 变化触发重跑
│   └── test_common/
│       ├── test_paths.py
│       ├── test_yaml_io.py
│       ├── test_done.py
│       └── test_bbox.py
├── integration/
│   ├── test_s09_render_smoke.py        # 跑 fixture 论文，断言 4 格式都生成、各文件 > 0 字节
│   ├── test_s09_render_partial.py      # 故意让 pptx 失败，断言 docx/pdf/html 仍出 + done.yaml.partial=true
│   └── test_s09_render_cache.py        # 跑两次，第二次 LLM 调用数应为 0
└── live/
    └── test_s09_render_live.py         # 真 LLM，@pytest.mark.live，CI 默认跳过
```

**每个 renderer smoke 断言**：
- `docx`: python-docx 读回 → 找到 `paper_title` + ≥1 张图 + 章节数 == `Document.chapters` 数
- `html`: 文本含 `paper_title` + `<img src="data:image` 标记（base64 嵌入）
- `pdf`: 文件前 5 字节 == `%PDF-`，文件 ≥ 10KB
- `pptx`: python-pptx 读回，slide 数 ∈ [15, 50]，首页 kind == "title"

**Fixture 论文**：用 `hu2025` 的 `runs/hu2025/s08_section_compose/chapters/` + `runs/hu2025/s07_figure_analyze/fig_notes.yaml`，复制到 `tests/fixtures/hu2025/` 作为冻结快照（避免随 pipeline 更新漂移）。该论文 11 章 + 多图，复杂度代表性强。

## 11. 向后兼容

| 项目 | 现有行为 | 新行为 |
|---|---|---|
| `runs/<paper_id>/s09_render/preview.docx` | 总是生成 | 默认仍生成（除非 `--formats` 显式排除 docx）|
| `runs/<paper_id>/s09_render/mypaper_bundle/` | 总是生成 | 不变，总是生成 |
| `runs/<paper_id>/s09_render/done.yaml` | 含 bundle_chapters/bundle_figures/preview_bytes | 增加 `formats`、`partial`、`pptx_summarizer` 字段；旧字段保留 |
| `from stages._common import xxx` | 单文件 | 改为包，但 re-export 保持全兼容 |
| CLI `paper2md run --paper xxx` 无 `--formats` | 出 docx + bundle | 出 docx + pdf + html + bundle（新增 pdf/html 是增强，不破坏）|

**风险点**：现有 46 篇论文已生成的 `runs/<paper_id>/s09_render/done.yaml` 缺新字段。`is_done()` 检查不会因此误判（只看 `done.yaml` 存在性，不校验字段）；如果用户重跑 `--only s09_render`，会覆盖产出新的 done.yaml。

## 12. 实施分阶段建议

供后续 writing-plans 阶段细化。粗略划分为 5 个独立可交付里程碑：

1. **M1**：`stages/_common.py` → `_common/` 包重构 + 单元测试。零行为变更，全 stage 集成测试应仍通过。
2. **M2**：`model.py` + `DocumentBuilder` + 把现 `_render_preview_docx` 迁移到 `DocxRenderer`。行为对齐现有 docx 输出（diff 字节级对比），CLI 仍跑通。
3. **M3**：`HtmlRenderer` + `PdfRenderer` + `templates/`。CLI `--formats docx,pdf,html` 跑通，3 格式同源。
4. **M4**：`SlidePlanner` + `PptxSummarizer` + `PptxRenderer` + LLM 缓存。CLI `--formats pptx` 跑通。
5. **M5**：错误处理（软失败 + `--retry-failed`）+ Dockerfile 系统依赖 + README 更新。

每个里程碑独立可测、独立可合，符合 superpowers「small reversible PRs」原则。

## 13. 不在本 spec 范围

明示排除，避免范围漂移：

- **s04 figures 重构**（FigureMerger 类、HANDOFF §6 figure-caption 边界 case）→ 下一个 spec，专项
- **s05 template 重构**（TemplateParser 类）→ 下一个 spec
- **s01 ocr 重构**（upscale 逻辑拆解）→ 下一个 spec
- **LLM 阶段调优**（s06/s07/s08 prompt 优化、摘要漂移问题）→ 独立 spec
- **表格渲染**（`TableBlock`）→ 等 s04 表格提取修好后再加
- **OCR/图表算法改进**（如 LaTeX 公式预处理）→ 独立 spec
- **新输出格式**（EPUB / 多页 HTML 站点）→ 未来按需扩展，本次仅 docx/pdf/html/pptx

## 14. 开放问题

无。本 spec 已对齐所有决策点。
