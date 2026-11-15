#!/usr/bin/env bash
# Build the static website for GitHub Pages.
#
# GitHub Pages cannot run the Python server, so the site carries the backend with it:
#   <out>/            the game (frontend/game)
#   <out>/py/bundle.zip  backend/app + simulation + data, run in the browser by js/engine-worker.js
#
#   bash scripts/build_pages.sh           -> _site/          (what the GitHub workflow deploys)
#   bash scripts/build_pages.sh --local   -> frontend/game/py/bundle.zip only, to test the
#                                            in-browser engine with any static server
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" == "--local" ]]; then
  OUT="$ROOT/frontend/game"
else
  OUT="${1:-$ROOT/_site}"
  rm -rf "$OUT"
  mkdir -p "$OUT"
  cp -r "$ROOT/frontend/game/." "$OUT/"
  touch "$OUT/.nojekyll"
fi
mkdir -p "$OUT/py"
python3 - "$ROOT" "$OUT/py/bundle.zip" <<'PY'
import sys, zipfile
from pathlib import Path
root, out = Path(sys.argv[1]), Path(sys.argv[2])
skip_dirs = {"__pycache__", "tests"}
skip_files = {"backend/app/main.py", "backend/app/deps.py"}   # FastAPI only
def wanted(p: Path) -> bool:
    rel = p.relative_to(root).as_posix()
    if any(part in skip_dirs for part in p.parts) or rel in skip_files or rel.startswith("backend/app/api/"):
        return False
    return p.suffix in {".py", ".json"}
files = [root / "backend/__init__.py"]
for top in ("backend/app", "simulation", "data"):
    files += sorted(p for p in (root / top).rglob("*") if p.is_file() and wanted(p))
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, p.relative_to(root).as_posix())
print(f"{out}: {len(files)} files, {out.stat().st_size // 1024} KB")
PY
