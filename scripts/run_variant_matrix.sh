#!/usr/bin/env bash
# scripts/run_variant_matrix.sh
# Run a single (variant, paper, run_idx) combo end-to-end.
# Usage: ./scripts/run_variant_matrix.sh <variant> <paper_id> <run_idx>
#   variant ∈ {a, b, c}
#   paper_id matches a directory under runs/ (with existing s01-s07)
#   run_idx is the repetition index (1 for non-meng, 1-3 for meng2024)

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <variant: a|b|c> <paper_id> <run_idx>" >&2
  exit 2
fi

variant="$1"
paper="$2"
run="$3"

case "$variant" in
  a) wt=".worktrees/variant-a-env" ;;
  b) wt=".worktrees/variant-b-cap" ;;
  c) wt=".worktrees/variant-c-figure" ;;
  *) echo "unknown variant: $variant"; exit 2 ;;
esac

# Find the project root (where this script lives)
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
repo_root=$(cd -- "${script_dir}/.." >/dev/null 2>&1 && pwd)
cd "${repo_root}"

new_id="${paper}_v${variant}_r${run}"
src_run="runs/${paper}"

# Copy cached s01-s07 from existing baseline run to avoid re-OCR
if [ ! -d "${src_run}" ]; then
  echo "ERROR: ${src_run} missing — cannot reuse OCR cache" >&2
  echo "Hint: run baseline (s01-s07) for this paper first." >&2
  exit 1
fi

target_runs_dir="${wt}/runs"
mkdir -p "${target_runs_dir}/${new_id}"

for stage in s01_ocr s02_clean s03_chapter s04_figures s05_template \
             s06_context s07_figure_analyze; do
  if [ -d "${src_run}/${stage}" ]; then
    # Copy only if not already present (idempotent re-runs)
    if [ ! -d "${target_runs_dir}/${new_id}/${stage}" ]; then
      cp -r "${src_run}/${stage}" "${target_runs_dir}/${new_id}/"
    fi
  fi
done

# Read pdf and template from baseline meta.yaml — argparse requires both flags
# even when only running s08/s09 (they are not used by those stages directly).
meta_yaml="${src_run}/meta.yaml"
if [ ! -f "${meta_yaml}" ]; then
  echo "ERROR: ${meta_yaml} not found — baseline run must have a meta.yaml" >&2
  exit 1
fi

# Extract pdf and template paths from meta.yaml (handles multi-line YAML strings)
orig_pdf=$(uv run python -c "
import yaml, sys
m = yaml.safe_load(open('${meta_yaml}'))
print(m['pdf'])
")
orig_template=$(uv run python -c "
import yaml, sys
m = yaml.safe_load(open('${meta_yaml}'))
print(m['template'])
")

if [ -z "${orig_pdf}" ] || [ -z "${orig_template}" ]; then
  echo "ERROR: could not extract pdf/template from ${meta_yaml}" >&2
  exit 1
fi

cd "${wt}"

# Source variant-specific .env.local if present (variant A uses this for env tuning)
if [ -f .env.local ]; then
  set -a
  # shellcheck disable=SC1091
  . .env.local
  set +a
fi

# Run s08 + s09 only (rest is cached). Capture stdout+stderr to s08.log.
echo "[run-matrix] starting ${new_id} (variant ${variant})" >&2
uv run lazy-paper run \
  --pdf "${orig_pdf}" \
  --template "${orig_template}" \
  --paper-id "${new_id}" \
  --only s08_section_compose,s09_render \
  --force \
  --runs-dir runs \
  2>&1 | tee "runs/${new_id}/s08.log"

# Back to repo root for metric collection
cd "${repo_root}"

# Collect metrics on the worktree's run dir
uv run python scripts/collect_variant_metrics.py "${target_runs_dir}/${new_id}"

echo "[run-matrix] done: ${new_id}" >&2
