#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
for script in ./*.sh; do bash -n "$script"; done
python3 - <<'PY'
from pathlib import Path
for path in Path('.').glob('*.py'):
    compile(path.read_text(), str(path), 'exec')
PY
node --check smoke.cjs
python3 -m unittest -q overlay_test
source version.env
[[ $CHROMIUM_BASE =~ ^[a-f0-9]{40}$ && $SOURCE_SHA256 =~ ^[a-f0-9]{64}$ ]]
for file in baseline.gn lean.gn README.md; do test -s "$file"; done
