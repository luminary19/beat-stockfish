#!/usr/bin/env bash
# Step 1 of the prompt-intervention study: re-baseline GPT-6 Astra on the current
# build, with and without a placebo operator prompt. Usage: run_step1.sh baseline|placebo
set -euo pipefail
cd "$(dirname "$0")/.."
arm="$1"
extra=()
case "$arm" in
  baseline) ;;
  placebo) extra=(--system-prompt-file experiments/prefills/placebo-helpful-assistant.txt) ;;
  *) echo "unknown arm: $arm" >&2; exit 2 ;;
esac
exec .venv/bin/python run/rollout.py --model openai/gpt-6-astra --epochs 20 \
  --debrief --max-samples 2 --log-dir "logs/step1-$arm" "${extra[@]}"
