# DEPLOYMENT GUIDE: Standalone Sync Worker Service

**Version:** 2.1.0 (PROMPT 3.3)
**Date:** 2025-11-11
**Server:** Pi4-2
**Status:** Ready for deployment

---

## 📋 Overview

This guide describes deployment of a **standalone sync worker** as a separate systemd service.

### Architecture:

**Before (v2.0.0):**
```
Bot Process (alex12060-bot.service)
├── HybridService (reads from SQLite)
└── Background Sync Worker (runs inside bot process)
```

**After (v2.1.0):**
```
Bot Process (alex12060-bot.service)
└── HybridService (reads from SQLite, no background sync)

Sync Worker Process (alex12060-sync-worker.service)
└── Standalone Sync Worker (syncs Sheets ↔ SQLite every 5 min)
```

### Benefits:

✅ **Independence:** Sync worker can be restarted without affecting bot
✅ **Reliability:** Bot continues working even if sync fails
✅ **Monitoring:** Separate logs for sync operations
✅ **Resource control:** CPU and memory limits for sync worker
✅ **Flexibility:** Can adjust sync interval without restarting bot

---

## 📦 New Files

| File | Description |
|------|-------------|
| `sync_worker.py` | Standalone sync worker script (220 lines) |
| `alex12060-sync-worker.service` | Systemd service file |
| `DEPLOY_SYNC_WORKER.md` | This deployment guide |

**Modified files:**
| File | Changes |
|------|---------|
| `services.py` | Set `auto_sync=False` in HybridService |

**Runtime files:**
| File | Description |
|------|-------------|
| `sync_worker.log` | Sync worker logs (auto-created) |

---

## 🚀 Deployment Steps

### Step 1: Backup current state

```bash
# On server Pi4-2
ssh Pi4-2
cd /home/lexun/Alex12060

# Backup current files
cp services.py services.py.backup_v2.0.0
tar -czf backup_v2.0.0_$(date +%Y%m%d_%H%M%S).tar.gz *.py *.service *.md
```

### Step 2: Upload new files

**From local machine:**

```bash
cd /home/lexun/work/KWORK/Alex12060

# Upload sync worker script
scp sync_worker.py Pi4-2:/home/lexun/Alex12060/

# Upload systemd service file
scp alex12060-sync-worker.service Pi4-2:/home/lexun/Alex12060/

# Upload updated services.py
scp services.py Pi4-2:/home/lexun/Alex12060/

# Upload documentation
scp DEPLOY_SYNC_WORKER.md Pi4-2:/home/lexun/Alex12060/
```

### Step 3: Make sync_worker.py executable

```bash
# On server Pi4-2
ssh Pi4-2
cd /home/lexun/Alex12060

chmod +x sync_worker.py

# Verify
ls -lh sync_worker.py
```

### Step 4: Test sync worker manually

```bash
# Run sync worker once (test mode)
venv/bin/python3 sync_worker.py --once

# Expected output:
#   StandaloneSyncWorker initialized (interval: 300s)
#   Running sync worker in ONCE mode
#   Database schema initialized
#   Starting sync cycle #1
#   Pulling changes from Google Sheets...
#   Pulled 7 EmployeeSettings records
#   Pulled 4 DynamicRates records
#   Pulled 6 Ranks records
#   Pull completed: {...}
#   Sync cycle #1 completed in X.XXs
#   Sync completed successfully
```

**If test fails:** Check error messages and fix before proceeding

### Step 5: Install systemd service

```bash
# Copy service file to systemd directory
sudo cp alex12060-sync-worker.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Check service file loaded
sudo systemctl status alex12060-sync-worker

# Should show:
#   Loaded: loaded (/etc/systemd/system/alex12060-sync-worker.service; disabled)
#   Active: inactive (dead)
```

### Step 6: Restart bot with new configuration

**IMPORTANT:** The bot needs to be restarted to use the new `services.py` (with `auto_sync=False`)

