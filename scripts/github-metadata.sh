#!/usr/bin/env bash
# Apply the v1.1.0 GitHub repo metadata (description, topics, homepage, release notes).
# Requires `gh` CLI installed and authenticated (`gh auth login`).
#
# Run from repo root:
#   bash scripts/github-metadata.sh

set -euo pipefail

REPO="thematteroftime/lazy-paper"

echo "==> Updating repo description + homepage"
gh repo edit "$REPO" \
  --description "Turn a PDF research paper into a structured, multi-format (DOCX/PDF/HTML/PPTX) bilingual deep analysis. 9-stage pipeline · pluggable OCR + LLM · audit-resumable." \
  --homepage "https://github.com/$REPO"

echo "==> Setting topics"
gh repo edit "$REPO" \
  --add-topic pdf \
  --add-topic ocr \
  --add-topic llm \
  --add-topic deepseek \
  --add-topic qwen-vl \
  --add-topic mineru \
  --add-topic paddleocr \
  --add-topic powerpoint \
  --add-topic pptx \
  --add-topic docx \
  --add-topic weasyprint \
  --add-topic python-pptx \
  --add-topic python-docx \
  --add-topic scientific-papers \
  --add-topic literature-review \
  --add-topic academic-tools \
  --add-topic research-tool \
  --add-topic ai-agents

echo "==> Creating GitHub Release for v1.1.0"
gh release create v1.1.0 \
  --repo "$REPO" \
  --title "v1.1.0 — quality, density, hand-off" \
  --notes "$(cat <<'EOF'
Second public release. Focus: output quality, LLM cost-control knob, code/docs polish, agent-friendly hand-off.

## Highlights

- **`LLM_MAX_TOKENS_CEILING`** env var caps every LLM call site through a shared `llm.client.max_tokens()` helper (default 40000). Per-stage defaults raised: s06 1500→4000, s07 2000→4000, s08 3000→12000, s09 outline 8000→16000, s09 summary/paper 2000→8000. DeepSeek-Reasoner's chain-of-thought tokens no longer starve the final JSON content.
- **CLI `--only`** accepts comma-separated stage lists (`s08_section_compose,s09_render`) and rejects unknown stage names.
- **s08 chapter heading consistency**: template's `number` field no longer leaks into displayed headings; PPT outline renderer adds its own positional 01–N prefix.
- **PPT deep-observation typography**: 11pt → 13pt, eyebrow bold, row height 0.52" → 0.70".
- **Image-data-url helper consolidated** to `stages/_common/images.py` (HTML renderer + LLM client share it).

## Docs

- New [`docs/AGENT_GUIDE.md`](https://github.com/thematteroftime/lazy-paper/blob/main/docs/AGENT_GUIDE.md): workflow patterns, cache gotchas, anti-patterns for AI agents maintaining the repo.
- Rewritten [`docs/INTERNAL/HANDOFF.md`](https://github.com/thematteroftime/lazy-paper/blob/main/docs/INTERNAL/HANDOFF.md): verified state, 5-paper test corpus, env-var table, safe-to-delete list.
- [`docs/PPT_KNOWN_ISSUES.md`](https://github.com/thematteroftime/lazy-paper/blob/main/docs/PPT_KNOWN_ISSUES.md): triaged math-subscript font fallback + KEY POINTS card overlap for v1.2.
- New [`README.zh.md`](https://github.com/thematteroftime/lazy-paper/blob/main/README.zh.md) (Chinese mirror); README badges + tech stack table; citation block.

## Verified

5 end-to-end papers (he2023, ali2025_flash, yang2025, liu2022, pan2025) — all produce DOCX/PDF/HTML/PPTX with LLM-grouped 4–5 section outline. 158/158 unit tests pass.

See [CHANGELOG.md](https://github.com/thematteroftime/lazy-paper/blob/main/CHANGELOG.md) for the full diff.
EOF
)"

echo "==> Done"
gh repo view "$REPO"
