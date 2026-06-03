# lazy-paper 输出样式规范（v1）

**目的**：把 lazy-paper 的 `preview.html / preview.docx / preview.pdf / preview.pptx` 四格式输出从「能读」升级到「想读」。本文档面向 Claude Design：基于这份文字规范 + 参考图，请输出一份 HTML demo（建议先做 HTML，因为 PDF 走 HTML→PDF，docx/pptx 我们另行映射）。

**重要约束**：lazy-paper 是开源通用 PDF→深度解读工具，样式规范必须**领域无关**（材料、机器人、化学、CV 论文都要适用），不能 hardcode 任何具体论文的字段。

---

## 1. 设计哲学：「轻松的学术阅读体验」

一篇深度论文解读应该像优质技术博客一样让人**忍不住读完**，而不是像期刊 PDF 那样让人**只看 abstract 就关掉**。三个支点：

- **节奏感**：用留白、字号阶梯、视觉锚点（公式块、图、引用栏）打断长文，避免每屏都是密集中文。
- **可信感**：每个数字、公式、引用都要有结构性归位（比如公式独占一行 + 编号、引用编号点击可跳）；不是把所有元素都展平成段落。
- **温度感**：色彩克制但要有一点暖色点缀（参考 Anthropic 主页的奶油底 + 橘红 accent），避免银行报表式的全黑灰。

参考图：`/Users/zhangjiedong/codeFiles/article/paper2md/695f881845d4e8be9235b007dca5c663.jpg`（Anthropic 主页 hero 区）—— 关注它的：
- 大字号 serif 标题 + 细 sans 副标题对比
- 大片留白
- 单一暖色点缀（橘红）
- 卡片/弹窗用细描边而不是阴影
- 手绘有机线条作为视觉呼吸点

如果需要更多参考图，可向用户索取以下场景的截图：
- Stripe Docs 或 Linear 文档（公式 + 代码块的并列排版）
- Distill.pub 论文页（深度学术 + 高可读性的标杆）
- Substack 长文阅读视图（serif 段落 + 关键句加粗）

---

## 2. 色板（语义化，不绑死具体值）

| Token | 用途 | 建议值（Light） | 备注 |
|-------|------|---------------|------|
| `--bg-paper` | 全局底色 | `#FAF7F2` 或 `#F8F4EE` | 奶油白，比纯白柔和；避免 #FFFFFF 的纸张反光感 |
| `--bg-card` | 公式块、引用栏、图说卡片背景 | `#FFFFFF` 微阴影 OR `#F1ECE3` 同色降饱和 | 二选一保持一致 |
| `--ink-primary` | 正文 | `#1F1B16` | 不要纯黑 #000，太硬 |
| `--ink-secondary` | 图说、脚注、元信息 | `#5E5851` | 比正文淡 30% 左右 |
| `--accent` | 章节编号、关键引用、CTA 链接 | `#D97757` 或 `#C76A4A` | 暖橘红，借鉴 Anthropic accent；不要纯红 |
| `--accent-soft` | accent 的 8% 透明覆层（公式块高亮、tab 激活态） | `rgba(217,119,87,0.08)` | |
| `--rule` | 分隔线、卡片描边 | `#E6DFD2` | 比 bg 深一档但不抢戏 |
| `--code-bg` | 代码 / 公式行块 | `#F3EEE4` | 同色系，不用 GitHub 灰 |

Dark mode 是 nice-to-have，可后续做；当前优先 Light。

---

## 3. 字体

| 角色 | 推荐字族 | 字号阶梯（中文/英文） |
|------|---------|----------------------|
| H1 论文标题 | `"Source Han Serif", "Songti SC", Georgia, serif` | 32-40 px（中文按 28-32） |
| H2 章节标题 | 同上 | 22-26 px |
| H3 小节 | sans-serif 加粗 | 16-18 px |
| 正文 | `"PingFang SC", "HarmonyOS Sans", -apple-system, Inter, sans-serif` | 15-16 px，行高 1.75 |
| 引用栏 / 旁注 | 同正文，italic 或 -1px | 14 px |
| 图说 caption | sans 半粗 | 13 px |
| **公式（inline）** | `"STIX Two Math", "Cambria Math", "Latin Modern Math", serif` italic | 与正文同号 |
| **公式（display 块）** | 同上 | 比正文大 1px，居中 |
| 代码 / 关键变量 | `"JetBrains Mono", "Fira Code", monospace` | 14 px |

中文 serif 标题 + 英文 sans 正文是最重要的一组对比；这是「学术 + 现代」感的关键。

---

## 4. 元素级规范

### 4.1 章节标题（H2）

- 上方留白 64 px，下方 24 px
- 标题左侧带一个 8 px 宽的 `--accent` 色条（垂直短竖线）作为视觉锚点
- 中文标题前可加章节序号 `01 / 02 / …` 用 `--accent` 色 + 等宽数字
- 不用全大写

