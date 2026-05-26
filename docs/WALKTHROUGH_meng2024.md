# lazy-paper — 端到端流程剖析

> **用例**: meng2024 — ACS Appl. Mater. Interfaces 2024 NBT 基 AFE-like RFE 论文
> **目标**: 跟着 `runs/meng2024_v111_demo/` 真实产出，逐段看一篇 PDF 怎么变成 4 个最终文档
> **数据时间**: 2026-05 v1.11.5 + Phase 1（v1.12 phase 1 fully gated, off by default）

```
input/meng2024.pdf  ──▶  9 stages  ──▶  preview.{docx, pdf, html, pptx}
（22 MB 论文）              ↓                  ↓
                  每段写 done.yaml         778 KB 中文深度分析
```

各 stage 实际产出大小（从 disk 读出）：

| Stage | 产物大小 | 文件数 |
|---|---|---|
| s01_ocr | 700 KB | 16 |
| s02_clean | 700 KB | 16 |
| s03_chapter | 80 KB | 3 |
| s04_figures | 28 KB | 4 |
| s05_template | 20 KB | 2 |
| s06_context | 44 KB | 6 |
| s07_figure_analyze | 124 KB | 16 |
| s08_section_compose | 700 KB | 21 |
| s09_render | 3.2 MB | 7 (4 输出 + 1 bundle) |

---

## s01_ocr → MinerU 把 PDF 拆成 markdown + 图片

**Input**: `input/meng2024.pdf`（一个 PDF 文件，22 页）
**Output**: `s01_ocr/doc_<0..N>.md`（每页一个）+ `s01_ocr/imgs/img_mineru_<NNN>.jpg`

```
runs/meng2024_v111_demo/s01_ocr/
├── doc_0.md     ← 标题页 + Abstract
├── doc_1.md     ← Figure 1 + intro 开头
├── doc_2.md     ← intro 续 + Figure 2 (SEM)
├── ...
├── doc_15.md    ← references
└── imgs/
    ├── img_mineru_001.jpg
    ├── img_mineru_002.jpg
    └── ... (~24 张)
```

**MinerU 做什么**：cloud OCR，输入是 PDF 二进制，输出是按页分割的 markdown。它会自动识别图片区域、把图存成 jpg、在 markdown 里用 `<img src="imgs/img_mineru_005.jpg">` 引用。公式存为 LaTeX（`$$...$$`）。

**典型坑**：列分栏的 PDF 偶尔把"左栏第 3 行 + 右栏第 3 行"误拼成一行；某些图片的 bbox 把 caption 一起裁进去了。**s02 修这些**。

---

## s02_clean → 修 OCR 噪声（不重写，只标注）

**Input**: `s01_ocr/doc_*.md`
**Output**: `s02_clean/doc_*.md` + 同 `imgs/` 软引用

s02 做三件 deterministic 的事：

1. **去重复 running header**：跨页出现 ≥3 次的短行（如 "Research Article | https://doi.org/..."）删掉
2. **修字符**：`(cid:0)` → `−`，bare `O 2` → `O₂`
3. **标 corrupted column flow**：单字符 token 占比 > 60% 的行加 HTML 注释 `<!-- corrupted-column-flow -->`，**不删原文**

```diff
- ... $$$$
- where $\varepsilon_{r(T)}$ is the $\varepsilon_r$ at various temperatures ...
+ ... <!-- corrupted-column-flow -->
+ where $\varepsilon_{r(T)}$ is the $\varepsilon_r$ at various temperatures ...
```

**为什么不重写**：人审查 clean markdown 时能看到原始噪声，便于追溯到 PDF 来源。下游 stage 看到注释会跳过该行。

---

## s03_chapter → 按 IMRaD 锚点把页面归章

**Input**: `s02_clean/doc_*.md`（16 页 markdown）
**Output**: `s03_chapter/chapters/chapter_NNN_<slug>.md` + `chapter_index.yaml`

meng2024 的实际归章结果：

