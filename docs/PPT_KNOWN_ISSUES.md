# PPT Renderer — Known Issues & Proposed Fixes (v1.1.0)

> Status: **diagnosed, not yet fixed**. This document captures the analysis so a follow-up cycle can fix with intent.

Two issues surface intermittently on the v1.1.0 PPT output. Both are real, reproducible, and have clear remediation paths. Neither is severe enough to block the v1.1 release; they go into v1.2.

## Issue A — Math subscripts/superscripts in chapter text render as plain ASCII

### Symptom

Section-divider KEY POINTS card and `_combined` slide body sometimes show e.g. `aphot/cphot 降至 1.003` where the source content was `aₚₕₒₜ/cₚₕₒₜ` (Unicode Latin subscript letters U+209A U+2095 U+2092 U+209C).

Reproducible on: `runs/pan2025/s09_render/preview.pptx` slide 8 (§2 section divider, bullet ① — `x=0.45 时 aphot/cphot 降至 1.003`).

### Root cause

The LLM in s08 correctly emits Unicode subscript characters when describing parameters like `a_phot` (it outputs `aₚₕₒₜ` to satisfy our "no LaTeX, use Unicode" prompt rule). The text flows through `_math.py::normalize_math()` cleanly — there's nothing for it to convert.

The breakage is at the **PPT font-substitution layer**:

1. `python-pptx` writes the Unicode codepoints into the slide XML correctly.
2. PowerPoint / Keynote / LibreOffice opens the slide and looks up a glyph for each char.
3. Our CJK font (Songti / 宋体) is the East-Asian font for all body text. It has no glyphs for the rare Latin subscript letters `ₚ ₕ ₒ ₜ`.
4. The Latin font (`Crimson Pro` or `Times`) often also lacks these (they live in the "Phonetic Extensions" block, U+1D2C–U+1D6A and U+2090–U+209C).
5. The rendering engine falls back to a glyph from `Arial Unicode MS` or similar — or simply omits the diacritic-style subscript and shows the **base letter at normal baseline**, which is what we see (`aphot`).

This is not a code bug — it's a font-coverage gap. The same string renders correctly when copy-pasted into a browser (modern web stacks have richer fallback).

### Proposed fixes (pick one)

| Option | Effort | Trade-off |
|---|---|---|
| **A1. Convert Unicode subscripts back to ASCII with explicit underscore notation at render time** (`aₚₕₒₜ` → `a_phot`) | 30 min | Visually less elegant, but 100% font-portable; matches scientific paper convention |
| **A2. Embed `Arial Unicode MS` or `Noto Sans Math` as a fallback font in the PPT** | 2 hr | Bloats the .pptx by ~5-10 MB; works on most viewers but not all |
| **A3. Pre-render math runs as rich-text fragments with explicit `<a:rFont typeface="..."/>` per character, mapping subscript chars to a Western font that covers U+209x** | 1 day | Cleanest aesthetics; complex code; still doesn't help if the viewer's machine doesn't have the font |
| **A4. Tighten the s08 prompt to *prefer* underscore notation (`a_phot`) over Unicode subscripts for multi-letter subscripts**, keeping Unicode only for single-digit cases like `Pb²⁺` | 30 min | Best long-term: keeps Pb²⁺ pretty (well-supported chars) and a_phot legible (no font hunt). |

**Recommendation**: **A4 + A1 in tandem**. Prompt the LLM to emit underscore form for multi-letter subscripts; at render time, defensively map any remaining U+209x → ASCII underscore. Belt and braces.

### Test case

After fix, all 5 verified papers should be re-rendered. The acceptance criterion: search the `runs/<paper_id>/s09_render/preview.pptx` text content for any U+2080..U+209F or U+2090..U+209C codepoint — should be zero in body text. Greek letters (U+0370+) and `Pb²⁺`-style number+sign superscripts (U+207x) are still allowed.

---

