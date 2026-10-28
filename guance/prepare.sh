#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 && $1 == /* && $1 != / ]] || { echo "Usage: $0 /absolute/build-root" >&2; exit 2; }
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
    curl --fail --location --retry 3 --output "$archive.part" "$SOURCE_URL"
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
for tool in buildtools/linux64/gn third_party/ninja/ninja; do
  [[ -x $tool ]] || { echo "Missing archive build tool: $tool" >&2; exit 2; }
done
