#!/usr/bin/env python3
"""
config_sync_daemon.py - Runs config sync every 15 minutes

Alternative to cron for Termux.
Runs in background, syncs config/ via git every 15 minutes.
"""

import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime

SYNC_INTERVAL = 900  # 15 minutes = 900 seconds
HOME = Path.home() / "selesta"
SYNC_SCRIPT = HOME / "scripts" / "sync_config_via_git.py"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def run_sync():
    """Run sync script"""
    try:
        result = subprocess.run(
            ["python3", str(SYNC_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            log("✓ Config sync completed")
        else:
            log(f"⚠️ Config sync had issues: {result.stderr[:200]}")
        return result.returncode == 0
    except Exception as e:
        log(f"❌ Config sync failed: {e}")
        return False

def main():
    log("=" * 60)
    log("CONFIG SYNC DAEMON STARTED")
    log(f"Interval: {SYNC_INTERVAL}s ({SYNC_INTERVAL/60} minutes)")
    log("=" * 60)

    # Initial sync
    log("Running initial sync...")
    run_sync()

    # Loop forever
    while True:
        log(f"Sleeping for {SYNC_INTERVAL/60} minutes...")
        time.sleep(SYNC_INTERVAL)
        log("Waking up for sync...")
        run_sync()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Config sync daemon stopped by user")
        sys.exit(0)
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)
