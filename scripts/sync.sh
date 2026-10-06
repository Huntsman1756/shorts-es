#!/bin/sh
# Cron-friendly sync: fetch the CNMV source, ingest if new, re-verify.
# Example crontab (twice daily):
#   17 7,19 * * *  /opt/shorts-es/scripts/sync.sh >> /var/log/shorts-es.log 2>&1
set -eu

DATA_DIR="${SHORTS_ES_DATA_DIR:-/data}"
export SHORTS_ES_DATA_DIR="$DATA_DIR"

echo "$(date -u +%FT%TZ) sync start"
shorts-es sync
shorts-es verify || echo "$(date -u +%FT%TZ) VERIFICATION FAILED"
echo "$(date -u +%FT%TZ) sync done"
