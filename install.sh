#!/usr/bin/env bash
# Install the InstanSeg pixi environment.
# Run this once from the InstanSeg plugin folder before using the Fiji plugin.

set -e
cd "$(dirname "$0")"

if ! command -v pixi &> /dev/null; then
    echo "ERROR: pixi not found on PATH."
    echo "Install it from https://prefix.dev/ and then re-run this script."
    exit 1
fi

echo "Installing InstanSeg environment (this may take a few minutes)..."
pixi install
echo ""
echo "Done. You can now run the InstanSeg plugin in Fiji."
