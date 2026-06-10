#!/bin/bash
# Deploy script for Alex12060 bot -> PROD 45.81.243.7
#
# The server working tree is a git remote named 'prod'
# (receive.denyCurrentBranch=updateInstead): pushing the branch updates
# /opt/alex12060-bot directly. Auth: SSH keys only — no passwords here.
#
# One-time local setup if the remote is missing:
#   git remote add prod root@45.81.243.7:/opt/alex12060-bot
set -e

SERVER="root@45.81.243.7"
BRANCH="dev-02"

echo "=== Alex12060 Deploy Script ==="
echo ""

echo "[1/5] Pushing to origin..."
git push origin "$BRANCH"

echo "[2/5] Pushing to prod server..."
git push prod "$BRANCH"

# Stray copies use old code and corrupt data; the worker also takes a
# pg advisory lock now, this is the second line of defence.
# [p] bracket keeps pkill from matching the ssh shell running this command.
echo "[3/5] Killing ALL sync_worker processes..."
ssh "$SERVER" "pkill -9 -f '[p]g_sync_worker' || true"

echo "[4/5] Restarting services..."
ssh "$SERVER" "systemctl restart alex12060-bot alex12060-sync-worker"

echo "[5/5] Verifying..."
sleep 3
ssh "$SERVER" "systemctl is-active alex12060-bot alex12060-sync-worker"
COUNT=$(ssh "$SERVER" "pgrep -fc pg_sync_worker || true")

if [ "$COUNT" = "1" ]; then
    echo ""
    echo "✓ Deploy successful! Only 1 sync_worker running."
else
    echo ""
    echo "⚠ WARNING: $COUNT sync_worker processes running!"
    ssh "$SERVER" "ps aux | grep pg_sync_worker | grep -v grep"
    exit 1
fi
