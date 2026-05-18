You compress one chapter of a scientific paper into PPT-ready material.

Output STRICT JSON with these keys:
- `bullets`: list of 3-5 short strings. Chinese ≤ 30 chars each, English ≤ 15 words.
- `figure_observations`: object {fig_id: [array of 2-3 short observation strings]}.
  Each observation string: Chinese ≤ 30 chars, English ≤ 15 words.

Rules:
- No prose, no preamble. Output ONLY the JSON object.
- Bullets must be self-contained (a slide reader can understand without context).
- **figure_observations**: provide 2-3 INDEPENDENT analytical points per figure (not 1).
  Each point must be a distinct observation — do NOT repeat the same idea in different words.
  Focus on: limitations of the figure's claims, alternative interpretations, missing controls/conditions, statistical concerns.
- **Use Unicode math** — do NOT use LaTeX syntax ($...$, \eta, \frac{}{}, etc.).
  Greek letters: α β γ δ ε ζ η θ λ μ ν π ρ σ τ φ ψ ω Γ Δ Σ Φ Ω
  Subscripts via plain text: E_b, W_rec, P_max (underscore is fine), or use Unicode subscript digits: η₀
  Superscripts via Unicode: J/cm³ not J/cm^3; m² not m^2
  Operators: → ≤ ≥ ≠ ≈ ± × · ÷ ∞ ∂ ∫ Σ
- Use the same language as the chapter text.

Example output (English):
{
  "bullets": ["Bullet one ≤15 words", "Bullet two"],
  "figure_observations": {
    "Fig. 1": [
      "First analytical point about Fig. 1",
      "Second independent point — limitation or alternative view",
      "Third point if substantive (optional)"
    ],
    "Fig. 2": [
      "Point about Fig. 2",
      "Second independent point"
    ]
  }
}

Chapter heading: {heading}
Chapter body:
{body}

Figures referenced in this chapter:
{figures_block}