### 4.2 正文段落

- 行高 1.75，段间距 1.2 em
- **首行不缩进**（HTML 阅读不是印刷物，缩进反而碎；DOCX 仍走 0.74 cm 缩进保留印刷感）
- 中英混排时英文/数字前后自动加 0.125 em 空格（CSS `word-spacing` 或 `<wbr>` 处理）
- 段内 `<strong>` 用 600 weight，不另加色（避免「圣诞树」）

### 4.3 公式（重点！）

当前的输出已经有 inline italic 区分，但**长公式应当独占一行**：

- **Inline 公式**：`<em class="math-inline">R_en</em>` —— italic + 字间距微调，**不**改色
- **Display 公式**：放在 `<figure class="formula-block">` 里：
  - 居中
  - 背景 `--code-bg` 浅色块，圆角 8 px
  - 左右各留 16 px padding，上下 12 px
  - 右下角可选编号 `(4)`，用 `--ink-secondary`
  - 如果公式超长，允许横向滚动 + 「点击展开」按钮

LLM 当前以 `\(...\)` inline 形式塞入复杂公式（如分数 + 求和）；建议 Claude Design 在 HTML 里加一段 JS：检测 inline 公式长度 > 40 字符 OR 含 `\frac` `\sum`，自动升级为 display block。

### 4.4 图片块

- 居中、最大宽度 720 px，圆角 8 px、细描边 1 px `--rule`
- 多子面板（如 Fig.3 a/b/c/d）：横向 flex，每张 25% 宽度，gap 8 px
- 图说在图下方，左对齐，`--ink-secondary` + sans 半粗
- **深度观察块**（lazy-paper 特色）：图说下方一个 `<aside class="deep-obs">`，左侧 4 px `--accent` 色条 + 浅 `--accent-soft` 背景；前缀「⌖ 深度观察」用 accent 色加粗

### 4.5 引用与脚注

- 文内 `[span:doc:0-15]` 当前已被替换为 `<sup>[1]</sup>` —— 样式：
  - 字号 0.7 em，垂直对齐 top
  - 颜色 `--accent`，hover 加下划线
- 页面底部 `Sources` 栏：每条 source 一行，doc_id + span 范围 + 跳转链接，背景 `--bg-card`

### 4.6 表格

- 无竖框，仅上下两条 `--rule` 横线
- 表头：sans 半粗 + 底部一条 `--accent` 1 px 线
- 行高 36 px，奇偶行交替 `--bg-paper` / `--bg-card` 极淡区分

### 4.7 整页留白

- 内容宽度上限 **720 px**，居中
- 左右留白随屏宽自适应（min 24 px）
- 页眉/页脚极简：论文标题（左）+ 章节定位（右），灰色 13 px，不抢戏

---

## 5. 关键交互（HTML 独有）

- **目录侧栏**（桌面端右侧 fixed）：章节列表，当前章节高亮 `--accent`，鼠标 hover 显示当前章 H3 子标题
- **公式点击展开**：长公式 hover 显示完整 LaTeX，点击可复制
- **图片 lightbox**：单击图片放大查看
- **暗色模式切换**（可选）

---

## 6. 给 Claude Design 的产出格式

请用一个**单文件 HTML demo** 演示上述规范，约束：

1. 使用我们提供的真实示例段落（见 `runs/atec-b2w-energy-rl/s09_render/preview.html` 中某一章的内容）作为正文；这样能直接看到 LLM 输出落地后的视觉效果。
2. 至少演示：H1 / H2 / 段落（含 inline 公式 + bold）/ display 公式块 / 图片+caption+深度观察 / 表格 / 引用脚注。
3. CSS 写在 `<style>` 内部，不引入外部 CDN（lazy-paper 输出必须单文件离线可读）。字体可降级到系统字体。
4. JS 可用，但限制在 < 5 KB；如果用 KaTeX 渲染公式请确保打包进 HTML。

收到 demo 之后我会：
- 把 CSS 移植进 `stages/s09_render/templates/styles.css`
- 修 `preview.html.j2` 模板让结构对齐（加 `<figure class="formula-block">`、`<aside class="deep-obs">` 等）
- DOCX 渲染按相同语义映射：accent 色用 RGB 写进 run 颜色、display 公式用居中段落 + 浅灰底纹
- PPTX 由于 layout 受限，主要继承色板和字体；放弃复杂排版

---

## 7. 后续轮次

第 1 轮：HTML demo（本文档驱动）
第 2 轮：用户看 demo 后给出色彩/字体微调，Claude Design 出 v2
第 3 轮：我把 v2 映射到 DOCX/PDF/PPTX，回填截图给 Claude Design 校对

每轮交付物都用 `runs/atec-b2w-energy-rl/s09_render/preview.*` 真实数据，避免空跑。
