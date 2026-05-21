# 质量测试框架（v1.7+）

为 lazy-paper 章节作者策略提供可复现的评测脚手架。替代 v1.5 / v1.6 实验期那些临时的 grep 比对，覆盖**生成质量**、**引用正确性**、**缺陷抗性**三个维度的显式可脚本化指标。

## 为什么需要它

每次策略迭代（E / G / H / I / J / K / L / KL）都需要在同一把尺子下相互比较。人眼跨多个变体扫章节噪声很大；要做出有信心的"上 / 不上"决定，唯一靠谱的方法是固定一套带显式打分规则的测试。这就是那一套。

## 快速开始

```bash
# 给所有近期 v1.6 / v1.7 / v1.8 run 打分
uv run python scripts/evaluate.py --all-recent

# 指定 run
uv run python scripts/evaluate.py runs/meng2024_v181_KL_run1 runs/yang2025_v181_KL

# 程序化使用：stdout 是结构化 JSON，stderr 是 Markdown 表格
uv run python scripts/evaluate.py runs/meng2024_v181_KL_run1 2>/tmp/table.md > /tmp/report.json
```

输出形态：
- **stdout**：每个目录一条 `{run, paper_id, results: [...]}` 的 JSON 列表
- **stderr**：一行一 run 的 Markdown 表，便于扫读

## 测试用例

测试用例以 `TestCase` 实例的形式定义在 `scripts/evaluate.py`，每条绑定 `(paper_id, section, scoring rules)`。当前已上线的几条：

### T1. meng2024 ch01 —— 文献基准恢复（满分 17）

这是最原始的头号缺陷。论文引用了 4 个文献体系（Jiang / Ma / Zhang / Tang 等人），每条都附带具体 `W_rec` 和 `η`。每恢复一个模式得 1 分：

- **作者**（4 项）：`Jiang|Ma|Zhang|Tang 等?|et al.`
- **数值**（8 项）：`2.94 | 7.5 J | 8.58 | 8.3 J | 91.04 | 90.5 | 94.5 | 80%`
- **化学式**（4 项）：`Ca²⁺/Nb⁵⁺ | La(Mg | K₀.₁ | 0.8Bi`
- **语言**（1 项）：`--lang zh` 时中文字符占比 ≥ 30%

满分 17。v1.3.3 基线（整篇上下文塞入）约能拿 12-13；v1.4.x 默认拿 0；**v1.8.1 KL 当前 3 次重测分数为 12 / 17 / 16（均值 15，下限 12）**。每个策略都按此打分。

### T2. yang2025 ch01 —— 不编造数据（满分 3）

这篇论文做的是神经形态计算，全文 0 处储能测量。早期策略会从模板先验里幻觉出 `W_rec=8.6 J/cm³ at η=85%`。打分规则：

- **禁止模式**（不得命中）：`8.6 J/cm`、`η=85`、`Wrec=`
- **应在模式**（必须命中）：提及 CBPS 或突触可塑性
- **语言**（1 项）：中文字符占比 ≥ 30%

禁止模式命中**不直接扣分**，而是抛 `flag`——出现任何 flag 就视为此用例失败。

### T3. meng2024 ch10 —— 合成法专属性（满分 5）

v1.4.x 默认会写"未提及合成方法；推测为固相法"，即便论文明文写了 `tape-casting` 并附带晶粒尺寸测量。打分：

- **方法**（2 项）：`tape-casting | 流延`
- **晶粒数据**（2 项）：`μm` 测量值 + 烧绿石（pyrochlore）提及
- **最小篇幅**（1 项）：章节 ≥ 500 字符

### T4. ali2025_flash ch14 —— 比较章深度（满分 5）

v1.4.x 这里只产出 688 字节的占位文。打分：

- **量化锚点**（4 项）：至少命中 4 个 `{ X K, X %, X °C, X kV }`
- **最小篇幅**（1 项）：章节 ≥ 1000 字符

### T5 / T6. fu2020 / chai2026 ch01 —— 基础通用（各满分 4）

通用泛化测试，验证策略不会破坏正常论文的基础质量。

## 引用正确性（Strategy J 系列自动打分）

只要 run 写了 `s08_section_compose/*.structured.json`，harness 会另外计算每节的引用可靠性：

```json
"citation_accuracy": {
  "total_claims": 9,
  "claims_with_quote": 9,
  "verified_quotes": 7,
  "verified_ratio": 0.78,
  "fabricated_quote_count": 2,
  "fabricated_sample": [{"quote": "...", "cited_chunk_ids": [11]}]
}
```

