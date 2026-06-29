#!/usr/bin/env bash
# Install the InstanSeg pixi environment into ~/.instanseg so that
# Fiji's script discovery never sees the environment files.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.instanseg"

echo "InstanSeg environment will be installed to:"
echo "  $INSTALL_DIR"
echo

if ! command -v pixi &>/dev/null; then
    echo "ERROR: pixi not found on PATH."
    echo "Install it from https://prefix.dev/ and then re-run this script."
    exit 1
fi

mkdir -p "$INSTALL_DIR"

echo "Copying environment files..."
cp "$SCRIPT_DIR/pixi.toml" "$INSTALL_DIR/pixi.toml"
[ -f "$SCRIPT_DIR/pixi.lock" ] && cp "$SCRIPT_DIR/pixi.lock" "$INSTALL_DIR/pixi.lock"

cd "$INSTALL_DIR"
echo "Installing InstanSeg environment (this may take a few minutes)..."
pixi install

echo
echo "Done. Python environment is at:"
echo "  $INSTALL_DIR/.pixi/envs/default"
echo "You can now run the InstanSeg plugin in Fiji."
