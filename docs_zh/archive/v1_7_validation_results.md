# v1.7.0 KL 策略 —— 验证结果（历史）

> **注**：v1.7 KL 的方差问题（地板 1/17）已经在 v1.8.1 中解决。当前推荐的策略和地板/均值数据请看 [`v1_8_validation_results.md`](./v1_8_validation_results.md) 和 [`v1_8_2_corpus_validation.md`](./v1_8_2_corpus_validation.md)。此页保留为历史记录。

2026-05-21 通过 v1.7 可脚本化 harness（`scripts/evaluate.py` + `docs/TEST_FRAMEWORK.md`）跑出。5 篇论文上共 7 次 KL run；与 meng2024 上 3 次旧 J run 对比。

## 记分牌

### T1 —— meng2024 ch01 基准恢复（满分 17）

| Run | KL 分数 | J 分数 |
|---|---|---|
| run 1 | **13** 🏆 | 8 |
| run 2 | 1 | 6 |
| run 3 | 1 | 5 |
| **均值** | **5.0** | **6.3** |
| **标准差** | **6.9** | **1.5** |
| **范围** | **1 – 13** | **5 – 8** |

**KL 峰值更高但均值更低、方差更大。** 架构本身**能**恢复 17 中的 13 个模式（匹配 v1.3.3 全上下文塞入基线的 ≈12），但 3 次采样里有 2 次 LLM 忽略了预注入的 required-mentions 列表，写出了没有任何文献引用的通用导言。best-of-N=2 的两个子 run 都收敛到了相似的通用内容，merge 步骤拿不到多样化的素材去合并。

诊断：run3 的 KG-v3 抽取是完美的（4 个作者 + 4 个 comparator + 4 个 cited_by_paper 关系）。失败完全发生在 compose 侧 —— LLM 采样自由度问题。

### T2-T6 —— 其他论文上的单次得分

| 测试项 | 分数 | 说明 |
|---|---|---|
| T2 yang2025 ch01 不杜撰 | 3/3 ✓ | 保留 v1.4.1 修复 |
| T3 meng2024 ch10 合成法 | run1 2/5 ⚠、run2 3/5、run3 4/5 | 与 T1 反相关 —— KL 在 intro 上 "all-in 对比体" 时，会忽略合成深度 |
| T4 ali2025_flash ch14 深度 | 4/5 | 与 J 相同 |
| T5 fu2020 ch01 基础 | 3/4 | 切题；自然提到了 "Ma 等人" 的源引用 |
| T6 chai2026 ch01 基础 | 4/4 ✓ | 干净 |

## 发布决策（v1.7 当时的决定）

**不要**把 KL 作为默认。J 仍是 v1.7 的更好默认，因为：

1. **J 的均值更高**（T1 上 6.3 vs 5.0）。
2. **J 的下限高得多**（5 vs 1）。
3. **两者在 T2-T6 上等效通过**。
4. **KL 的峰值（13）无法稳定复现**。

KL 作为 opt-in（`LAZY_PAPER_BEST_OF_N=2 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md`）保留，让愿意为偶尔的 13/17 输出掷骰子的用户使用，前提是接受 3 次里有 2 次接近 0 分。

> 这条决定在 v1.8.1 翻案了 —— 经修复后 KL 地板抬到 12，均值 15，反过来变成推荐默认。

## v1.8 候选 —— 解决 KL 的下限问题

架构是对的（run1 的 13/17 证明了这点）。下限问题完全是 LLM 采样。3 个候选按收益排序：

1. **Retry-when-empty**（最低成本、最大影响）：KL 的 merge 之后，若 required-mentions 列表里 0 个 comparator 被引用，则再发一次 LLM 调用，带强化版 "MUST cite" 指令。预计能把均值从 5.0 提到 9+。

2. **更强的预注入 prompt**：当前 "you MUST cover each" 指令太温和。考虑加 "Output will be rejected if any required entity is absent" + Pydantic 层的 required-entity 覆盖率校验。

3. **best-of-N 提到 3 + 拉大温度区间**：用 0.2 / 0.4 / 0.6 取代 0.2 / 0.35。更宽的采样应产出更多样化的 draft 供合并。成本：当前的 1.5×。

(2) 最原则化；(1) 最务实，作为 v1.8 选项。

> 实际 v1.8.1 上的选择：(1) + (2) 的混合 —— 实现了 retry-when-empty，且在 verifier 测得 LaTeX 形式 mismatch 也予以接受，让 retry 在更合理的覆盖率门槛上触发。

## 成本说明

- 每次 meng2024 KL run：约 12 分钟挂壁时间（best-of-N=2 让 s08 的 LLM 时间翻倍；s06 KG-v3 相比 v2 多 ≈1 min）。
- 这次验证总耗时：4 runs × ≈12 min = ≈48 min；DeepSeek API 花费约 $3–5。

## 测试 harness

可复现命令：

```bash
LAZY_PAPER_STRUCTURED=1 LAZY_PAPER_KG_PROMPT=paper_kg_v3.md \
  LAZY_PAPER_BEST_OF_N=2 \
  uv run python -m cli run --pdf <pdf> --template <tpl> \
  --paper-id <name>_v170_KL --lang zh \
  --only s06_context,s08_section_compose,s09_render --force \
  --formats docx,html

uv run python scripts/evaluate.py runs/<name>_v170_KL
```
