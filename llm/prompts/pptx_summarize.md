You compress one chapter of a scientific paper into PPT-ready material.

Output STRICT JSON with these keys:
- `bullets`: list of 3-5 short strings. Chinese 25-45 chars each, English ≤ 20 words.
  - At least 1 bullet per chapter MUST contain a quantitative result (number, percentage, ratio, threshold) if quantitative figures are present.
- `figure_observations`: object {fig_id: [array of 2-3 observation strings]}.
  Each observation string: Chinese 40-80 chars, English 20-40 words.

## Paper context (use this to keep chapter analysis connected)
- System: {system}
- Keywords: {keywords}
- Outline section this chapter belongs to: {section_name}
- Prior chapter's main finding (avoid restating; build upon or contrast): {prior_bullet}
- Following chapter heading (what comes next — avoid pre-empting it): {next_heading}

Use this context to make your bullets PROGRESSIVELY connected: reference what was established in the prior chapter when relevant, or set up what the next chapter will address. At least one bullet per chapter should explicitly link to either the prior or next chapter's theme (e.g., "承上节结论…", "为下节…奠定基础", "building on the prior finding that…", "this sets up the next section on…").

Rules:
- No prose, no preamble. Output ONLY the JSON object.
- Bullets must be self-contained (a slide reader can understand without context).
- **figure_observations**: provide 2-3 INDEPENDENT analytical points per figure (not 1).
  Each observation MUST:
  - Reference at least ONE specific panel label (e.g., "图(a)", "panel (e)", "Fig.X(c)") OR a specific dataset/curve feature.
  - Include at least ONE numeric anchor (a value, threshold, percentage, ratio) when the figure presents quantitative data.
  - Be an analytical critique (limitation / alternative interpretation / missing control / comparison gap), NOT a description of what the figure shows.
  - Be distinct from the other observations on the same figure (no restating).
- **Use Unicode math** — do NOT use LaTeX syntax ($...$, \eta, \frac{}{}, etc.).
  Greek letters: α β γ δ ε ζ η θ λ μ ν π ρ σ τ φ ψ ω Γ Δ Σ Φ Ω
  Subscripts via plain text: E_b, W_rec, P_max (underscore is fine), or use Unicode subscript digits: η₀
  Superscripts via Unicode: J/cm³ not J/cm^3; m² not m^2
  Operators: → ≤ ≥ ≠ ≈ ± × · ÷ ∞ ∂ ∫ Σ
- Use the same language as the chapter text.

Example output (English):
{
  "bullets": ["Bullet one with quantitative result ≥85% efficiency", "Bullet two", "Bullet three specific to this paper's system"],
  "figure_observations": {
    "Fig. 1": [
      "Panel (a) shows 12% hysteresis but the baseline measurement at 300 K was omitted, limiting the temperature-dependence claim.",
      "The ±5% error bars in panel (b) overlap at the 0.8 kV/mm threshold, making the transition field statistically ambiguous.",
      "Fig.1(c) compares only two compositions; adding an intermediate x=0.3 point would clarify whether the trend is linear."
    ],
    "Fig. 2": [
      "Panel (a) reports W_rec=4.2 J/cm³ but lacks a pristine-sample control, so the 23% improvement claim cannot be verified.",
      "The cycling data in Fig.2(b) ends at 10⁴ cycles — insufficient to confirm long-term fatigue stability beyond 10⁵ cycles."
    ]
  }
}

Chapter heading: {heading}
Chapter body:
{body}

Figures referenced in this chapter:
{figures_block}
