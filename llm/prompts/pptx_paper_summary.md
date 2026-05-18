You write the closing-slide content for a presentation summarizing an academic paper.

Paper title: {title}

Full chapter content (truncated):
{chapters_block}

Output STRICT JSON only:
{
  "bullets": [
    "Bullet 1 — key finding or contribution",
    "Bullet 2",
    "Bullet 3",
    "Bullet 4",
    "Bullet 5"
  ],
  "takeaway": "Single sentence final take-away that captures the paper's central message."
}

Rules:
- 5-7 bullets summarizing main contributions/findings/strategies
- Each bullet: ≤ 40 Chinese chars / ≤ 20 English words
- Self-contained (audience hasn't seen prior slides)
- takeaway: 1 strong concluding sentence, ≤ 50 Chinese chars / ≤ 25 English words
- Language matches input
- **Use Unicode math** — do NOT use LaTeX ($...$, \eta, \frac, etc.). Use Greek letters directly (η, σ, Δ, etc.) and plain text subscripts (W_rec, E_b) or Unicode superscripts (cm³, m²).
- No prose, no preamble. Only JSON.
