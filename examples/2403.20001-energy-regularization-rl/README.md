# Adaptive Energy Regularization — example output

**Source paper.** Liang, Sun, Zhu et al., *Adaptive Energy Regularization for Autonomous Gait Transition and Energy-Efficient Quadruped Locomotion*, arXiv:[2403.20001v2](https://arxiv.org/abs/2403.20001) (Unitree Go1 quadruped, RL-based locomotion policy).

**Template.** [`templates/Table of Contents-ATEC-B2w-Reward-ZGY.docx`](../../templates/Table%20of%20Contents-ATEC-B2w-Reward-ZGY.docx) — 14-section RL reward-design outline targeting the ATEC2026 B2w wheel-foot robot competition, with a deep dive on the additive `(R_motion + α_en R_en)` + multiplicative `exp(-R_aux)` envelope philosophy.

**What's noteworthy.** The source paper is a figure-rich IEEE-format PDF whose figures are mostly vector plots (Fig. 1, 3a/b/c/d, 4, 5, 6). The v1.13 MinerU `chart`-type fix recovered 12 of 12 referenced figures, including the four panels of the Fig. 3 ablation. The `s07_figure_analyze` deep-observation block surfaces methodological caveats (e.g. "single experiment per α_en — no variance bars").

**Open** [`preview.html`](preview.html) in a browser for KaTeX math + sticky topbar + accent themes.
