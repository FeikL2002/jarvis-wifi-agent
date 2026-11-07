#!/bin/zsh
set -eu
JARVIS_DIR="${0:A:h}"
cd -- "$JARVIS_DIR"

fail() {
  print -u2 -- "$1"
  read -r "?Press Return to close this window. " || true
  exit 1
}

[[ "$(uname -s)" == "Darwin" ]] || fail "Jarvis Wi-Fi Discovery requires macOS."
if [[ ! -x "$JARVIS_DIR/.venv/bin/python" ]]; then
  JARVIS_PYTHON=""
  for JARVIS_CANDIDATE in python3.12 python3.14 python3.13 python3.11 python3.15 python3; do
    if command -v "$JARVIS_CANDIDATE" >/dev/null 2>&1 && "$JARVIS_CANDIDATE" -c 'import platform, sys; sys.exit(0 if sys.version_info >= (3, 11) and platform.machine() == "arm64" else 1)' >/dev/null 2>&1; then
      JARVIS_PYTHON="$(command -v "$JARVIS_CANDIDATE")"
      break
    fi
  done
  [[ -n "$JARVIS_PYTHON" ]] || fail "Install a native Apple Silicon Python 3.11 or newer, then launch Jarvis again. See README.md."
  print -- "Creating Jarvis's Python environment in this folder..."
  "$JARVIS_PYTHON" -m venv "$JARVIS_DIR/.venv" || fail "Could not create .venv. See README.md for manual setup."
fi
JARVIS_PYTHON="$JARVIS_DIR/.venv/bin/python"
"$JARVIS_PYTHON" -c 'import platform, sys; sys.exit(0 if sys.version_info >= (3, 11) and platform.machine() == "arm64" else 1)' || fail "The existing .venv needs native Apple Silicon Python 3.11+. See README.md to recreate it."
if ! "$JARVIS_PYTHON" -c 'from importlib.metadata import version; import CoreWLAN, CoreLocation; assert version("pyobjc-framework-CoreWLAN") == "13.0"; assert version("pyobjc-framework-CoreLocation") == "13.0"' >/dev/null 2>&1; then
  print -- "Installing the two macOS framework bridges..."
  "$JARVIS_PYTHON" -m pip install -r "$JARVIS_DIR/requirements.txt" || fail "Dependency installation failed. Check your internet connection and README.md."
fi
print -- "Starting Jarvis Wi-Fi Discovery. Keep this window open; press Control-C to stop."
exec "$JARVIS_PYTHON" "$JARVIS_DIR/app.py" "$@"