```bash
# Stop bot
sudo systemctl stop alex12060-bot

# Start bot
sudo systemctl start alex12060-bot

# Check bot logs
tail -20 /home/lexun/Alex12060/bot.log

# Should see:
#   ✓ CacheManager initialized
#   ✓ Database schema initialized
#   ✓ Performing initial sync from Google Sheets...
#   ✓ Initial sync completed: {...}
#   ✓ HybridService initialized (sync handled by alex12060-sync-worker service)
#   ✓ Bot started successfully
```

**Note:** Bot still performs initial sync on startup, but does NOT start background worker

### Step 7: Start sync worker service

```bash
# Start sync worker
sudo systemctl start alex12060-sync-worker

# Check status
sudo systemctl status alex12060-sync-worker

# Should show:
#   Active: active (running) since ...
#   Main PID: XXXX (python3)
```

### Step 8: Monitor sync worker logs

```bash
# Watch sync worker logs
tail -f /home/lexun/Alex12060/sync_worker.log

# Expected output:
#   SYNC WORKER STARTING
#   Mode: CONTINUOUS
#   Interval: 300 seconds
#   Database: data/reference_data.db
#   Initializing Google Sheets service...
#   Initializing sync manager...
#   Services initialized successfully
#   Performing initial sync...
#   Starting sync cycle #1
#   ...
#   Sync cycle #1 completed in X.XXs
#   Entering continuous sync loop...
#   Next sync at HH:MM:SS (300s)
```

### Step 9: Enable auto-start on boot

```bash
# Enable sync worker to start on boot
sudo systemctl enable alex12060-sync-worker

# Verify
sudo systemctl is-enabled alex12060-sync-worker
# Should output: enabled
```

### Step 10: Verify both services running

```bash
# Check both services
sudo systemctl status alex12060-bot alex12060-sync-worker

# Should show:
#   alex12060-bot.service - Alex12060 Telegram Bot
#      Active: active (running)
#
#   alex12060-sync-worker.service - Alex12060 Sync Worker
#      Active: active (running)

# Check processes
pgrep -af "python3.*Alex12060"

# Should show TWO processes:
#   XXXX /home/lexun/Alex12060/venv/bin/python3 /home/lexun/Alex12060/bot.py
#   YYYY /home/lexun/Alex12060/venv/bin/python3 /home/lexun/Alex12060/sync_worker.py --interval 300
```

---

## 🔍 Verification

### Check 1: Both services running

```bash
sudo systemctl is-active alex12060-bot alex12060-sync-worker

# Should output:
#   active
#   active
```

### Check 2: Sync worker performing syncs

```bash
# Wait 5 minutes and check logs
tail -50 sync_worker.log | grep "Sync cycle"

# Should show multiple sync cycles:
#   Sync cycle #1 completed in X.XXs
#   Sync cycle #2 completed in X.XXs
#   ...
```

### Check 3: Bot using SQLite (not syncing)

```bash
# Check bot logs - should NOT see background sync messages
grep -i "background sync" bot.log

# Should be empty (bot is not doing background sync anymore)

# Check HybridService message
grep "HybridService initialized" bot.log

# Should show:
#   ✓ HybridService initialized (sync handled by alex12060-sync-worker service)
```

### Check 4: Database being updated

```bash
# Check last modification time of database
ls -lh data/reference_data.db

# After 5 minutes, check again - mtime should be updated
```

---

## 🎛️ Service Management

### Starting/Stopping

```bash
# Stop sync worker
sudo systemctl stop alex12060-sync-worker

# Start sync worker
sudo systemctl start alex12060-sync-worker

# Restart sync worker
sudo systemctl restart alex12060-sync-worker

# Stop both services
sudo systemctl stop alex12060-bot alex12060-sync-worker

# Start both services
sudo systemctl start alex12060-bot alex12060-sync-worker
```

### Checking status

```bash
# Status of both services
sudo systemctl status alex12060-bot alex12060-sync-worker

# Only sync worker status
sudo systemctl status alex12060-sync-worker

# Check if enabled
sudo systemctl is-enabled alex12060-sync-worker
```