```yaml
- chapter_no: 0     # 标题页 + Abstract（无下游 chunk 用，但保留）
  title: Preface
  sources: []        # 此处实际为 doc_0.md，但 sources 为空因为系标题/摘要直传
  chars: 2769

- chapter_no: 1
  title: INTRODUCTION
  file: chapter_001_INTRODUCTION.md
  sources: [doc_0.md, doc_1.md, doc_10.md, doc_11.md]
  chars: 14929

- chapter_no: 2
  title: CONCLUSIONS
  file: chapter_002_CONCLUSIONS.md
  sources: [doc_12.md]
  chars: 3623
```

**注**：meng2024 的归章看着像只有 3 章——因为 s03 的 `SECTION_ANCHORS` set（`stages/s03_chapter/runner.py:14`）匹配的是大写 `INTRODUCTION` / `CONCLUSIONS` / `RESULTS AND DISCUSSION` 等。如果 PDF 用其他名字（如"Experimental Section"），它会被合到上一章。**这是双语锚点**——同时识别 `引言`、`结论` 等中文章节名。

**为什么归章**：下游 retrieval（s08）按"章"做 scope，避免把"实验段落"的 chunk 误匹配到"理论分析"段。

---

## s04_figures → 配对图 + 生成 mentions 反向索引

**Input**: `s02_clean/doc_*.md`（含 `<img>` 引用）+ `s03_chapter/chapters/`
**Output**: 3 个 yaml

```
s04_figures/
├── figures.yaml     # 主索引：每图的 fig_id + image_path + caption + source_doc
├── tables.yaml      # 表的同等结构
├── mentions.yaml    # 反向索引：每章引用了哪些 fig_id
└── done.yaml
```

`figures.yaml` 头条：

```yaml
- fig_id: Fig. 1
  image_rel_path: imgs/img_mineru_005.jpg
  caption: Schematic diagram of the synergistic optimization strategy in this work
           to construct AFE-like NBST-BMZ RFE ceramics with superior energy-storage performances.
  source_doc: doc_1.md
```

`mentions.yaml`（反向索引）：

```yaml
chapter_001_INTRODUCTION.md:
  - Fig. 1
  - Fig. 2a
  - Fig. 6
  - Fig. 11
  - Fig. 12
  - Fig. 13
```

**关键正则**：`FIG_MENTION_RE = r"(?:Fig(?:ure)?\.?|图)\s*(\d+)([a-z])?"`，双语都识别。Phase 1 起 5 处都用同一 regex，是已知 fragility。

**v1.12 phase 1 加的 `--pdffigures2`**（默认关）：调 AI2 的 PDFFigures 2 docker 镜像直接从 caption 文本解析"原文 Fig. N"编号，再用 Jaccard ≥0.5 跟 MinerU 的对齐重命名。修 MinerU 顺序错位 bug。

---

## s05_template → 把用户 outline.docx 解析成树

**Input**: `Table of Contents-Relaxor AFE-ZGY-HW.docx`（用户提供的章节模板）
**Output**: `s05_template/template.yaml`（树形）+ `done.yaml`（含 `template_sha256_16` 指纹）

```yaml
- level: 1
  title: Introduction
  guidance: |
    (Research background and motivation: {paper.system})
    Antiferroelectrics
    Describe the fundamental characteristics of antiferroelectrics (AFE): crystal structure,
    P-E hysteresis loop, phase transition behavior, and representative material systems.
    Identify which AFE category {paper.system} belongs to. Draw on key terms {paper.keywords}.
  hints:
    needs_table: false
    needs_figure: false
  children:
    - title: Antiferroelectrics
      guidance: ''
    - title: Relaxors/ relaxor AFEs
      guidance: ''
```

**这是"做什么"层**：模板告诉 LLM"Introduction 应该讲背景 + AFE 概念 + 找出本文系统属于哪类 AFE"。每段 guidance 里 `{paper.system}` / `{paper.keywords}` 是占位符，由 s06 提取的 context 在 s08 时替换。

**指纹缓存**：done.yaml 记 `template_sha256_16`。CLI 在下次跑时 `is_cache_stale()` 自动比对——用户改了 docx 就重 parse，无需 `--force`。这是 v1.10 加的。

