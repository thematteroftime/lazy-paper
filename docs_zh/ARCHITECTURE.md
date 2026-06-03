# lazy-paper 架构文档

> 面向新人（包括未来 Claude session 和外部贡献者）的系统级参考。读完后无需阅读源码，就能理解整个 pipeline 是怎么把一篇 PDF 论文变成多格式深度分析的。
>
> 本文档对应代码版本 **v1.13-render**（2026-06-03），321 个 pytest 测试，9 个 pipeline stage。
>
> 安装、CLI 命令、provider 配置请看 [README.zh.md](../README.zh.md) / [USER_GUIDE.md](USER_GUIDE.md)；本文档专注于 **"系统是怎么工作的"**。
>
> 英文同结构文档：[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)。

---

## 目录

1. [一句话定位](#1-一句话定位)
2. [设计哲学](#2-设计哲学)
3. [目录结构](#3-目录结构)
4. [Pipeline 全图 (s01 → s09)](#4-pipeline-全图-s01--s09)
5. [s08_section_compose 内部结构](#5-s08_section_compose-内部结构)
6. [图像处理链路 (s04 + s07 + s09)](#6-图像处理链路-s04--s07--s09)
7. [模板系统 (s05 + 占位符替换)](#7-模板系统-s05--占位符替换)
8. [LLM 客户端 (llm/client.py)](#8-llm-客户端-llmclientpy)
9. [测试体系](#9-测试体系)
10. [配置 & 环境变量](#10-配置--环境变量)
11. [v1.11 设计决策记录](#11-v111-设计决策记录)
12. [已知限制 / v1.12 候选](#12-已知限制--v112-候选)

---

## 1. 一句话定位

**lazy-paper 把一篇科研 PDF + 一份 `.docx` 章节大纲模板，变成四种格式 (DOCX/PDF/HTML/PPTX) 的双语 (中/英) 深度分析文档**，全程一条 `lazy-paper run` 命令搞定。

"深度分析"指的是：每个章节不是简单复述论文，而是带量化锚点（具体数值）、引用标记（`[span:doc:start-end]`）、图表引用（binding 到真实 fig_id）的批判性章节，由 instructor 校验的 Pydantic schema 强约束 LLM 输出。

---

## 2. 设计哲学

### 2.1 为什么是 9-stage pipeline 而不是一个超长 LLM 调用？

"PDF → 多格式深度分析"如果做成单 LLM 调用会出现：
- **不可缓存**：用户改一行 prompt 要重跑整篇 OCR (几分钟 + 几块钱)。
- **不可审计**：错误发生在哪一步？没办法回看中间产物。
- **不可并行**：每 stage 都被绑在主调用上，无法局部失败重试。
- **超出 context window**：30 页论文 + 20 张图 + 大纲指令 → 单次 prompt 100K+ token。

lazy-paper 把流程拆成 9 个独立 stage：每个 stage **读上一 stage 的输出文件夹、写自己的输出文件夹、落一个 `done.yaml` marker**。

- 任何 stage 失败，下次跑同一 `--paper-id` 会从上一个 `done.yaml` 续跑。
- 任何 prompt 修改，只要 `--force --only s08_section_compose` 就能局部重跑。
- 每次 LLM call 都把 `<name>.prompt.md` 和 `<name>.response.json` 落到磁盘，全量可审计。

### 2.2 强约束 Pydantic schema (Strategy J/KL)

s06 (KG extract) 和 s08 (section compose) 都用 `instructor` 库把 LLM 输出强约束成 Pydantic 模型：

```python
class GroundedClaim(BaseModel):
    text: str = Field(min_length=2)
    cited_chunk_ids: list[int] = Field(default_factory=list)
    cited_quote: str = ""
    figure_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("cited_chunk_ids")
    def _check_chunk_ids(cls, ids, info):
        allowed = info.context.get("allowed_chunk_ids")
        if allowed and any(i not in allowed for i in ids):
            raise ValueError(...)   # instructor 会自动 retry
        return ids
```

LLM 必须返回符合 schema 的 JSON，否则 instructor 自动重试（`max_retries=3`）。validator 还能拒掉"引用了 retrieval 集合外的 chunk"这种幻觉。这种**"预注入候选 + schema 校验"**模式（Perplexity-style pre-injection）是 s08 grounding 的核心。

### 2.3 Strategy KL 是什么

Strategy KL 是 v1.8.1 后默认推荐的 s08 compose path，由三个 env var 解锁：

```bash
LAZY_PAPER_STRUCTURED=1               # 启用 instructor compose + verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md   # 让 KG 抽取 author 实体并 link 到 comparator
LAZY_PAPER_BEST_OF_N=2                # 每章节跑 2 次 LLM，round-robin 合并
```

它们一起把每章节的 literature citation recovery 从 baseline 10/17 提到 15/17 (meng2024 平均)。

"KL"中的 K = best-of-N merge，L = structured + verifier。代码里出现的 `_STRUCTURED_SYSTEM` / `_single_compose` / `_merge_drafts` 都是 KL 的实现。

### 2.4 简洁性优先

参考 `CLAUDE.md`：每行改动都要追溯到具体需求，不写推测性抽象，不为单次调用建抽象层。
v1.11 first-principles refactor (commit `a4d90ab`) 主动**删掉了** 3 个 over-engineered 模块 (cross-citation reject 40 LOC + figure-retry 85 LOC + ad-hoc headline metric prompt rule)，详见 §11。

---

## 3. 目录结构

```
paper2md/
├── cli.py                       # 唯一入口：parse args → 串 9 个 stage
├── conftest.py                  # 仅 pytest 时给 macOS 注入 DYLD_FALLBACK_LIBRARY_PATH
├── pyproject.toml               # uv 管理；3.11+；setuptools build
├── .env.example                 # 所有 env var 文档化
├── llm/
│   ├── client.py                # OpenAI-compatible client (role 抽象 + max_tokens ceiling)
│   ├── models.yaml              # role 配置：vision / text / embeddings
│   ├── retriever.py             # 混合检索：BM25 + dense + RRF + entity boost
│   ├── paper_kg.py              # PaperKG (Entity / Relation, parquet 序列化)
│   ├── prompts/                 # 8 个 system+user prompt md 文件
│   └── citation/                # [span:doc:start-end] marker 渲染 (Onyx 移植)
├── stages/
│   ├── _common/                 # slugify / stage_dir / yaml_io / mark_done / normalize_ocr_latex
│   ├── s01_ocr/                 # PDF → OCR → doc_*.md + imgs/
│   ├── s02_clean/               # 去 running header / 修字符 / flag 错乱多栏
│   ├── s03_chapter/             # 按 IMRaD anchor 切章节 (双语)
│   ├── s04_figures/             # 配图+caption；合并多 panel；建 mentions map
│   ├── s05_template/            # 解析用户的大纲 .docx 成树状 yaml
│   ├── s06_context/             # LLM 抽 paper context + KG extract (instructor)
│   ├── s07_figure_analyze/      # 每张图调一次 vision LLM
│   ├── s08_section_compose/     # 上帝文件——按模板逐节生成 grounded 文本
│   └── s09_render/              # 4 个 renderer (docx / pdf / html / pptx)
├── tests/                       # 顶层 pytest (CLI / retriever / KG / citation / harness)
├── docs/                        # 用户/维护者文档
├── scripts/                     # audit_pptx / evaluate / fetch_katex / pdffigures2_sidecar
├── templates/                   # outline-template `.docx` 示例
└── runs/                        # 每次 run 的中间产物 + 最终输出 (gitignored)
```

`tests/` 在两个位置：每个 stage 自带 `tests/` 子目录 (locality)，顶层 `tests/` 跑 CLI、共享 lib、跨 stage 集成。详见 §9。

---

## 4. Pipeline 全图 (s01 → s09)

```
                                                 ┌──▶ preview.docx
PDF  +  outline.docx                             ├──▶ preview.pdf
       │                                         ├──▶ preview.html
       ▼                                         └──▶ preview.pptx
  s01_ocr  ▶  s02_clean  ▶  s03_chapter ─┐
                                         │
  s04_figures ─────────┐                 ├─▶ s09_render
                       ├─▶ s06_context ──┤        ▲
  s05_template ────────┤    (+ KG)       │        │
                       │                 │        │
  s07_figure_analyze ──┴─▶ s08_section_compose ───┘
                              (Strategy KL: retriever + verifier + retry)
```

每个 stage 的运行入口都是 `runner.py::run(...)` 关键字参数，由 `cli.py::_run_one()` 调度。`STAGE_ORDER` 写死在 `cli.py:46-50`。

### 4.1 s01_ocr — PDF → markdown + 图片

| 项 | 内容 |
|---|---|
| **输入** | `.pdf` 文件 + token (MinerU 或 PaddleOCR) |
| **输出** | `doc_<N>.md` (每页一份) + `imgs/<bbox-encoded>.jpg` |
| **关键文件** | `stages/s01_ocr/runner.py`, `stages/s01_ocr/mineru.py` |
| **入口** | `runner.py::run()` 按 `OCR_BACKEND` env 分派到 `_mineru.run` 或 `_run_paddleocr` |

两个 backend：
- **MinerU** (默认，`OCR_BACKEND=mineru`)：图质量更好，对图表密集论文更适合。
- **PaddleOCR-VL** (`OCR_BACKEND=paddleocr`)：备选。runner 会 poll 云端任务直到 `state=done`。

**关键算法 — upscale_images** (`runner.py:29-202`)：PaddleOCR 返回的图是 ~130 DPI 截出，太糊。runner 用 `pypdfium2` 把对应 PDF 页面渲染到 300 DPI，按图片文件名里编码的 bbox (`..._X1_Y1_X2_Y2.jpg`) 重新 crop。`bbox_from_filename` 在 `stages/_common/bbox.py` 里实现。

### 4.2 s02_clean — OCR 后处理

| 项 | 内容 |
|---|---|
| **输入** | `s01_ocr/doc_*.md` + `imgs/` |
| **输出** | 同结构，文本字段被净化 |
| **关键文件** | `stages/s02_clean/runner.py` |

三件事：
1. **`strip_running_headers`** (`runner.py:11`)：跨页重复 ≥3 次的短行被丢掉 (页眉/页脚)。
2. **`repair_chars`** (`runner.py:31`)：`(cid:0)` → `−`；裸数字 `O 2` → `O₂` (氧化物下标修复)。
3. **`flag_corrupted_column_flow`** (`runner.py:46`)：单字符 token 占比 >60% 的行加 `<!-- corrupted-column-flow -->` 注释，下游可以选择跳过 (不破坏文本，只 flag)。

### 4.3 s03_chapter — 按 IMRaD anchor 切章节

| 项 | 内容 |
|---|---|
| **输入** | `s02_clean/doc_*.md` |
| **输出** | `chapters/chapter_<NNN>_<slug>.md` + `chapter_index.yaml` |
| **关键文件** | `stages/s03_chapter/runner.py` |

**双语支持的位置 — `SECTION_ANCHORS` 集合** (`runner.py:14-27`)：
```python
SECTION_ANCHORS = {
    # English IMRaD
    "abstract", "introduction", "methods", "results", "discussion",
    "conclusion", "references", ...
    # Chinese equivalents
    "摘要", "引言", "实验", "结果", "讨论", "结论", "参考文献", ...
}
```

**加新语言**: 把对应的 section title 字面量加到这个 set。这是双语扩展的第一站 — 没有它，中文论文会被切成单章节，下游全部失效。

`detect_science_anchor` (`runner.py:37`) 用 `_ANCHOR_LINE_RE` 匹配 `[#编号] [章节号.] <Title>` 形式，title 必须以 `[A-Z一-鿿]` 开头。匹配上后 `flush()` 把当前累积行写成一章。

**章节号支持（v1.13）**：编号匹配组同时识别阿拉伯数字（`1.`、`2.3.`）**和**罗马数字（`I.`、`II.`、`III.`…）。IEEE / 会议论文用罗马数字编号的章节以前会被压成一坨 `Preface`，现在能正常切分。v1.13 同时扩充了 `SECTION_ANCHORS`：加入 `related work / background / problem statement / approach / system overview / evaluation / ablation / limitations / future work` 与中文等价（相关工作 / 背景 / 问题描述 / 方法概述 / 系统设计 / 评估 / 消融），机器人 / RL 论文也能正确识别。

### 4.4 s04_figures — 配图、合并 panel、建 mention map

| 项 | 内容 |
|---|---|
| **输入** | `s02_clean/doc_*.md` + `s03_chapter/chapters/` + 原始 PDF |
| **输出** | `figures.yaml`, `tables.yaml`, `mentions.yaml` |
| **关键文件** | `stages/s04_figures/runner.py` |

**双语 regex (顶层常量)** (`runner.py:18-26`)：
```python
FIG_CAP_RE = re.compile(
    r"(?:^|<div[^>]*>)\s*((?:Fig(?:ure)?\.?|图)\s*\d+[A-Za-z]?)\.?\s*(.*?)(?:</div>|$)",
    re.MULTILINE | re.IGNORECASE,
)
TAB_CAP_RE = re.compile(r"(?:^|<div[^>]*>)\s*((?:Table|表)\s*\d+)...")
FIG_MENTION_RE = re.compile(r"(?:Fig(?:ure)?\.?|图)\s*(\d+)([a-z])?", re.IGNORECASE)
```

加新语言：在 `Fig(?:ure)?\.?|图` 这种 alternation 里加 `|<新前缀>`。这是 v1.11 加进去的——之前中文论文 figure mention 全部漏检。

**`_normalize_fig_id`** (`runner.py:29`)：把 `Fig 3`, `Figure 3a`, `图 3` 都统一成 `Fig. 3` / `Fig. 3a`。下游 (s07, s09, s08 figure-binding) 全部依赖这个规范形式做 key。

**`_merge_figure_subpanels`** (`runner.py:135`)：同一 `fig_id` 下的多 panel crop (`Fig. 3` 有 a/b/c 子图) 被合并成一张 union bbox 大图，从原 PDF 重新渲染。per-page calibrate scale (`_calibrate_scale`) + 用 `min(sx, sy)` uniform scale 避免非等比拉伸 bleed 进相邻图。

`mentions.yaml` 是 `{chapter_filename: [Fig. 1, Fig. 3, ...]}` 倒排索引，给 s07 找 surrounding-text excerpt 用。

**`is_generation_prompt_caption` (v1.11.1, `runner.py:28-56`)**：caption-stub 过滤器，丢掉 `(letter) A/An <curated descriptor> <medium> of …` 这种模式（典型例：DALL-E 论文 OCR 出来的字面 generation prompt `(a) A high quality photo of a dog playing in a green field next to a lake.` — hif_2 Fig 43 之前被 s07 当成物理图分析）。这是两层防御中的第一层；s07 还会再 skip 一次（见 §4.7）。curated descriptor list 严格，保住真实材料 caption (`"(a) SEM image of NBST"`) 不被误伤。

**MinerU `chart`-vs-`image` 类型（v1.13，`stages/s01_ocr/mineru.py`）**：MinerU 的 `content_list.json` 把科研散点 / 折线 / 柱状图归为 `type: chart` + `chart_caption`，把实拍照片 / 矢量示意图归为 `type: image` + `image_caption`。v1.13 之前 `_content_list_to_docs` 只走 `image`，导致一篇散点图为主的文本 PDF（如 arXiv:2403.20001v2，MinerU 返回 16 张 raw 图但只有 2 张被标 `image`）丢掉 10/12 张图、剩两张还标错图号。修复：两种 type 都处理，`image_caption` 空时 fallback 到 `chart_caption`。同一修复链顺手让 `_ensure_figure_number` 跳过形如 `"(a) Straight Line Walking"` 的子面板 caption ——s04 的"就近 caption 配对"会让这四张子面板都挂到几行后的真实 `Fig. 3:` caption 上。

### 4.5 s05_template — 解析大纲 docx

| 项 | 内容 |
|---|---|
| **输入** | 用户提供的 `.docx` 大纲 (例：`Table of Contents-Relaxor AFE-ZGY-HW.docx`) |
| **输出** | `template.yaml` (节点树) + `done.yaml` (含 `template_sha256_16` 指纹) |
| **关键文件** | `stages/s05_template/runner.py` |

**核心函数 `parse_template`**（`runner.py:89`）：用 `python-docx` 遍历段落，依据 `style`（List Paragraph / 普通）和编号 regex（`_NUMBERED_RE`）决定一个段落是"新章节标题"还是"上一章节的 guidance 行"。`_is_guidance_line`（`runner.py:50`）过滤掉以 `(`、`-`、`→`、小写字母或动词（"Provide"、"Discuss"）起头的行 —— 这些明显是指令而不是标题。

**指纹缓存 (`is_cache_stale`, `runner.py:161`)**：`done.yaml` 落 `template_sha256_16`。CLI 在 `_run_one()` 里调用 `is_cache_stale` —— 用户改了 docx 文件，下次跑会自动 invalidate s05，避免 stale title 文本 silently 传到下游 (这是 v1.10 加的，因为之前编辑模板后必须 `--force` 才生效)。

### 4.6 s06_context — paper context + KG

| 项 | 内容 |
|---|---|
| **输入** | `s03_chapter/chapters/` |
| **输出** | `context.yaml`, `paper_kg.parquet`, `paper_kg.rel.parquet` |
| **关键文件** | `stages/s06_context/runner.py`, `stages/s06_context/kg_extract.py` |

两个独立 LLM call：

**Step 1 — paper context** (`runner.py:52`)：text LLM 从前言/摘要里抽 title, system, keywords, key_terms, abbreviations。落到 `context.yaml`，被 s08 / s09 全程消费。

**Step 2 — KG extract** (`kg_extract.py::build_paper_kg`)：`instructor` 强约束 LLM 返回 `PaperKG` (`llm/paper_kg.py`)。10/11 类 closed schema：
```
material, dopant, parameter, value, unit, figure, table,
claim, method, comparator, author  (author 是 v1.7 KG-v3 加的)
```

每个 Entity 带 `source_span = (doc_name, char_start, char_end)`，s08 的 `build_required_mentions` 用这个 span 找对应 retrieval chunk。

**为什么这一步可能失败 (soft-degrade)**：LLM 可能 schema parse 失败、parquet write 失败、source 空。失败时落 `kg_extract.failed` marker，s08 检测到这个 marker 就 fall back 到 v1.3.3 legacy compose path。**KG 失败永远不让整个 pipeline 倒**。

**Step 3 — headline_metrics 注入 (v1.11.1)**：runner 在 KG 构建成功后，从 `paper_kg` 抽 `mat_main --has_W_rec--> value` / `--has_eta-->` 关系，把 flagship sample 的核心数值打包成 `headline_metrics` block 写进 `context.yaml`，例如：

```yaml
headline_metrics:
  flagship: "0.8Bi(Mg0.5Ti0.5)O₃-0.2BaTiO₃"
  W_rec: 5.00
  eta: 90.09
```

`llm/prompts/section_compose.md` 的 "FLAGSHIP GROUND TRUTH" block 直接消费这些数值，强约束 composer 用准确的 flagship 数字而不是 scavenge comparator chunk 的邻近值（修复 v1.10 meng2024 ch07/09/13/15 跨章节 W_rec 漂移）。实现见 `stages/s06_context/runner.py:73-86` + `kg_extract.py:61`。

**Prompt 切换**：`LAZY_PAPER_KG_PROMPT=paper_kg_v3.md` 用 v3 prompt (11 类带 author)；默认 `paper_kg.md` (10 类无 author)。Strategy KL 必须用 v3，因为 compose prompt 依赖 `<Author> et al.` 引文形式。

### 4.7 s07_figure_analyze — 视觉 LLM 分析每张图

| 项 | 内容 |
|---|---|
| **输入** | `s04_figures/figures.yaml` + `s04_figures/mentions.yaml` + `s03_chapter/chapters/` + `s06_context/context.yaml` |
| **输出** | `fig_notes.yaml` (每图一条) + `<fig_id>.{prompt.md,response.json}` |
| **关键文件** | `stages/s07_figure_analyze/runner.py` |

每个 fig_id 调一次 vision LLM (Qwen-VL-Max 默认)：
1. 通过 `_excerpts` (`runner.py:18`) 拿到引用该图的 ±1 段周边文字 (双语 mention 搜索)。
2. 把 fig_id 的所有 panel 路径都送进 prompt (`panel_note` 提示 LLM 当成一张图分析)。
3. LLM 按 `figure_analyze.md` prompt 返回 YAML：`visual_summary`, `text_claim_check[]`, `deep_observation`, `caption`。
4. `safe_parse_yaml` (`stages/_common/yaml_io.py`) 容忍 stray fence/LaTeX，parse 不出来时把原文存 `raw` 字段，s09 builder 还能用 regex 救回字段。

`LANG_INSTRUCTIONS` (`runner.py:53`)：双语切换 — 加新语言加一条。

**v1.11.1 防护**：
- **Caption-stub skip** (`runner.py:93-96`)：对 `is_generation_prompt_caption` 命中的 figure 直接跳过 vision-LLM 调用，作为 s04 过滤的 defense-in-depth (老 baseline 没跑过 s04 新 filter 的情况)。
- **zh-ratio guard** (`runner.py:151+`)：当 `--lang zh` 但前 5 条 `visual_summary` CJK 字符占比 < 30%，stderr WARNING — 这是某些 vision LLM 静默忽略 `lang_instruction` 的信号（v1.10 baseline 7/15 篇出现过此污染，零检测）。

### 4.8 s08_section_compose — 上帝 stage

详见 §5。简要：

| 项 | 内容 |
|---|---|
| **输入** | s05 template + s03 chapters + s06 context+KG + s07 fig_notes + s04 figures |
| **输出** | `chapters/<NN>-<slug>.md` (一节一文件) + 各种 audit 文件 |
| **关键文件** | `stages/s08_section_compose/runner.py` (调度), `structured.py` (Strategy KL 核心，1380 行) |

对模板里的每一个节点，决定走 3 条路径之一：
1. `LAZY_PAPER_STRUCTURED=1` + 有 KG + 有 retriever → Strategy KL (`structured.compose_structured`)
2. `LAZY_PAPER_AGENT=1` + 有 KG + 有 retriever → pydantic-ai agent (`agent.run_section_agent`)
3. 默认 fallback → `_legacy_compose` (prompt-stuffed)

任何 path 失败都向下 fallback，永不 crash 整章 pipeline。

**`reviewer.py` 两层架构**：compose 完成后，每节都过 `reviewer.regex_check()` (line 71) — Python regex 在 source chunk + KG 里 grep 4 类 flag (`numeric_not_in_source` / `fig_not_in_yaml` / `formula_not_in_kg` / `unit_mismatch`)，结果落 `critic_flags.yaml`。**只有当 regex tier 抛 ≥1 flag 时**，`llm_review()` (line 199) 才会触发一次 LLM critic 调用生成 `CritiqueRevision` (针对性改写)。两层 gate 让大部分 quality check 在零 LLM 成本下完成，LLM critic 只在 regex 已经定位到问题时启动。Strategy KL 的 verifier (§5.5) 和这套 reviewer 是正交的：verifier 在 compose path 内部做 claim-level 取舍 (拒/接受/advisory)，reviewer 是 post-compose 的旁路审计 + 选择性改写。

### 4.9 s09_render — 4 renderer 出最终文件

| 项 | 内容 |
|---|---|
| **输入** | `s08_section_compose/chapters/` + `s07_figure_analyze/fig_notes.yaml` + `s06_context/context.yaml` |
| **输出** | `preview.{docx,pdf,html,pptx}` + `mypaper_bundle/` |
| **关键文件** | `stages/s09_render/runner.py`, `builder.py`, `model.py`, `renderers/{docx,html,pdf,pptx}.py` |

**Document model 是中介数据结构** (`model.py`)：
```python
@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                          # "zh" | "en"
    chapters: tuple[Chapter, ...]

class Chapter:  heading, level, blocks  # blocks 是 Paragraph | FigureBlock | TableBlock

@dataclass(frozen=True)
class Paragraph:
    text: str                          # Unicode-normalized（给 DOCX / PPTX / 打印 PDF）
    raw_text: str = ""                 # 保留 LaTeX 原文（给 HTML / KaTeX）；空串 → fallback 到 text
```

**为什么用双 text 字段（v1.13）**：DOCX 与 PPTX 不能渲染 LaTeX，所以走 Unicode 归一化（`α_en`、`Σ|τ||q̇|`、`R²`）。HTML 把 LaTeX 直接交给 KaTeX，效果远超任何 Unicode 近似。Builder 同时填两个字段，让每个 renderer 自取：HTML 走 `raw_text` 经 `iter_html_runs(...)` 输出 `<span data-tex>`；DOCX 走 `text` 经 `iter_runs(...)` 输出 italic / bold run；PPTX 直接吃 `text`。WeasyPrint 因不跑 JS，会看到 `<span data-tex>` 内的 Unicode 兜底。

**`DocumentBuilder.build()`** (`builder.py:22`)：把 markdown 字符串转换成 Document。**图绑定**逻辑在这里：`_is_referenced` (`builder.py:113`) 检测 `Fig. N` 或 `图N` / `图 N` 字面是否出现在章节正文里；命中则把这张图 embed 进 `FigureBlock`，且**每张图全文档只 embed 一次** (第一个引用它的章节赢)。

**`_UNTITLED_FALLBACK` (v1.11.1, `builder.py:13`)**：`{"zh": "未命名章节", "en": "Untitled"}` — 当 markdown 缺少 H1/H2 heading 时按 `lang` 给章节填一个本地化兜底名（之前 zh 论文也会出现 "Untitled" 英文字面，与全文中文上下文断裂）。

**4 个 renderer 都继承 `Renderer` (`renderers/base.py`)**：
- `docx.py` — python-docx；中文宋体、西文 Times New Roman；**v1.13** 接入共享 design tokens（accent `#D97757` 章节编号 + heading 左侧 vertical border、次级灰图说、accent 边深度观察块），通过 OOXML `<w:pBdr>` / `<w:rFonts>` 实现。
- `html.py` — Jinja2 + base64 image；HYPERLINK 模式把 `[span:doc:start-end]` 渲染成可点击的 `<sup>[1]</sup>` 上标 + sources footer；**v1.13** 公式 emit `<span class="math-inline|math-auto" data-tex="…">Unicode 兜底</span>`，KaTeX（默认 CDN，`LAZY_PAPER_INLINE_KATEX=1` 内联）首屏接管渲染。
- `pdf.py` — 复用 HtmlRenderer 输出，过 WeasyPrint 转 PDF；`styles.css` 中的 `@media print` 屏蔽 topbar / TOC / 控件，公式以 italic serif Unicode 内联兜底（WeasyPrint 不跑 JS）。
- `pptx.py` — python-pptx；用 `slide_planner` 分配 slide kind (title/outline/section_divider/bullets/figure/closing_rich)，bullet 文本由 `pptx_summarizer` (LLM) 生成；带 LLM cache (`out_dir/llm_cache/`)。v1.13 PPTX 没动。

**设计语言来源**：HTML/DOCX/PDF 的视觉规范由 Claude Design 基于一份参考图发出，[`docs/assets/lazy-paper-demo.html`](../docs/assets/lazy-paper-demo.html) 是契约文件，`html.py` + `styles.css` 都从它移植。Renderer 都是 stateless / 每文档；token 在 `styles.css` `:root`，3 套强调色主题（`orange / teal / indigo`）切换零 Python 改动。

**partial failure 容错** (`runner.py:124-132`)：单个 renderer 失败不阻塞其他，error 落进 `done.yaml.formats[fmt]`，`partial: true` 触发 CLI WARNING。`--retry-failed` 只重跑失败的格式。

---

## 5. s08_section_compose 内部结构

s08 占整个 codebase 复杂度的 ~40% (`structured.py` 1380 行, `runner.py` 632 行)。逐块拆解。

### 5.1 三条 compose 路径

`runner.py::run` 里的关键分支 (`runner.py:442-546`)：

```
                    ┌── LAZY_PAPER_STRUCTURED=1 + kg + retriever ──▶ Strategy KL
                    │       (structured.compose_structured)
对每个模板节点 ────┼── LAZY_PAPER_AGENT=1 + kg + retriever ──▶ pydantic-ai agent
                    │       (agent.run_section_agent)
                    └── 默认 / 上面任意失败 ─────────────────────▶ _legacy_compose
                            (prompt-stuffed, runner.py:233)
```

Strategy KL 出问题 → fall back legacy；legacy 不会 fall back (它是兜底)。所有 fall back 都打 `[s08] ... failed: ... ; falling back to ...` 日志，跑出来在 stderr 可见。

### 5.2 Strategy KL — 核心数据流

```
                  ┌─ template node (title + guidance)
                  │
   ┌──────────────▼────────────┐
   │ _build_retrieval_query    │  title + guidance + KG-scoped entity texts + keywords
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ retriever.retrieve(top_k=15) │  dense + BM25 + RRF (+ optional entity boost)
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ build_required_mentions   │  survey 章节 → 所有 comparator entity
   │ select_top_required(cap=5) │  非 survey → 仅 token-overlap entity
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ _figure_relevance(top_k=4) │  仅 LAZY_PAPER_FIGURE_BIND=1 时；Jaccard 选图
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐  ┌──────────────────────┐
   │ best-of-N compose         │──▶ _single_compose × N  │  N=BEST_OF_N, temp 0.2/0.4/0.6
   │ (instructor + Pydantic)   │  └──────────────────────┘
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ _merge_drafts             │  round-robin interleave + 3 层 dedup signature
   └──────────────┬────────────┘
                  │
   ┌──────────────▼────────────┐
   │ verify_section_draft      │  4 项 verifier: schema-prefix / quote-match / OOS / figure
   └──────────────┬────────────┘
                  │
            ┌─────┴─────┐
            │           │
   coverage > 0.5      else
            │           │
            │      ┌────▼─────────┐
            │      │ retry-when-empty │  1 次 strengthened retry，列出每个 missing 实体
            │      └────┬─────────┘
            │           │
            └─────┬─────┘
                  │
   ┌──────────────▼────────────┐
   │ retry-when-short          │  prose < MIN_CHARS 或 claims < MIN_CLAIMS 时再 retry
   │ (3 层 swap guard)          │  仅严格更好才换
   └──────────────┬────────────┘
                  │
            draft.render(mode="REMOVE")
                  │
            chapters/<NN>-<slug>.md
```

入口在 `structured.py::compose_structured` (line 989)，是整个文件的核心函数。

### 5.3 GroundedClaim schema

```python
class GroundedClaim(BaseModel):                     # structured.py:57
    text: str = Field(min_length=2)
    cited_chunk_ids: list[int] = Field(default_factory=list)
    cited_quote: str = Field(default="")
    figure_ids: list[str] = Field(default_factory=list, max_length=3)
```

**为何这样设计**：
- `text` 是给 reader 看的散文，最低 2 字符兜底防空。
- `cited_chunk_ids` 是 0-based index 到当前 section 检索到的 15 个 chunk 的列表。validator 拒掉越界的 id (Perplexity pre-injection pattern)。
- `cited_quote` 是 verbatim 抄自 chunk 的小片段，给 verifier 用。空字符串跳过 verify (有些 claim 是综合性描述，没办法逐字引用)。
- `figure_ids` 的 `max_length=3` 是 hard cap (Meta-Auditor M2: ali2025_flash ch11 出现过 62-citation 跑飞，单 claim 列 30+ 个图)。

```python
class SectionDraft(BaseModel):                      # structured.py:94
    claims: list[GroundedClaim] = Field(min_length=2, max_length=14)
```

`min_length=2` 是为了 OOS (domain mismatch) 也要至少写 2 条解释；`max_length=14` 是单节 cap (防止 LLM 跑飞写一节 30 个 claim)。

### 5.4 composer 怎么拼 prompt

**System prompt** = `_STRUCTURED_SYSTEM` (`structured.py:720`)，包含：
- chunk-only 引用规则 + required mentions 解释；
- `<Author> et al.` 强约束 (当 `author_text` 给定时不能省略)；
- FORBIDDEN 列表 (schema prefix, duplicate facts, forward-looking 设计建议 like "consider adding La doping")；
- Figure citation requirement (`figure_ids=["Fig. N"]` + 文字里必须有字面 "Fig. N" / "图N")；
- DOMAIN MISMATCH OVERRIDE (源论文不涉及该主题时输出 "源论文未涉及…" 的 2-3 claim)。

**User prompt** 在 `compose_structured` (line 1027) 里拼：
```
## Section to write
- Title: ...
- Guidance: ...

## Paper context (前 3000 字符)

## Available chunks (cite ONLY these 0-based IDs)
[0] (chapter_xxx.md chars 0-400)
    <chunk 0 前 1200 字>
[1] ...
...
[14] ...

## Required mentions (you MUST cover each)
- comparator: "BiFeO3-based..."
  author: "Jiang et al." (use this form...)
  evidence_chunk_id: 3
  evidence_quote: "..."
  linked_values: W_rec=2.94 J/cm³

## Figures topically relevant to this section  (FIGURE_BIND=1 才有)
- Fig. 3: ...
    visual: ...
    observation: ...

## Already established in prior sections
§1 ...
§2 ...

Emit the SectionDraft JSON now.
```

`_single_compose` (line 844) 用 `instructor.from_openai(..., mode=Mode.MD_JSON)` 把 OpenAI client 包成 schema-validated 调用，传 `validation_context={"allowed_chunk_ids": set(range(len(chunks)))}` 给上面的 validator。

### 5.5 verifier 做什么 (verify_section_draft, line 286)

逐 claim 跑下面这些检查，分别决定 **拒掉 / 接受 / 接受+advisory**：

| 检查 | 触发动作 | 实现位置 |
|---|---|---|
| **锚定 claim 缺 quote** (v1.12 phase 2) — claim 文本含作者或数值+单位锚点；`cited_quote` 为空 | 拒绝（`anchored_claim_no_quote`）；`LAZY_PAPER_ANCHORED_QUOTE=0` 退出 | line 329-345 |
| **schema prefix leak** — text 以 `GroundedClaim:` / `Claim:` 开头 | 直接 reject | line 323 |
| **quote-vs-chunk match** — `cited_quote` 在 cited_chunk_ids 里 fuzzy match ≥ 0.85 | 没匹配上则 reject | line 332-354 |
| **chunk-id slop fallback** — quote 在别的 chunk 里能匹上 | 修正 `cited_chunk_ids`，accept | line 343-354 |
| **anchor advisory** — claim 写了 "Jiang et al." / "2.94 J/cm³" 但 quote 不含这个 token | 仅 advisory (logged，仍 accept) | line 361-366 |
| **figure_ids whitelist** — figure_ids 不在 section_figures 里 | `LAZY_PAPER_FIGURE_ID_WHITELIST=1` (默认) → 替换 text 里的 "Fig. N" → "源论文相关图示"；并把 figure_ids 字段清掉。`=0` 仅 advisory | line 383-437 |
| **figure mention literal** — figure_ids 非空但 text 里没出现字面 "Fig. N" / "图N" | advisory (`figure_hint_unmet`) | line 438-454 |
| **OOS chapter overflow** — 任一 claim 命中 OOS opener regex + accepted > 3 | 截断到前 3 条 | line 463-480 |
| **results section thin numerics** — title 含 results/性能/结果 但 anchors < 2 + claims ≥ 3 | advisory (logged，不 reject) | line 482-495 |
| **author-not-in-chunk** (v1.11.1) — claim 文本提到 "Author Y et al." / "Author 等" 但所有 cited_chunk_ids 的 chunk 文本里都没出现该 surname | 默认 advisory (`author_not_in_chunk_advisory`)；`LAZY_PAPER_AUTHOR_HARDREJECT=1` 升级为硬拒整条 claim | line 470-497 |

**4-tier quote match (`_quote_in_chunk`, line 170)**：
1. exact substring → 1.0
2. case-insensitive → 0.99
3. **normalized** (`normalize_ocr_latex` 折叠 LaTeX cmd / OCR digit space / NFKD super/subscript / Unicode dash → ASCII) → 0.97
4. fuzzy longest-common-substring → coverage 比率

第 3 步是关键，让 LaTeX-form OCR 像 `$W _ { \mathrm { rec } }$` 能匹配 LLM 写的 `W_{rec}`。详见 `stages/_common/normalize.py`。

### 5.6 retry-when-empty 和 retry-when-short

两个独立的 retry 触发条件 (`compose_structured` line 1090-1268)：

**retry-when-empty**：post-verify 后 required mention coverage ≤ `LAZY_PAPER_RETRY_THRESHOLD` (默认 0.5)。
- 重发一次 prompt，system 末尾追加每个 missing entity 的具体 anchor hint (`"Jiang et al." or "Jiang 等人"` / `"W_rec=2.94 J/cm³"`)。
- 仅当 retry 比原 draft missing 更少才 swap。

**retry-when-short**：verified prose < `LAZY_PAPER_MIN_SECTION_CHARS` (默认 500) 或 claims < `LAZY_PAPER_MIN_SECTION_CLAIMS` (默认 4)。
- 重发一次 prompt，system 末尾追加 "previous draft only X chars, write 5-8 substantive claims"。
- 3 重 swap guard (audit β#3 加上的)：
  1. prose 更长
  2. accepted claim ≥ 原 accepted 数 **且 ≥ 1** (不能 0→0 silent swap)
  3. required missing 不回退

**为什么是两条独立 retry 而不是合并**：empty 和 short 是不同问题。一节可以 required 全覆盖但仍然 sparse (3 个 claim 全是 1 行)；另一节可以 claim 多但漏了关键 comparator。合并 retry prompt 会模糊 diagnosis 信号。

### 5.7 LOCALES + UNKNOWN_FIGURE_LABEL — 双语机制

`structured.py:34-42` 的顶层常量：

```python
LOCALES = ("zh", "en")

UNKNOWN_FIGURE_LABEL = {
    "zh": "源论文相关图示",
    "en": "a figure referenced in the source",
}
```

**这是 v1.11 把字符串集中到顶层的位置 — 加新语言只改这里 + s03/s04/s07 的对应表**。

被 `verify_section_draft(..., lang=...)` 消费 (line 421)：当 figure_id whitelist 触发，把 claim text 里的 `Fig. N` / `图N` 字面替换成 locale-aware 的中性短语，这样 reader 不会看到死链。

**加新语言 (例如 `ja`) 的完整 checklist**：

| 文件 | 位置 | 改什么 |
|---|---|---|
| `stages/s03_chapter/runner.py:14` | `SECTION_ANCHORS` | 加 「要旨」「序論」「方法」「結果」「結論」 |
| `stages/s04_figures/runner.py:18-26` | `FIG_CAP_RE`, `TAB_CAP_RE`, `FIG_MENTION_RE` | 把 `图\|Fig` 改成 `图\|図\|Fig`，`表\|Table` 改成 `表\|Table` |
| `stages/s07_figure_analyze/runner.py:53` | `LANG_INSTRUCTIONS` | 加 `"ja": "Write ... in Japanese ..."` |
| `stages/s08_section_compose/runner.py:195` | `LANG_INSTRUCTIONS` | 同上 |
| `stages/s08_section_compose/structured.py:34` | `LOCALES`, `UNKNOWN_FIGURE_LABEL` | 加 `"ja"` 入口 |
| `stages/s09_render/builder.py:120` | `_make_label` | 决定日文要不要把 `Fig.` 替成 `図` |
| `cli.py:215` | `--lang choices=("en","zh")` | 加 `"ja"` |

`section_compose.md` prompt 是 lang-neutral 的 (`{lang_instruction}` 占位符)，不需要改。

---

## 6. 图像处理链路 (s04 + s07 + s09)

```
PDF  ─▶ s01_ocr ─▶ doc_*.md ──┐                    s07 vision LLM
   ▼                          │                    ┌────────────┐
   └▶ raw imgs/<bbox>.jpg ────┤   pair img↔caption │ deep_observation
        (~130 DPI)            │   merge sub-panels │ visual_summary
                              ▼                    │ text_claim_check
                         s04_figures               │ caption (shorter)
                              │                    └────┬───────┘
                              │ figures.yaml             │ fig_notes.yaml
                              │   mentions.yaml          │
                              ▼                          ▼
                         s09_render (DocumentBuilder)
                              │
                              │ _is_referenced(fid, body):
                              │   if "Fig. N" in body or "图N" in body or "图 N" in body
                              │
                              ├─▶ FigureBlock(image_paths, caption, deep_observation)
                              │   (每个 fig_id 全文档只 embed 一次)
                              │
                              ▼
                         renderers (docx / html / pdf)
                              docx: WD_ALIGN.CENTER 放图 + 「【深度观察】」前缀
                              html: base64-embed → <img>
                              pdf:  通过 HtmlRenderer 走 WeasyPrint
```

### 关键约束：双语 regex

s04 (caption + mention 抽取), s07 (周边文字搜索), s08 verifier (figure mention literal), s09 builder (binding) 全部用 **双语对齐**的 regex。一处缺漏整条链路就断 (v1.10 之前中文论文 figure embed ratio 几乎 0)。

| Stage | 文件:行 | regex |
|---|---|---|
| s04 caption | `s04_figures/runner.py:18` | `FIG_CAP_RE = r"...(?:Fig(?:ure)?\.?\|图)\s*\d+..."` |
| s04 mention | `s04_figures/runner.py:26` | `FIG_MENTION_RE = r"(?:Fig(?:ure)?\.?\|图)\s*(\d+)([a-z])?"` |
| s07 excerpt | `s07_figure_analyze/runner.py:25` | `r"(?:\bFig(?:ure)?\.?\|图)\s*{fig_num}(?![0-9])"` |
| s08 verifier figure literal | `structured.py:444` | `rf"Fig\.\s*{num}\|图\s*{num}"` |
| s09 binding | `builder.py:113-120` | `fig_id in body or f"图{num}" in body or f"图 {num}" in body` |

s09 这一处是 substring 匹配 (非 regex)，因为只检查全句首+全句尾以外的字面包含 — 简单且零误判。

### "图绑定"唯一性约束

`DocumentBuilder.build()` 在 `embedded: set[str]` 里跨章节共享：第一个引用 Fig.3 的章节胜出，后面章节即便也写"如图 3 所示"也不会重复 embed。这就是 v1.10 Variant C **figure_ids 硬约束**的动机 —— LLM 必须在"相关章节"第一次写到 fig_id，才能保证图绑到"合适的"章节，而不是绑到上下文不强的早期章节。

---

## 7. 模板系统 (s05 + 占位符替换)

### 7.1 s05 解析

输入是一份用户写的 `.docx`，每一节是一段 numbered/list-styled paragraph + 若干 guidance 行。例：
```
1. Background and motivation
   Discuss the AFE-RFE transition; tabulate prior W_rec records.
   - Compare with PbZrO3 baselines.
2. Synthesis route
   ...
```

`parse_template` 输出树状 yaml：
```yaml
- level: 1
  number: "1"
  title: "Background and motivation"
  guidance: "Discuss the AFE-RFE transition; tabulate prior W_rec records.\nCompare with PbZrO3 baselines."
  hints: {needs_table: true, needs_figure: false}
  children:
    - {title: "Compare with PbZrO3 baselines", guidance: ""}
```

`hints` 是从 guidance 文本里 regex 推断的 (`_NEEDS_TABLE_RE` / `_NEEDS_FIGURE_RE`)，会传给 s08 的 prompt。

### 7.2 占位符替换 (s08)

guidance 里可能出现 `{paper.title}` / `{paper.system}` / `{paper.keywords}` / `{paper.figures}` 等占位符，s08 在 compose 前用 `substitute_placeholders` (`runner.py:127`) 替换成具体值。

可用 key 见 `_build_paper_data` (`runner.py:32`)：title, system, keywords, key_terms, abbreviations, figures, tables, fig_observations_brief。

未知 key 故意**保留原文**而不是 silently 删除，方便作者发现拼写错误。

---

## 8. LLM 客户端 (llm/client.py)

### 8.1 role 抽象

`llm/models.yaml` 定义 3 个 role：

```yaml
vision:
  env_prefix: LLM_VISION
  default_base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  default_model: qwen-vl-max-latest
  supports_images: true
text:
  env_prefix: LLM_TEXT
  default_base_url: https://api.deepseek.com/v1
  default_model: deepseek-chat
  supports_images: false
embeddings:
  env_prefix: LLM_EMBEDDINGS
  fallback_env_prefix: LLM_VISION   # 共享 DashScope key
  default_model: text-embedding-v3
```

每个 role 通过 `LLM(role="text")` 构造时读 `{prefix}_API_KEY` / `{prefix}_BASE_URL` / `{prefix}_MODEL`。**`fallback_env_prefix`** 是为了 embeddings 默认蹭 vision 的 DashScope key (用户只配一份 key 也能跑)。

### 8.2 chat()

```python
def chat(self, *, system, user, images=(), temperature=0.2, max_tokens=2000) -> LLMResponse:
```

返回 `LLMResponse(content, model, usage, latency_ms)`。images 走 `image_to_data_url` (base64 inline)，只有 `supports_images=true` 的 role 才能传 image，否则 raise。

### 8.3 max_tokens 计算

```python
def max_tokens(default: int) -> int:                # llm/client.py:24
    raw = os.environ.get("LLM_MAX_TOKENS_CEILING")
    ceiling = int(raw) if raw and raw.strip().isdigit() else 40000
    return min(default, max(1, ceiling))
```

每个调用点写一个 stage-default (例如 s06 KG = 32000, s08 compose = 12000, s07 figure = 4000)，然后 `LLM_MAX_TOKENS_CEILING` (默认 40000) 给所有 call clip。用户想压成本就把 ceiling 调小。

### 8.4 没有内部 cache

text/vision LLM 调用本身**不缓存** (DeepSeek input prefix cache 是 provider 端自动的，这里不参与)。唯一显式 cache 是 s09 pptx_summarizer (`out_dir/llm_cache/`)，按 chapter input hash + prompt version 索引，避免反复重算 PPT 的 bullet。

---

## 9. 测试体系

### 9.1 布局

```
conftest.py                                  # macOS DYLD 注入 (天生 mac 兼容性)
tests/                                        # 顶层：CLI + lib + harness
  conftest.py
  test_cli.py                                # CLI argparse + --only/--force/--retry-failed
  test_cli_retry_failed.py
  test_llm_client.py                         # role 解析 + max_tokens clamp
  test_llm_smoke.py                          # marker live (默认 skip)
  test_paper_kg.py                           # parquet roundtrip
  test_retriever.py                          # BM25 + RRF + entity boost
  test_citation.py                           # [span:...] marker rendering
  test_evaluate_harness.py                   # scripts/evaluate harness
  test_common/                               # 重复测 stages/_common 部分公共 lib
    test_paths.py, test_bbox.py, test_yaml_io.py, test_done.py

stages/<stage>/tests/                         # 每个 stage 自带 locality
  s01_ocr/tests/        test_runner / test_mineru / test_dispatch
  s02_clean/tests/      test_runner
  s03_chapter/tests/    test_runner (含双语 anchor 测试)
  s04_figures/tests/    test_runner
  s05_template/tests/   test_runner (含 cache stale 测试)
  s06_context/tests/    test_runner / test_kg_extract
  s07_figure_analyze/tests/  test_runner
  s08_section_compose/tests/
    test_structured.py          # GroundedClaim / verify_section_draft / merge
    test_figure_hard_constraint.py  # variant C figure_ids 行为
    test_runner.py
    test_substitution.py
    test_units.py
    test_reviewer.py
    test_agent.py
  s09_render/tests/
    test_builder.py             # DocumentBuilder + figure binding
    test_model.py
    test_runner.py
    test_renderers_smoke.py
    test_citation_render.py
    test_slide_planner.py
    test_pptx_summarizer.py
    test_cache_reuse.py
    test_partial_failure.py
  _common/tests/        test_normalize.py    # OCR/LaTeX 4-tier 折叠
```

### 9.2 marker

```toml
[tool.pytest.ini_options]
markers = ["live: tests that call real LLM/OCR APIs (skipped by default; run via -m live)"]
addopts = "-m 'not live'"
```

`uv run pytest -q` 跑 **300 passing, 2 deselected (live)**，typical < 5 秒。`uv run pytest -m live` 才真打到 LLM/OCR endpoint。

### 9.3 关键测试类别

| 类别 | 代表文件 | 测的是什么 |
|---|---|---|
| **regex** | `stages/_common/tests/test_normalize.py` | OCR→LLM 4-tier folding (LaTeX cmd / digit space / NFKD / dash) |
| **schema** | `s08/tests/test_structured.py` | `GroundedClaim` validator 拒 out-of-set chunk id；`SectionDraft` min/max length |
| **dedup** | `s08/tests/test_structured.py::test_merge_drafts_*` | (author, value) anchor / distinctive token / 120-char prefix 3 层 fallback |
| **verifier** | `s08/tests/test_figure_hard_constraint.py` | figure_id_unknown 替换；figure_hint_unmet advisory；OOS overflow cap |
| **figure binding** | `s09/tests/test_builder.py` | 双语 substring 检测；每图唯一 embed |
| **partial failure** | `s09/tests/test_partial_failure.py` | 单 renderer 失败不阻塞其他；`--retry-failed` 只重跑失败的 |
| **cache** | `s05/tests/test_runner.py`, `s09/tests/test_cache_reuse.py` | template SHA-16 stale detection；pptx LLM cache 按 prompt version 失效 |

---

## 10. 配置 & 环境变量

参考 `.env.example`。

### 10.1 必填

| 变量 | 作用 |
|---|---|
| `OCR_BACKEND` | `mineru` (默认推荐) / `paddleocr` |
| `MINERU_TOKEN` | OCR_BACKEND=mineru 时必填，https://mineru.net 获取 |
| `PADDLEOCR_TOKEN` | OCR_BACKEND=paddleocr 时必填 |
| `LLM_VISION_API_KEY` | s07 vision LLM key (默认 DashScope) |
| `LLM_TEXT_API_KEY` | s06/s08/s09 text LLM key (默认 DeepSeek) |

**v1.11.1 — `meta.yaml.lang` 持久化** (`cli.py:262-266`)：每次 `lazy-paper run` 都把 `--lang` 写进 `runs/<paper_id>/meta.yaml`，方便外部 auditor/demo 脚本不读 `fig_notes.yaml` 也能知道这一 run 的 baseline 语言（v1.10 baseline-pollution 排查时的痛点 — 没有 single source of truth 看 run-lang）。

### 10.2 LLM endpoint 切换

每个 role 都接受 `_BASE_URL` / `_MODEL` override：

```bash
LLM_TEXT_BASE_URL=https://api.openai.com/v1
LLM_TEXT_MODEL=gpt-4o
LLM_TEXT_API_KEY=sk-...
```

可换 OpenAI / Anthropic-compatible gateway / 自托管 vLLM / Ollama。

### 10.3 Strategy KL (推荐生产配置)

```bash
LAZY_PAPER_STRUCTURED=1               # 启 structured compose + verifier
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md   # 11 类 KG (含 author entity)
LAZY_PAPER_BEST_OF_N=2                # 2 次 LLM 样本，round-robin 合并
```

### 10.4 v1.10 figure binding

```bash
LAZY_PAPER_FIGURE_BIND=1              # s08 在 prompt 加入 section_figures block
                                       # + 触发 figure-retry 已被 v1.11 cut (见 §11)
LAZY_PAPER_FIGURE_ID_WHITELIST=1      # 默认 ON。verifier 拒掉未知 fig_id 并把 text 里的
                                       # "Fig. N" / "图N" 替换成 UNKNOWN_FIGURE_LABEL
                                       # =0 退回到 advisory-only (老行为)
```

### 10.5 Depth mode (opt-in)

```bash
LAZY_PAPER_MIN_SECTION_CHARS=1200     # retry-when-short 阈值 (默认 500)
LAZY_PAPER_BEST_OF_N=3                # 3 次采样 (覆盖上面的 2)
LAZY_PAPER_MIN_SECTION_CLAIMS=4       # retry-when-short 触发的 claim 下限 (默认 4)
```

### 10.6 verifier / retry fine-tune

```bash
LAZY_PAPER_VERIFIER_THRESHOLD=0.85    # quote-vs-chunk fuzzy match 阈值
LAZY_PAPER_RETRY_THRESHOLD=0.5        # post-verify coverage ≤ 这个值触发 retry-when-empty
LAZY_PAPER_REQUIRED_CAP=5             # 非 survey 章节 required-mention 上限
LAZY_PAPER_AUTHOR_HARDREJECT=0        # v1.11.1：author-not-in-chunk 默认 advisory；=1 升级为硬拒
```

### 10.7 retriever 调参

```bash
LAZY_PAPER_CHUNK_SIZE=400             # 默认 400 (Strategy G 实验)
LAZY_PAPER_CHUNK_OVERLAP=80
LAZY_PAPER_HIERARCHICAL=1             # 启 parent-child chunk + auto-merge (Strategy H)
LAZY_PAPER_PARENT_SIZE=2000
LAZY_PAPER_PARENT_OVERLAP=200
LLM_EMBEDDINGS_BATCH_SIZE=10          # DashScope cap
```

### 10.8 全局 cap

```bash
LLM_MAX_TOKENS_CEILING=40000          # clamp 所有 LLM call 的 max_tokens (default 40000)
LAZY_PAPER_HTML_CITATIONS=hyperlink   # HTML 渲染 cite marker 模式
                                       # hyperlink (default) / keep / remove
```

### 10.9 实验性 / legacy

```bash
LAZY_PAPER_AGENT=1                    # 走 pydantic-ai agent path (4 tool, ~8 iter)
LAZY_PAPER_TWO_STEP=1                 # outline → expand 双步 compose (Strategy B)
LAZY_PAPER_WHOLE_PAPER=1              # 跳过 retriever，直接喂全文 (Strategy I)
```

后三者历史实验未默认启用，保留为 fallback option 用于回归测试。

### 10.10 渲染（v1.13）

```bash
LAZY_PAPER_INLINE_KATEX=1             # 把 KaTeX CSS + JS + 20 woff2 字体作为 data: URI
                                       # 内联进 preview.html（440 KB → ~1.08 MB），
                                       # 真正离线单文件可读。默认关，开 = 不再请求 cdn.jsdelivr.net。
                                       # 首次使用前：
                                       #   uv run python scripts/fetch_katex.py
                                       # 把字体拉到 stages/s09_render/templates/vendor/katex/。
```

### 10.11 OCR 后端（v1.13）

```bash
MINERU_FORCE_OCR=1                    # 默认 ON（之前硬编码 OFF）。强制 MinerU 走 layout-OCR
                                       # 而非"文本层优先"——figure-rich 文本 PDF 的矢量图
                                       # 之前会被跳过，此修复关键。
MINERU_ENABLE_TABLE=1                 # 默认 ON。
MINERU_ENABLE_FORMULA=1                # 默认 ON。
MINERU_KEEP_RAW=0                     # 默认 OFF。设为 1 保留 MinerU zip 解压物 (_mineru_raw/)，
                                       # 排查某篇论文 figure recall 回归时用。
MINERU_MODEL_VERSION=                 # 默认空（云端选）。未来 API 模型参数预留 hook；当前
                                       # 仅接受空值（不发该字段）。
```

---

## 11. v1.11 设计决策记录

v1.11.0 是一次 **first-principles refactor** (commit `a4d90ab`)，主动**删掉**了 3 个 over-engineered 模块。v1.11.1 在 cycle 11 sentence-level audit 后补了 4 个 HIGH bug fix（v1.11.0 没 push，v1.11.1 是 v1.11 线第一个 stable）。理由记录于此以防未来重蹈覆辙。

### 11.1 cross-citation reject (cut)

**做了什么**：v1.10 在 verifier 里加了一段 ~40 LOC 逻辑：当 claim 引用了 author 但 author 不在 retrieval chunk 的引用列表里，reject 整个 claim。

**为什么 cut**：根因是 `cited_quote == ""` 的 claim 被 verifier silently 接受，让 author hallucination 漏过 quote-grounding 门。修这条路径要在 **prompt** 强制 author claim 必须带 quote，而不是在 verifier 后端再加一层 reject。40 LOC 处理 1 个 paper (ali2025 ch08) 的边缘情况，性价比太低。**推迟到 v1.12 + 正交的 reference-list 检查** (claim 提到的 author 必须出现在 paper.references KG 实体里)。

**代码标记**: `structured.py:368-372` 有 `# v1.11 architecture-review CUT: cross-citation reject was 40 LOC...`

**v1.12 phase 2 闭环**：底层缺陷 —— empty `cited_quote` 绕过 verifier —— 在 v1.12 phase 2 通过 `structured.py:329-345` 的 anchor-aware 空 quote 分支最终修复（见 §5.5 verifier 表顶行）。同时配套在 `_STRUCTURED_SYSTEM`（s08 compose 系统 prompt）里加入 HARD RULE 约束。原计划的正交 reference-list 检查（引用作者必须出现在 `paper.references` KG 实体里）最终未实现；基于 anchor 的方案已证明足够。实测影响：meng2024 的 `cited_quote` 空率从 32% 降到 0%；ali2025_flash RAGAS faithfulness +5.4pp。

### 11.2 figure-retry pass (cut)

**做了什么**：v1.10 Variant C 在 verifier 之后加了一段 ~85 LOC：当 `>=50%` 的 section_figures 没在 verified draft 里被字面提到时，重发 1 次 LLM call 让它补全。

**为什么 cut**：v1.10 跑出来发现 figure-retry 的 swap guard 自己 bug 多 (3 轮修补)。同时 v1.11 引入的 DEEP figure-claim prompt rule (`_STRUCTURED_SYSTEM` 的 "DEEP figure-claim discipline" 段，line 786) 直接在 prompt 阶段就要求每个 figure-citing claim 带具体 panel + 数值 + mechanism，**source 已经处理了 figure-retry 想解决的 placeholder 问题**。继续保留是双重投入。

**代码标记**: `structured.py:1270-1273` 有 `# v1.11 architecture-review CUT: figure-retry was 85 LOC...`

### 11.3 headline metric prompt rule (cut)

**做了什么**：v1.10 短暂加过一段 ad-hoc prompt 规则强制每章节首句必须以 "headline metric" 开头 (例 "本工作实现 W_rec=8.6 J/cm³")。

**为什么 cut**：让 LLM 在所有章节都用同样的句式，prose 单调；且 results 类章节命中而 discussion/conclusion 类章节强行套用反而显得机械。**已被通用的 quantitative validation regex + retry-when-short 覆盖**——不需要专门的 prompt rule。

### 11.4 加入的 (Tier 1)

cycle 5-7 加入并保留的：
- `_SCHEMA_PREFIX_RE` 拒 "GroundedClaim:" / "Claim:" 字面泄漏 (cycle 5 Meta)
- `_claim_dedup_anchors` 用 value+unit 复合做 dedup key（cycle 5 A3 — 修"5 GPa"和"5 J/cm³"共享 key 的 bug）
- `_OOS_CLAIM_RE` + `_MAX_OOS_CLAIMS=3` chapter-level OOS cap (cycle 6 Meta — hif_2 ch04 emit 1 OOS opener + 11 off-topic 时 claim-level cap 救不了)
- DOMAIN MISMATCH OVERRIDE prompt 路径 (cycle 5)
- `normalize_ocr_latex` BS3 (`\%` 等 LaTeX escape) + BS4 (`NFKD` super/subscript + Unicode dash 折叠) (cycle 2 Auditor 2)

### 11.5 v1.11.1 — 4 个 HIGH bug fix (cycle 11)

v1.11.0 通过了 architecture-review ship gate (hardcode scan + lang threading + test count)，但 cycle 11 sentence-level audit (3 个 subagent 交叉验证 output vs source paper) 又抓出 4 个 HIGH issue。v1.11.0 没有被 push；v1.11.1 是 v1.11 线第一个 stable。

- **Bug #1+#2 — flagship metric 跨章节漂移**：meng2024 ch07/09/13/15 对同一 flagship sample 给出 3 个不同 W_rec 值。根因：s08 在 retrieval chunk 里 scavenge comparator 邻近数字。Fix：s06 从 KG 抽 flagship 的 `headline_metrics` 注入 `context.yaml`，prompt 在 "FLAGSHIP GROUND TRUTH" block 强约束 composer 用准值。见 §4.6 Step 3。
- **Bug #3 — author misattribution**：meng2024 ch13 把 Ma et al. 的 La(Mg)-doped-NBT 结果错归到 Cao et al. (邻近 chunk 里的另一作者)。Fix：post-verify advisory `author_not_in_chunk_advisory`，默认 advisory，`LAZY_PAPER_AUTHOR_HARDREJECT=1` 升级为硬拒。见 §5.5 verifier table 末行。
- **Bug #4 — OCR text-prompt 当物理图分析**：hif_2 ch15 对 "图 43" 输出捏造物理 critique，实际该图是 unCLIP appendix 的 generation prompt 字面 `(a) A high quality photo of a dog…`。Fix：`is_generation_prompt_caption` 双层过滤 (s04 + s07 defense-in-depth)。见 §4.4。
- **Bilingual regression prevention** (Audit C)：`cli.py` 写 `meta.yaml.lang`；`s07` zh-ratio guard；`s09_render/builder.py` 本地化 `_UNTITLED_FALLBACK`。见 §4.7 / §4.9 / §10.1。

---

## 12. 已知限制 / v1.12 候选

CHANGELOG v1.10 "Deferred to v1.11" 还有未完工的：

- **BS1+BS2 normalize**：letter-spaced subscript (例如 OCR 输出 "L i 3 +" 而 LLM 写 "Li³⁺") 因为有 OCR↔LLM 不对称性，BS3+BS4 的对称折叠策略不适用。需要单独 case-by-case 解决，未排期。
- **s04 caption-aware numbering**：当前 s04 用 OCR 出现顺序编号 figure (`Fig. 1, Fig. 2, ...`)，OCR 漏掉一张图就跟原论文 figure number 不对齐，导致 LLM 看 source 写 "Fig. 5" 但 s04 没有 Fig. 5。需要 caption 文本里去抠原 figure number。
- **comparator gap**：`build_required_mentions` 只在 KG entity 里找 comparator，但有些 paper 在 references 列表里提到了对照工作而正文没显式列为 entity。要扫全文找 "Et al. ... reported" 模式的句子。
- **template-paper subject mismatch graceful degrade**：用户给一份"Relaxor AFE"模板跑一篇深度学习论文时，s08 只在每节输出 OOS overflow（"源论文未涉及..."），没有 fallback 到通用论文结构。
- **DOCX HYPERLINK dead code**：DOCX renderer 还不消费 citation_mode=HYPERLINK，只能 KEEP/REMOVE。需要把 sources 列表线接到 docx renderer。
- **6 hardcodes → env vars**：`structured.py` 里 `cap=5`, `top_k=4`, `parameter spread 0.2*i` 等数字硬编码，spec §11 要求暴露成 env var。
- **real-time LLM cost meter**：当前 `usage` 落到每个 response.json 但没 aggregated；v1.12 要在 done.yaml 加 `total_tokens / total_cost`。
- **dedup signature 优化**：merge_drafts 的 fallback prefix 仍用 120 字符，短 claim (60-100 字符) 会因前缀不匹配而漏 dedup。

---

## 参考文献 (本仓库内)

- 用户指南: [`docs_zh/USER_GUIDE.md`](USER_GUIDE.md)
- Agent / AI 协作: [`docs_zh/AGENT_GUIDE.md`](AGENT_GUIDE.md)
- 全量 changelog: [`CHANGELOG.md`](../CHANGELOG.md)
- 第三方代码归属: [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
