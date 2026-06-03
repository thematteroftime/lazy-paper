# examples — reference outputs

Three real lazy-paper runs against three different source papers. Open the
`preview.html` files in a browser for the best rendition (KaTeX math, sticky
topbar, accent themes); the `.docx` / `.pdf` / `.pptx` siblings are the same
content rendered for those formats.

| Folder | Source paper | Template used | Outputs |
|---|---|---|---|
| [`2403.20001-energy-regularization-rl/`](2403.20001-energy-regularization-rl/) | Liang et al., *Adaptive Energy Regularization for Autonomous Gait Transition and Energy-Efficient Quadruped Locomotion*, arXiv:2403.20001v2 | `Table of Contents-ATEC-B2w-Reward-ZGY.docx` (energy-RL reward design) | docx · html · pdf · pptx |
| [`2605.13058-mujica-multiskill/`](2605.13058-mujica-multiskill/) | Li et al., *MUJICA: Multi-skill Unified Joint Integration of Control Architecture for Wheeled-Legged Robots*, arXiv:2605.13058v1 | `Table of Contents-ATEC-B2w-MUJICA-v2-ZGY.docx` (multi-skill RL fusion) | docx · html · pdf · pptx |
| [`prx-2015-nonreciprocal-md/`](prx-2015-nonreciprocal-md/) | Ivlev et al., *Statistical Mechanics where Newton's Third Law is Broken*, Phys. Rev. X 5, 011035 (2015) | MD-reproduction outline (paper → MD-engine config feed) | docx · html · pdf |

## What each demonstrates

- **2403.20001 · energy-RL** — figure-rich text-PDF; exercises the v1.13 MinerU `chart`-type extraction (12/12 figures recovered, including the Fig. 3 four-panel ablation).
- **2605.13058 · MUJICA** — IEEE-style paper with roman-numeral sections; exercises the v1.13 chapter detector.
- **PRX 2015 nonreciprocal MD** — paper-to-reproduction outline; each chapter forces extraction of numeric anchors (τ = 3.1, Δ_eff = 0.57, ε = 0.082) and explicit `ASK USER:` flags for parameters the source paper does not give. Used to feed a sibling repo's [`agentic-md-for-dummies`](https://github.com/thematteroftime/agentic-md-for-dummies) MD engine.

## Reproducing any of these

```bash
uv run python -m cli run \
  --pdf <source-paper.pdf> \
  --template "templates/<corresponding-template>.docx" \
  --paper-id <slug> --lang zh --formats docx,pdf,html,pptx
```

The templates referenced in the table above live in [`templates/`](../templates/).
