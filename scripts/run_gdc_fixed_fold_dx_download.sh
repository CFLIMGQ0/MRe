#!/usr/bin/env bash
set -uo pipefail

if [[ "$#" -lt 2 ]]; then
  echo "Usage: $0 DESTINATION_ROOT COHORT [COHORT ...]" >&2
  exit 2
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION_ROOT="$1"
shift
COHORTS=("$@")

MANIFEST_DIR="${GDC_MANIFEST_DIR:-${PROJECT_DIR}/gdc_download/manifests}"
GDC_CLIENT="${GDC_CLIENT:-${PROJECT_DIR}/tools/gdc-client-2.3.0/gdc-client}"
RESERVE_BYTES="${GDC_RESERVE_BYTES:-85899345920}"
N_PROCESSES="${GDC_N_PROCESSES:-4}"

if [[ ! -x "${GDC_CLIENT}" ]]; then
  echo "GDC client is not executable: ${GDC_CLIENT}" >&2
  exit 2
fi

mkdir -p "${DESTINATION_ROOT}"
exec 9>"${DESTINATION_ROOT}/.download.lock"
if ! flock -n 9; then
  echo "Another downloader already holds ${DESTINATION_ROOT}/.download.lock" >&2
  exit 3
fi

# The desktop proxy can consume metered VPN traffic. GDC is reachable directly
# from both compute hosts, so force direct IPv4-compatible networking.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
unset ALL_PROXY all_proxy NO_PROXY no_proxy

timestamp() {
  date '+%F %T%z'
}

for cohort in "${COHORTS[@]}"; do
  manifest="${MANIFEST_DIR}/tcga_${cohort}_fixed_folds_dx.tsv"
  output_dir="${DESTINATION_ROOT}/tcga_${cohort}"
  log_file="${DESTINATION_ROOT}/tcga_${cohort}.gdc-client.log"

  if [[ ! -f "${manifest}" ]]; then
    echo "[$(timestamp)] missing manifest: ${manifest}" >&2
    continue
  fi
  mkdir -p "${output_dir}"

  incomplete_ids=()
  required_bytes=0
  total_files=0
  complete_files=0
  while IFS=$'\t' read -r file_id filename md5 size state; do
    [[ "${file_id}" == "id" ]] && continue
    [[ -z "${file_id}" ]] && continue
    total_files=$((total_files + 1))
    target="${output_dir}/${file_id}/${filename}"
    if [[ -f "${target}" ]] && [[ "$(stat -c '%s' "${target}")" -eq "${size}" ]]; then
      complete_files=$((complete_files + 1))
    else
      incomplete_ids+=("${file_id}")
      required_bytes=$((required_bytes + size))
    fi
  done < "${manifest}"

  if [[ "${#incomplete_ids[@]}" -eq 0 ]]; then
    echo "[$(timestamp)] ${cohort}: complete (${complete_files}/${total_files})"
    continue
  fi

  available_bytes="$(df -B1 --output=avail "${output_dir}" | tail -n 1 | tr -d ' ')"
  needed_with_reserve=$((required_bytes + RESERVE_BYTES))
  if (( available_bytes < needed_with_reserve )); then
    echo "[$(timestamp)] ${cohort}: skipped; required=${required_bytes}, available=${available_bytes}, reserve=${RESERVE_BYTES}" >&2
    continue
  fi

  echo "[$(timestamp)] ${cohort}: downloading ${#incomplete_ids[@]} incomplete files; ${complete_files}/${total_files} already complete"
  "${GDC_CLIENT}" download \
    --dir "${output_dir}" \
    --n-processes "${N_PROCESSES}" \
    --http-chunk-size 8388608 \
    --retry-amount 50 \
    --wait-time 30 \
    --no-related-files \
    --no-annotations \
    --log-file "${log_file}" \
    --color_off \
    "${incomplete_ids[@]}"
  status=$?
  echo "[$(timestamp)] ${cohort}: gdc-client exit=${status}"
done