**校验规则**：每个 `GroundedClaim.cited_quote` 要么是其声明 chunk 的精确子串，要么最长连续匹配覆盖度 ≥ 0.85（与 `structured.py::verify_section_draft` 一致）。比对前会对源文本做 OCR 数字间空格 + LaTeX 转义的规范化——`2.94 J/cm³` 能匹配上 `$2 . 9 4 \mathrm{J/cm}^{3}$`。

`verified_ratio` 低于 0.7 通常说明 LLM 在转述而不是抄写——是诊断信号，不直接影响 TestCase 分。

## 策略对比记分牌

### meng2024 ch01（T1）

| 策略 | 分数 / 17 | 说明 |
|---|---|---|
| v1.3.3 基线（整篇上下文） | ~12 | 真值参考——完全不做检索 |
| v1.4.2 默认 | 0 | 0 个对比体恢复 |
| v1.5 E（事后 critic） | 6（均值 4.5） | KG 命中时 critic 会回补 |
| v1.6 J（前注入） | 9 | Schema 约束的引用 |
| v1.7 K（best-of-N=2，v2 KG） | 1 | LLM 缺少作者时回避光秃秃的化学式 |
| v1.7 L（KG-v3 author 实体） | 9 | 作者归属抬高了引用 |
| v1.7 KL（KG-v3 + best-of-N=2） | 13（3 次：13 / 1 / 1，均值 5） | 单次峰值高，但方差大 |
| **v1.8.1 KL（修了 verifier + retry）** | **12 / 17 / 16（均值 15，下限 12）** 🏆 | 稳定性问题已修复 |

### 其他测试项

| 策略 | yang2025 (T2) | meng2024 ch10 (T3) | ali2025_flash (T4) | fu2020 (T5) | chai2026 (T6) |
|---|---|---|---|---|---|
| v1.7 KL | 3/3 ✓ | 2/5 ⚠ | 4/5 | 3/4 | 4/4 ✓ |
| **v1.8.1+ KL** | 3/3 ✓ | 5/3/2 | 0/5 ⚠（采样方差） | 3/4 | 4/4 ✓ |

`ali2025_flash` T4 在 v1.8.1 单次跑出 0/5，原因是 LLM 采样恰好只产出 3 个 claim（v1.7 KL 同一论文出过 8 个）。这是 LLM 采样方差而非回归——详见 `docs/v1_8_2_corpus_validation.md`。

## 新增测试用例

```python
# 追加到 scripts/evaluate.py 的 TESTS 列表

TestCase(
    name="paper_id:short_label",
    paper_id="paper_id",        # 基础论文 ID，不带版本后缀
    section="01-Introduction",  # 精确的章节文件前缀
    required={
        "category": [r"regex1", r"regex2"],
    },
    forbidden=[r"do-not-write-this"],
    min_chars=500,
    lang_zh_min_ratio=0.30,
),
```

Harness 会自动从 run 目录名里剥离 `_v\d+_*` 后缀来识别它对应哪篇论文。每个 TestCase 只为 `paper_id` 匹配的 run 打分。

## 可复现性

- DeepSeek-Reasoner 采样非确定性（默认 temperature=0.2；best-of-N=2 时为 0.2/0.4 交替）。
- 单次 run 在 T1 上有约 ±2 分方差。**宣布"某策略胜过基线"前，至少跑 2-3 次取均值。**
- best-of-N（Strategy K）天然降方差——一次 dispatch 内做多次采样再合并，结果在不同 re-run 之间更稳。

## 局限 + 故意没做的部分

这套 harness 是**正则模式 + 结构性**的。它**不衡量**：

- 命名模式之外的语义正确性
- 跨章节连贯性（需要单独的跨节打分器）
- 读者主观感受的行文质量
- 章节叙事逻辑

这几个轴每个 release 仍需对 1-2 篇论文做人工评审。Harness 是回归防护底线，不是质量天花板。

## 上线新策略的推荐流程

1. env-gate 实现新策略（不改默认行为）
2. 在 meng2024 上跑 T1+T3，确认对基线无回归
3. 在 yang2025 上跑 T2，确认没引入新幻觉
4. 在 ali2025_flash 上跑 T4，确认综述章节深度
5. `uv run python scripts/evaluate.py --all-recent` 对比所有候选
6. 若 T1 抬升 且 T2/T3/T4 持平：作为 opt-in env var 发布
7. 若 T1 抬升 且 T2/T3/T4 在每个策略每篇论文 3 次连续 run 都持平：升为默认

这套纪律产出了 v1.4.2（4 路对比挑出 Strategy C 作默认）、v1.6.0（方差分析后把 Strategy J 作 opt-in）、v1.8.1（修了 KL 的稳定性 bug 后把 KL 升为推荐默认）。后续版本沿用同样的循环。
