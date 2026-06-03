# `docs_zh/` 镜像政策

只镜像高流量、面向使用者的英文文档：

| 文件 | 状态 |
|---|---|
| `AGENT_GUIDE.md` | ✓ 与 `docs/AGENT_GUIDE.md` 镜像 |
| `ARCHITECTURE.md` | ✓ 与 `docs/ARCHITECTURE.md` 镜像 |
| `USER_GUIDE.md` | ✓ 与 `docs/USER_GUIDE.md` 镜像 |
| `INTERNAL/HANDOFF.md` | ✓ 与 `docs/INTERNAL/HANDOFF.md` 镜像 |
| `archive/` | 选择性镜像（v1.7+ 的关键节点） |

未镜像的文档（保留英文版即可）：`STYLE_SPEC.md`、`TEST_FRAMEWORK.md`、`WALKTHROUGH_meng2024.md`、`INTERNAL/audit_subagent_template.md`、`superpowers/`。改动镜像文档时请同步两边；若引入新一类高流量文档，再决定是否纳入镜像。
