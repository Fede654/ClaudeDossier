#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/builddir"

# Ensure builddir exists (do a quick rebuild if needed)
if [ ! -f "$BUILD_DIR/data/io.fede.ClaudeSessionHub.gresource" ]; then
    echo "Building resource bundle first..."
    source "$SCRIPT_DIR/.venv/bin/activate"
    meson setup "$BUILD_DIR" --wipe > /dev/null 2>&1 || true
    meson compile -C "$BUILD_DIR" > /dev/null 2>&1
fi

# Compile schemas for dev use (into build dir so we don't pollute system)
mkdir -p "$BUILD_DIR/data"
glib-compile-schemas "$SCRIPT_DIR/data/" --targetdir="$BUILD_DIR/data/" 2>/dev/null || true

export GSETTINGS_SCHEMA_DIR="$BUILD_DIR/data"
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

source "$SCRIPT_DIR/.venv/bin/activate"
exec python3 "$BUILD_DIR/local-hub" "$@"
