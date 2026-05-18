You compress one chapter of a scientific paper into PPT-ready material.

Output STRICT JSON with these keys:
- `bullets`: list of 3-5 short strings. Chinese ≤ 30 chars each, English ≤ 15 words.
- `figure_one_liners`: object {fig_id: short string}. Chinese ≤ 40 chars, English ≤ 20 words.

Rules:
- No prose, no preamble. Output ONLY the JSON object.
- Bullets must be self-contained (a slide reader can understand without context).
- One-liners must capture the figure's takeaway, not describe it.
- Use the same language as the chapter text.

Chapter heading: {heading}
Chapter body:
{body}

Figures referenced in this chapter:
{figures_block}
