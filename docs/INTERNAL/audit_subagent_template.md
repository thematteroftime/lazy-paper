# Audit Subagent Prompt Template

Hard-won discipline from the v1.10 → v1.11.4 session (5 audit-methodology
reversals on shipped or near-shipped fixes). Use this template as the
opening of every audit-subagent prompt that judges whether a bug is
real, a fix landed correctly, or a refactor is safe.

## The 5 reversals (what this template prevents)

1. **Cycle 12 #1 (ali2025 ch13 "fabrication")** — plain `grep "17.3"`
   missed OCR-tokenised `$\sim 1 7 . 3$`. Hotfix patch added and reverted.
2. **Cycle 12 #3 (559 LOC "dead code")** — every candidate was env-gated
   live wiring. Would have catastrophically deleted production code.
3. **Cycle 13 (retriever cap 12→24)** — Meta #2 recommended without
   sanity run; fix didn't address ch06 binding bug + introduced -60 %
   chapter collapse on meng2024.
4. **Cycle 14 F1 (numeric verifier)** — designed against OCR-split chunks
   without empirical test; Meta #2 ran it and found 4/5 false positives.
5. **Cycle 14 F4 (ch07 "no-retry" diagnosis)** — Meta #1 read code path
   wrongly; Meta #2 ran the chapter and found retry HAD fired, true
   problem was a swap-guard rejection.

## Mandatory rules for an audit subagent

### 1. Do not cite the spec. Cite the file.

If the spec says "ali2025 chunks contain 17.3", you must independently
verify: `uv run python scripts/audit_grep.py 17.3 runs/ali2025_flash/s02_clean/`
and quote the verbatim hit line back in your report. Saying "spec X said
Y" is not evidence; it is a citation of someone else's claim.

### 2. Never use `grep` on OCR'd source. Use `audit_grep.py`.

MinerU OCR encodes numerics as LaTeX char streams (`$\sim 1 7 . 3$`).
A plain `grep` for `17.3` silently misses every such case. The
`scripts/audit_grep.py` tool normalises both pattern and source with
`stages._common.normalize.normalize_ocr_latex` (the same normaliser the
s08 verifier uses).

### 3. Test the design empirically before recommending a fix.

If your fix is "regex extract numerics + substring-check chunks", you
must run that exact logic on at least one real chapter and report the
hit/miss count. Designs that look correct in the abstract reliably
break on OCR-fragmented chunks — every reversal in this project's
history had this exact shape.

### 4. Worktree-gate any fix that touches a prompt or a verifier.

For changes to `llm/prompts/*.md` or `verify_section_draft`, work in an
isolated git worktree, snapshot baseline grep counts before the change,
run the fix on at least meng2024 + ali2025_flash, assert the canary
metrics (e.g. meng2024 T1 = 9/9/9; ch06 contains `5.00` AND `340` AND
NOT `214`), and only fast-forward merge into `main` if all assertions
pass. Otherwise `git worktree remove --force` — no partial fixes on
`main`.

### 5. Two independent meta-auditors when stakes are high.

Cycle 12 / 13 / 14 / 15 each saw Meta #2 reverse Meta #1's recommendation
after running the proposed fix on real data. Two meta auditors with no
shared context is cheap insurance; both should grep / run code
independently, not cite each other. The disagreement IS the audit
signal.

### 6. Don't synthesise away the dissent.

If Meta #2 says the fix breaks ch06 and Meta #1 says ship, the right
move is "stop, run the empirical comparison". The wrong move is "ship
because the average vote leans approve."

### 7. State your confidence and what would change it.

End every audit report with one paragraph:

- **What you verified by direct file/grep:** ...
- **What you inferred from spec or upstream report:** ...
- **What evidence would flip your recommendation:** ...

If "nothing would flip my recommendation," you're not auditing, you're
voting.

## Recommended audit-subagent prompt skeleton

```
You are audit subagent <N> on cycle <K> investigating <ONE-LINE
QUESTION>. You may NOT cite the spec; you MUST cite the file path and
the verbatim grep / read output you got from running the command
yourself. For numeric verification against OCR source, use
`scripts/audit_grep.py`, NEVER plain `grep`. Your output goes to
`/tmp/cycle<K>_<role>_<N>.md` and contains:

1. ## Verify: <claim> — your command + verbatim output + verdict
   (repeat for each claim you investigated)
2. ## What you inferred (not verified) and why you couldn't verify
3. ## Recommendation + what evidence would flip it
4. ## 1-line decision
```

## When the rules will feel like overkill

When the patch is 2 LOC of doc/literal alignment (e.g. v1.11.4 `#3 +
#5`), running 3 spec + 2 meta is overkill. Skip the audit committee for
zero-blast-radius drive-by changes — but bring the full committee back
the moment a fix touches a verifier, a prompt, a retrieval threshold,
or an LLM-call wiring change.
