#!/usr/bin/env bash
# Copy the Subtree plugin into the Sublime Text user packages directory on Linux.
# Override the destination with SUBLIME_PACKAGES_DIR=... if your Sublime install
# uses a non-standard location.

set -euo pipefail

PACKAGES_DIR="${SUBLIME_PACKAGES_DIR:-$HOME/.config/sublime-text/Packages}"
TARGET="$PACKAGES_DIR/Subtree"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "$PACKAGES_DIR" ]]; then
    echo "error: Sublime Text Packages directory not found: $PACKAGES_DIR" >&2
    echo "       set SUBLIME_PACKAGES_DIR=... if Sublime is installed elsewhere." >&2
    exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
    echo "error: rsync is required but not found on PATH." >&2
    exit 1
fi

echo "Installing Subtree:"
echo "  source: $SOURCE_DIR"
echo "  target: $TARGET"

mkdir -p "$TARGET"

rsync -a --delete \
    --exclude='.git/' \
    --exclude='.gitignore' \
    --exclude='tests/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='install-linux.sh' \
    "$SOURCE_DIR/" "$TARGET/"

echo "Done. Restart Sublime Text (or reload the plugin) to pick up changes."
