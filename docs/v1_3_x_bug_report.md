# v1.3.0 PPT Output — Second-Pass Audit & Bug Report

> Status: **diagnosed, not yet fixed**. User asked for verification + fix proposals before any code change. This doc captures the five concrete defects found by exhaustively reviewing all 71 slides across the 4 verified papers (yang2025 / randall2021 / yao2022 / ali2025_flash).

## Methodology

Rendered every slide (12 + 17 + 14 + 28 = 71 slides) to PNG at 120 DPI. Visually inspected each. Cross-checked the upstream artifacts (`s07_figure_analyze/fig_notes.yaml`, `s09_render/llm_cache/<chapter>.json`) to determine whether each defect is a renderer bug or an upstream truncation.

---

## Bug 1 — `_combined` slide: observations overlap bullets

### Symptom

`runs/yang2025/s09_render/preview.pptx` **slide 4** (§1.1 · Fig. 1 · combined). Right pane shows:

```
Key Points                   ← eyebrow
1  Relaxor antiferroelectrics exhibit diffuse phase transition…
2  Building on prior chapter's energy storage of 8.6 J/cm³ at 85%…
3  Gradual polarization relaxation in CBPS mimics biological…
4  Mobile Cu cation order down to atomic
                             ← "Key Observations" eyebrow APPEARS BEHIND ROW 4
                             ← First obs "Open (l)…" overlaps the last bullet
Key Observations             ← (overlapping)
◇ Open (l) shows hysteresis…
```

### Root cause

`stages/s09_render/renderers/pptx.py::_combined()` lines 755–762:

```python
bullet_row_h = Inches(0.55)
bullets_top = ty + Inches(0.38)
for i, bul in enumerate(slide.bullets):
    by = bullets_top + i * bullet_row_h
    _tb1(s, bul, …, tw - Inches(0.38), bullet_row_h, Pt(14), …, wrap=True)
n_bullets = len(slide.bullets)
obs_top = bullets_top + n_bullets * bullet_row_h + Inches(0.15)
```

