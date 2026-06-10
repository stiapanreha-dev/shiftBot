#!/usr/bin/env bash
# Daily PostgreSQL backup for alex12060 + offsite copy to Google Drive.
# Cron: /etc/cron.d/alex12060-backup
set -euo pipefail

DB_NAME="alex12060"
BACKUP_DIR="/var/backups/alex12060"
KEEP_DAYS=14
BOT_DIR="/opt/alex12060-bot"

mkdir -p "$BACKUP_DIR"
stamp=$(date +%Y%m%d_%H%M%S)
outfile="$BACKUP_DIR/${DB_NAME}_${stamp}.sql.gz"

sudo -u postgres pg_dump --no-owner "$DB_NAME" | gzip > "$outfile"

# sanity: a real dump of this DB is never this small
size=$(stat -c%s "$outfile")
if [ "$size" -lt 10000 ]; then
    echo "$(date '+%F %T') ERROR: backup file too small (${size} bytes): $outfile" >&2
    exit 1
fi
echo "$(date '+%F %T') local backup OK: $outfile (${size} bytes)"

find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +"$KEEP_DAYS" -delete

# offsite copies are best effort — the local backup above is already safe
OFFSITE_HOST="root@85.239.57.119"   # SRV009
OFFSITE_DIR="/var/backups/alex12060-offsite"
OFFSITE_KEEP_DAYS=30
if scp -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$outfile" "$OFFSITE_HOST:$OFFSITE_DIR/"; then
    echo "$(date '+%F %T') offsite copy OK: $OFFSITE_HOST"
    ssh -o ConnectTimeout=15 "$OFFSITE_HOST" \
        "find $OFFSITE_DIR -name '${DB_NAME}_*.sql.gz' -mtime +$OFFSITE_KEEP_DAYS -delete" || true
else
    echo "$(date '+%F %T') WARNING: offsite copy to $OFFSITE_HOST failed" >&2
fi

# Google Drive copy: requires Drive API enabled in the service account project
if ! "$BOT_DIR/venv/bin/python" "$BOT_DIR/scripts/upload_backup_gdrive.py" "$outfile"; then
    echo "$(date '+%F %T') WARNING: Google Drive upload failed (Drive API enabled?)" >&2
fi
