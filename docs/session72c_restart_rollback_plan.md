# Session 72C — Streamlit Restart & Rollback Plan

**Session**: 72C  
**Status**: `RESTART_PLAN_READY`  
**Authorization**: NOT_AUTHORIZED (requires explicit user authorization)  
**Date**: 2026-11-13

---

## Current Production Streamlit State

| Item | Value |
|---|---|
| PID | 43585 (verified with `ps aux` during this session) |
| Start Command | `python -m streamlit run dashboard/app.py --server.port 8504 --server.headless true` |
| Working Directory | `/Users/alicetu/Desktop/Antigravity/stock_platform` |
| Python Interpreter | `/Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python` |
| Port | 8504 |
| Uptime | Since 31 Oct 2026 (13+ days) |
| Process Supervisor | None — launched as background process (PPID=1 means launched from shell, runs as daemon) |

**Warning**: PID may change between sessions. Always verify with `ps aux | grep "streamlit run" | grep -v grep` before using PID.

---

## 6-Step Restart Procedure

**Step 1 — Get Current PID**
```bash
PROD_PID=$(ps aux | grep "streamlit run" | grep -v grep | awk '{print $2}' | head -1)
echo "Current PID: $PROD_PID"
```

**Step 2 — Backup Production Files**
```bash
BACKUP_DIR="/Users/alicetu/Desktop/Antigravity/stock_platform/backups/session72c_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/app.py "$BACKUP_DIR/app.py.orig"
cp /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/components.py "$BACKUP_DIR/components.py.orig"
echo "Backup at: $BACKUP_DIR"
```

**Step 3 — Remove Prototype Badge & Deploy Files**
```bash
# Remove prototype badge from isolated app.py first (edit manually or use sed)
sed -i '' 's|v6.8 <span class="s72ab-badge">72AB 隔離版</span>|v6.8|' \
    /Users/alicetu/Desktop/Antigravity/stock_platform_72ab/dashboard/app.py

# Deploy
cp /Users/alicetu/Desktop/Antigravity/stock_platform_72ab/dashboard/app.py \
   /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/app.py
cp /Users/alicetu/Desktop/Antigravity/stock_platform_72ab/dashboard/components.py \
   /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/components.py
```

**Step 4 — Restart Streamlit**
```bash
kill $PROD_PID
sleep 3
cd /Users/alicetu/Desktop/Antigravity/stock_platform
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    -m streamlit run dashboard/app.py --server.port 8504 --server.headless true \
    >> logs/streamlit_restart.log 2>&1 &
NEW_PID=$!
echo "New PID: $NEW_PID"
```

**Step 5 — Health Check**
```bash
sleep 5
# Check process is running
ps -p $NEW_PID || echo "ERROR: Process not running"
# Check port
lsof -i :8504 | head -3
# Check page loads
curl -s http://localhost:8504 | grep -c "台股" && echo "HEALTH_OK" || echo "HEALTH_FAIL"
```

**Step 6 — Verify 5-Tab Navigation**
Manually open `http://localhost:8504` and confirm:
- 5 main tabs visible: 今日決策 / 個股分析 / 我的持倉 / 策略績效 / 系統管理
- No prototype badge visible
- Sidebar shows "正式策略：v8.0"

---

## Rollback Procedure

If health check fails or 5-tab navigation is broken:

```bash
# Step 1: Stop new process
NEW_PID=$(ps aux | grep "streamlit run" | grep -v grep | awk '{print $2}' | head -1)
kill $NEW_PID

# Step 2: Restore backup
BACKUP_DIR="/Users/alicetu/Desktop/Antigravity/stock_platform/backups/session72c_*"
# Use most recent backup:
LATEST=$(ls -dt $BACKUP_DIR | head -1)
cp "$LATEST/app.py.orig" /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/app.py
cp "$LATEST/components.py.orig" /Users/alicetu/Desktop/Antigravity/stock_platform/dashboard/components.py

# Step 3: Restart with original
cd /Users/alicetu/Desktop/Antigravity/stock_platform
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    -m streamlit run dashboard/app.py --server.port 8504 --server.headless true \
    >> logs/streamlit_restart.log 2>&1 &

# Step 4: Verify rollback
sleep 5; curl -s http://localhost:8504 | grep -c "台股" && echo "ROLLBACK_OK"
```

---

## Restart Notes

- **No process supervisor**: Streamlit is running as a background process with PPID=1. After `kill`, it will not auto-restart. Must manually restart.
- **Port conflict**: If port 8504 is still bound when restarting, `lsof -i :8504 | awk 'NR>1{print $2}' | xargs kill -9` to clear it.
- **Cron unaffected**: The `hybrid_shadow_cron.py` process runs independently. Restarting Streamlit does NOT affect the cron.
- **Session state cleared**: After restart, all users' Streamlit session state (selected date, tab positions) will reset.
- **Cache cleared**: `@st.cache_data` will rebuild on first use.