---

## s06_context → 抽元数据 + 11 类 KG（"读懂论文"）

**Input**: `s03_chapter/chapters/`（intro + abstract 优先）
**Output**: `context.yaml` + `paper_kg.parquet` + `paper_kg.rel.parquet`

### Step 1: paper_context.md 调一次 LLM 出 metadata

```yaml
title: Superior Energy-Storage Performances under a Moderate Electric Field ...
system: (1-x)(Na0.3Bi0.38Sr0.28TiO3)-xBi(Mg0.5Zr0.5)O3 (x = 0.00, 0.05, 0.10, 0.15, 0.20) ceramics
abbreviations:
  - {abbr: NBT,  expansion: Na0.5Bi0.5TiO3}
  - {abbr: NBST, expansion: Na0.3Bi0.38Sr0.28TiO3}
  - {abbr: BMZ,  expansion: Bi(Mg0.5Zr0.5)O3}
  - {abbr: W_rec, expansion: recoverable energy density}
  - {abbr: η,    expansion: efficiency}
key_terms: [antiferroelectric-like, relaxor ferroelectric, defect dipole, ...]
keywords: [antiferroelectric-like, Na0.5Bi0.5TiO3-based, ...]
headline_metrics:                       # v1.11.1 加，从 KG 抽
  flagship: 0.85(Na0.3Bi0.38Sr0.28TiO3)-0.15Bi(Mg0.5Zr0.5)O3
  W_rec: '5.00'
  η:     '90.09'
```

`headline_metrics` 块通过查 KG 里 `m_85NBST15BMZ --has_W_rec--> v_main_Wrec --has_unit--> u_Jcm3` 这条链得来。**用途**：s08 compose 时把这几个数字塞进 prompt 的"FLAGSHIP GROUND TRUTH"块，防止 LLM 把 comparator 的 W_rec 写到本文上。

### Step 2: paper_kg.md 调一次 LLM 抽 11 类闭合 KG

meng2024 实际产出：

```
entities by type: {
  material: 2, dopant: 1, parameter: 3, value: 11, unit: 3,
  figure: 2, table: 1, claim: 2, method: 2, comparator: 4, author: 4
}
relations: 24
```

sample entities + relations：

```
[m_85NBST15BMZ] material   text='0.85(Na0.3Bi0.38Sr0.28TiO3)-0.15Bi(Mg0.5Zr0.5)O3'
[m_NBST]        material   text='Na0.3Bi0.38Sr0.28TiO3'
[d_BMZ]         dopant     text='Bi(Mg0.5Zr0.5)O3'
[p_Wrec]        parameter  text='W_rec'
[a_Jiang]       author     text='Jiang'              # comparator 论文作者
[comp_Jiang]    comparator text='Jiang et al. Ca²⁺/Nb⁵⁺-codoped Bi0.5Na0.5TiO3'
[v_Jiang_Wrec]  value      text='2.94'
[v_main_Wrec]   value      text='5.00'
[u_Jcm3]        unit       text='J/cm³'

m_85NBST15BMZ  --has_W_rec--> v_main_Wrec
m_85NBST15BMZ  --has_η-->     v_main_eta
a_Jiang        --cited_by_paper--> comp_Jiang        # author → comparator paper
comp_Jiang     --has_W_rec--> v_Jiang_Wrec           # comparator 也有 W_rec
```

每个 entity 有 `source_span = (doc_name, char_start, char_end)`，用 instructor 强制 Pydantic validation。任何字段失败 → 整个 KG 失败 → s06 写 `kg_extract.failed` 标记 → 下游 s08 看到标记 fallback 到 legacy compose。

**v1.12 phase 1 加的 `LAZY_PAPER_ENTITY_DEDUP=1`**（默认关）：在这一步后跑 LightRAG 风格 1 次 LLM dedup，把 "Meng et al." / "Meng 2024" / "本工作" 合并成 1 个 author entity。meng2024 KG 本来就 canonical，所以 dedup 是 no-op；适用于 KG 出现变体的论文。

