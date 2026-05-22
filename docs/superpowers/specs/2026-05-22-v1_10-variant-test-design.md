# v1.10 候选变体并行测试 — 设计文档

> **Date**: 2026-05-22
> **Author**: brainstorming session via neat-freak + writing-skills
> **Status**: design approved, awaiting implementation plan

## 1. 背景与动机

v1.9.2 完成 18-paper 验证后，用户审计输出文件发现：相比预期，
section 字数偏少、引用图片偏少。诊断（见上一会话 transcript）识别
出 6 个根因，其中 5 个属于 v1.8.x → v1.9.x audit cycle 累积加上的
"安全护栏"——护栏正确但**调得太紧，把深度也一起压没了**：

1. `select_top_required(cap=5)` 硬上限 5 个 required mention
2. `MIN_SECTION_CHARS=500` 太宽松
3. `retry-when-short` swap 守卫太严（v1.9.2 audit β#3）
4. 图引用是**软提示**（schema 无 `figure_ids`，verifier 不验图）
5. `_merge_drafts` 120 字 prefix dedupe 抹平 best-of-N 多样性
6. verifier `ratio_threshold=0.85` — 设计意图，不该松

本次实验目标：通过 3 个最小变体在 7 篇论文上并行测试，量化每个
根因的实际贡献，决定 v1.10 ship 哪些。

## 2. 三个候选变体

### 变体 A — 纯 env 调优

- `LAZY_PAPER_MIN_SECTION_CHARS=1200`（默认 500 → 1200）
- `LAZY_PAPER_BEST_OF_N=3`（默认 2 → 3）
- **代码改动**：0 行
- **预期机制**：retry-when-short 触发率↑；best-of-N 多采 1 份再 merge
- **预期 LLM 成本**：单论文 +50%（s08 主调用 2→3）

### 变体 B — required cap 按节型分级

- `stages/s08_section_compose/structured.py:482-540` `select_top_required` 改为按节型分级
- `LAZY_PAPER_REQUIRED_CAP_SURVEY=12`（survey 节用）
- `LAZY_PAPER_REQUIRED_CAP=5`（非 survey 节，沿用现状）
- `_is_survey_section()` 已存在 (`structured.py:287`)，调用处传过去
- **代码改动**：~15 行
- **预期机制**：长 survey 节 12 个 comparator 不再被截到 5，prompt
  里 required mentions 完整列出，LLM 必须 cite 每一个
- **预期 LLM 成本**：prompt 长度增加，无额外 LLM 调用

### 变体 C — figure_ids 进 schema + 硬约束

跨 3 处共 ~50 行：

1. `SectionDraft.GroundedClaim` 加 `figure_ids: list[str] = []` 字段
2. `_STRUCTURED_SYSTEM` prompt 加段：
   > For EVERY figure listed in 'Figures topically relevant to this
   > section', write at least one claim that sets figure_ids to
   > ["Fig. N"] AND includes "Fig. N" / "图N" literally in claim text
3. `verify_section_draft` 加一档 figure check（advisory）
4. `compose_structured` 加 figure-retry：`section_figures` 非空 AND
   verified 中缺失 ≥ 50% → 触发一次硬提示 retry

- **代码改动**：~50 行
- **预期机制**：把"图引用"从软提示升级为 schema/verifier 硬约束，
  s09 literal-mention binding 必然命中
- **预期 LLM 成本**：可能多 1 次 figure-retry / 节，单论文 ~+$0.30

## 3. 测试矩阵

7 篇论文 × 3 变体；meng2024 因 zero-variance 防守，每变体跑 3 次：

| 论文 | A | B | C | meng 重复 | TestCase |
|---|---|---|---|---|---|
| meng2024 | ✓ × 3 | ✓ × 3 | ✓ × 3 | 9 次 | T1 (headline), T3 |
| yang2025 | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | T2 fabrication |
| chai2026 | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | T6 basic |
| ali2025_flash | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | T4 comparison |
| gaur2022 | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | (generic) |
| he2023 | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | (generic) |
| pan2025 | ✓ × 1 | ✓ × 1 | ✓ × 1 | — | (generic) |

**总跑数**：3 变体 × (6 generic + meng×3) = **27 次新跑**

**baseline 对照**：复用现有 `<paper>_v190` / `<paper>_v190b` 产物。

**成本估算**：s01_ocr / s06_context / s07_figure_analyze 全缓存（仅
s08/s09 重跑）→ ~$0.3-0.5/跑 → **总 ~$8-14**

## 4. 并行架构

3 个 git worktree，每个一份变体代码改动：

