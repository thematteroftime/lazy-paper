# v1.10 Variant Comparison — Final Report

> **Date:** 2026-05-22 → 2026-05-23
> **Spec:** `docs/superpowers/specs/2026-05-22-v1_10-variant-test-design.md`
> **Plan:** `docs/superpowers/plans/2026-05-22-v1_10-variant-test.md`
> **External reference:** `docs/archive/v1_10_external_reference.md`

---

## §1 Baseline 复核结果 (spec §10)

Per spec §10 (post-hoc corrected: evaluator is fully deterministic, not LLM-judge dependent):

`scripts/recheck_baseline.py` 重评 10 个 baseline TestCase × 1 次：
**全部 OK，零 DRIFT** —— baseline 历史分数 100% 复现：

| paper | testcase | historical | current | verdict |
|---|---|---|---|---|
| meng2024_v190 | T1 ch01_benchmark_recovery | 9 | 9 | OK |
| meng2024_v190 | T3 ch10_synthesis_specificity | 3 | 3 | OK |
| meng2024_v190_run2 | T1 | 9 | 9 | OK |
| meng2024_v190_run2 | T3 | 3 | 3 | OK |
| meng2024_v190_run3 | T1 | 9 | 9 | OK |
| meng2024_v190_run3 | T3 | 5 | 5 | OK |
| yang2025_v190 | T2 ch01_no_fabrication | 3 | 3 | OK |
| chai2026_v190 | T6 ch01_basic | 4 | 4 | OK |
| ali2025_flash_v190 | T4 ch14_depth | 4 | 4 | OK |
| fu2020_v190 | T5 ch01_basic | 3 | 3 | OK |

**结论**：变体对比可放心引用历史 baseline 分数。

---

## §2 实验规模

- **3 变体**：A (env tuning) / B (cap tiering) / C (figure_ids hard constraint)
- **9 语料论文**：7 corpus (meng2024/yang2025/chai2026/ali2025_flash/gaur2022/he2023/pan2025) + 2 HIF (hif_1 Adv Mat ferroelectric survey 62 pages / hif_2 DALL-E 2 27 pages)
- **总跑数**：33 (每变体 7 generic + meng×3 + 2 HIF = 11)
- **总成本估算**：~$15-20 LLM (cost meter 未启用，按 chapter × token 估)

---

## §3 三变体 6 指标对比 (across all 33 runs + baselines)

### M1 字数 (mean per paper, accumulated 15 chapters)

| Paper | baseline | A | B | C |
|---|---|---|---|---|
| ali2025_flash | 12570 | 13431 | 14211 | **17096** |
| chai2026 | 11814 | 9584 | 11195 | 9967 |
| gaur2022 | 11060 | 11269 | 11700 | 10834 |
| he2023 | 12450 | 12261 | 11047 | **14218** |
| meng2024 | 12175 (mean 3) | 12468 (mean 3) | **12918** (mean 3) | 13026 (mean 3) |
| pan2025 | 12090 | 13787 | 13352 | 14032 |
| yang2025 | 11700 | 12860 | 13490 | 10769 |
| hif_1 | — | 8654 | 9473 | 10171 |
| hif_2 | — | 15178 | 13768 | 13209 |
| **avg** | 11979 | 12166 | 12350 | 12591 |

C 平均最高 (+4% vs baseline)，但论文间波动大。

### M2 图嵌入率（spec §7 核心成功标准 ≥30% 改善）

| Paper | available | baseline | A | B | **C** |
|---|---|---|---|---|---|
| ali2025_flash | 26 | 6 (23%) | 5 (19%) | 4 (15%) | **26 (100%)** |
| chai2026 | 2 | 2 (100%) | 2 | 0 | 2 |
| gaur2022 | 1 | 1 | 1 | 1 | 1 |
| he2023 | 8 | 6 (75%) | 4 | 7 | **8 (100%)** |
| meng2024 | 7 | 6 (86%) | 4 (57%) | 5 (71%) | **7 (100%)** |
| pan2025 | 4 | 4 | 1 | 4 | 4 |
| yang2025 | 5 | 5 | 2 | 5 | 5 |
| hif_1 | 20 | — | 2 (10%) | 4 (20%) | **20 (100%)** |
| hif_2 | 17 | — | 3 (18%) | 5 (29%) | **17 (100%)** |

**Variant C 在所有多图论文上达到真 100%**。这是 spec §7 "M2 提升 ≥30%" 目标的唯一达标变体。