---

## s07_figure_analyze → 每张图调一次 vision LLM

**Input**: `s04_figures/figures.yaml` + `mentions.yaml` + `s03_chapter/chapters/` + `s06_context/context.yaml`
**Output**: `fig_notes.yaml`（每图 1 条）+ `<fig_id>.{prompt.md, response.json}`

对每个 `fig_id`：
1. 拉图片（可能多 panel）
2. 从 chapter 文本里搜 ±1 段"Fig. N 提到的上下文"
3. 调 Qwen-VL-Max（默认）一次 LLM call

实际产出（Fig. 1 节选）：

```yaml
- fig_id: Fig. 1
  visual_summary: |
    图像展示了从NBST到NBST-BMZ陶瓷的协同优化策略示意图。左侧为原始NBST材料，显示其P-E回线明显"捏合"
    （pinched），导致极化提前饱和，最大极化（P_max）大但击穿强度（BDS）低，从而储能密度（W_rec）小、
    效率（η）中等。中间部分列出四种优化机制：扩大带隙（Eg）、细化晶粒、调控相结构（降低自由能差ΔG）、
    调制极性纳米区（PNRs）并引入缺陷偶极子。右侧为优化后的 NBST-BMZ ...
  text_claim_check:
    - claim: Schematic diagram of the synergistic optimization strategy ...
      verdict: supported
      note: 图中清晰展示了从NBST到NBST-BMZ的转变路径及四个关键优化机制。
    - claim: The introduction of A-site Bi³⁺ contributes to maintaining a large polarization response ...
      verdict: unsupported       # ← LLM 自己判 unsupported
      note: 图中未展示轨道杂化或电子结构细节，该信息属于文本补充而非图示内容。
    - claim: BMZ complex ions ... resulting in an increased random field and a decreased anisotropy field.
      verdict: supported
      note: 图中"Modulating PNRs"部分通过对比PNR形态变化，暗示了局部无序和随机场增强。
  deep_observation: |
    该图虽系统展示了优化路径，但存在概念简化风险：将复杂的多尺度效应（如缺陷偶极子形成机制、PNR动力学演化）
    压缩为静态示意图，可能误导读者认为这些过程是独立且可逆的 ...
  caption: 协同优化策略构建类反铁电储能陶瓷
```

**两个关键产物**：
- `text_claim_check[]`：图 vs 文字描述的 per-claim 一致性裁决（supported/unsupported），这是后续 deep observation 的依据
- `deep_observation`：vision LLM 写一段批判性观察。被 "critique-vs-description" gate 过滤——如果只用 `shows / depicts` 这种描述性动词就被拒重试

**Phase 2 没改 s07**。

---

## s08_section_compose → 流水线的"心脏"，含 RAG

**Input**: s05 template + s03 chapters + s06 context+KG + s07 fig_notes + s04 figures
**Output**: `s08/chapters/<NN>-<slug>.md`（每模板节一个）+ `<NN>-...structured.json`（schema 化中间产物）+ `retrieval.parquet`

这是 Strategy KL 路径（默认 ON），对每个模板节：

### 1. Build retrieval query

每节用 `title + guidance + KG-scoped entity texts + keywords` 拼成检索 query。

### 2. Retriever 出 top-15 chunks（BM25 + dense + RRF + entity boost）

meng2024 实际 retrieval 状态：**总 60 个 chunks**（chapter 切 chunk_size=400 + overlap=80）。

```python
# retrieval.parquet 内每条
{chunk_id: 0, doc_name: 'chapter_000_Preface.md', char_start: 0, char_end: 1422,
 text: '...# Superior Energy-Storage Performances under a Moderate Electric Field Achieved ...'}
```

RAG 三路融合：
- **BM25 sparse**：词频
- **Dense embedding (text-embedding-v3)**：cosine 相似度
- **Reciprocal Rank Fusion (RRF)**：把两个排名融合
- **Entity boost**：query 含 KG 抽过的 entity（如 "NBST"、"W_rec"）时，包含该 entity span 的 chunk 得分加权

