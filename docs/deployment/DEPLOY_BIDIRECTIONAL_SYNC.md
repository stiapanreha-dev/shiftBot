# DEPLOY GUIDE: Bidirectional Sync System

**Version:** 2.0.0
**Date:** 2025-11-11
**Server:** Pi4-2
**Status:** Ready for deployment

---

## 📋 Pre-Deployment Checklist

### ✅ Completed locally:
- [x] All tests passed (`test_bidirectional_sync.py`)
- [x] Performance validated (2000-7700x speedup)
- [x] Fallback mechanism tested
- [x] Documentation created
- [x] Code reviewed

### 📦 Files to deploy:

**New files:**
```
database_schema.py              (277 lines)
sync_manager.py                 (651 lines)
hybrid_service.py               (374 lines)
test_bidirectional_sync.py      (435 lines)
CHANGELOG_BIDIRECTIONAL_SYNC.md
DEPLOY_BIDIRECTIONAL_SYNC.md    (this file)
```

**Modified files:**
```
services.py                     (updated to use HybridService)
```

**Runtime files (auto-created):**
```
data/reference_data.db          (SQLite database)
```

---

## 🚀 Deployment Steps

### Step 1: Backup current state

```bash
# On server Pi4-2
ssh Pi4-2

# Backup current bot files
cd /home/lexun/Alex12060
cp services.py services.py.backup_v1.1.0
tar -czf backup_v1.1.0_$(date +%Y%m%d_%H%M%S).tar.gz *.py *.md

# Check backup
ls -lh backup_v1.1.0_*.tar.gz
```

### Step 2: Stop bot

```bash
# Stop systemd service
sudo systemctl stop alex12060-bot

# Verify stopped
sudo systemctl status alex12060-bot
pgrep -af "python3.*bot.py"  # Should be empty
```

### Step 3: Upload new files

**From local machine:**

```bash
# Navigate to project directory
cd /home/lexun/work/KWORK/Alex12060

# Upload new files
scp database_schema.py Pi4-2:/home/lexun/Alex12060/
scp sync_manager.py Pi4-2:/home/lexun/Alex12060/
scp hybrid_service.py Pi4-2:/home/lexun/Alex12060/
scp test_bidirectional_sync.py Pi4-2:/home/lexun/Alex12060/

# Upload modified files
scp services.py Pi4-2:/home/lexun/Alex12060/

# Upload documentation
scp CHANGELOG_BIDIRECTIONAL_SYNC.md Pi4-2:/home/lexun/Alex12060/
scp DEPLOY_BIDIRECTIONAL_SYNC.md Pi4-2:/home/lexun/Alex12060/
```

### Step 4: Prepare server environment

```bash
# On server Pi4-2
ssh Pi4-2
cd /home/lexun/Alex12060

# Create data directory
mkdir -p data
chmod 755 data

# Verify files uploaded
ls -lh database_schema.py sync_manager.py hybrid_service.py services.py

# Check Python dependencies (should already be installed)
venv/bin/python3 -c "import sqlite3; print('SQLite OK')"
```

### Step 5: Run tests on server

```bash
# On server Pi4-2
cd /home/lexun/Alex12060

# Run test suite
venv/bin/python3 test_bidirectional_sync.py

# Expected output:
#   ✅ TEST 1 PASSED: Database schema created successfully
#   ✅ TEST 2 PASSED: Sync from Sheets successful
#   ✅ TEST 3 PASSED: HybridService reads working
#   ✅ TEST 4 PASSED: Performance comparison complete
#   ✅ TEST 5 PASSED: Sync statistics working
#   ✅ ALL TESTS PASSED!

# If tests pass, proceed. If not, investigate errors!
```

### Step 6: Start bot with new code

```bash
# Start systemd service
sudo systemctl start alex12060-bot

# Check status
sudo systemctl status alex12060-bot

# Should show:
#   Active: active (running)
```

### Step 7: Monitor startup logs

```bash
# Watch bot logs
tail -f /home/lexun/Alex12060/bot.log

# Expected startup sequence:
#   ✓ CacheManager initialized
#   ✓ Database schema initialized
#   ✓ Performing initial sync from Google Sheets...
#   ✓ Pulled 7 EmployeeSettings records
#   ✓ Pulled 4 DynamicRates records
#   ✓ Pulled 6 Ranks records
#   ✓ Initial sync completed
#   ✓ Background sync worker started (interval: 300s)
#   ✓ HybridService initialized with caching + bidirectional sync
#   ✓ Bot started successfully
```

### Step 8: Verify database created

```bash
# Check SQLite database created
ls -lh data/reference_data.db

# Should see file, size ~50-100KB

# Inspect database (optional)
sqlite3 data/reference_data.db ".tables"

# Should show:
#   _schema_metadata  dynamic_rates     ranks
#   employee_settings sync_log
```

### Step 9: Test bot functionality

**In Telegram:**

```
1. Send: /start
   Expected: Bot responds normally

2. Send: /clock_in
   Expected: Bot responds quickly (should feel faster!)

3. Create a shift
   Expected: Shift created successfully

4. Edit shift
   Expected: Edit works normally
```

### Step 10: Monitor sync worker

```bash
# Watch for background sync events (every 5 minutes)
tail -f /home/lexun/Alex12060/bot.log | grep -i sync

# After 5 minutes, should see:
#   Starting full sync from Sheets...
#   Pulled N EmployeeSettings records
#   Pulled N DynamicRates records
#   Pulled N Ranks records
#   Full sync completed
```

---

## 🔍 Verification