> **M2 计数勘误**：cycle 1 (Auditor 1) 揭示 V0 metric 实现把 `<img>` 标签数（包括多面板的 panel）计为 figures，导致 baseline 14/7 这类 >100% 的虚假信号。v1.10 commit `2e3ca35` 修正为按 `<figure>` block 计数（一图一计），上表为修正后值。

### M3 post-verify required missing / required (mean across runs)

| Paper | A | B | C |
|---|---|---|---|
| ali2025_flash | 20/47 (43%) | 28/67 (42%) | 23/47 (49%) |
| chai2026 | 42/48 (88%) | 62/76 (82%) | 37/48 (77%) |
| gaur2022 | 32/68 (47%) | 63/96 (66%) | 42/68 (62%) |
| he2023 | 35/67 (52%) | 53/95 (56%) | 36/67 (54%) |
| meng2024 | 16/55 (29%) | 27/75 (36%) | 15/55 (27%) |
| hif_1 | 13/65 (20%) | 28/85 (33%) | 21/65 (32%) |
| hif_2 | 0/65 (0%) | 0/77 (0%) | 7/65 (11%) |
| pan2025 | 30/69 (43%) | 47/97 (48%) | 28/69 (41%) |
| yang2025 | 18/26 (69%) | 8/30 (27%) | 18/26 (69%) |

B 因 cap=12 调整 produced more required mentions but **没有改善覆盖率**（meng: A 71% vs B 64% covered; gaur: A 53% vs B 34%）。**Auditor 3 cycle 2 据此判断 cap=12 一刀切让 LLM 注意力分散**，反而坏事。

### M5 retry 触发数 (mean per paper, empty/short fires)

| Paper | A | B | C |
|---|---|---|---|
| ali2025_flash | 5.0/1.0 | 5.0/2.0 | 5.0/1.0 |
| chai2026 | 11.0/0.0 | 8.0/0.0 | 9.0/0.0 |
| gaur2022 | 4.0/1.0 | 8.0/1.0 | 11.0/0.0 |
| he2023 | 7.0/2.0 | 7.0/0.0 | 9.0/0.0 |
| meng2024 | 4.0/0.3 | 3.0/0.0 | 2.0/1.3 |
| hif_1 | 0.0/1.0 | 2.0/1.0 | 2.0/0.0 |
| hif_2 | 0.0/0.0 | 0.0/0.0 | 1.0/0.0 |
| pan2025 | 7.0/0.0 | 6.0/0.0 | 4.0/1.0 |
| yang2025 | 5.0/1.0 | 1.0/0.0 | 5.0/0.0 |

retry-when-empty 在每个变体每篇论文都频繁触发，是 load-bearing 安全网。

### M6 cost — 未实测 token 计数（v1.11 候选添加 LLM cost 计数器）

### M4 TestCase 评分（spec §7 zero-variance floor）

| TestCase | baseline | A | B | C |
|---|---|---|---|---|
| **meng2024 T1 ch01** | 9 / 9 / 9 (stdev **0**) | 5 / 9 / 9 (stdev 1.88) ⚠️ | 5 / 17 / 15 (stdev **5.25**) ❌ | **9 / 9 / 9 (stdev 0)** ✅ |
| meng2024 T3 ch10 | 3 / 3 / 5 | 4 / 5 / 4 | 5 / 4 / 4 | 4 / 4 / 4 |
| yang2025 T2 | 3 / 3 | 3 | 3 | 3 |
| chai2026 T6 | 4 / 4 | 3 | 3 | 4 |
| **ali2025_flash T4** | 4 / 3 | 4 | 3 | **5** 🏆 |
| fu2020 T5 | 3 / 3 | (not run) | (not run) | (not run) |

**Spec §7 zero-variance floor 唯有 C 通过**。Variant C is the only variant that preserves the meng2024 T1 = 9/9/9 zero-variance achievement of v1.9.x while improving ali2025_flash T4 from 4→5.

---

## §4 M1 zero-variance probe — meng2024 × 3 runs

| Variant | per run | mean | stdev | floor (≤ baseline=1503)? |
|---|---|---|---|---|
| baseline | 10117 / 12742 / 13666 | 12175 | **1503** | — |
| **A** | 12819 / 12065 / 12521 | 12468 | **310** ✨ | ✅ |
| B | 13740 / 13012 / 12002 | 12918 | 713 | ✅ |
| **C** | 12703 / 13525 / 12849 | 13026 | **358** ✨ | ✅ |

所有 3 变体均通过 M1 stdev floor（远低于 baseline 1503）。A 与 C 最稳。

---

## §5 figure_hallucinated 真相 (cycle 1 Auditor 2 + cycle 2 Auditor 1 共建)

