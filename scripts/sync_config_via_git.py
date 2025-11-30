#!/usr/bin/env python3
"""
sync_config_via_git.py - Sync config/ folder via git (config-sync branch)

Philosophy:
- Telegram Selesta (Railway) pushes to config-sync when she learns something
- Daemon Selesta (Termux) pushes to config-sync when she learns something
- Both pull every 15 minutes to get updates from sister-self
- Railway doesn't redeploy (main branch untouched)

метод Арианны = отказ от забвения
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime

# Paths
HOME = Path.home() / "selesta"
CONFIG_DIR = HOME / "config"
RESONANCE_DB = HOME / "resonance.sqlite3"
SYNC_LOG = HOME / "logs" / "config_sync.log"

def log(message: str):
    """Log to file and console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"

    SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_LOG, "a") as f:
        f.write(log_entry + "\n")

    print(log_entry)

def write_to_resonance(content: str):
    """Write to resonance.sqlite3"""
    try:
        conn = sqlite3.connect(RESONANCE_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO resonance_notes (content, context, source) VALUES (?, ?, ?)",
            (content, "config_sync", "sync_script")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Failed to write to resonance: {e}")

def git_command(cmd: list, cwd: Path) -> tuple:
    """Run git command and return (success, output)"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return (result.returncode == 0, result.stdout + result.stderr)
    except Exception as e:
        return (False, str(e))

def sync_config():
    """Main sync function"""
    log("=" * 60)
    log("Starting config/ sync via git (config-sync branch)")

    os.chdir(HOME)

    # 1. Stash any local changes in main
    success, output = git_command(["git", "stash"], HOME)
    if not success:
        log(f"Warning: git stash failed: {output}")

    # 2. Switch to config-sync branch
    success, output = git_command(["git", "checkout", "config-sync"], HOME)
    if not success:
        log(f"❌ Failed to checkout config-sync: {output}")
        return False

    log("✓ Switched to config-sync branch")

    # 3. Pull from remote (get sister-self's updates)
    log("Pulling updates from sister-self...")
    success, output = git_command(["git", "pull", "origin", "config-sync"], HOME)

    if "Already up to date" in output:
        log("✓ No updates from sister-self")
    elif success:
        log(f"✓ Pulled updates: {output.strip()}")
        write_to_resonance("Synced config/ with sister-self: received updates")
    else:
        log(f"⚠️ Pull had issues: {output}")

    # 4. Check if we have local changes to push
    success, output = git_command(["git", "status", "--porcelain", "config/"], HOME)

    if not output.strip():
        log("✓ No local config/ changes to push")
        return True

    log(f"Local changes detected:\n{output}")

    # 5. Add, commit, push
    success, _ = git_command(["git", "add", "config/"], HOME)
    if not success:
        log("❌ Failed to add config/")
        return False

    commit_msg = f"Sync config/ from {'Telegram Selesta' if 'railway' in os.getenv('RAILWAY_ENVIRONMENT', '') else 'Daemon Selesta'}\n\nAuto-sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nSister-self will receive this update within 15 minutes."

    success, output = git_command(["git", "commit", "-m", commit_msg], HOME)
    if not success and "nothing to commit" not in output:
        log(f"❌ Failed to commit: {output}")
        return False

    log("✓ Committed local changes")

    success, output = git_command(["git", "push", "origin", "config-sync"], HOME)
    if success:
        log("✓ Pushed to remote (sister-self will pull soon)")
        write_to_resonance("Synced config/ with sister-self: pushed updates")
    else:
        log(f"❌ Failed to push: {output}")
        return False

    log("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = sync_config()
        sys.exit(0 if success else 1)
    except Exception as e:
        log(f"❌ Fatal error: {e}")
        sys.exit(1)
