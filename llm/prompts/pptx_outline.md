You are restructuring an academic paper's chapter list into 4-5 high-level sections for a presentation outline.

Paper title: {title}

Paper-specific terminology to use in group naming:
- System: {system}
- Key terms: {key_terms}
- Keywords: {keywords}

Chapter headings (in order) with content metadata and first-paragraph preview:
{chapters_block}

Output STRICT JSON only:
{
  "groups": [
    {"name": "无序结构调控", "chapter_headings": ["弛豫铁电体相变机制", "短程有序域演化"], "takeaway": "本文核心机制：A位无序调控短程有序域以实现弛豫态稳定。"}
    // ... 3-4 more groups
  ]
}

**STRICT NAMING RULES**:
- Each group `name` MUST contain at least ONE paper-specific noun from the key_terms or system listed above.
- FORBIDDEN generic names (will be rejected): "背景", "概述", "方法", "结果", "讨论", "结论", "总结", "应用", "Background", "Methods", "Results", "Discussion", "Conclusion", "Introduction"
- Group names must be 2-6 Chinese characters or 2-4 English words.
- Each group covers a distinct PHENOMENON / TECHNIQUE / SYSTEM (not a section role).
- The example above shows domain-grounded naming: "无序结构调控" (structural disorder tuning) is paper-specific, not "背景" (background).

Rules:
- 4-5 groups total. Prefer 4 for short papers, 5 for long.
- **Even for papers with many figures (10+), produce 4-5 groups based on conceptual content, NOT figure count.**
- Every chapter heading from input MUST appear in exactly one group's `chapter_headings`.
- Preserve chapter order within groups; respect overall chapter order across groups.
- takeaway: 1 sentence, ≤ 25 Chinese chars / ≤ 15 English words, focused on the central message.
- Output language matches input language (mostly Chinese chapters → Chinese name+takeaway).
- **Use Unicode math** — do NOT use LaTeX ($...$, \eta, \frac, etc.). Use Greek letters directly (η, σ, Δ, etc.) and plain text subscripts (W_rec, E_b) or Unicode superscripts (cm³, m²).
- No prose, no preamble. Only the JSON object.