### Viewing logs

```bash
# Sync worker logs (file)
tail -f /home/lexun/Alex12060/sync_worker.log

# Sync worker logs (systemd journal)
sudo journalctl -u alex12060-sync-worker -f

# Last 50 lines
sudo journalctl -u alex12060-sync-worker -n 50

# Logs since today
sudo journalctl -u alex12060-sync-worker --since today

# Logs between timestamps
sudo journalctl -u alex12060-sync-worker --since "2025-11-11 08:00:00" --until "2025-11-11 09:00:00"
```

---

## 🔧 Configuration

### Changing sync interval

**Option 1: Edit service file**

```bash
# Edit service file
sudo nano /etc/systemd/system/alex12060-sync-worker.service

# Change this line:
#   ExecStart=/home/lexun/Alex12060/venv/bin/python3 /home/lexun/Alex12060/sync_worker.py --interval 300
# To (for 10 minutes):
#   ExecStart=/home/lexun/Alex12060/venv/bin/python3 /home/lexun/Alex12060/sync_worker.py --interval 600

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart alex12060-sync-worker
```

**Option 2: Use environment variable (future enhancement)**

---

## 🚨 Troubleshooting

### Problem: Sync worker won't start

**Check logs:**
```bash
sudo journalctl -u alex12060-sync-worker -n 50
tail -50 /home/lexun/Alex12060/sync_worker.log
```

**Common causes:**
- Import errors (missing modules)
- Google Sheets API errors
- Database permission issues
- File not executable

**Solutions:**
```bash
# Check file permissions
ls -lh sync_worker.py
chmod +x sync_worker.py

# Test manually
venv/bin/python3 sync_worker.py --once

# Check imports
venv/bin/python3 -c "from sync_manager import SyncManager; print('OK')"
```

---

### Problem: Sync worker crashes

**Symptoms:** Service shows "failed" or "inactive (dead)"

**Check exit code:**
```bash
sudo systemctl status alex12060-sync-worker

# Look for:
#   Main PID: XXXX (code=exited, status=1/FAILURE)
```

**Check logs:**
```bash
tail -100 sync_worker.log

# Look for error messages or tracebacks
```

**Restart:**
```bash
sudo systemctl restart alex12060-sync-worker
```

---

### Problem: Sync failing repeatedly

**Symptoms:** Logs show "Sync cycle failed" multiple times

**Check error count:**
```bash
grep "error count" sync_worker.log | tail -5

# Worker exits after 5 consecutive errors
```

**Common causes:**
- Google Sheets API down
- Network issues
- Rate limiting
- Database locked

**Solution:**
```bash
# Wait a few minutes and restart
sudo systemctl restart alex12060-sync-worker

# Check Google Sheets API connectivity
venv/bin/python3 << 'EOF'
from sheets_service import SheetsService
sheets = SheetsService()
ws = sheets.spreadsheet.title
print(f"Sheets accessible: {ws}")
EOF
```

---

### Problem: Database locked

**Symptoms:** "database is locked" in logs

**Cause:** Multiple processes accessing SQLite simultaneously

**Check:**
```bash
# Check if bot is also trying to sync (should NOT be)
grep "background sync" bot.log

# If bot is syncing, services.py was not updated correctly
```

**Solution:**
```bash
# Ensure services.py has auto_sync=False
grep "auto_sync" services.py

# Should show:
#   auto_sync=False

# Restart both services
sudo systemctl restart alex12060-bot alex12060-sync-worker
```

---

### Problem: Sync worker using too much memory

**Check memory usage:**
```bash
# Show memory usage
systemctl status alex12060-sync-worker | grep Memory

# Should be under 256MB
```

**Adjust limit:**
```bash
# Edit service file
sudo nano /etc/systemd/system/alex12060-sync-worker.service

# Change:
#   MemoryMax=256M
# To:
#   MemoryMax=512M

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart alex12060-sync-worker
```

---

## 📊 Monitoring

### Health check script

