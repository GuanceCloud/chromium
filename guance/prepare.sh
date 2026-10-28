#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 1 && $# -le 2 && $1 == /* && $1 != / ]] || { echo "Usage: $0 /absolute/build-root [amd64|arm64]" >&2; exit 2; }
arch=${2:-amd64}
[[ $arch == amd64 || $arch == arm64 ]] || { echo 'Unknown architecture' >&2; exit 2; }
[[ $(uname -m) == x86_64 ]] || { echo 'Source archive preparation requires a Linux x86_64 build host' >&2; exit 2; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(git -C "$script_dir" rev-parse --show-toplevel)
source "$script_dir/version.env"
mkdir -p "$1"
build_root=$(realpath "$1")
[[ $build_root != "$repo" && $build_root != "$repo/"* ]] || { echo 'Build outside the source-control checkout' >&2; exit 2; }
archive="$build_root/chromium-$CHROMIUM_VERSION.tar.xz"
stamp="$build_root/source.sha256"
if [[ ! -f "$stamp" ]]; then
  if [[ ! -f "$archive" ]]; then
    if command -v aria2c >/dev/null 2>&1; then
      # Hosted Ubuntu runners include aria2; parallel ranges reduce cold setup.
      aria2c --max-connection-per-server=8 --split=8 --min-split-size=16M \
        --continue=true --allow-overwrite=true --auto-file-renaming=false \
        --file-allocation=none --connect-timeout=30 --timeout=120 \
        --max-tries=3 --retry-wait=5 --lowest-speed-limit=16K \
        --summary-interval=30 --console-log-level=warn \
        --dir="$build_root" --out="$(basename "$archive.part")" "$SOURCE_URL"
    else
      curl --fail --location --retry 2 --connect-timeout 30 --max-time 1800 \
        --speed-limit 16384 --speed-time 120 --output "$archive.part" "$SOURCE_URL"
    fi
    mv -- "$archive.part" "$archive"
  fi
  echo "$SOURCE_SHA256  $archive" | sha256sum --check
  [[ ! -e "$build_root/src" ]] || { echo 'Unmanaged src directory; use a dedicated build root' >&2; exit 2; }
  mkdir "$build_root/src"
  tar -xJf "$archive" --strip-components=1 -C "$build_root/src"
  printf '%s\n' "$SOURCE_SHA256" > "$stamp"
fi
[[ $(cat "$stamp") == "$SOURCE_SHA256" ]] || { echo 'Build root belongs to a different source version' >&2; exit 2; }
git -C "$repo" cat-file -e "$CHROMIUM_BASE^{commit}" 2>/dev/null ||
  git -C "$repo" fetch --depth=1 --filter=blob:none https://github.com/chromium/chromium.git "$CHROMIUM_BASE"
python3 "$script_dir/overlay.py" "$repo" "$build_root/src" "$CHROMIUM_BASE" "$build_root/overlay-paths.json"
cd "$build_root/src"
actual=$(awk -F= '{printf "%s%s", sep, $2; sep="."}' chrome/VERSION)
[[ $actual == "$CHROMIUM_VERSION" ]] || { echo "Expected $CHROMIUM_VERSION, got $actual" >&2; exit 2; }
# The official archive includes dependencies and GN/Ninja. These upstream
# scripts fill missing toolchains and reuse their version stamps on warm runs.
python3 tools/clang/scripts/update.py
python3 tools/rust/update_rust.py
if [[ $arch == arm64 ]]; then
  python3 build/linux/sysroot_scripts/install-sysroot.py --arch=arm64
fi
for tool in buildtools/linux64/gn third_party/ninja/ninja; do
  [[ -x $tool ]] || { echo "Missing archive build tool: $tool" >&2; exit 2; }
done
