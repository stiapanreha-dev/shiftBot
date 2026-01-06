#!/bin/bash
# Deploy script for Alex12060 bot
# Usage: ./deploy.sh

set -e

SERVER="45.12.254.38"
USER="root"
PASS="LYagMFjFY06Q8T"
PATH_REMOTE="/opt/alex12060-bot"

echo "=== Alex12060 Deploy Script ==="
echo ""

# 1. Git push
echo "[1/5] Pushing to git..."
git push

# 2. Pull on server
echo "[2/5] Pulling on server..."
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "cd $PATH_REMOTE && git pull"

# 3. Kill ALL sync worker processes (critical!)
echo "[3/5] Killing ALL sync_worker processes..."
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "pkill -9 -f pg_sync_worker || true"

# 4. Restart services
echo "[4/5] Restarting services..."
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "systemctl restart alex12060-bot alex12060-sync-worker"

# 5. Verify only one sync worker running
echo "[5/5] Verifying..."
sleep 3
COUNT=$(sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "ps aux | grep pg_sync_worker | grep -v grep | wc -l")

if [ "$COUNT" -eq "1" ]; then
    echo ""
    echo "✓ Deploy successful! Only 1 sync_worker running."
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "ps aux | grep pg_sync_worker | grep -v grep"
else
    echo ""
    echo "⚠ WARNING: $COUNT sync_worker processes running!"
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no $USER@$SERVER "ps aux | grep pg_sync_worker | grep -v grep"
    exit 1
fi