`M2_figures_hallucinated_count` 标记 chapter md 引用了不在 `fig_notes.yaml` 中的 fig_id：

| Paper | A | B | C |
|---|---|---|---|
| meng2024 | 1.3 | 2.0 | 2.3 |
| chai2026 | 0 | 1 | 1 |
| gaur2022 | 0 | 3 | 2 |
| hif_2 | 1 | 1 | 3 |

**真正的根因（Auditor 1 cycle 2 发现）**：
- 这些"hallucinated" fig_id 都对应论文里**真实存在**的 figures
- 但 s04_figures 抽取时使用 **OCR detection 顺序编号**（1, 2, 3, ...），而非论文 caption 实际编号
- 例：ali2025_flash ch14 中 VC 引用"图10"，实际对应论文 **Fig. S5 (supplementary)**；"图23" 对应 **Fig. S18**
- LLM 从 source chunks 文本正确读到这些图（看到 "Fig. S5"），但 s04 给的 fig_id 编号不同 → s09 字面匹配失败 → silent drop

**这不是 Variant C 的过失，是 s04_figures 的设计缺陷**（v1.11 候选 #2）。

---

## §6 外部 reference 对照 (Task 16 + cycle 1+2 修正)

| 设计点 | STORM | OpenScholar | LitLLM | gpt-researcher | PaperQA2 | Onyx | A | B | **C** |
|---|---|---|---|---|---|---|---|---|---|
| informed-retry | — | ✓ | — | — | — | — | — | — | ✓ (figure-retry) |
| per-comparator drafting | ✓ | — | ✓ | — | — | — | — | ✓ (cap tier) | — |
| figure_ids 硬约束 | — | — | — | — | ✓ partial | — | — | — | ✓ |
| quote grounding | — | ✓ | — | — | ✓ | — | (existing) | (existing) | (existing) |
| outline-grouping | ✓ | — | — | — | — | — | — | — | — |
| 实施 citation HYPERLINK | — | — | — | — | — | ✓ HTML only | — | — | (HTML ✓ DOCX dead) |

**修正 Task 16**: "Onyx HYPERLINK 是 dead code" 仅 DOCX 准确，HTML 渲染器有独立 HYPERLINK 实现（功能正常）。

---

## §7 HIF 扩展验证小结 (spec §11.2)

| Paper | A M1 | A M2 | B M1 | B M2 | **C M1** | **C M2** |
|---|---|---|---|---|---|---|
| hif_1 (Adv Mat 综述 62 页) | 8654 | 2/20 | 9473 | 4/20 | 10171 | **20/20 (100%)** |
| hif_2 (DALL-E 2 ML, 17 figs) | 15178 | 3/17 | 13768 | 5/17 | 13209 | **17/17 (100%)** |

跨领域 (HIF-2 是 ML 论文) 上 variant C 的 figure_ids 硬约束依然产生真 100% 嵌入率。

注：HIF 使用了与原文领域不匹配的材料学模板（`Table of Contents-Relaxor AFE-ZGY-HW.docx`），导致章节标题与论文内容错位。这影响 M1 字数（HIF-1 偏低），但 M2/M3/M5 仍可用于变体间对比。
Auditor 1 cycle 1 观察到 3 种 failure 模式（VA 编造、VB 忽略模板、VC 强行并列），都属于"模板与原文主题不匹配时的降级策略缺失" — v1.11 candidate #4。

---

## §8 审计周期发现总结

### Cycle 1 (3 auditor)
- **Auditor 1**: VC ch01 质量 3.6/5 最高；所有变体 + baseline 都漏 Jiang/Ma comparator (prompt systemic gap)；HIF-1 模板-原文不匹配时三种 failure 模式
- **Auditor 2**: `normalize_ocr_latex` 4 盲区导致每 run 41-74 误拒；1 个真 hallucination (VC meng2024 Dielectric: 把 quote 翻译成中文)；"悬空图引用"实是 s04_figures 漏抽
- **Auditor 3**: VC critical bug — `figure_ids` advisory 跑在 rejected claim 上 (commit `2e30e1c` 已修)

