#!/bin/zsh
set -eu
JARVIS_DIR="${0:A:h}"
cd -- "$JARVIS_DIR"

fail() {
  print -u2 -- "$1"
  read -r "?Press Return to close this window. " || true
  exit 1
}

[[ "$(uname -s)" == "Darwin" ]] || fail "Building the app requires macOS."
if [[ ! -x "$JARVIS_DIR/.venv/bin/python" ]]; then
  JARVIS_PYTHON=""
  for JARVIS_CANDIDATE in python3.12 python3.14 python3.13 python3.11 python3.15 python3; do
    if command -v "$JARVIS_CANDIDATE" >/dev/null 2>&1 && "$JARVIS_CANDIDATE" -c 'import platform, sys; sys.exit(0 if sys.version_info >= (3, 11) and platform.machine() == "arm64" else 1)' >/dev/null 2>&1; then
      JARVIS_PYTHON="$(command -v "$JARVIS_CANDIDATE")"
      break
    fi
  done
  [[ -n "$JARVIS_PYTHON" ]] || fail "Install native Apple Silicon Python 3.11 or newer first. See README.md."
  "$JARVIS_PYTHON" -m venv "$JARVIS_DIR/.venv" || fail "Could not create .venv. See README.md."
fi
JARVIS_PYTHON="$JARVIS_DIR/.venv/bin/python"
"$JARVIS_PYTHON" -c 'import platform, sys; sys.exit(0 if sys.version_info >= (3, 11) and platform.machine() == "arm64" else 1)' || fail "The existing .venv needs native Apple Silicon Python 3.11+."
print -- "Installing optional app-building dependencies..."
"$JARVIS_PYTHON" -m pip install -r "$JARVIS_DIR/requirements-build.txt" || fail "Could not install app-building dependencies."
print -- "Building a local app. This does not add a Developer ID signature or notarize the result."
"$JARVIS_PYTHON" "$JARVIS_DIR/setup_app.py" py2app || fail "App build failed. Read the error above and README.md."
print -- "Built: $JARVIS_DIR/dist/Jarvis Wi-Fi Discovery.app"
print -- "Read the README permission/signing section before expecting SSIDs or BSSIDs."
read -r "?Press Return to close this window. " || true
