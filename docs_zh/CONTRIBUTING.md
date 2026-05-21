# 为 lazy-paper 做贡献

## 开发环境

```bash
git clone https://github.com/thematteroftime/lazy-paper
cd lazy-paper
uv python install 3.11
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env  # 填入你的 API key
```

## 跑测试

```bash
uv run pytest             # 253 个测试，~25s
uv run pytest -m live     # 实时 LLM 烟雾测试（默认跳过）
```

## 代码风格

- 4 空格缩进，不要 tab
- 公共函数签名加 type hints
- 结构化数据优先用 dataclasses，少用裸 dict
- 渲染器必须**消费** `Document` 模型而**不能修改**它
- LLM prompt 放在 `llm/prompts/*.md`，用 `.replace(...)` 占位符

## Pull Request 规范

- 从 `main` 切分支，命名形如 `feat/<topic>` 或 `fix/<topic>`
- 一个 PR 一个逻辑变更优先；合并时 squash 也可以
- 所有测试必须通过：`uv run pytest -q`
- 渲染器改动须在 `stages/s09_render/tests/` 加烟雾测试
- 新流水线 stage 须按现有 stage 的 `runner.py` + `tests/` 结构来组织

## 反馈问题

报告论文处理不正确时，请附上：

- 失败 stage 的 `runs/<paper_id>/<stage>/done.yaml`
- 如适用，`runs/<paper_id>/...` 下相关的 `.prompt.md` 和 `.response.json`
- 使用的 OCR 后端（`OCR_BACKEND` env var）
