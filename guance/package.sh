#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 3 && $# -le 4 && ( $2 == dev || $2 == release || $2 == release-size ) ]] || { echo "Usage: $0 /absolute/src dev|release|release-size /absolute/dist [amd64|arm64]" >&2; exit 2; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$script_dir/package.py" "$(realpath "$1")" "$2" "$3" "${4:-amd64}"