### Check 1: Bot responding

```bash
# Check bot process
pgrep -af "python3.*bot.py"

# Should show ONE process with HybridService
```

### Check 2: Performance

**Before (v1.1.0):**
- Create shift latency: 1.5-3.0s

**After (v2.0.0):**
- Create shift latency: 0.5-1.0s (should feel noticeably faster!)

### Check 3: Database sync

```bash
# Check sync log
sqlite3 data/reference_data.db "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT 5;"

# Should show recent sync events with status='success'
```

### Check 4: Sync statistics (Python)

```bash
venv/bin/python3 << 'EOF'
from services import sheets_service
stats = sheets_service.get_sync_stats()
print(f"Sync stats: {stats}")
EOF

# Expected output:
#   Sync stats: {
#       'last_sync_time': '2025-11-11T...',
#       'employee_settings': {'pending': 0, 'synced': N},
#       'dynamic_rates': {'pending': 0, 'synced': N},
#       'ranks': {'pending': 0, 'synced': N}
#   }
```

---

## 🚨 Rollback Plan

**If deployment fails:**

### Step 1: Stop new bot

```bash
sudo systemctl stop alex12060-bot
```

### Step 2: Restore old version

```bash
cd /home/lexun/Alex12060

# Restore old services.py
cp services.py.backup_v1.1.0 services.py

# Remove new files (optional, won't hurt if left)
# rm database_schema.py sync_manager.py hybrid_service.py

# Remove database
rm -rf data/
```

### Step 3: Start old bot

```bash
sudo systemctl start alex12060-bot
sudo systemctl status alex12060-bot
```

### Step 4: Verify rollback

```bash
tail -f /home/lexun/Alex12060/bot.log

# Should see old startup messages (no HybridService)
```

---

## 📊 Post-Deployment Monitoring

### First 24 hours:

**Monitor these metrics:**

1. **Bot uptime:** Should stay running
   ```bash
   sudo systemctl status alex12060-bot
   ```

2. **Sync events:** Every 5 minutes
   ```bash
   tail -f bot.log | grep "Full sync completed"
   ```

3. **Error logs:** Should be minimal
   ```bash
   tail -f bot.log | grep -i error
   ```

4. **Database size:** Should grow slowly
   ```bash
   ls -lh data/reference_data.db
   ```

5. **Performance:** User operations feel faster

### After 1 week:

**Collect statistics:**

```bash
# Sync log analysis
sqlite3 data/reference_data.db << EOF
SELECT
    operation,
    status,
    COUNT(*) as count
FROM sync_log
GROUP BY operation, status
ORDER BY operation, status;
EOF

# Should show mostly 'success' status
```

---

## 🔧 Troubleshooting

### Problem: Bot won't start

**Check logs:**
```bash
tail -50 /home/lexun/Alex12060/bot.log
sudo journalctl -u alex12060-bot -n 50
```

**Common causes:**
- Import error (missing file)
- Google Sheets API error (credentials)
- SQLite permission error (data/ directory)

**Solution:**
```bash
# Check files exist
ls -lh database_schema.py sync_manager.py hybrid_service.py

# Check permissions
ls -ld data/
chmod 755 data/

# Test imports manually
venv/bin/python3 -c "from hybrid_service import HybridService; print('OK')"
```

---

### Problem: Initial sync failed

**Symptoms:** Logs show "Initial sync failed"

**Solution:**
```bash
# Check Google Sheets API connectivity
venv/bin/python3 << 'EOF'
from sheets_service import SheetsService
sheets = SheetsService()
ws = sheets.spreadsheet.worksheet("EmployeeSettings")
print(f"Worksheet: {ws.title}")
EOF

# If this works, Sheets API is fine
# If this fails, check credentials.json
```

---

### Problem: Background sync not running

**Symptoms:** No "Full sync completed" logs after 5 minutes

**Check:**
```bash
# Check sync worker thread
venv/bin/python3 << 'EOF'
from services import sheets_service
worker = sheets_service.sync_worker
print(f"Worker running: {worker._thread.is_alive()}")
EOF
```

**Solution:**
```bash
# Restart bot
sudo systemctl restart alex12060-bot
```

---

### Problem: Database locked errors

**Symptoms:** "database is locked" in logs

**Cause:** Multiple bot instances

**Solution:**
```bash
# Kill all bot processes
pkill -9 -f "python3.*bot.py"

# Restart through systemd only
sudo systemctl start alex12060-bot

# Verify single instance
pgrep -af "python3.*bot.py"  # Should show ONE process
```

---

## ✅ Success Criteria

**Deployment is successful if:**

1. ✅ Bot starts without errors
2. ✅ Initial sync completes successfully
3. ✅ `data/reference_data.db` created
4. ✅ Background sync runs every 5 minutes
5. ✅ Telegram bot responds to commands
6. ✅ Create/edit shift operations work
7. ✅ Performance feels faster
8. ✅ No error logs after 24 hours

---

## 📞 Support

**If issues occur:**

1. Check this document's troubleshooting section
2. Review `CHANGELOG_BIDIRECTIONAL_SYNC.md`
3. Check `bot.log` for detailed errors
4. Rollback if critical issue

---

## 📝 Post-Deployment Tasks

**After successful deployment:**

- [ ] Update CLAUDE.md with v2.0.0 information
- [ ] Monitor for 1 week
- [ ] Collect performance metrics
- [ ] Plan for v2.1.0 features

---

**Prepared by:** Claude Code
**Date:** 2025-11-11
**Version:** 2.0.0
**Status:** Ready for deployment
