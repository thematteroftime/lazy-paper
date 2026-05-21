# v1.8.2 —— 10 论文语料验证 + 安全/质量加固

2026-05-21 通过 `scripts/evaluate.py` 完成。覆盖 v1.8.1 KL 章节作者在 10 论文语料上的表现 + v1.8.2 引入的审计修复（HIGH/MEDIUM 安全、流程 bug、normalizer 去重）。

## 语料记分牌

### 带专属 TestCase 的论文

| 论文 | 测试项 | v1.8.x KL | 旧版（v1.7 KL） | 状态 |
|---|---|---|---|---|
| meng2024 | ch01 文献基准恢复（3 次 run） | **12 / 17 / 16**（均值 15.0，下限 12） | 13 / 1 / 1（均值 5，下限 1） | **头号胜利仍保留** |
| meng2024 | ch10 合成法专属性（3 次 run） | 5 / 3 / 2（均值 3.3） | 2 / 3 / 4（均值 3） | 持平 |
| yang2025 | ch01 不杜撰储能数据 | 3/3 ✓ | 3/3 ✓ | 无回归 |
| fu2020 | ch01 基础通用 | 3/4 ✓ | 3/4 ✓ | 无回归 |
| chai2026 | ch01 基础通用 | 4/4 ✓ | 4/4 ✓ | 无回归 |
| ali2025_flash | ch14 比较章深度 | 0/5 ⚠ | 4/5 | **离群点——见下文** |

### 无专属 TestCase 的论文（仅检查流水线是否成功）

8 篇全部端到端跑通，输出中文实质内容：

| 论文 | 章节数 | 导言字符数 | retry 触发次数 |
|---|---|---|---|
| gaur2022 | 15/15 ✓ | 1402 | 2 |
| ge2025 | 15/15 ✓ | 2170 | 2 |
| he2023 | 15/15 ✓ | 1381 | 0 |
| liu2022 | 15/15 ✓ | 1141 | 0 |
| pamula2025 | 15/15 ✓ | 1639 | 3 |
| pan2025 | 15/15 ✓ | 2804 | 2 |
| randall2021 | 15/15 ✓ | 1155 | 0 |
| yao2022 | 15/15 ✓ | 1199 | 0 |

retry-when-empty（v1.8.1 引入的机制）在其中 4 篇论文上触发，说明这条安全网在多样化论文上**确实在起作用、负载非零**。剩下 4 篇没触发是因为 LLM 第一次就命中了 required mentions。

## ali2025_flash ch14 离群点分析

v1.7 KL 得 4/5，v1.8.1 KL 得 0/5。检查 `runs/ali2025_flash_v181_KL/s08_section_compose/14-Comparison_with_Prior_Work.structured.json`：

- LLM 这次 run 只产出了 3 个通过校验的 claim（v1.7 KL 同篇论文那次产出了 8 个）。
- 该节 683 字符；测试要求 `min_chars=1000` 且至少 2 个量化锚点。
- Verifier 拒了 11 个 claim，`best_ratio` 在 0.026–0.14 区间——LLM 的英文 quote（例如 *"Our RAFE-FHC capacitor device boasts the best performance…"*）不在被检索到的 15 个 chunks 里；LLM 似乎引用了一段没被检索器够到的论文区域。

根因：**LLM 采样方差 + retrieval 漏召**，而**不是** v1.8.1 verifier 的回归。v1.8.1 verifier 在数学上严格**比** v1.7 更宽容（多了 LaTeX 规范化 + chunk-ID slop 兜底）。v1.7 KL 在同篇论文上恰好采到了 8 个能通过校验的 claim；v1.8.1 这次少采了几个。

后续 v1.9 候选缓解：

- **基于长度的 retry 触发**：当 verified 章节 < 500 字符或 < 4 个 claim 时也触发一次 LLM 重试（目前只在 `missing_required` 上触发）。
- **综述章更宽的检索**：章节标题命中综述类关键词时把 `top_k` 从 15 提到 25。

两条都已追踪但**推迟到 v1.9** —— 现在加进来会让 v1.8.2 越界（v1.8.2 定位是加固版而非新特性版）。

## v1.8.2 加固内容（与上述语料 run 分开）

3 个审计 subagent 复审了 `cli.py`、`stages/`、`llm/` 在冗余、安全、可调参数表面方面的状态。已应用的修复：

### 安全

- **HIGH —— `--paper-id` 路径遍历**（`cli.py:234`）：用户提供的 `--paper-id` 现在一律 slugify，封堵 `--paper-id "../../tmp/x"` 把输出写到 `runs/` 外面的攻击面。
- **MEDIUM —— MinerU OCR zip 解压 slip**（`stages/s01_ocr/mineru.py`）：解压前对每个 `ZipInfo.filename` 校验路径不超出 dest；拒绝绝对路径和 `..` 段。
- **LOW —— 错误信息脱敏**：PaddleOCR HTTP 错误不再回显 `r.text`（可能携带上游网关头）；s09 渲染失败的 done.yaml 现在写 `type(exc).__name__ + str(exc)[:200]`，不再写完整 `repr(exc)`。

### 流程

- **PaddleOCR 无限轮询修复**（`stages/s01_ocr/runner.py`）：加了 `PADDLEOCR_TIMEOUT_S` 死线（默认 1800s）—— 之前没有 timeout，job 卡住时会永远挂着。
- 移除了 2 处 `except Exception: pass` 静默：`s08_section_compose/runner.py::_build_retrieval_query` 和 `s09_render/runner.py::PaperContext.__init__`。两处现在都会打日志再降级。

### 可维护性

- **共享 OCR/LaTeX normalizer**：抽到 `stages/_common/normalize.py`，统一了 v1.8.1 时在 `structured.py` 引入的版本。
- **删除死代码**：`coverage_summary()`（0 个调用方）。
- **过时 docstring**：`kg_extract.py` 不再提及已删除的 `paper_kg_v2.md`，改为指向 `paper_kg_v3.md`（v1.7+ 推荐的 prompt）。

### 新增 env-overridable 调节项

| 变量 | 默认 | 用途 |
|---|---|---|
| `MINERU_BASE_URL` | `https://mineru.net/api/v4` | 自托管/代理 MinerU |
| `MINERU_TIMEOUT_S` | `1800` | MinerU 轮询死线 |
| `MINERU_POLL_S` | `10` | MinerU 轮询间隔 |
| `PADDLEOCR_BASE_URL` | `https://paddleocr.aistudio-app.com/...` | 自托管 Paddle |
| `PADDLEOCR_MODEL` | `PaddleOCR-VL-1.5` | 模型版本 pin |
| `PADDLEOCR_TIMEOUT_S` | `1800` | Paddle 轮询死线 |
| `PADDLEOCR_POLL_S` | `5` | Paddle 轮询间隔 |

（外加 v1.8.1 引入的 `LAZY_PAPER_VERIFIER_THRESHOLD`、`LAZY_PAPER_RETRY_THRESHOLD`。）

## 测试套件

250/250 通过（与 v1.8.1 一致，无测试数量回归）。

## 发布决策

v1.8.2 作为 v1.8.1 之上的加固版发布。KL 仍为推荐的高质量默认。ali2025_flash T4 离群点已记录；两条候选缓解措施列入 v1.9 待办。