```
paper2md/                    main (HEAD = 02d9ad0)
  ↓ git worktree add
.worktrees/variant-a-env/    无代码改动，仅 .env tuning
.worktrees/variant-b-cap/    structured.py select_top_required 改
.worktrees/variant-c-figure/ structured.py SectionDraft+prompt+verify 改
```

每个 worktree 跑各自的 `runs/<paper>_v<variant>_r<run>/`，paper_id
后缀区分。worktree branch 命名：`variant-a-env-test` / `-b-cap-test`
/ `-c-figure-test`。

## 5. 数据采集

每次跑结束后写 `runs/<paper>_<variant>_r<run>/metrics.yaml`：

```yaml
variant: A|B|C|baseline
paper: meng2024
run: 1
M1_chars_per_section:    # wc s08/chapters/*.md
  ch01: 1245
  ch02: 1788
  ...
M2_figures_embedded:     # 以 HTML 渲染产物为准：grep -c '<img ' s09/preview.html
M2_figures_available:    # len(fig_notes.yaml)
M2_embed_ratio:          # M2_embedded / M2_available
M3_post_verify_missing:  # parse s08 log "post-verify-missing X/Y (Z%)"
M4_testcase_scores:      # scripts/evaluate.py；有 TestCase 的论文跑 1 次
                         # 评测（meng2024 例外：T1/T3 每变体跑 3 次）
M5_retry_empty_fires:    # grep "retry-when-empty: lifted" s08.log
M5_retry_short_fires:    # grep "retry-when-short: lifted" s08.log
M6_llm_cost_usd:         # 从 LLM client token 计数推算
```

通过 `scripts/collect_variant_metrics.py`（~80 行）自动跑这套抓取。

## 6. 对比报告

实验结束后 generate `docs/v1_10_variant_comparison.md`：

- 每个变体 vs baseline 在 6 指标上的 delta 表
- meng2024 T1 stdev 检查（必须保持 ≤ stdev(baseline) = 0）
- 决策矩阵：哪个变体最值得 ship 进 v1.10、哪个有 regression

## 7. 成功标准

- **必要（M4 防退化）**：meng2024 T1 stdev ≤ baseline stdev（=0）
  - 即三次跑必须保持 9/9/9 或更高的一致性
- **目标**：至少 1 个变体让 M1（字数）和 M2（图嵌入比）显著提升
  （≥ 30%）且 M4 不退化
- **可接受**：M6 成本 +50% 内

## 8. 清理范围（执行前置）

```
runs/<paper>/          ✓ 保留（主目录 cache）
runs/<paper>_v190/     ✓ 保留（v1.9.0 baseline 对比锚点）
runs/<paper>_v190b/    ✓ 保留（v1.9.0 二次跑方差锚点）
runs/<paper>_v191/     ✓ 保留（v1.9.1 新 OCR）
runs/<paper>_v140/     ✗ 删
runs/<paper>_v160_J/   ✗ 删
runs/<paper>_v170_KL/  ✗ 删
runs/<paper>_v181_KL/  ✗ 删
```

预计释放 ~150MB（337MB → ~190MB）。

## 9. 决策候选 → v1.10

实验完成后，按指标排序决定哪些变体进 v1.10：

- **A 单独**胜出：v1.10 仅调默认 env，无代码改动
- **B 单独**胜出：v1.10 ship cap 分级
- **C 单独**胜出：v1.10 ship figure_ids 硬约束
- **A + B + C 都正向**：v1.10 全 ship（按 priority C > B > A）
- **任何变体 regression**：保留现状，未通过的根因留待下一轮

## 10. Baseline 数据二次复核（前置）

任何对比"之前例子的历史数据"的指标，都要先验证那份历史数据当下
仍可重现，否则 delta 没有参照价值。

### 区分两类指标

| 类别 | 指标 | 是否需要复核 | 原因 |
|---|---|---|---|
| Deterministic | M1 字数、M2 图嵌入数、M3 coverage、M5 retry 次数、M6 成本 | ❌ 不需要 | 直接从 baseline runs/ 的 artifact / log 读，0 LLM 调用 |
| LLM-judge 依赖 | M4 TestCase 得分 | ✅ **必须** | judge 自身有方差，历史记录的分数（如 meng2024 T1 = 9/9/9）当下未必复现 |

### M4 复核操作（实验启动前完成）

1. 用当前 `scripts/evaluate.py` 重跑 baseline TestCase：
   - meng2024 v190 三次跑 → 重新评 T1 + T3
   - yang2025 v190 → 重评 T2
   - chai2026 v190 → 重评 T6
   - ali2025_flash v190 → 重评 T4
