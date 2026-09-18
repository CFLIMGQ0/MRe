#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${MREPATH_PYTHON:-/home/administrator/miniconda3/envs/mrepath-train/bin/python}"
DATA_ROOT="${PROJECT_DIR}/data/tcga_brca/clam_20x_resnet50_paper_k9"
RESULTS_ROOT="${PROJECT_DIR}/results_brca_multimodal_5fold"
PREPROCESS_UNIT="mrepath-brca-preprocess-20260807.service"

cd "${PROJECT_DIR}"

while systemctl --user is-active --quiet "${PREPROCESS_UNIT}"; do
  echo "[wait] BRCA preprocessing is still active"
  sleep 60
done

h5_count="$(find "${DATA_ROOT}/h5_files" -maxdepth 1 -type f -name '*.h5' 2>/dev/null | wc -l)"
graph_count="$(find "${DATA_ROOT}/graph_files" -maxdepth 1 -type f 2>/dev/null | wc -l)"
if [[ "${h5_count}" -lt 900 ]] || [[ "${graph_count}" -lt 900 ]]; then
  echo "[error] BRCA preprocessing incomplete: h5=${h5_count}, graphs=${graph_count}"
  exit 1
fi

"${PYTHON_BIN}" scripts/convert_h5_features_to_pt.py \
  --h5-dir "${DATA_ROOT}/h5_files" \
  --pt-dir "${DATA_ROOT}/pt_files" \
  --feature-dim 1024

"${PYTHON_BIN}" scripts/prepare_coadread_legacy_baselines.py \
  --study tcga_brca --cohort brca --minimum-cases 850

export MREPATH_BASELINE_STUDY=tcga_brca
export MREPATH_BASELINE_COHORT=brca
export MREPATH_BASELINE_MINIMUM_CASES=850
export MREPATH_BASELINE_FEATURE_ROOT="${DATA_ROOT}/pt_files"
export MREPATH_PIBD_DATA_ROOT="${DATA_ROOT}"
export MREPATH_BASELINE_RESULTS="${RESULTS_ROOT}"
export MREPATH_BASELINE_EPOCHS=30
export MREPATH_BASELINE_SEED=1

bash scripts/run_coadread_legacy_multimodal.sh

MREPATH_BASELINE_MODELS="mcat motcat survpath" \
  bash scripts/run_coadread_survpath_family.sh

MREPATH_PIBD_RESULTS="${RESULTS_ROOT}/pibd" \
  bash scripts/run_coadread_pibd_resnet.sh

"${PYTHON_BIN}" main.py \
  --study tcga_brca \
  --task survival \
  --which_splits 5folds \
  --type_of_path combine \
  --modality hgnn \
  --data_root_dir "${DATA_ROOT}" \
  --label_file "${PROJECT_DIR}/datasets_csv/metadata/tcga_brca.csv" \
  --omics_dir "${PROJECT_DIR}/datasets_csv/raw_rna_data/combine/brca" \
  --results_dir "${RESULTS_ROOT}/mrepath" \
  --batch_size 1 \
  --num_workers 8 \
  --lr 0.0001 \
  --opt adam \
  --reg 0.00001 \
  --seed 1 \
  --alpha_surv 0.0 \
  --max_epochs 30 \
  --encoding_dim 1024 \
  --label_col survival_months_dss \
  --k 5 \
  --bag_loss nll_surv \
  --n_classes 4 \
  --num_patches 4096 \
  --wsi_projection_dim 256 \
  --fusion concat \
  --lr_scheduler constant \
  --warmup_epochs 0 \
  --checkpoint_selection best \
  --mrepath_graph_type shgnn \
  --mrepath_hyperedges both \
  --mrepath_weighting dynamic \
  --mrepath_fusion ifa \
  --mrepath_gene_aggregation default \
  --mrepath_genomic_encoder original

echo "[complete] BRCA paper model and seven baselines finished"
