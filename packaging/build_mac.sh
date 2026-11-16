#!/usr/bin/env bash
# Build ProjectStarter.app on macOS. Run from the project root: bash packaging/build_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip pyinstaller pytest >/dev/null
python -m pytest -q
pyinstaller packaging/oneclick.spec --noconfirm
ditto -c -k --sequesterRsrc --keepParent dist/ProjectStarter.app dist/ProjectStarter-macos.zip
echo "Done: dist/ProjectStarter.app  (zipped: dist/ProjectStarter-macos.zip)"
