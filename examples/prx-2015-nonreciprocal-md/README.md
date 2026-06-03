# PRX 2015 nonreciprocal MD — paper-to-reproduction example

**Source paper.** Ivlev, Bartnick, Heinen, Du, Nosenko, Löwen, *Statistical Mechanics where Newton's Third Law is Broken*, Phys. Rev. X **5**, 011035 (2015). Two-species 2D complex plasma with non-reciprocal pair forces; predicts asymptotic temperature ratio `τ = 3.1`, scaling `T_A,B ∝ t^(2/3)`, density scaling `∝ n^(2/3)`.

**Template.** A bespoke 14-chapter "MD-reproduction" outline (not in `templates/` — generated for this one paper to demonstrate a *paper-to-engine* workflow). Each chapter forces extraction of numeric anchors and explicit `ASK USER:` flags for parameters the source paper does not state. Mirrors the 12-section `physics_design.md` schema of the sibling [`agentic-md-for-dummies`](https://github.com/thematteroftime/agentic-md-for-dummies) MD engine.

**What's noteworthy.** Compared to a generic "deep analysis" output, this run's preview.docx feeds an MD engine directly:

- `§3 Units convention` extracts the reduced-units mapping (`m = r₀ = φ₀ = k_B = 1`, `τ = √(mr₀²/φ₀)`, temperature normalized by `φ₀`) — required for any reproduction.
- `§4 Force field` extracts the Hertzian potential `φ_r(r) = ½φ₀[max(0, 1−r/r₀)]²` and `φ_n(r) = ⅓φ₀[…]³` verbatim, matching the engine's `forces/HertzianNonreciprocal` kernel.
- `§5 Non-reciprocity construction` extracts `Δ_eff = 0.57`, `ε = 0.082` from §IID, plus the `f_AB = 1−Δ`, `f_BA = 1+Δ` pseudo-Hamiltonian factors.
- `§8 Box geometry` derives `L = √(πr₀²N / φ)` from the area-fraction relation — matches the engine's lattice generator exactly.
- `§11 Sweep dimensions` enumerates Fig. 1 (T₀ ∈ {0.1, 1, 10}) and Fig. 2 (φ ∈ {0.1, 0.3, 0.5, 0.7, 0.9}) verbatim.
- `§14 Open questions` surfaces the four parameters the paper does *not* give (`dt_initial`, `ν_A,B`, `T_b`, `t_max`) with proposed values flagged `INFERRED`. The engine's skill workflow consumes this as the `ASK USER:` gate before emitting `configs/plan_*.json`.

This run shows the project being used not as "deep reading" but as **paper-driven structured extraction for downstream code generation**.

**Open** [`preview.html`](preview.html) for the best rendition (KaTeX math is essential for this paper).
