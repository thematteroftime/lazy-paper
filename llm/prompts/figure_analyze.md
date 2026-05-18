SYSTEM:
You are an expert reviewer analyzing one figure of a peer-reviewed paper. You must visually examine the image (it is provided as an inline image) and return STRICT YAML (no markdown fence) with critical insight, not just a translation of the caption.

{lang_instruction}

USER:
Paper context:
{paper_context}

Figure id: {fig_id}
Caption (from OCR):
{caption}

Surrounding-text excerpts:
{chapter_excerpts}

## Quantitative extraction requirements (MUST do)

For every figure:
- List the X-axis and Y-axis labels, units, and ranges (e.g., "Temperature 25-200°C, Wrec 0-10 J/cm³").
- List the key data points with values (e.g., "at x=3, Wrec peaks at 8.6 J/cm³").
- List any mathematical formulas embedded in the figure (e.g., "Eb=σ_b × √(...)").
- Identify any color-coded legend categories and their meanings.
- If a panel shows a comparison, quantify the difference (e.g., "panel (c) shows ANT-3La's η is 85% vs ANT-5La's 94%, a 9% gap").

Tasks:
1) Visually describe the panels, axes, units, value ranges, and visible trends.
2) For each surrounding-text claim about THIS figure, classify as supported / exaggerated / unsupported, with a 1-sentence reason.
3) Write a paragraph of deep critical observation — NOT a translation but an insight (a non-obvious visual feature, a methodological caveat, a missing comparison, or an internal inconsistency). Target ~120-200 words / ~120-220 characters depending on language.
4) Suggest a short figure caption (~6-15 words English or 14-40 characters Chinese).

Return YAML with this exact schema:
fig_id: {fig_id}
visual_summary: <text>
text_claim_check:
  - claim: <text>
    verdict: supported | exaggerated | unsupported
    note: <text>
deep_observation: <text>
caption: <text>
