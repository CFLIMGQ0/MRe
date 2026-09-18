#!/usr/bin/env bash
# Download one disjoint manifest; never delete caches or partial downloads.
set -uo pipefail

if [[ $# -ne 5 ]]; then
  echo "Usage: $0 MANIFEST DESTINATION GDC_CLIENT START_RESERVE_GIB STOP_FLOOR_GIB" >&2
  exit 2
fi
manifest="$1"
destination="$2"
gdc_client="$3"
start_reserve_gib="$4"
stop_floor_gib="$5"
if [[ ! -s "$manifest" || ! -x "$gdc_client" ]] ||
   [[ ! "$start_reserve_gib" =~ ^[0-9]+$ || ! "$stop_floor_gib" =~ ^[0-9]+$ ]] ||
   (( start_reserve_gib <= stop_floor_gib )); then
  echo "Invalid manifest, client, or reserve values" >&2
  exit 2
fi
for utility in flock setsid stat df; do
  command -v "$utility" >/dev/null || exit 2
done

# Ignore desktop and shell proxies, including on resumed runs.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY='*' no_proxy='*'

mkdir -p "$destination" || exit 2
exec 9>"$destination/.brca-download.lock"
flock -n 9 || { echo "Destination already has an active downloader" >&2; exit 3; }

timestamp() { date '+%F %T%z'; }
available_bytes() { df -B1 --output=avail "$destination" | tail -n 1 | tr -d ' '; }
required_bytes=0
total_files=0
complete_files=0
while IFS=$'\t' read -r file_id filename md5 size state; do
  [[ "$file_id" == id ]] && continue
  [[ -z "$file_id" ]] && continue
  if [[ ! "$size" =~ ^[0-9]+$ || "$filename" == */* || "$file_id" == */* ]]; then
    echo "Invalid manifest row" >&2
    exit 2
  fi
  total_files=$((total_files + 1))
  target="$destination/$file_id/$filename"
  if [[ -f "$target" ]] && [[ "$(stat -c '%s' "$target")" == "$size" ]]; then
    complete_files=$((complete_files + 1))
  else
    # Conservative on resume: count each incomplete file at its full size.
    required_bytes=$((required_bytes + size))
  fi
done < "$manifest"
(( total_files > 0 )) || exit 2
if (( complete_files == total_files )); then
  echo "[$(timestamp)] Already complete by size: $complete_files/$total_files"
  exit 0
fi
available="$(available_bytes)"
if [[ ! "$available" =~ ^[0-9]+$ ]] ||
   (( available < required_bytes + start_reserve_gib * 1073741824 )); then
  echo "[$(timestamp)] Insufficient space: required=$required_bytes available=$available reserve_gib=$start_reserve_gib" >&2
  exit 75
fi

client_pid=''
stop_client() {
  if [[ -n "$client_pid" ]] && kill -0 "$client_pid" 2>/dev/null; then
    # setsid below creates a separate group containing only this download.
    kill -TERM -- "-$client_pid" 2>/dev/null || true
  fi
}
trap 'stop_client; exit 143' TERM HUP
trap 'stop_client; exit 130' INT
echo "[$(timestamp)] START direct=true files=$total_files already_complete=$complete_files required_bytes=$required_bytes reserve_gib=$start_reserve_gib stop_floor_gib=$stop_floor_gib destination=$destination"
setsid "$gdc_client" download --manifest "$manifest" --dir "$destination" \
  --n-processes 2 --http-chunk-size 8388608 --retry-amount 50 --wait-time 30 \
  --no-related-files --no-annotations --color_off \
  --log-file "$destination/gdc-client.log" &
client_pid=$!
while kill -0 "$client_pid" 2>/dev/null; do
  available="$(available_bytes)"
  if [[ ! "$available" =~ ^[0-9]+$ ]] ||
     (( available < stop_floor_gib * 1073741824 )); then
    echo "[$(timestamp)] SPACE GUARD STOP: available=$available floor_gib=$stop_floor_gib; partial files retained" >&2
    stop_client
    wait "$client_pid" 2>/dev/null || true
    exit 75
  fi
  sleep 15
done
wait "$client_pid"
status=$?
echo "[$(timestamp)] GDC client exit=$status"
exit "$status"