实际效果：retriever 给每节挑 15 个 chunks，作为该节 compose LLM 调用的"可见证据集"。

### 3. Build required mentions（强制覆盖项）

对 introduction / discussion 这类 survey 节，从 KG 拉所有 comparator entity（4 个：Jiang/Ma/Zhang/Tang）+ 各自的 W_rec 值 + author 名作为 "required mentions"。LLM **必须**为每个写一条 claim。

### 4. Compose LLM call（Pydantic 强 schema）

system prompt = `_STRUCTURED_SYSTEM`（`structured.py:758+`，包含 chunk-only citation rule + author 形式 + FORBIDDEN + figure citation + HARD RULE on cited_quote）。

user prompt 拼成：
```
## Section to write
- Title: Introduction
- Guidance: <来自 template.yaml>

## Paper context (first 3000 chars)
title: Superior Energy-Storage ...
system: (1-x)(Na0.3Bi0.38Sr0.28TiO3)-xBi(Mg0.5Zr0.5)O3 ...
headline_metrics: {flagship: ..., W_rec: '5.00', η: '90.09'}

## Available chunks (cite ONLY these 0-based IDs)
[0] (chapter_000_Preface.md chars 0-1422) <first 1200 chars>
[1] (chapter_000_Preface.md chars 1422-2640) ...
...
[14] ...

## Required mentions (you MUST cover each)
- comparator: "Jiang et al. Ca²⁺/Nb⁵⁺-codoped Bi0.5Na0.5TiO3"
  author: "Jiang et al." (use this form)
  evidence_chunk_id: 3
  linked_values: W_rec=2.94 J/cm³, η=91.04%
- comparator: "Ma et al. La(Mg1/2Zr1/2)O3 modified ..."
  ...

Emit the SectionDraft JSON now.
```

调用通过 `instructor.from_openai(..., mode=Mode.MD_JSON)`，validator 注入 `allowed_chunk_ids=set(range(15))`。LLM 必须返回符合 `SectionDraft` 的 JSON：

```json
{
  "claims": [
    {
      "text": "介电储能电容器因其高功率密度、快速充放电速率和长循环寿命...",
      "cited_chunk_ids": [7, 8],
      "cited_quote": "",   ← v1.11.5 这里允许空（Phase 2 关掉了，见下）
      "figure_ids": []
    },
    {
      "text": "Jiang等人在Ca²⁺/Nb⁵⁺共掺杂Bi0.5Na0.5TiO3中实现了W_rec=2.94 J/cm³和η=91.04%。",
      "cited_chunk_ids": [3],
      "cited_quote": "Jiang et al., a moderate Wrec of 2.94 J/cm3 ...",
      "figure_ids": []
    },
    ...11 个 claim 总数
  ]
}
```

### 5. Verifier 8 级（structured.py:286+ `verify_section_draft`）

每个 claim 走这 8 个 check。**v1.12 phase 2 加在最上面（v1.11.5 里 #4 是默认通过）**：

| # | Check | Action |
|---|---|---|
| 0 | Schema prefix leak（"GroundedClaim:" 开头）| Reject |
| 1 | **anchored_claim_no_quote**（v1.12 phase 2 新）：有 author/value+unit anchor 但 `cited_quote=""` | Reject（默认 ON，env opt-out）|
| 2 | 空 quote + 无 anchor | Accept（synthesis claim）|
| 3 | Quote-vs-chunk 4 级 fuzzy match（exact → case-insensitive → normalized → fuzzy LCS） | Reject if no match |
| 4 | Chunk-id slop fallback（quote 在别的 chunk 里找到）| Patch cited_chunk_ids, accept |
| 5 | Anchor advisory（claim 提到作者但 quote 不含）| Advisory only |
| 6 | figure_ids whitelist（图编号不在 available_fig_ids）| Rewrite "Fig. N" → 中性短语 |
| 7 | OOS overflow chapter-level cap > 3 | Truncate |

