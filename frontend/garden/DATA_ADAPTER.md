# garden 真实数据接入(交接给 Claude Code)

demo 当前由 `garden-data.js` 的 `generate()` 生成种子假数据。
接入真实 lazy-paper 导出只需一件事:**在 `garden-app.js` 之前定义 `window.GARDEN_EXPORT`**,
`GardenData.adapt()` 会把它映射为内部结构(布局坐标、星座连线、实体索引都在前端计算,
导出器不需要提供任何 layout)。

## 接入方式

```html
<!-- lazy-paper Garden.html 中,在 garden-app.js 之前 -->
<script>
  // 方式 A:构建时内联
  window.GARDEN_EXPORT = {/* 见下方 shape */};
</script>
<!-- 方式 B:运行时拉取 -->
<script>
  fetch('garden-export.json').then(r=>r.json()).then(j=>{
    window.GARDEN_EXPORT = j;
    GardenApp.applyTweaks({});   // 触发 regen → adapt
  });
</script>
```

## GARDEN_EXPORT shape

```jsonc
{
  "manifest": {
    "papers": [{
      "id": "a1b2c3d4",            // 必填,稳定唯一(用于星体形态哈希)
      "title": "…",                 // 必填
      "lang": "en|zh",
      "n_chunks": 95,
      "n_entities": 17,
      "total_tokens": 93000,
      "ingested_at": "2026-03-05T08:00:00Z",  // ISO 或 epoch ms;驱动冷却曲线
      "keywords": ["…"],
      "questions": ["…"],           // critical questions,可选
      "figures": [{"id":"fig_1","caption":"…"}]  // 可选
    }]
  },
  "entities":  { "<paper_id>": [{"id":"e0","type":"method","text":"…"}] },
  // type ∈ 11 类闭集: method material dopant parameter value unit
  //                  figure table claim comparator author
  "relations": { "<paper_id>": [["e4","has_value","e5"],["e5","in_unit","e6"]] },
  // 谓词: has_value in_unit applied_to evidenced_by compared_with
  "sections":  { "<paper_id>": [{"num":"Ⅰ","zh":"引言","en":"INTRODUCTION",
                                  "chunks":12,"ents":["e0"],"q":"…"}] },
  // 可选;缺省时前端按实体类型自动分配到 Ⅰ引言/Ⅱ方法/Ⅲ结果/Ⅳ讨论
  "clusters":  [{"key":"sc","en":"superconductivity","zh":"超导材料",
                 "paper_ids":["a1b2c3d4"]}]
  // 可选,≤6 个;缺省时论文随机入簇(后续可换成共享实体亲和度聚类)
}
```

## 已知缺口(留给接入时处理)

- `ingestOne()`(「模拟 ingest」按钮)在真实数据模式下仍生成假论文 —— 接入后应改为
  re-fetch export 或隐藏按钮(`data.fromExport === true` 可判断)。
- Tweaks 的「库规模/聚类数」滑杆在真实数据模式下无效(adapt 忽略这两个参数)。
- 「打开 preview.html」按钮目前显示占位提示;真实产物应跳转
  `<source_run>/preview.html` 或 garden 构建的 lite 阅读页。
- 聚类:导出器可以直接给 `clusters`;若想前端聚类,在 `adapt()` 里用
  `buildLinks()` 的共享实体图做社区发现即可(数据已齐)。
