# 中文文档索引

这里是 `docs/` 下英文文档的中文翻译。代码、文件路径、CLI 参数、env-var 名、英文技术术语（Strategy KL、KG、RAG、instructor、MinerU 等）保留英文以便对照源码。

> **当前版本**：v1.11.1（2026-05-24）· 300 个测试通过 · v1.10 Variant C + v1.11 first-principles refactor + v1.11.1 4-bug-fix。详见 `INTERNAL/HANDOFF.md`。

## 用户文档

| 文档 | 说明 |
|---|---|
| [USER_GUIDE.md](./USER_GUIDE.md) | 用户使用指南 —— 安装、上手、调优、排障 |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 如何为项目贡献代码 |
| [TEST_FRAMEWORK.md](./TEST_FRAMEWORK.md) | 质量测试框架与评测 harness |

## 工程文档

| 文档 | 说明 |
|---|---|
| [ARCHITECTURE.md](../docs/ARCHITECTURE.md) | 系统架构（已经是简体中文，权威版本在 `docs/` 下，单一来源） |
| [AGENT_GUIDE.md](./AGENT_GUIDE.md) | 给 AI agent（Claude Code / Cursor / Copilot）维护本项目时的指南 |
| [INTERNAL/HANDOFF.md](./INTERNAL/HANDOFF.md) | 生产交接 —— env vars、当前状态、上手 checklist |

## 历史验证报告

历史版本（v1.7 – v1.9.2）验证报告归档在 [`archive/`](./archive/) 子目录：

- `v1_7_validation_results.md`
- `v1_8_validation_results.md`、`v1_8_2_corpus_validation.md`
- `v1_9_validation_results.md`、`v1_9_1_variance_check.md`、`v1_9_2_20_paper_validation.md`

当前 v1.10 / v1.11 验证状态见 [`../docs/v1_10_variant_comparison.md`](../docs/v1_10_variant_comparison.md)（英文）以及 [`INTERNAL/HANDOFF.md`](./INTERNAL/HANDOFF.md) 的状态 banner。

## 仍为英文的文档

以下保留在 `../docs/` 下、未翻译：

- `v1_10_external_reference.md`、`v1_10_variant_comparison.md` —— v1.10 ship-time 的外部参考与 variant 决策报告
- `archive/v1_4_*` / `v1_5_*` / `v1_6_*` —— 历史设计与实验文档
- `superpowers/`、`INTERNAL/superpowers/` —— Claude Code 工作流相关
- `CHANGELOG.md` —— 项目根目录的 changelog（结构化 release notes）

如果你需要其中任何一篇的中文版，提 issue 即可。

## 相关链接

- [项目主 README（中文）](../README.zh.md)
- [项目主 README（英文）](../README.md)
- [CHANGELOG.md](../CHANGELOG.md)
- [GitHub releases](https://github.com/thematteroftime/lazy-paper/releases)
