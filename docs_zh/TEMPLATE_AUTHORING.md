# 模板生成（v1.15）

`lazy-paper template` 把**你的研究问题**变成 pipeline 实际运行的大纲——不再
从手写模板里挑最接近的（模板是全系统最高杠杆的单点选择，见 README），而是
生成一份同时贴合论文内容和你意图的问题模板。

## 快速上手

```bash
# 新 PDF（文本层预扫描，不调 OCR API）：
uv run python -m cli template --idea "能否迁移到双足？" --pdf papers/mypaper.pdf

# 已有 run（更丰富：章节、图注、context）：
uv run python -m cli template --idea "能量项的代价与约束" --run mypaper

# 结合知识库（自动加入跨论文对比问题）：
uv run python -m cli template --idea "..." --run mypaper --use-library
```

产物：`templates/auto-<想法-slug>.docx` + `.prompt.md` / `.response.json`
审计文件，终端同时打印完整大纲供审阅。

## 约定

- 生成的 docx 是**普通 Word 文件**——直接打开改标题、增删问题。人工审阅是
  设计内的最后一步，不是可选项。
- 它能**确定性地**通过 s05 解析：编号行（"1 标题"）成为章节，问题段落全部
  进入该章节的 `guidance`。写完后立即用真实 s05 解析器自检，发现漂移即报错。
- 之后照常跑 pipeline：`… run --pdf <论文> --template <生成的模板>`。

## 参数

| 参数 | 作用 |
|---|---|
| `--idea`（必填） | 你的研究视角；至少一半问题为它服务 |
| `--pdf` / `--run` | 预扫描来源：文本层 vs 已有产物 |
| `--use-library` | 注入库内论文清单 + 相关片段；强制 ≥2 个点名对比问题 |
| `--sections N` | 大纲宽度（默认 6） |
| `--lang zh\|en` | 标题与问题语言 |
