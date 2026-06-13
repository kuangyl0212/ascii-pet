#!/bin/bash
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"
BIN="${HOME}/.local/bin"

mkdir -p "$BIN"

cp "$REPO/ascii-pet" "$BIN/ascii-pet"
cp "$REPO/ascii-pet-launcher" "$BIN/ascii-pet-launcher"
chmod +x "$BIN/ascii-pet" "$BIN/ascii-pet-launcher"

echo "Installed. Launching..."
exec "$BIN/ascii-pet-launcher"
