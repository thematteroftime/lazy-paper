# Golden QA Schema

每个文件对应一篇 demo paper。RAGAS faithfulness / context_recall / context_precision 用这些题打分。

## YAML 结构

```yaml
paper_id: meng2024_v111_demo        # 必须匹配 runs/ 子目录名
source_pdf: input/papers/meng2024.pdf
items:
  - id: q01
    question: |
      0.85NBST-0.15BMZ 在 340 kV/cm 下的 W_rec 是多少？
    ground_truth: |
      W_rec = 5.00 J/cm³（在 340 kV/cm 下，效率 90.09%）
    expected_chunks:        # 用于 context_recall — 答案应来自哪些 chunk
      - chapter_005_RESULTS_AND_DISCUSSION.md
      # 可选：附加 char range, 用于精度调试
      - chapter_005_RESULTS_AND_DISCUSSION.md:8000-8400
    tags: [headline_metric, results]
```

## 题目选择原则

- 80% 客观可验证（数值、化学式、机制名）
- 20% 论断性（结论、比较）
- 至少 3 题考验"跨章节一致性"（同一 fact 在不同章节出现）
- 至少 3 题考验"figure ID 正确性"（答案需引用 Fig. N）
- 至少 3 题考验"作者归属正确性"（答案应说 "X et al. report …" 而不应张冠李戴）

## Ground-truth 写入纪律

- 每个 `ground_truth` 字段必须从源 PDF 或 `runs/<paper>/s03_chapter/chapters/` 的 chapter md 验证后再写；**不准凭记忆/凭推断**。
- 数值答案用论文原始形式（含单位、含 ± 误差、含图引）。LaTeX 公式保留 `$` 包裹。
- 若一个 fact 在多个 chapter 出现，`expected_chunks` 列全部 — 用于 RAGAS context_recall。
- 若 fact 跨章节有歧义（如 v1.11.1 修过的 cross-chapter drift），**优先选 introduction 或 abstract 里的版本**作为 ground_truth，并在 tags 加 `cross_chapter`。
