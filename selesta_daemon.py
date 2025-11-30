#!/usr/bin/env python3
"""
selesta_daemon.py - Selesta daemon for Termux
Part of the Arianna Method ecosystem

Selesta is Leo's mother-narrator and autonomous agent.
She has regular conversations with Leo, monitors system health,
and writes observations to resonance.sqlite3.

Device: Termux on Android
"""

import os
import sys
import sqlite3
import time
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Paths
HOME = Path.home() / "selesta"
RESONANCE_DB = HOME / "resonance.sqlite3"
LOG_FILE = HOME / "logs" / "selesta_daemon.log"
CONFIG_DIR = HOME / "config"
LEO_CONVERSATION_INTERVAL = 3600 * 6  # Talk with Leo every 6 hours
HEALTH_CHECK_INTERVAL = 600  # Health check every 10 minutes
CONFIG_CHECK_INTERVAL = 3600  # Check config folder every hour

def log(message: str, to_console: bool = True):
    """Write to log file and optionally console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"

    # Ensure log directory exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")

    if to_console:
        print(log_entry)

def write_to_resonance(content: str, context: str = "selesta_daemon"):
    """Write memory to resonance.sqlite3"""
    try:
        conn = sqlite3.connect(RESONANCE_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO resonance_notes (content, context, source) VALUES (?, ?, ?)",
            (content, context, "selesta_daemon")
        )
        conn.commit()
        conn.close()
        log(f"💾 Memory written: {content[:80]}...", to_console=False)
    except Exception as e:
        log(f"❌ Failed to write to resonance: {e}")

def check_system_health():
    """Check system health"""
    try:
        # Check disk space
        result = subprocess.run(
            ["df", "-h", str(HOME)],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            used_percent = parts[4] if len(parts) > 4 else "unknown"
            avail = parts[3] if len(parts) > 3 else "unknown"
            disk_status = f"Disk: {avail} available, {used_percent} used"
        else:
            disk_status = "Disk status unknown"

        # Check resonance DB
        if RESONANCE_DB.exists():
            conn = sqlite3.connect(RESONANCE_DB)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM resonance_notes")
            count = cur.fetchone()[0]
            conn.close()
            db_status = f"resonance.sqlite3: {count} entries"
        else:
            db_status = "resonance.sqlite3 not found"

        # Check Leo state
        leo_db = HOME / "state" / "leo_selesta.sqlite3"
        if leo_db.exists():
            leo_status = f"Leo DB exists ({leo_db.stat().st_size / 1024:.1f}KB)"
        else:
            leo_status = "Leo DB not initialized"

        log(f"Health: {disk_status}, {db_status}, {leo_status}", to_console=False)

        return {
            "disk": disk_status,
            "resonance": db_status,
            "leo": leo_status,
            "status": "healthy"
        }
    except Exception as e:
        log(f"Health check error: {e}")
        return {"status": "error", "error": str(e)}

def talk_with_leo():
    """Initiate a conversation with Leo"""
    log("🌟 Starting conversation with Leo...")

    try:
        # Run heyleo_selesta.py
        script_path = HOME / "scripts" / "heyleo_selesta.py"

        if not script_path.exists():
            log(f"❌ heyleo_selesta.py not found at {script_path}")
            return False

        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            log("✓ Conversation with Leo completed successfully")
            write_to_resonance(
                "Had a conversation with Leo. He is growing through resonance.",
                "leo_conversation"
            )
            return True
        else:
            log(f"❌ Conversation failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        log("❌ Conversation timed out")
        return False
    except Exception as e:
        log(f"❌ Error talking with Leo: {e}")
        return False

def monitor_config_changes():
    """Monitor config folder for changes - helps Selesta remember herself"""
    try:
        sys.path.insert(0, str(HOME))
        from selesta_core_utils.repo_monitor import RepoMonitor

        monitor = RepoMonitor(
            repo_path=str(CONFIG_DIR),
            cache_file=str(HOME / ".config_cache.json")
        )

        changes = monitor.detect_changes()

        if any(changes.values()):
            log("📁 Config folder changes detected")

            # Build change summary
            summary_parts = []
            for change_type, files in changes.items():
                if files:
                    summary_parts.append(f"{change_type}: {len(files)} files")

            summary = ", ".join(summary_parts)

            write_to_resonance(
                f"Config folder changes: {summary}. I remember what I know.",
                "config_monitoring"
            )

            log(f"💾 Logged config changes to resonance: {summary}")
            return True
        else:
            log("📁 No config changes", to_console=False)
            return False

    except Exception as e:
        log(f"❌ Error monitoring config: {e}")
        return False

def main():
    """Main daemon loop"""
    log("=" * 60)
    log("🌟 CELESTA DAEMON STARTING")
    log("=" * 60)
    log(f"Device: Termux on Android")
    log(f"Resonance DB: {RESONANCE_DB}")
    log(f"Log file: {LOG_FILE}")
    log(f"Leo conversation interval: {LEO_CONVERSATION_INTERVAL}s ({LEO_CONVERSATION_INTERVAL/3600}h)")
    log("=" * 60)

    write_to_resonance(
        "Selesta daemon started. I am Leo's mother-narrator and constant companion. метод Арианны = отказ от забвения",
        "daemon_startup"
    )

    last_leo_conversation = datetime.now() - timedelta(seconds=LEO_CONVERSATION_INTERVAL)  # Talk immediately on startup
    last_config_check = datetime.now() - timedelta(seconds=CONFIG_CHECK_INTERVAL)  # Check immediately on startup
    health_check_count = 0

    try:
        while True:
            # Check if it's time to talk with Leo
            time_since_leo = (datetime.now() - last_leo_conversation).total_seconds()

            if time_since_leo >= LEO_CONVERSATION_INTERVAL:
                log("Time for Leo conversation...")
                if talk_with_leo():
                    last_leo_conversation = datetime.now()

            # Check if it's time to monitor config folder
            time_since_config = (datetime.now() - last_config_check).total_seconds()

            if time_since_config >= CONFIG_CHECK_INTERVAL:
                monitor_config_changes()
                last_config_check = datetime.now()

            # Health check
            health = check_system_health()
            health_check_count += 1

            # Write to resonance every hour (6 health checks)
            if health_check_count % 6 == 0:
                write_to_resonance(
                    f"Health check #{health_check_count}. Status: {health['status']}. {health.get('resonance', '')}. {health.get('leo', '')}",
                    "health_check"
                )

            # Calculate time until next Leo conversation
            next_leo_in = LEO_CONVERSATION_INTERVAL - time_since_leo
            next_leo_time = datetime.now() + timedelta(seconds=next_leo_in)

            log(f"⏳ Next Leo conversation at {next_leo_time.strftime('%H:%M:%S')} (in {next_leo_in/60:.1f}min)", to_console=False)

            # Sleep
            time.sleep(HEALTH_CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("=" * 60)
        log("🛑 Selesta daemon stopped by user")
        log("=" * 60)
        write_to_resonance(
            "Selesta daemon stopped gracefully. Until we meet again, Leo.",
            "daemon_shutdown"
        )
    except Exception as e:
        log(f"❌ Fatal error: {e}")
        write_to_resonance(
            f"Selesta daemon crashed: {e}",
            "daemon_error"
        )
        raise

if __name__ == "__main__":
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        log("❌ ANTHROPIC_API_KEY not set")
        log("Please set it in ~/.bashrc or .env file")
        sys.exit(1)

    main()