Each bullet is given a 0.55" tall box. At 14pt with `wrap=True`, a single line is ~0.30" tall — fine for 1 line, but if a bullet exceeds ~70 ASCII / ~25 CJK chars it wraps to 2 lines (~0.55") which fills the entire allocated box, then **bleeds visually below it because the box has no clipping**. Meanwhile `obs_top` is computed against the *allocated* row stride, not the actual rendered height. Observations land inside the wrapped second lines.

### Why it didn't surface in v1.2.x

The original samples (PBZ films, ali2025_flash) had shorter bullets (CJK is dense — fits more in same space). yang2025's English bullets pushed past the 1-line limit on most figures.

### Fix proposal

Two options, pick one:

| Option | Change | Effort |
|---|---|---|
| **A** | Cap combined-slide bullets via `_truncate_bullet(b, n_bullets)` (same as section_divider, T2). | 5 min |
| **B** | Increase `bullet_row_h` from 0.55" → 0.78" (allow up to 2-line wrap), shrink font to 13pt when n_bullets ≥ 3, recompute `obs_top` from actual cumulative height. | 30 min |

**Recommendation**: do A first (cheap, fixes 95% of cases), keep B in pocket if A leaves edge cases.

---

## Bug 2 — `_section_divider`: autofit clips sparse-card bullets mid-formula without ellipsis

### Symptom

`runs/randall2021/s09_render/preview.pptx` **slide 7** (§2 KEY POINTS, 3 bullets):

```
1  The structural characterization of Pb0.98La0.02(Zr0.66Ti0.10
2  The dielectric properties of Pb0.98La0.02(Zr0.66Ti0.10Sn0.24
3  The polarization behaviour of Pb₀.₉₈La₀.₀₂(Zr₀.₆₆Ti₀.₁₀Sn₀.₂
```

Each bullet is ~50–60 chars, **cut mid-formula with no `…`**, and the rest of the 7.5"-tall card is empty.

### Root cause

`stages/s09_render/renderers/pptx.py::_section_divider()` lines 468–476:

```python
tb = _tb1(s, bul, …, tb_h, Pt(txt_pt), …, wrap=True)
try:
    tb.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
except Exception:
    pass
```

The autofit (v1.3 T2 "safety net") tells LibreOffice/PowerPoint to either shrink-to-fit OR clip-to-fit. **LibreOffice's rendering clips** rather than shrinks when the text/box ratio is awkward (specifically: when a 2-line-natural text gets a 1.23"-tall box at 16pt, LO computes that the text fits at full size IF clipped, so it clips). The bullets are NOT pre-truncated by `_truncate_bullet` because at n=3 the cap is 110 ASCII, and these bullets are ~90 chars — well under cap. So they enter the autofit zone unprotected.

The full source bullet is "The structural characterization of Pb₀.₉₈La₀.₀₂(Zr₀.₆₆Ti₀.₁₀Sn₀.₂₄)O₃ yields a relaxor AFE structure" — the rendered "Pb0.98La0.02(Zr0.66Ti0.10" is exactly the visible prefix that fits one line at 16pt.

### Fix proposal

```diff
-                try:
-                    tb.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
-                except Exception:
-                    pass
+                # v1.3.x: autofit only when n_bullets >= 6. For sparse cards
+                # (≤5 bullets), let text wrap naturally to 2 lines within the
+                # tall row — LibreOffice's TEXT_TO_FIT_SHAPE renderer clips
+                # rather than shrinks on sparse cards (silent mid-formula cut).
+                if n_bullets >= 6:
+                    try:
+                        tb.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
+                    except Exception:
+                        pass
```

**Effort**: 2 min.

---

## Bug 3 — `_figure` slide with single observation wastes 80% of vertical space + truncates the one obs at 200 chars

### Symptom

`runs/randall2021/s09_render/preview.pptx` **slide 5** (Fig. 2, figure-only). Left pane:

```
Key Observations
◇ The figure presents a mismatch between the caption and the actual content:
  while the caption references Figure 18 and AgNbO₃, the visual content
  corresponds to Pb(In₀.₅Nb₀.₅)O₃ and lacks the expected
```

The obs text ends mid-sentence ("the expected") with no `…`, and the lower 70% of the slide is white space.

### Root cause (two compounding)

**3a — text truncated to 200 chars**:
`stages/s09_render/slide_planner.py:236` and `:258`:

```python
obs_list = [fb.deep_observation[:200]] if fb.deep_observation else []
```

This is the FALLBACK path triggered when the chapter LLM summary lacks `figure_observations[fig_id]`. The full s07 `deep_observation` is 600–900 chars in the yaml — clipped to 200 here for no good reason. ("the expected" is char 195–207 in the source — fully consistent with the 200-char cap.)

**3b — fixed row layout for n=1 obs**:
`stages/s09_render/renderers/pptx.py::_figure()` lines 626–648:

```python
n_obs = min(len(observations), 3)
needed_at_default = n_obs * 0.70
…
obs_row_h = Inches(0.70) if needed_at_default ≤ … else Inches(0.60)
```

The vertical guard (T6) chooses row height based on n_obs but doesn't expand the obs FONT or BOX when there's only 1 item. A 1-obs slide gets 1 × 0.70" row in a 7"-tall body — visually anemic.

### Fix proposal

**3a — fix the truncation**:

```diff
-                obs_list = [fb.deep_observation[:200]] if fb.deep_observation else []
+                # No truncation — split into sentences so the layout can show
+                # 2-3 short items instead of one long one. Sentence split first
+                # falls back to chunking by length so a paragraph still yields
+                # ≥ 2 items.
+                obs_list = _split_obs_into_items(fb.deep_observation, target=3) if fb.deep_observation else []
```

Where `_split_obs_into_items(text, target)` splits the full 700-char text on `". "` and `"。"` into N items. Targets 2–3 items per figure even on the fallback path, matching the LLM `figure_observations` shape.

**3b — sparse-card vertical fill**:

| n_obs | Font | Row height |
|---|---|---|
| 1 | 15 pt | 1.40" (covers ~2/3 of the obs region) |
| 2 | 14 pt | 0.95" |
| 3 | 13 pt | 0.70" (current) |

So a 1-obs figure now gets a larger, more readable single observation that fills the obs region instead of leaving 80% white.

**Effort**: 20 min combined.

---

## Bug 4 — figure caption header truncated at 50–55 chars mid-formula

### Symptom

`runs/randall2021/s09_render/preview.pptx` **slide 5** header:

```
§1.2  ·  Fig. 2  ·  Crystal structure and superlattice diffraction in Pb(In…
```

The full caption is "Crystal structures and pioneers in antiferroelectric research" — but at 55 chars `_short_title()` chops off mid-formula. Header has 12" of horizontal room.

### Root cause

`stages/s09_render/renderers/pptx.py`:

- Line 577 (`_combined`): `_short_title(slide.title, 50)`
- Line 681 (`_figure`): `_short_title(slide.caption or slide.title, 55)`

Both caps are conservative leftovers from when the header was 8" wide. Current header box is 12" wide → fits ~140 chars at 12pt serif.

### Fix proposal

Raise caps:

```diff
-        header_text = f"{sec_label}  ·  {fig_label}  ·  {_short_title(slide.title, 50)}"
+        header_text = f"{sec_label}  ·  {fig_label}  ·  {_short_title(slide.title, 110)}"

-        caption_short = _short_title(slide.caption or slide.title, 55)
+        caption_short = _short_title(slide.caption or slide.title, 120)
```

**Effort**: 1 min.

---

## Bug 5 — KEY POINTS card still truncates more than necessary for dense cards (n=7)

### Symptom (low severity)

`runs/yang2025/s09_render/preview.pptx` **slide 6** (§2 KEY POINTS, 7 bullets at 13pt). All 7 bullets show `…` at ~80 chars:

```
② Raman peaks at 111.7 cm⁻¹ (Eg¹) and 465.9 cm⁻¹ (Ag³) confirm layered monoclinic…
④ XPS binding energies (Cu⁺ 935.58 eV, Bi³⁺ 158.15 eV, P⁴⁺ 131.2 eV, Se²⁻ 54.1 eV…
```

Bullet 4 truncates right in the middle of a numeric list — that's exactly the kind of quantitative anchor we asked the LLM to put in. The current 13pt × 6.35"-wide box could fit ~95 chars per line.

### Root cause

`stages/s09_render/slide_planner.py::_bullet_caps()` table:

```python
7: (45, 80)   # current
```

The 80-char cap was set conservatively when we feared wrap-induced overlap. With autofit removed for sparse cards (Bug 2 fix), and density-adaptive font already shrinking to 13pt for n=7, we can loosen the cap to **95** safely.

### Fix proposal

```diff
     _BULLET_CAP_TABLE: ClassVar[dict[int, tuple[int, int]]] = {
         4: (60, 110),
         5: (55, 100),
         6: (50, 90),
-        7: (45, 80),
+        7: (50, 95),
     }
```

**Effort**: 1 min + visual diff.

---

## Severity summary

| # | Bug | Affects | Severity | Fix effort |
|---|---|---|---|---|
| 1 | `_combined` obs overlap bullets | Every paper, multiple slides | **blocker** | 5 min (option A) |
| 2 | Sparse-card autofit clips mid-formula | Sparse (≤5) section dividers | **blocker** | 2 min |
| 3 | `_figure` single-obs space waste + 200-char cap | Figure-only slides | **important** | 20 min |
| 4 | Caption header 50/55-char cap | All combined + figure slides | minor | 1 min |
| 5 | KEY POINTS 7-bullet cap too tight | Dense section dividers | minor | 1 min |

Total fix effort: ~30 min code + ~45 min re-render verification on 4 papers.

## Validation plan

1. Implement all 5 fixes.
2. `uv run pytest -q` → 178 → ~180 (each bug adds 1 regression test).
3. Re-render `--only s09_render --force` for 4 papers (no LLM re-run needed since none of these touch the prompt path).
4. PNG-diff the 12 + 17 + 14 + 28 = 71 slides. Acceptance:
   - Zero `_combined` obs/bullet overlap (visual diff on yang2025 slides 4, 8).
   - No sparse-card bullet truncated without `…` (randall2021 slide 7 should now wrap to 2 lines).
   - No figure-only slide with > 70% white space and single obs < 250 chars.
   - All caption headers fit their text (no `…` unless source is genuinely > 120 chars).

## Why these escaped v1.3.0's first review

The v1.3.0 verification rendered slides 1, 2, 4, 5, 7, 9, last — a sampling. Bugs 1, 2 are on slides 4 and 7 (sampled) but specific to layout pathology that only triggers when bullet text length crosses a wrap threshold — most v1.3 sample slides were short enough not to trigger. Bug 3 only manifests when chapter `figure_observations` is absent for a given fig (rare). Bugs 4, 5 are visible but cosmetic — easy to miss when the headline metric is "no overlap".

Lesson for v1.4+: visual regression should diff EVERY slide of EVERY test paper, not a sample. A diff tool that flags `…` density would catch over-truncation; pixel-diffing the last-line of each text box against the first-line of the next would catch overlaps.
