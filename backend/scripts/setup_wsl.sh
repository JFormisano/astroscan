#!/usr/bin/env bash
# Set up the REAL plate solver outside Docker, on Ubuntu/Debian (WSL on Windows works).
# After this, `pytest` runs the solver tests that otherwise skip, and uvicorn can use solve-field.
#
#   wsl -d Ubuntu
#   cd /mnt/c/UBHACK2026/astroscan/backend
#   bash scripts/setup_wsl.sh
#   source ~/.astroscan/env.sh && pytest
#
# Installs: astrometry.net (apt), the 4110-4119 star-index files (~46 MB, checksum-verified), a
# Python venv with requirements.txt, and ~/.astroscan/env.sh to activate all of it.
# Safe to re-run: it skips what is already there. Needs sudo only for the apt step.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${ASTROSCAN_HOME:-$HOME/.astroscan}"
INDEX_DIR="$HOME_DIR/index"
VENV_DIR="$HOME_DIR/venv"
CFG="$HOME_DIR/astrometry.cfg"
INDEX_URL="https://data.astrometry.net/4100"
mkdir -p "$INDEX_DIR"

say() { printf '\n==> %s\n' "$*"; }

say "1/4 system packages (astrometry.net, curl, python venv)"
if command -v solve-field >/dev/null && command -v astrometry-engine >/dev/null && command -v curl >/dev/null \
   && python3 -m venv --help >/dev/null 2>&1; then
  echo "already installed: $(command -v solve-field)"
else
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y --no-install-recommends astrometry.net curl ca-certificates python3-venv python3-pip
fi

say "2/4 star-index files 4110-4119 into $INDEX_DIR"
cd "$INDEX_DIR"
curl -fsSL -o md5sums.txt "$INDEX_URL/md5sums.txt"
for n in 4110 4111 4112 4113 4114 4115 4116 4117 4118 4119; do
  f="index-$n.fits"
  if [ -f "$f" ] && grep " $f\$" md5sums.txt | md5sum -c --status - 2>/dev/null; then
    echo "have $f"
  else
    echo "downloading $f"
    curl -fsSL -o "$f" "$INDEX_URL/$f"
  fi
done
grep -E 'index-41(1[0-9])' md5sums.txt | md5sum -c - >/dev/null && echo "checksums ok"
rm -f md5sums.txt
printf 'add_path %s\nautoindex\ncpulimit 300\n' "$INDEX_DIR" > "$CFG"

say "3/4 Python environment in $VENV_DIR"
[ -d "$VENV_DIR" ] || python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

say "4/4 environment file"
cat > "$HOME_DIR/env.sh" <<EOF
# source this:  source ~/.astroscan/env.sh
source "$VENV_DIR/bin/activate"
export ASTROMETRY_INDEX_DIR="$INDEX_DIR"
export ASTROMETRY_CONFIG="$CFG"
# Optional: point at the test photos so the real-photo tests run (they are git-ignored).
[ -d "$BACKEND_DIR/../test_photos" ] && export TEST_PHOTOS_DIR="$(cd "$BACKEND_DIR/.." && pwd)/test_photos"
EOF

echo
echo "Done. astrometry.net $(dpkg-query -W -f='${Version}' astrometry.net 2>/dev/null || echo installed)"
echo "Next:  source $HOME_DIR/env.sh && cd $BACKEND_DIR && pytest -q"