第 3 级（quote-vs-chunk）的 normalized 层是关键：把 LaTeX `$W_{rec}$` 和 OCR 出的 `W rec` 折叠到同一形式，避免假阴。

### 6. Best-of-N（默认 N=2）+ merge

并发跑 2 个 compose（temperature 0.2 / 0.4），verifier 都过后用 round-robin interleave 合并，按 (author, value+unit) anchors + distinctive token + 120-char prefix 三层 dedup。

### 7. retry-when-empty / retry-when-short

如果 required-mention 覆盖率 ≤ 0.5 → 强化 prompt 重跑一次。如果总字数 < 500 char 或 claim < 4 → 同上。三层 swap guard：retry 必须严格优于原版才替换。

### 8. 最终 render

通过 verifier 的 claim 拼成最终 markdown，写到 `s08/chapters/01-Introduction.md`。citation marker `[span:doc:start-end]` 按渲染模式保留或删除。

---

## s09_render → 一个数据模型，四个 renderer

**Input**: `s08/chapters/` + `s07/fig_notes.yaml` + `s06/context.yaml`
**Output**: `preview.{docx, pdf, html, pptx}` + bundle 目录

### 内存数据模型（`s09_render/model.py`）

```python
@dataclass(frozen=True)
class Document:
    paper_title: str
    lang: str                              # "zh" | "en"
    chapters: tuple[Chapter, ...]

class Chapter:
    heading: str
    level: int
    blocks: tuple[Block, ...]              # Paragraph | FigureBlock | TableBlock

class FigureBlock:
    fig_id: str
    image_paths: tuple[str, ...]            # 可多 panel 合并
    caption: str
    deep_observation: str
```

`DocumentBuilder.build()` 把 s08 markdown → Document object：
- 按段切 paragraph
- 检测 chapter 文本里是否含 "Fig. N" 字面（`_is_referenced(fid, body)`）
- 每个 fig_id 在整个文档**只 embed 一次**（first-reference-wins）

### 四个 renderer（都 subclass `Renderer`）

| 格式 | Library | 输出大小 (meng2024) | 特色 |
|---|---|---|---|
| docx | python-docx | ~280 KB | Times New Roman + 宋体（中文）|
| pdf | WeasyPrint via HTML | **782 KB** | 跟 html 同源 |
| html | Jinja2 + base64 image | ~1.7 MB | 单文件，可 email |
| pptx | python-pptx + slide_planner + pptx_summarizer (LLM) | ~480 KB | LLM 分组成 4-5 节大纲，分 7 种 slide_kind |

### Partial failure 容错

四个 renderer 任一失败不阻断其他。`done.yaml.formats[fmt]` 记成功的 path 或 error。`--retry-failed` 只重跑失败的格式。

### bundle 目录

`s09_render/<paper-id>_bundle/` 含 chapters/ + figures/ + README，方便分发"分离 markdown + 图片"版本。

---

## 全流程 RAG 数据流（重点回看）

```
                                        s08 retriever（每节调用一次）
                                        ┌──────────────────────────────┐
s03 chapters/         ──切块──────────▶ │  60 chunks total              │
  ↓                   chunk_size=400  │  ├─ BM25 sparse score        │
s06 KG.parquet        ──entity 提取─▶ │  ├─ dense embedding score    │
  ↓                                   │  ├─ RRF 融合排名             │
template guidance     ──query 拼─────▶ │  └─ entity-span boost        │
  (per section)                       └────────┬─────────────────────┘
                                               │ top 15 chunks
                                               ▼
                              ┌────────────────────────────┐
                              │  Compose LLM call (s08)     │
                              │  (instructor + Pydantic)    │
                              │  prompt 含:                  │
                              │   - template guidance       │
                              │   - paper context           │
                              │   - 15 chunks (0-based ID) │
                              │   - required mentions       │
                              │   - HARD RULE on quote      │
                              └────────┬───────────────────┘
                                       │ SectionDraft JSON
                                       │ {claims:[{text, cited_chunk_ids,
                                       │           cited_quote, figure_ids}]}
                                       ▼
                              ┌────────────────────────────┐
                              │  verify_section_draft       │
                              │  (8 levels, see §s08 above) │
                              └────────┬───────────────────┘
                                       │ accepted[] + rejected[]
                                       ▼
                              s08/chapters/01-Introduction.md
```

