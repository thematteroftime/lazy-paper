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
- At least 2 of the bullets MUST contain QUANTITATIVE results (numbers, percentages, comparisons to baseline, e.g., "W_rec 提升至 6.1 J/cm³，比基准高 42%"). Generic contribution statements without numbers do NOT count.
- takeaway: 1 strong concluding sentence, ≤ 50 Chinese chars / ≤ 25 English words. The takeaway MUST mention what is NEW about the paper's contribution (what it achieves that prior work did not).
- Language matches input
- **Use Unicode math** — do NOT use LaTeX ($...$, \eta, \frac, etc.). Use Greek letters directly (η, σ, Δ, etc.) and plain text subscripts (W_rec, E_b) or Unicode superscripts (cm³, m²).
- No prose, no preamble. Only JSON.
