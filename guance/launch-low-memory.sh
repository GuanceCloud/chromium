#!/bin/sh
set -eu

# Optional Chromium 156 profile. Place beside headless_shell or set the binary.
# Keep JIT, Wasm, sandbox, site isolation and CDP screenshots unchanged.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
binary=${DATAKIT_HEADLESS_SHELL_BINARY:-"$script_dir/headless_shell"}
if [ ! -x "$binary" ]; then
  echo "Set DATAKIT_HEADLESS_SHELL_BINARY to an executable Headless Shell" >&2
  exit 2
fi

# Chromium uses the last occurrence. Merge with the caller's feature policy
# rather than replacing it. ExecAllocator supplies --disable-features=value.
disabled_features=
for argument in "$@"; do
  case "$argument" in
    --disable-features=*) disabled_features=${argument#--disable-features=} ;;
  esac
done
disabled_features=${disabled_features:+$disabled_features,}SpareRendererForSitePerProcess,PartitionAllocLargeThreadCacheSize

exec "$binary" "$@" \
  "--disable-features=$disabled_features" \
  --num-raster-threads=1
