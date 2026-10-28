#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 && ( $2 == dev || $2 == release ) ]] || { echo "Usage: $0 /absolute/src dev|release /absolute/dist" >&2; exit 2; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$script_dir/package.py" "$(realpath "$1")" "$2" "$3"
