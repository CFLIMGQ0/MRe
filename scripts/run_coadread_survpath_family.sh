#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${MREPATH_PYTHON:-/home/administrator/miniconda3/envs/mrepath-train/bin/python}"
SURVPATH_REPO="${MREPATH_SURVPATH_REPO:-/home/administrator/.cache/mrepath/third_party/SurvPath}"
FEATURE_ROOT="${MREPATH_BASELINE_FEATURE_ROOT:-/home/administrator/.cache/mrepath/tcga_coadread/pibd_resnet50/pt_files}"
RESULTS_ROOT="${MREPATH_BASELINE_RESULTS:-${PROJECT_DIR}/results_coadread_multimodal_20260725}"
MODELS="${MREPATH_BASELINE_MODELS:-mcat motcat survpath}"
EPOCHS="${MREPATH_BASELINE_EPOCHS:-30}"
SEED="${MREPATH_BASELINE_SEED:-1}"
STUDY="${MREPATH_BASELINE_STUDY:-tcga_coadread}"
COHORT="${MREPATH_BASELINE_COHORT:-coadread}"

run_model() {
    local name="$1"
    local modality
    local marker="${RESULTS_ROOT}/.${name}.complete"

    if [[ "${MREPATH_RESUME_BASELINES:-0}" == "1" && -f "${marker}" ]]; then
        echo "[baseline] skipping completed ${name}"
        return 0
    fi
    case "${name}" in
        mcat) modality="coattn" ;;
        motcat) modality="coattn_motcat" ;;
        survpath) modality="survpath" ;;
        *)
            echo "Unsupported SurvPath-family model: ${name}" >&2
            return 2
            ;;
    esac

    mkdir -p "${RESULTS_ROOT}/${name}"
    echo "[baseline] starting ${name} at $(date --iso-8601=seconds)"
    (
        cd "${SURVPATH_REPO}"
        export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
        export PYTHONDONTWRITEBYTECODE=1
        export PYTHONUNBUFFERED=1
        export PYTHONWARNINGS=ignore
        "${PYTHON_BIN}" main.py \
            --study "${STUDY}" \
            --task survival \
            --split_dir splits \
            --which_splits 5foldcv \
            --type_of_path combine \
            --modality "${modality}" \
            --data_root_dir "${FEATURE_ROOT}" \
            --label_file "${PROJECT_DIR}/datasets_csv/metadata/${STUDY}.csv" \
            --omics_dir "${PROJECT_DIR}/datasets_csv/raw_rna_data/combine/${COHORT}" \
            --results_dir "${RESULTS_ROOT}/${name}" \
            --batch_size 1 \
            --lr 0.0001 \
            --opt adam \
            --reg 0.00001 \
            --alpha_surv 0.0 \
            --max_epochs "${EPOCHS}" \
            --seed "${SEED}" \
            --encoding_dim 1024 \
            --label_col survival_months_dss \
            --k 5 \
            --bag_loss nll_surv \
            --n_classes 4 \
            --num_patches 4096 \
            --wsi_projection_dim 256 \
            --fusion concat
    )
    touch "${marker}"
    echo "[baseline] finished ${name} at $(date --iso-8601=seconds)"
}

for model in ${MODELS}; do
    mkdir -p "${RESULTS_ROOT}/${model}"
    run_model "${model}" 2>&1 | tee -a "${RESULTS_ROOT}/${model}.log"
done
