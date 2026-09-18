#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=/home/administrator/miniconda3/envs/mrepath-train/bin/python
MODE=${1:-formal}

case "$MODE" in
  smoke)
    epochs=1
    patches=256
    folds=(0)
    results_root=results_bernoulli_kan_smoke256
    ;;
  formal)
    epochs=30
    patches=4096
    folds=(0 1 2 3 4)
    results_root=results_bernoulli_kan_5fold
    ;;
  *)
    echo "usage: $0 [smoke|formal]" >&2
    exit 2
    ;;
esac

cd "$ROOT"
for dataset in coadread stad; do
  "$PYTHON" -u scripts/run_pc_cmka_word_ablations.py \
    --dataset "$dataset" \
    --suite bernoulli_kan \
    --folds "${folds[@]}" \
    --max-epochs "$epochs" \
    --num-workers 8 \
    --num-patches "$patches" \
    --results-root "$results_root"
done