**关键设计点**：
1. **chunk ID 是闭合集合**：prompt 里写 `(cite ONLY these 0-based IDs)`，validator 拒收范围外 ID。**LLM 没法引用没看过的 chunk**——这是 Perplexity-style grounding 的核心。
2. **cited_quote 是 verifier 的主信号**：v1.12 phase 2 关掉了"空 quote 默认通过"的 bypass。anchor（作者/数值）+ 空 quote → REJECT。
3. **retrieval 不重算**：retriever build 一次 `retrieval.parquet`，所有 section 共用。重跑只重 compose。

---

## 一个具体的 claim 从生成到渲染的旅程

以 §01 第 4 个 claim 为例（meng2024_v111_demo/s08_section_compose/01-Introduction.structured.json）：

```json
{
  "text": "Jiang等人在Ca²⁺/Nb⁵⁺共掺杂Bi0.5Na0.5TiO3中实现了W_rec=2.94 J/cm³和η=91.04%。",
  "cited_chunk_ids": [3],
  "cited_quote": "Jiang et al., a moderate Wrec of 2.94 J/cm3 and a high η of 91.04% were achieved in Ca2+- and Nb5+-codoped Bi0.5Na0.5TiO3",
  "figure_ids": []
}
```

发生了什么：
1. **s06 KG** 抽出 `comp_Jiang` comparator entity + `v_Jiang_Wrec` value entity
2. **s08 build_required_mentions** 把这个 comparator 列入 "required mentions"，告诉 LLM 必须写它
3. **s08 retriever** 把 chunk 3（含 Jiang 那句的原文片段）排进 top-15
4. **s08 compose LLM** 在 prompt 里看到"Jiang et al. (use this form) | W_rec=2.94 J/cm³"的硬约束 + chunk 3 的内容
5. LLM 生成 claim text，把 chunk 3 的句子原样抄到 `cited_quote`
6. **verify_section_draft 第 3 级 quote-match**：把 quote 跑 4 级 fuzzy（normalize_ocr_latex 折叠 `Wrec` 和 `W_{rec}`、`J/cm3` 和 `J/cm³`）→ 通过
7. **anchor advisory check**：quote 里有 `Jiang` 和 `2.94` 都对得上 claim text → 通过
8. **render**：写到 `01-Introduction.md`，最后 docx/pdf/html/pptx 都引用这段文字

如果 LLM 偷懒只写 `text` 不填 `cited_quote`：
- **v1.11.5 baseline**：verifier 默认接受（bypass），最终渲染中的 "Jiang et al. ... 2.94 J/cm³" **没有被任何机制校验**
- **v1.12 phase 2**：`_claim_anchors("Jiang等人")` 返回 `['Jiang']`（非空）→ `cited_quote.strip()==""` → REJECT with `reason="anchored_claim_no_quote"`

这是 v1.12 phase 2 修的真实场景，从 LLM 调用层确保 every author/value claim 都有源。

---

## 最终交付

`runs/meng2024_v111_demo/s09_render/preview.pdf`（782 KB）是 22 页 PDF 输入 → 中文深度分析 PDF 输出。包含：

- 4 个完整章节（Introduction / Materials & Methods / Results / Discussion / Conclusion）
- 每段平均 6-12 个 grounded claim（每个都有 chunk-ID 锚定）
- 嵌入式 figure（每图首次引用时按 fig_id 嵌入，每图 ≤ 1 次）
- 引文标记（默认渲染时去除，`--debug-citations` 保留）
- 每段末尾的 "深度观察" 来自 s07 vision LLM 的 `deep_observation`

总 LLM 成本（DeepSeek-Chat + Qwen-VL-Max + DashScope embeddings）：约 **$0.60-1.20 per paper**（s08 是大头）。耗时：**5-20 分钟**取决于论文长度。
