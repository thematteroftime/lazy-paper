You are restructuring an academic paper's chapter list into 4-5 high-level sections for a presentation outline.

Paper title: {title}

Chapter headings (in order) with first-paragraph preview:
{chapters_block}

Output STRICT JSON only:
{
  "groups": [
    {"name": "Background", "chapter_headings": ["Introduction", "Relaxor ferroelectrics"], "takeaway": "Brief 1-sentence summary of what this group covers."}
    // ... 3-4 more groups
  ]
}

Rules:
- 4-5 groups total. Prefer 4 for short papers, 5 for long.
- Each group `name`: 2-5 words, formal academic style ("Background", "Methods", "Results", "Discussion", "Conclusion" OR domain-specific like "Phase Engineering", "Energy Storage Performance").
- Every chapter heading from input MUST appear in exactly one group's `chapter_headings`.
- Preserve chapter order within groups; respect overall chapter order across groups.
- takeaway: 1 sentence, ≤ 25 Chinese chars / ≤ 15 English words, focused on the central message.
- Output language matches input language (mostly Chinese chapters → Chinese name+takeaway).
- **Use Unicode math** — do NOT use LaTeX ($...$, \eta, \frac, etc.). Use Greek letters directly (η, σ, Δ, etc.) and plain text subscripts (W_rec, E_b) or Unicode superscripts (cm³, m²).
- No prose, no preamble. Only the JSON object.
