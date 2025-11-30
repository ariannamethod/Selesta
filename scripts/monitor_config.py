#!/usr/bin/env python3
"""
monitor_config.py - Monitor config folder for changes using repo_monitor

Runs periodically to detect changes in config/ folder and writes them to resonance.
Celesta uses these to stay aware of what knowledge she has.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from selesta_core_utils.repo_monitor import RepoMonitor

def main():
    """Run config folder monitoring"""
    print("Monitoring config folder for changes...")

    # Initialize monitor for config folder
    monitor = RepoMonitor(
        repo_path=str(Path.home() / "selesta" / "config"),
        cache_file=".config_cache.json"
    )

    # Detect changes
    changes = monitor.detect_changes()

    if any(changes.values()):
        print("⚡ Changes detected in config folder:")
        for change_type, files in changes.items():
            if files:
                print(f"\n{change_type.upper()}:")
                for f in sorted(files):
                    print(f"  - {f}")
    else:
        print("✓ No changes detected in config folder")

if __name__ == "__main__":
    main()
