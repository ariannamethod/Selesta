"""Arianna Core Utils - Memory, Documents, Agents

This package contains essential utilities for Arianna Method:
- repo_monitor: SHA256-based repository change detector (writes to resonance.sqlite3)
- whotheythinkiam: Self-reflection utility (README identity shifts to resonance)
- cynical_filter: Monday's DeepSeek reasoning (critiques to resonance)
- intuition_filter: Arianna's Perplexity intuition (insights to resonance)
- perplexity_core: Deep research engine (research to resonance)
- scribe_git_tools: Scribe's Git operations (commits to resonance)
- defender_git_tools: Defender's Git operations (commits to resonance)
- scribe_file_browser: File system awareness (insights to resonance)
- genesis_arianna: Autonomous thought generator (reflections to resonance + GitHub)
- genesis_monday: Cynical thought generator (reflections to resonance + GitHub)

ALL utilities now write to resonance.sqlite3 for complete system awareness.
"""

__version__ = "0.1.0"

import sqlite3
from pathlib import Path


def ensure_resonance_schema(db_path: Path = None):
    """
    Ensure resonance.sqlite3 has the required tables.
    Call this before any INSERT to resonance_notes.
    """
    if db_path is None:
        db_path = Path.home() / "selesta" / "resonance.sqlite3"

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create resonance_notes if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resonance_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            content TEXT NOT NULL,
            context TEXT,
            source TEXT
        )
    """)

    # Create index for faster queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_resonance_notes_context
        ON resonance_notes(context)
    """)

    conn.commit()
    conn.close()

    return True

