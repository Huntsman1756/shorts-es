#!/bin/sh
# Backup the parts that cannot be regenerated: the observation history.
# The workbook can always be re-fetched from CNMV, but *when we saw it*
# cannot — snapshots + SQLite + manifest are the valuable artifacts.
set -eu

DATA_DIR="${SHORTS_ES_DATA_DIR:-/data}"
BACKUP_DIR="${1:-$DATA_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"

mkdir -p "$DEST"
cp "$DATA_DIR/shorts-es.db" "$DEST/" 2>/dev/null || true
cp -r "$DATA_DIR/snapshots" "$DEST/snapshots" 2>/dev/null || true
cp "$DATA_DIR/snapshots.jsonl" "$DEST/" 2>/dev/null || true
echo "backup written to $DEST"
