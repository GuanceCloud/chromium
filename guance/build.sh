#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 3 && $# -le 4 ]] || { echo "Usage: $0 /absolute/src dev|release|release-size|release-compact jobs [amd64|arm64]" >&2; exit 2; }
source_dir=$(realpath "$1")
mode=$2
jobs=$3
arch=${4:-amd64}
[[ $arch == amd64 || $arch == arm64 ]] || { echo 'Unknown architecture' >&2; exit 2; }
[[ $mode == dev || $mode == release || $mode == release-size || $mode == release-compact ]] || { echo 'Unknown build mode' >&2; exit 2; }
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'Jobs must be a positive integer' >&2; exit 2; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/version.env"
cd "$source_dir"
version=$(awk -F= '{printf "%s%s", sep, $2; sep="."}' chrome/VERSION)
[[ $version == "$CHROMIUM_VERSION" ]] || { echo "Expected $CHROMIUM_VERSION, got $version" >&2; exit 2; }
output="out/Guance-$mode"
if [[ $arch == arm64 ]]; then output="out/Guance-arm64-$mode"; fi
mkdir -p "$output"
cp "$script_dir/baseline.gn" "$output/baseline.gn"
# Upstream license generation copies args.gn to a temporary GN output directory.
# Flatten this local import so that metadata discovery can reuse the arguments.
cat "$script_dir/baseline.gn" > "$output/args.gn"
sed '/^import("baseline.gn")$/d' "$script_dir/lean.gn" >> "$output/args.gn"
if [[ $arch == arm64 ]]; then printf '\ntarget_cpu = "arm64"\n' >> "$output/args.gn"; fi
if [[ $mode == dev ]]; then
  # CFI requires ThinLTO. This profile is only for development verification.
  printf '\n# Development only: reduce cold compile/link time.\nchrome_pgo_phase = 0\nuse_thin_lto = false\nis_cfi = false\n' >> "$output/args.gn"
fi
if [[ $mode == release-size || $mode == release-compact ]]; then
  printf '\n# Experimental: measure PSS and throughput before adopting.\noptimize_for_size = true\n' >> "$output/args.gn"
fi
if [[ $mode == release-compact ]]; then
  printf '\n# Experimental: rebuild all C++ with relative vtables.\nuse_relative_vtables_abi = true\n' >> "$output/args.gn"
fi
# Nested V8 metagen GN invocations also need this restricted root.
if ! grep -q '^# Guance Headless Shell build scope$' .gn; then
  printf '\n# Guance Headless Shell build scope\nroot = "//headless"\nroot_patterns = [ "//headless:headless_shell" ]\n' >> .gn
fi
buildtools/linux64/gn gen "$output" --root-target=//headless \
  --root-pattern=//headless:headless_shell --fail-on-unused-args
buildtools/linux64/gn args "$output" --list --short > "$output/effective-args.gn"
third_party/ninja/ninja -C "$output" -j "$jobs" headless_shell
