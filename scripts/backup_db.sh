#!/usr/bin/env bash
# Copy data/progress.db into data/backups/ with a UTC timestamp.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/progress.db"
DEST_DIR="$ROOT/data/backups"
mkdir -p "$DEST_DIR"
if [[ ! -f "$SRC" ]]; then
  echo "No database at $SRC — nothing to back up."
  exit 0
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_DIR/progress_${STAMP}.db"
cp -p "$SRC" "$DEST"
echo "Backed up to $DEST"
