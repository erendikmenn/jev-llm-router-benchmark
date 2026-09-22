#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 OFFSET LIMIT [RESULT_ROOT]" >&2
  exit 2
fi

offset="$1"
limit="$2"
result_root="${3:-results/swebench-balanced-v2-100-20260922}"
end=$((offset + limit))
batch="$(printf '%02d' "$((offset / limit))")"
batch_dir="${result_root}/official-eval/batch-${batch}"
predictions="${batch_dir}/predictions.jsonl"
run_id="balanced-v2-registry-b${batch}"

mkdir -p "$batch_dir"
jq -s -c ".[$offset:$end][]" "${result_root}/predictions.jsonl" > "$predictions"

ids=()
images=()
while IFS= read -r instance_id; do
  ids+=("$instance_id")
  image_suffix="${instance_id/__/_1776_}"
  images+=("swebench/sweb.eval.x86_64.${image_suffix}:latest")
done < <(jq -r '.instance_id' "$predictions")

if [[ "${#ids[@]}" -ne "$limit" ]]; then
  echo "expected $limit predictions, found ${#ids[@]}" >&2
  exit 1
fi

cleanup_images() {
  for image in "${images[@]}"; do
    docker image rm "$image" >/dev/null 2>&1 || true
  done
}
trap cleanup_images EXIT

for image in "${images[@]}"; do
  docker pull --platform linux/amd64 "$image"
done

instance_args=()
for instance_id in "${ids[@]}"; do
  instance_args+=("-i" "$instance_id")
done

uvx --from swebench swebench eval verified \
  -p "$predictions" \
  --run-id "$run_id" \
  -j 2 \
  -t 1800 \
  --report-dir "$batch_dir" \
  "${instance_args[@]}"
