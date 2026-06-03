# MUJICA — example output

**Source paper.** Yuqi Li, Peng Zhai, et al., *MUJICA: Multi-skill Unified Joint Integration of Control Architecture for Wheeled-Legged Robots*, arXiv:[2605.13058v1](https://arxiv.org/abs/2605.13058) (Unitree Go2-W wheeled-legged, single-policy multi-skill RL with DC-motor constraints).

**Template.** [`templates/Table of Contents-ATEC-B2w-MUJICA-v2-ZGY.docx`](../../templates/Table%20of%20Contents-ATEC-B2w-MUJICA-v2-ZGY.docx) — 14-section fusion outline that combines MUJICA's multi-skill architecture with the energy-regularization paper above. The core design conviction baked into the template's guide text: the skill indicator `ζ` must live in *inferred state* (from `û_t` wheel-ground distance + `v̂_t` base velocity), not in observation space — so the energy paper's "let gait emerge" philosophy survives.

**What's noteworthy.** This is an IEEE-conference paper with roman-numeral sections (`I. INTRODUCTION`, `II. RELATED WORK`, …). v1.13's `s03_chapter` roman-numeral detection picks them up cleanly; the chapter index splits into 8 real chapters instead of collapsing into a single `Preface`.

**Open** [`preview.html`](preview.html) for the best rendition.
