# v1.3 Plan — Output Quality + Layout Robustness

> Status: **draft, awaits approval**. Combines (a) the layout work prompted by the user and (b) the read-only audit's top findings. Each item lists evidence, fix, risk, and which audit tier it belongs to.

## Summary

Two parallel directions, both about **output quality**:

1. **Layout robustness** — outline rows overlapping, KEY POINTS card truncating too aggressively. Visual diagnostics from `/tmp/v1_3_evidence/`.
2. **Generation depth** — LLM prompts mandate quantitative content / critique style, but no code enforces those mandates; section composer truncates figure-observation context too tightly.

Total: ~9 items. Below: 5 in Tier 1 (ship in v1.3), 3 in Tier 2 (recommended if budget), 1 in Tier 3 (defer).

---

## Tier 1 — ship in v1.3

### T1. Outline adaptive row layout (layout)

**Evidence**: `runs/yang2025/s09_render/preview.pptx` slide 2: group 3 takeaway "…optoelectronic response." wraps and the second line crosses into group 4's separator line.

**Code**: `stages/s09_render/renderers/pptx.py::_outline_grouped()` lines 289–328. Currently `row_h = Inches(0.9)` flat.

**Algorithm**:
1. Estimate lines per takeaway: `lines = ceil(len(takeaway) / chars_per_line)` with `chars_per_line ≈ 95` ASCII / `38` CJK at 13pt in the 9.6"-wide takeaway box.
2. Per-row height = `header_h(0.42") + lines * line_h(0.24") + gap_h(0.12")`.
3. Cumulative `y = title_bottom + sum(prev row heights)`.
4. If `total > 5.6"` available → first try `line_spacing = 1.05` (instead of 1.2) for takeaways; second fallback trim takeaway tail with `…` only if still over.

**Tradeoff**: rows no longer at fixed grid; visual rhythm slightly uneven. Acceptable for a list-of-cards design.

**Test**: 4-paper PNG diff — no second-line bleed in any outline slide.

### T2. KEY POINTS card density-adaptive truncation + autofit (layout)

**Evidence**: `runs/yang2025/s09_render/preview.pptx` slide 3: all 7 bullets `…` truncated at ~70 ASCII chars. ~35 chars of horizontal space wasted.

**Code**: `stages/s09_render/slide_planner.py::_truncate_bullet()` lines 268–276 (flat 38 / 70 cap); `stages/s09_render/renderers/pptx.py::_section_divider()` lines 396–425.

**Algorithm**:

| n_bullets | CJK cap | ASCII cap | Font |
|---|---|---|---|
| 1–4 | 60 | 110 | 16 pt |
| 5 | 55 | 100 | 15 pt |
| 6 | 50 | 90 | 14 pt |
| 7 | 45 | 80 | 13 pt |

Replace flat `_BULLET_*_MAX` constants with a per-density table. Pass `n_bullets` through `_truncate_bullet(text, n_bullets)`. Add `text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` on each bullet box as a safety net.

**Test**: 4-paper PNG diff — no overlap, no `…` truncation for n_bullets ≤ 4.

### T3. Quantitative-content validation in PptxSummarizer (depth) [audit #1, #7]

**Evidence**: `llm/prompts/pptx_summarize.md` mandates "at least 1 bullet per chapter must contain a numeric result"; `pptx_paper_summary.md` mandates "3 of 7 closing bullets MUST contain quantitative results" and "takeaway MUST include 1 quantitative comparison". But `summarize()` and `summarize_paper()` only validate JSON shape — content rules are silently violated.

**Code**: `stages/s09_render/pptx_summarizer.py::summarize()` lines 311–326; `summarize_paper()` lines 247–268.

**Algorithm**:

```python
_QUANT_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*(?:%|×|x|fold)|"            # 91%, 2×, 3-fold
    r"\s*[JV]/?cm[²³]?|"                             # J/cm³, V/cm
    r"\s*kV/?cm|"                                    # kV/cm
    r"\s*GHz|MHz|kHz|°C|nm|μm|µm|mm)",              # frequencies, temperatures, lengths
    re.IGNORECASE,
)

def _count_quant(s: str) -> int:
    return len(_QUANT_RE.findall(s))

def _validate_chapter_summary(payload: dict) -> None:
    bullets = payload.get("bullets") or []
    if not any(_count_quant(b) >= 1 for b in bullets):
        raise ValueError("No quantitative content in any bullet (≥1 required)")

def _validate_paper_summary(payload: dict) -> None:
    bullets = payload.get("bullets") or []
    n_quant = sum(1 for b in bullets if _count_quant(b) >= 1)
    if n_quant < 3:
        raise ValueError(f"Only {n_quant}/{len(bullets)} bullets are quantitative (≥3 required)")
    if _count_quant(payload.get("takeaway", "")) < 1:
        raise ValueError("Takeaway has no quantitative comparison")
```

