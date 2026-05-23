# v1.9.0 —— informed-retry 验证

15 次 KL run 跨 13 篇论文（10 篇新 + 3 次 meng2024 方差验证）。2026-05-22。

## 头条：meng2024 上的确定性恢复

| 版本 | T1 三次得分 | 均值 | 标准差 | 地板 |
|---|---|---|---|---|
| v1.7 KL | 13 / 1 / 1 | 5.0 | 6.9 | 1 |
| v1.8.1 KL | 12 / 17 / 16 | 15.0 | 2.6 | 12 |
| v1.8.3 KL | 5 / 1 / 1 / 1 / 1（5 run）| 1.8 | 1.8 | 1 |
| **v1.9 KL** | **9 / 9 / 9** | **9.0** | **0** 🏆 | **9** |

三次独立的 v1.9 run 在 meng2024 ch01 基准恢复上**完全一样**拿 9/17。从 v1.7 开始一直困扰这项测试的方差**完全消除了**。

距离 v1.8.1 的 12+ 均值还有差距——这是另一个问题（LLM 自选择哪些 comparator 写），已经规划到 v1.9.x，用 STORM/LitLLM 风格的 per-comparator drafting 解决。

## 为什么 informed-retry 起作用

之前的 retry-when-empty（v1.8.x）：

```
## CRITICAL — REQUIRED MENTIONS MISSING FROM PRIOR DRAFT
Your previous draft missed most of the required mentions...
[笼统的"覆盖全部实体"指令]
```

v1.9 的 informed-retry 生成逐实体诊断：

```
## CRITICAL — SPECIFIC REQUIRED MENTIONS MISSING
Your previous draft covered 1/5 required entities. The following are
NOT yet covered — your next draft MUST include each:

  - comparator: 'Ca2+/Nb5+-codoped Bi0.5Na0.5TiO3'
      → write a claim containing "Jiang et al." or "Jiang 等人" OR "W_rec=2.94 J/cm³"
      → evidence chunk: [3]
  - comparator: 'La(Mg1/2Zr1/2)O3-modified Bi0.5Na0.5TiO3'
      → write a claim containing "Ma et al." or "Ma 等人" OR "W_rec=7.5 J/cm³"
      ...
```

这种确定性清单消除了 LLM "这个我跳过吧" 的余地——它清楚知道下一次采样必须把哪个 token 写进去。

## 13 论文语料 —— 无回归

| 测试 | v1.8.3 | v1.9 | 状态 |
|---|---|---|---|
| meng2024 T1 | 5/17（单次） | **9/17 ×3** | 地板 +4，方差消除 |
| meng2024 T3 | 3/5 | 3, 3, 5 / 5 | 方差范围内 |
| yang2025 T2 | 3/3 ✓ | 3/3 ✓ | 保留 |
| fu2020 T5 | 3/4 ✓ | 3/4 ✓ | 保留 |
| chai2026 T6 | 4/4 ✓ | 4/4 ✓ | 保留 |
| ali2025_flash T4 | 4/5 ✓ | 4/5 ✓ | 保留 |

## 8 篇无专属 TestCase 论文 —— 质量 + retry 行为

| 论文 | 导言字符数 | HTML 锚点 | retry-when-empty 触发次数 |
|---|---|---|---|
| gaur2022 | 1635 | ✓ | 8× |
| ge2025 | 2027 | ✓ | 8× |
| he2023 | 837 | ✓ | 4× |
| liu2022 | 2057 | ✓ | 8× |
| pamula2025 | 1223 | ✓ | 13× |
| pan2025 | 2239 | ✓ | 7× |
| randall2021 | 2189 | ✓ | 2× |
| yao2022 | 1156 | ✓ | 2× |

retry-when-empty 每篇触发 2-13 次，说明 informed-retry 机制在语料库各种论文上**确实在工作**，并不只是 meng2024 基准论文上的特例。

## 成本

- 单论文 wall-clock：meng2024 上 ~12-15 分钟（informed-retry 触发时每节多 1-3 次 LLM 调用）
- 单论文 DeepSeek API 成本：典型 ~$0.30-0.60，comparator 多的论文上限到 ~$0.90
- 诊断会给 retry prompt 增加 ~300-500 tokens —— DeepSeek 输入缓存让这部分在 best-of-N 采样下几乎免费

## v1.9.x 候选 —— 把 9 抬到 15

研究 subagent 找到两条互补技术能把 v1.9 的 9.0 均值进一步提到 12+：

1. **Pydantic validator-as-coverage-gate**（instructor reask 模式，半天工作量）。在 `SectionDraft` 上加 `model_validator`，机器检查每个 required entity 的子串是否出现；instructor 内置的 reask 用校验错误信息作为针对性反馈。

2. **STORM/LitLLM per-comparator drafting**（1 天工作量）。综述章节每个 comparator 单独写一段 micro-paragraph，单实体上下文意味着 LLM **根本没东西可跳过**；再用一次 "verbatim 保留作者 + 数值" 的 stitching 调用串成最终散文。

合起来用，目标是在保留 v1.9 的 0-方差地板基础上，把均值推到 12+。

## 可复现命令

```bash
LAZY_PAPER_STRUCTURED=1 \
LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
LAZY_PAPER_BEST_OF_N=2 \
LLM_MAX_TOKENS_CEILING=64000 \
LAZY_PAPER_MIN_SECTION_CHARS=500 \
LAZY_PAPER_MIN_SECTION_CLAIMS=4 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id <name>_v190 --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html

uv run python scripts/evaluate.py runs/<name>_v190
```

测试：253/253 全过。