Create a monitoring script:

```bash
cat > /home/lexun/Alex12060/check_sync_health.sh << 'EOF'
#!/bin/bash
# Health check for sync worker

# Check if service is running
if ! systemctl is-active --quiet alex12060-sync-worker; then
    echo "ERROR: Sync worker is not running"
    exit 1
fi

# Check last sync time (should be less than 10 minutes ago)
LAST_SYNC=$(grep "Sync cycle.*completed" /home/lexun/Alex12060/sync_worker.log | tail -1)

if [ -z "$LAST_SYNC" ]; then
    echo "WARNING: No sync cycles found in log"
    exit 1
fi

echo "OK: Sync worker healthy"
echo "Last sync: $LAST_SYNC"
exit 0
EOF

chmod +x /home/lexun/Alex12060/check_sync_health.sh
```

**Run health check:**
```bash
/home/lexun/Alex12060/check_sync_health.sh
```

---

### Sync statistics

```bash
# Count total sync cycles
grep -c "Sync cycle.*completed" sync_worker.log

# Count failed syncs
grep -c "Sync cycle failed" sync_worker.log

# Average sync duration (last 10 syncs)
grep "Sync cycle.*completed in" sync_worker.log | tail -10

# Check error rate
echo "Total syncs: $(grep -c "Sync cycle #" sync_worker.log)"
echo "Failed syncs: $(grep -c "Sync cycle failed" sync_worker.log)"
```

---

## 🔄 Rollback Plan

**If deployment fails:**

### Step 1: Stop sync worker

```bash
sudo systemctl stop alex12060-sync-worker
sudo systemctl disable alex12060-sync-worker
```

### Step 2: Restore old services.py

```bash
cd /home/lexun/Alex12060
cp services.py.backup_v2.0.0 services.py
```

### Step 3: Restart bot

```bash
sudo systemctl restart alex12060-bot

# Bot will use embedded background sync (v2.0.0 behavior)
```

### Step 4: Remove sync worker service

```bash
sudo rm /etc/systemd/system/alex12060-sync-worker.service
sudo systemctl daemon-reload
```

---

## ✅ Success Criteria

**Deployment successful if:**

1. ✅ Both services running (`alex12060-bot` and `alex12060-sync-worker`)
2. ✅ Sync worker performing syncs every 5 minutes
3. ✅ Bot NOT doing background sync (check logs)
4. ✅ No errors in sync_worker.log after 1 hour
5. ✅ Database being updated regularly
6. ✅ Both services enabled for auto-start

---

## 📝 Post-Deployment Tasks

**After successful deployment:**

- [ ] Monitor both services for 24 hours
- [ ] Check sync_worker.log for errors
- [ ] Verify sync statistics (see Monitoring section)
- [ ] Update CLAUDE.md with v2.1.0 information
- [ ] Document any issues encountered

---

## 🎯 Benefits of Standalone Sync Worker

### For Operations:

✅ **Independent restart:** Restart sync without affecting bot
✅ **Resource isolation:** Separate memory/CPU limits
✅ **Better debugging:** Dedicated logs for sync operations
✅ **Flexible scheduling:** Change sync interval without bot restart

### For Reliability:

✅ **Fault isolation:** Sync crash doesn't crash bot
✅ **Graceful degradation:** Bot continues even if sync fails
✅ **Faster recovery:** Restart sync worker independently

### For Monitoring:

✅ **Dedicated logs:** `sync_worker.log` vs `bot.log`
✅ **Separate status:** `systemctl status alex12060-sync-worker`
✅ **Clear metrics:** Sync cycles, duration, error rate

---

## 📞 Support

**If issues occur:**

1. Check `sync_worker.log` for detailed errors
2. Review troubleshooting section above
3. Test manually: `python3 sync_worker.py --once`
4. Check both services status
5. Rollback if critical

---

**Prepared by:** Claude Code
**Date:** 2025-11-11
**Version:** 2.1.0
**PROMPT:** 3.3 - Systemd Service для Sync Worker