2. 与 docs 历史记录对比：
   - 偏差 ≤ ±1 → 视为 judge 噪声，记录但接受
   - 偏差 ≥ 2 → baseline 历史分数不可信，扩大 sample（每 TestCase 跑 3 次取均值）
3. 实验对比时使用**当下重评的 baseline 分数**作为参照，不引用 docs 里的历史记录

### 成本

- ~$0.5 × 5 个 TestCase × 1-3 次 = **~$2.5-7 额外**
- 总实验预算调整：$8-14 → **$10-21**

### 文档记录

复核结果写到 `runs/_baseline_recheck.yaml` + 实验报告 §1 引用，使
对比起点可审计。

## 11. External reference + extended corpus（避免闭门造车）

用户原则：「时间充裕、成本充裕，质量/深度/完善 > 速度」。本次实验
不只比 3 变体的指标 delta，也要把 v1.10 候选放到**业界开源 deep-
research / paper-synthesis 工作**的设计图谱里对照，并加 2 篇**跨
领域 + 高 IF**论文做外部验证语料。

### 11.1 开源 deep-research / paper-synthesis 工作 survey

调研全部 6 个候选系统：

| 系统 | 出处 | 关键对照点 |
|---|---|---|
| **STORM** | Stanford OVAL | 多智能体 outline-then-write、wikipedia-style 综述生成 — 对照 s05 outline + s08 compose；v1.10 候选 per-comparator drafting 灵感来源 |
| **OpenScholar** | AI2 | retrieval-grounded scholarly QA、informed-retry 范式 — 对照 v1.9 informed-retry 设计 |
| **LitLLM** | — | per-comparator drafting、citation grounding — 对照变体 B/C 设计 |
| **gpt-researcher** | open-source autonomous research agent | 对照 `LAZY_PAPER_AGENT=1` 实验路径 |
| **PaperQA2 / GPT-Pdf** | scientific paper QA | 对照 figure binding / verifier |
| **Onyx citation processor** | 已 vendored 用作 citation 处理 | 已知 reference，但要复盘当前用得对不对 |

**输出**：`docs/v1_10_external_reference.md` 含每系统的：
1. 简介（来源、定位、核心机制）
2. 对照点（figure citation / quote grounding / coverage 兜底 / informed-retry 类机制）
3. 与 v1.10 三变体的异同（借鉴 vs 分歧）
4. 决策建议（哪些 best practice 应吸纳进 v1.10）

**工作量**：~30-45 min WebSearch + 1-2 h 写作。**质量优先**：每个
系统至少看 README + 1 篇代表论文 abstract + 关键 code module。

### 11.2 高 IF 扩展语料

7 篇语料都是材料学/电容器领域。加 2 篇拓宽领域 + 提升难度：

| # | 类别 | 期刊 IF | 用途 |
|---|---|---|---|
| HIF-1 | Nature / Science / Nat Rev Mat 综述 | 30-50+ | 测**长 survey** 场景：变体 B 的 cap 分级在 12+ comparator 链下扛不扛 |
| HIF-2 | ML 高图论文（NeurIPS/ICML/CVPR + 8-15 张图） | proceedings 顶会 | 测**多图引用**：变体 C 的 figure_ids 硬约束在多图场景的实效 |

**PDF 来源**：由 user 提供（可上传 PDF 到 input/，或指定开放访问
URL）。如 user 暂不提供，从 arXiv 拉 1 篇开放材料学 / 1 篇 CS 论文
作 fallback，但首选 user 挑选的高 IF 真实论文。

**跑法**：每变体 +2 paper = 总跑数 27 → **33 跑**；额外 LLM 成本
~$3-5。

**指标采集**：与 7 篇内置语料完全相同，metrics.yaml 写到对应
worktree 的 `runs/<paper>_v<variant>_r1/`。

### 11.3 报告侧补充

`docs/v1_10_variant_comparison.md` 加：
- §6 **外部 reference 对照**：把 v1.10 三变体放进 §11.1 调研出的
  设计图谱里，说"我们在哪些点跟主流一致 / 哪些点是 contrarian /
  哪些点借鉴了谁"
- §7 **高 IF 扩展验证**：HIF-1 / HIF-2 两篇的 6 指标 delta，对比
  7 篇内置语料的均值，看变体在跨领域 / 高难度场景是否仍然 hold

## 12. 不在本次 scope 的工作

以下 v1.10 候选不在本实验中验证：

- `_merge_drafts` 120-char prefix dedup 改 60-char（根因 #5）
- 抽 `_attempt_retry` helper 去重（refactor，无 behavior 变化）
- 6 个 retry-temperature / figure-top_k / claim-range hardcode 暴露
  为 env var（已在 v1.10 候选列表）

这些可在本实验结果出来后单独 brainstorm 第二轮。
