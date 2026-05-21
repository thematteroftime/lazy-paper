# 中文文档索引

这里是 `docs/` 下英文文档的中文翻译。代码、文件路径、CLI 参数、env-var 名、英文技术术语（Strategy KL、KG、RAG、instructor、MinerU 等）保留英文以便对照源码。

## 用户文档

| 文档 | 说明 |
|---|---|
| [USER_GUIDE.md](./USER_GUIDE.md) | 用户使用指南 —— 安装、上手、调优、排障 |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 如何为项目贡献代码 |
| [TEST_FRAMEWORK.md](./TEST_FRAMEWORK.md) | 质量测试框架与评测 harness |

## 工程文档

| 文档 | 说明 |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统架构 —— 9 阶段流水线 + Strategy KL 详解 + 数据流图 |
| [AGENT_GUIDE.md](./AGENT_GUIDE.md) | 给 AI agent（Claude Code / Cursor / Copilot）维护本项目时的指南 |
| [INTERNAL/HANDOFF.md](./INTERNAL/HANDOFF.md) | 生产交接 —— env vars、当前状态、上手 checklist |

## 验证报告（按版本倒序）

| 文档 | 说明 |
|---|---|
| [v1_8_2_corpus_validation.md](./v1_8_2_corpus_validation.md) | **当前**：10 论文语料 + 3-subagent 审计加固 |
| [v1_8_validation_results.md](./v1_8_validation_results.md) | v1.8.1：KL 稳定性修复，地板从 1 抬到 12 |
| [v1_7_validation_results.md](./v1_7_validation_results.md) | v1.7.0（历史）：KL 首次上线、方差暴露问题 |

## 仍为英文的文档

以下保留在 `../docs/` 下、未翻译：

- `v1_4_roadmap.md`, `v1_5_experimental_results.md`, `v1_5_test_cases.md`, `v1_6_strategy_j_design.md` —— 历史设计文档，仅作存档参考
- `superpowers/`, `INTERNAL/superpowers/` —— Claude Code 工作流相关
- `CHANGELOG.md` —— 项目根目录的 changelog（结构化 release notes）

如果你需要其中任何一篇的中文版，提 issue 即可。

## 相关链接

- [项目主 README（中文）](../README.zh.md)
- [项目主 README（英文）](../README.md)
- [CHANGELOG.md](../CHANGELOG.md)
- [GitHub releases](https://github.com/thematteroftime/lazy-paper/releases)