## Issue B — KEY POINTS bullets overlap when text wraps to a second line

### Symptom

On `_section_divider` slides (the divider with a left section title + right "本节要点" card), when the card has 6–7 bullets and at least one bullet's text wraps to a second line, the next bullet visually overlaps the wrapped content.

Reproducible on: `runs/pan2025/s09_render/preview.pptx` slide 8 (7 bullets in §2 card; bullets 5–6 vertically compress).

### Root cause

In `stages/s09_render/renderers/pptx.py::_section_divider()` (lines 396–414), bullets are laid out with fixed row height computed by dividing the card's usable height by `n_bullets`:

```python
row_h = usable_h / max(n_bullets, 1)        # ≈ 0.53" when n_bullets=7
...
_tb1(s, bul, Inches(5.9), by, Inches(6.35), Inches(row_h * 0.7),
     Pt(16), T.TEXT, T.LAT_SANS, T.EA_SANS, wrap=True)
```

The bullet text box height is hard-clamped to `row_h * 0.7` (≈ 0.37" for n=7). A 16pt line is ~0.27" tall; one line fits, but a 2-line wrap (≈ 0.54") exceeds the allocated box and visually bleeds into the row below.

The 16pt font + `wrap=True` allows wrapping, but the *positioning math* assumes one line per bullet.

### Proposed fixes (combinable)

| Option | Effort | Effect |
|---|---|---|
| **B1. Scale font down when n_bullets ≥ 6** (16pt → 13pt, marker 14 → 12pt) | 15 min | Each line ~25% shorter — most "2-line risk" bullets become 1-line. Easy. |
| **B2. Set text-box height to the full `row_h` (drop the `* 0.7` clamp) + slight inter-row spacing** | 15 min | Lets the text-box use full row; if 2 lines still wrap, they bleed less or trigger Office's auto-shrink. |
| **B3. Measure-then-place: use python-pptx's `TextFrame.fit_text()` to auto-size font down per box** | 1 hr | Office runs the fit_text algorithm at render time; messy because fit_text mutates the XML in a way that can conflict with our explicit font styling. |
| **B4. Hard-cap bullet length to ~38 CJK chars / ~70 ASCII chars in `SlidePlanner._extract_group_preview_bullets()`**; truncate with `…` | 30 min | Guarantees one line; some semantic loss. |
| **B5. Adaptive card height**: grow the card vertically to accommodate wrapped bullets up to a ceiling (e.g. 5.5"), then start dropping bullets | 2 hr | Best UX; some risk of bullet card running into footer. |

**Recommendation**: **B1 + B2** in tandem. B1 is the highest ROI (most papers have ≤5 bullets and don't trigger overflow; for 6–7 bullets a smaller font is acceptable). B2 ensures the rare 2-line bullet doesn't visually crash into the next row even when it does happen. B4 as a defensive cap inside `SlidePlanner` for the worst-case 80-char bullets is also cheap insurance.

### Test case

After fix, render all 5 papers + visually inspect every `section_divider` slide. The acceptance criterion: no bullet's wrapped second line vertically overlaps the next bullet's row.

---

## Why we're punting these to v1.2

Both fixes touch the visual layout pipeline. The current v1.1.0 output is **readable** — the math is technically correct (the Unicode is there, just not styled), and the overlap is cosmetic, not data loss. Shipping v1.1.0 unblocks the documentation and packaging work the user requested as priority. Once these two items are in v1.2, the PPT renderer reaches "publication-grade" by visual review.

## Tracking

- v1.2 milestone: fix A4 + A1 + B1 + B2 + B4. Re-render the 5 verified papers. Visual diff against v1.1 output. Update `CHANGELOG.md` Unreleased section.
- Test additions: a regression unit test in `stages/s09_render/tests/test_pptx_subscript_fallback.py` that builds a slide with `aₚₕₒₜ` content and asserts the rendered XML uses `a_phot` (post A1).
