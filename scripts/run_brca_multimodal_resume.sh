#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${MREPATH_PYTHON:-/home/administrator/miniconda3/envs/mrepath-train/bin/python}"
CMTA_REPO="${MREPATH_CMTA_REPO:-/home/administrator/.cache/mrepath/third_party/CMTA}"
DATA_ROOT="${PROJECT_DIR}/data/tcga_brca/clam_20x_resnet50_paper_k9"
RESULTS_ROOT="${PROJECT_DIR}/results_brca_multimodal_5fold"
ORIGINAL_CMTA_RUN="${RESULTS_ROOT}/cmta/tcga_brca/[cmta]-[concat]-[1.0]-[2026-08-08]-[00-40-44]"
RESUME_ROOT="${RESULTS_ROOT}/cmta_resume"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export PYTHONWARNINGS=ignore

cd "${PROJECT_DIR}"

"${PYTHON_BIN}" scripts/prepare_coadread_legacy_baselines.py \
  --study tcga_brca --cohort brca --minimum-cases 850

for fold in 3 4; do
  fold_root="${RESUME_ROOT}/fold_${fold}"
  marker="${fold_root}/COMPLETE"
  if [[ -f "${marker}" ]]; then
    echo "[resume] CMTA fold ${fold} already complete"
    continue
  fi
  mkdir -p "${fold_root}"
  echo "[resume] starting CMTA fold ${fold} at $(date --iso-8601=seconds)"
  (
    cd "${CMTA_REPO}"
    MREPATH_CMTA_FOLDS="${fold}" \
    MREPATH_CMTA_FIXED_RESULTS_DIR="${fold_root}" \
      "${PYTHON_BIN}" main.py \
        --dataset tcga_brca \
        --data_root_dir "${DATA_ROOT}" \
        --results_dir "${RESULTS_ROOT}/cmta" \
        --which_splits 5foldcv \
        --modal coattn \
        --model cmta \
        --num_epoch 30 \
        --batch_size 1 \
        --loss nll_surv_l1 \
        --lr 0.0001 \
        --weight_decay 0.00001 \
        --optimizer Adam \
        --scheduler None \
        --alpha 1.0 \
        --OOM 4096 \
        --seed 1
  ) 2>&1 | tee -a "${RESULTS_ROOT}/cmta_resume_fold_${fold}.log"
  [[ -s "${fold_root}/partial_results.csv" ]]
  touch "${marker}"
  echo "[resume] finished CMTA fold ${fold} at $(date --iso-8601=seconds)"
done

"${PYTHON_BIN}" scripts/aggregate_brca_cmta_resume.py \
  --original-run "${ORIGINAL_CMTA_RUN}" \
  --resume-root "${RESUME_ROOT}" \
  --output "${RESULTS_ROOT}/cmta/fold_metrics.csv"

export MREPATH_SKIP_CMTA=1
export MREPATH_RESUME_BASELINES=1
bash scripts/run_brca_multimodal_suite.sh
