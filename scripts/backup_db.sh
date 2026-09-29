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

# offsite copy is best effort — the local backup above is already safe.
# Google Drive copy via rclone — OAuth of the personal Google account.
# Service accounts have no storage quota since 2025, so the SA used for
# Sheets sync cannot own files; rclone token lives in /root/.config/rclone/.
GDRIVE_REMOTE="gdrive:alex12060-db-backups"
GDRIVE_KEEP_DAYS=30
if rclone copy "$outfile" "$GDRIVE_REMOTE/" --drive-use-trash=false; then
    echo "$(date '+%F %T') Google Drive copy OK"
    rclone delete "$GDRIVE_REMOTE/" --min-age "${GDRIVE_KEEP_DAYS}d" --drive-use-trash=false || true
else
    echo "$(date '+%F %T') WARNING: Google Drive copy failed" >&2
fi