Hook into existing retry loop. On 3 retries failed, fall back to whatever the LLM produced (don't completely block render) and log the violation.

**Tradeoff**: regex may miss exotic units (W/g, μA, etc.). Expanded over time. Acceptable false-negative; never false-positive (some quantitative content always passes).

**Test**: unit tests for `_count_quant` over realistic AFE/PPT bullets; integration test that a non-quantitative LLM mock triggers retry.

### T4. Loud failure logging in PptxSummarizer (observability) [audit #4]

**Evidence**: `stages/s09_render/pptx_summarizer.py` lines 232–293, 247–268, 311–326 — all three summarizer methods catch `Exception` and return `None` after 3 retries with no logging. Slides render blank with no signal.

**Fix**: at the `return None` site, log to stderr:

```python
import sys
print(
    f"[pptx_summarizer] {method_name} failed for {label} after {_MAX_RETRIES} retries: "
    f"{type(last_error).__name__}: {str(last_error)[:200]}",
    file=sys.stderr, flush=True,
)
```

`method_name ∈ {"summarize_outline", "summarize", "summarize_paper"}`; `label` = chapter heading or "paper".

**Tradeoff**: noisier output. Acceptable — failures are rare and important.

**Test**: existing failure tests assert the log is emitted (use `capsys`).

### T5. Wider figure-observation context for s08 composer (depth) [audit #2]

**Evidence**: `stages/s08_section_compose/runner.py` lines 92–102 truncate each figure's `deep_observation` (originally ~120–200 words) to 100 chars before injection into `section_compose.md`. Chapters lose critical methodological caveats and can only paraphrase.

**Code**: `stages/s08_section_compose/runner.py::_build_paper_data()`.

**Fix**: raise the `[:100]` cap to `[:400]` and the caption cap from `[:120]` to `[:300]`. Total s08 prompt grows by ~3KB on a 26-figure paper — well within new s08 max_tokens of 12000.

**Tradeoff**: longer prompt → slightly slower LLM call; better chapter analytical depth.

**Test**: snapshot a fixture chapter; assert composer receives full observation text.

---

## Tier 2 — recommended (ship if v1.3 budget allows)

### T6. Figure-slide observation vertical guard (layout, deferred from layout plan Fix C)

**Evidence**: `runs/ali2025_flash/s09_render/preview.pptx` slide 8 — observations crowd the lower-left edge near the footer with zero slack.

**Code**: `_figure()` lines 569–584, `_combined()` lines 698–717.

**Fix**: if `obs_y + n_obs * row > slide_bottom - footer_h`, drop to 12pt font and 0.60" row height for observations.

### T7. Figure observations: critique-vs-description regex enforcement [audit #6]

**Evidence**: `pptx_summarize.md` asks for "critique" but LLM sometimes outputs descriptive ("Panel (a) shows…").

**Fix**: regex reject `\b(shows|depicts|displays|illustrates|presents)\b` in observation text on retry. Soft — log + retry once, then accept.

**Risk**: rejects legitimate "shows" usage. Mitigation: only reject if NO critique markers (`limitation|caveat|missing|would|should|alternative|absent`) in the same observation.

### T8. Bigger chapter excerpt budget for synthesis [audit #8]

**Evidence**: `stages/s08_section_compose/runner.py::_relevant_chapter_excerpts()` line 160 caps at 8000 chars total. For 15-chapter papers this is ~1–2 paragraphs per referenced chapter — too little for cross-chapter contradiction detection.

**Fix**: raise to 15000 chars, or full text when `len(chapters) ≤ 10`.

**Tradeoff**: +~7KB prompt; longer LLM call; deeper synthesis.

---

## Tier 3 — defer to v1.4

### T9. Cross-renderer table styling consistency [audit #5]

DOCX uses "Light Grid" style; HTML uses bare `<table class="md-table">`; PDF inherits HTML. Tables look polished in Word, plain in HTML. Standardize: bold headers, light-gray banding, consistent border weight.

**Why deferred**: low frequency (most papers have 0–1 tables); requires CSS+docx style refactor; not blocking output.

---

## How `python-pptx` controls layout — reference (for T1–T2 implementation)

`python-pptx` is a thin XML writer; PowerPoint computes layout at render time. Three relevant knobs:

| Mechanism | What it does | Used by |
|---|---|---|
| `shape.height` + `text_frame.auto_size` (`MSO_AUTO_SIZE.NONE / SHAPE_TO_FIT_TEXT / TEXT_TO_FIT_SHAPE`) | Viewer decides whether to grow box or shrink font | T2 (autofit safety net) |
| `paragraph.space_before` / `space_after` (EMU) | Inter-paragraph spacing | T1 (gap_h) |
| `paragraph.line_spacing` (float multiplier) | Multiplier on line height | T1 (1.05 fallback) |

`python-pptx` **cannot measure rendered text width or height**. We approximate via character counts calibrated against current fonts (Crimson Pro, Songti). Calibration error ≈ ±15%, mitigated by 10% safety margin.

---

## Validation plan

After implementation:

1. `uv run pytest -q` → 172 → ~180 tests pass (each T1–T5 adds 2 tests).
2. Re-render 4 papers (yang2025, randall2021, yao2022, ali2025_flash) — all 4 formats, parallel via batch script.
3. PNG diff on outline slide + 3 section-divider slides per paper. Acceptance:
   - No takeaway second-line bleed.
   - No bullet truncated at `< 80` ASCII chars when `n_bullets ≤ 4`.
   - All quantitative-content checks pass on PPT summaries.
4. Update `CHANGELOG.md` 1.3.0; bump pyproject; tag `v1.3.0`.

---

## Scope discipline

Tier 1: ~5 files, ~120 LOC, ~10 new tests. Risk: low — additive validation + arithmetic layout, no breaking schema change.
Tier 2: another ~3 files, ~60 LOC.
Tier 3: explicitly deferred.

If user approves Tier 1 only: estimate 2 hours implementation + 30–45 min re-render verification.
If user approves Tier 1 + 2: +1 hour.

---

## Open questions (please answer before I start)

1. **Approve Tier 1 (T1–T5)?** Default: yes.
2. **Also Tier 2 (T6–T8)?** Default: yes, if no objection — these are quick wins for depth.
3. **Defer Tier 3 (T9) to v1.4?** Default: yes.
4. **Validation parallelism**: re-render the 4 papers in parallel (4× LibreOffice + render speed) or sequentially (safer for LLM rate limits)? Default: sequential at s09, parallel at LO conversion.