### Cycle 2 (3 auditor)
- **Auditor 1 ext**: VC ali2025 ch14 引用"图10/23"实对应 Fig.S5/S18 (s04 OCR 编号 vs paper supplementary 编号错位)；VA 严重事实错 (PbZrO₃ 含铅却称"无铅")；VB 数值幻觉 (FHC 45 vs 真实 63.5 J/cm³)
- **Auditor 2 ext**: BS3 (`\%`) + BS4 (Unicode 上标) 是 normalize 的精确单行修法 (commit `1093c4f` 已加)；BS1+BS2 (letter-spaced 下标) 因不对称性推迟 v1.11
- **Auditor 3 ext**: figure-retry 缺 coverage 守护 (C-1) + min-accepted 守护 (C-2) (commit `0cc056d` 已修)；advisory 与 reject 共用同一 list 致 audit log 计数虚高 (commit `535d035` 已修)；最终决策 **SHIP A + C, HOLD B**

---

## §9 最终决策

### Ship Variant C

依据：
1. **唯一通过 spec §7 zero-variance floor** (meng2024 T1 = 9/9/9 stdev 0)
2. **M2 在所有多图论文真 100%**（ali2025 26/26, hif_1 20/20, hif_2 17/17, he2023 8/8, meng2024 7/7）
3. **M4 唯一突破 baseline** (ali2025 T4: 4 → 5)
4. **生成质量综合最高** (Auditor 1 cycle 1+2: 3.6/5 + 3.2/5)
5. **6 个 commits 在 `variant-c-figure-test` 分支**，含 4 个新功能 + 2 个 Auditor 修复
6. M1 stdev 358 — 跨变体第二低 (仅次 A 310)

### Skip / Defer

- **Variant A**：技术上零代码风险可 ship，但**质量得分最低 (Auditor 1 cycle 2 在 ali2025 ch14 上发现严重事实错: PbZrO₃ 含铅却称"无铅")**。env 调优本身有效（BEST_OF_N=3 + MIN_CHARS=1200 让内容更深），但无 figure_ids 约束导致 M2 接近 baseline 水平（5/26, 3/17 等）。Variant A 的 env 调优**可以作为 v1.10 ship 时的推荐默认**，但不需独立 variant 标签。
- **Variant B**：cap=12 一刀切**没有改善 M3 覆盖率**（meng: A 71% vs B 64%; gaur: A 53% vs B 34%），且 M1 stdev 713 最差，引入新方差。**不推荐 ship**。重设计方向：动态 cap = min(comparator_count, 10)。

### v1.10 Ship 内容

- 合并 `variant-c-figure-test` (6 commits) 到 main
- 合并 main 上独立 polish: normalize BS3+BS4 fix (`1093c4f`)
- 将 variant A 的 env 调优作为推荐默认写入 `.env.example` 注释（不改 code 默认值，避免 surprise）
- 标记 variant B branch 为 deferred，留作 v1.11 重设计入口

### v1.11 候选 (按 ROI 排序，per Auditor 3 cycle 2 + cycle 1)

| Rank | 项 | 修法 | 预估收益 | 复杂度 |
|---|---|---|---|---|
| 1 | normalize_ocr_latex BS1+BS2 (letter-spaced subscript) | OCR 侧 collapse 单字符空格 → 字母 + 数字间空格 | M3 missing% -5~10pp | M |
| 2 | s04_figures OCR-vs-actual 编号错位 | 改成解析 caption 中 "Fig. SN"/"Fig. N" 字面 | M2 hallucinated → 0 | M |
| 3 | prompt comparator gap (Jiang/Ma 等) | `build_required_mentions` 扫全文 paper.comparators 而非只 KG | 内容质量 +1 分/章 | M |
| 4 | 模板-原文主题不匹配降级策略 | 节内容前先 keyword-match 决定"按模板"或"按原文" | 跨领域生成可用度 | L |
| 5 | Variant B 动态 cap = min(comparator_count, 10) | 重设计 cap 算法 | M3 覆盖率改善 | S |
| 6 | LLM cost 实时计数器 (M6) | hook 进 llm.client; 写到 metrics.yaml | 实验 ROI 可视化 | S |
| 7 | DOCX HYPERLINK dead code 修复 | thread sources from runs/ 到 s09 renderers | 用户得真 hyperlink | M |
| 8 | _merge_drafts dedup 60 字 + (author,value) 锚点 | 已知 spec §11 | best-of-N 多样性 | S |
| 9 | 6 hardcode → env var | spec 已列 | 调优灵活性 | S |

---

## §10 风险 & 已知 limitation

- normalize BS3+BS4 修法已 ship 但**33 runs 是修法前数据**，预期实际收益（M3 missing% 下降）需 v1.10 之后真实跑验证
- s04_figures 编号错位导致 M2_hallucinated 计数虚高 — 但这是跨变体相同问题，不影响相对排名
- HIF 论文用了不匹配领域的模板，HIF M1 数据偏离主流
- M6 cost 未实测（设计已知）
