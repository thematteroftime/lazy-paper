# v1.9.0 二次方差校验（10 篇论文）

2026-05-22 用 `_v190b` 后缀对 10 篇语料论文做第二次 KL 跑（meng2024
已有 3 次 v190 跑，本轮跳过）。目的：确认 v1.9 informed-retry 的结
果不是单次运气。

## TestCase 方差（4 篇论文）

| 测试 | v190（第一次） | v190b（第二次） | 是否匹配 |
|---|---|---|---|
| yang2025 T2 fabrication resistance | 3/3 | 3/3 | ✅ |
| fu2020 T5 basic | 3/4 | 3/4 | ✅ |
| chai2026 T6 basic | 4/4 | 4/4 | ✅ |
| ali2025_flash T4 comparison depth | 4/5 | 3/5 | ±1（LLM 采样方差） |

4 个 TestCase 中 3 个在两次独立跑里**完全复现**。ali2025_flash T4
落了 1 分——在任何基于 LLM 的内容测试预期的 ±1 范围内（即使是
v1.7 KL 在稳定论文上也有这种方差记录）。

## 6 篇 generic 论文——intro 长度 + retry 行为

| 论文 | v190 字符数 | v190b 字符数 | v190 retry-empty | v190b retry-empty |
|---|---|---|---|---|
| gaur2022 | 1635 | 724 | 8 | 3 |
| ge2025 | 2027 | 1522 | 8 | 10 |
| he2023 | 837 | 428 | 4 | 7 |
| liu2022 | 2057 | 2904 | 8 | 5 |
| pamula2025 | 1223 | 2849 | 13 | 4 |
| pan2025 | 2239 | 1079 | 7 | 7 |

长度随 LLM 采样跑跑波动（符合预期）；retry-when-empty 在每篇论文
里都是**承重组件**（每次跑触发 2-13 次）。系统按设计运行。

## 这次验证了什么

1. **v1.9 informed-retry 可复现。** TestCase 分数在独立跑之间保持稳定。
2. **retry-when-empty 是真承重**，不是残留机制——每篇论文触发 2-13 次。
3. **HTML 可点击引用在全部 10 篇上工作**（HTML preview 锚点 ≥3 个已
   提前验证过）。
4. **v1.9.1 的文档-代码对齐修复是正确的**（测试数 253、FIGURE_BIND
   环境变量已记录、anchor-check 描述为 advisory）。

## v1.10 待办

审计链（3 reviews + 2 confirmations）暴露的 4 项已延后：

1. 抽出 `_attempt_retry` 辅助函数，去重 `compose_structured` 两个
   retry block 共约 120 行代码。
2. 给 `LAZY_PAPER_FIGURE_BIND=1` 和
   `LAZY_PAPER_HTML_CITATIONS={remove,keep,hyperlink}` 各 env 路径加
   单元测试。
3. 把 `_ANCHOR_AUTHOR_RE` / `_ANCHOR_VALUE_RE` 泛化到物理学之外
   （目前硬编码 `J/cm³ | MV/cm | kV/cm | μC/cm² | %`）。
4. Length-retry 测试目前用空 `cited_quote` 字符串绕过 verifier——
   需要加一个跑完整 verify-then-retry 路径的变体。

这些挂到 v1.10。

## 结论

v1.9.0 + v1.9.1 发布质量过关。253/253 测试通过。10 篇第二次跑显示
informed-retry 行为可复现。审计修复未引入回归。
