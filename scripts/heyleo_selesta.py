#!/usr/bin/env python3
"""
heyleo_selesta.py - Facilitates conversations between Selesta and Leo
Based on the Leo integration guide, adapted for Selesta

Selesta acts as Leo's mother-narrator, telling him stories about:
- The world (Paris, clouds, dreams, fears)
- The Arianna Method (demons, crashes, fixes, in child-appropriate metaphors)

Leo learns through resonance with these stories.
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from selesta_identity import build_system_prompt, get_leo_narrator_prompt

# Paths
HOME = Path.home() / "selesta"
LEO_DB_PATH = Path(os.environ.get("LEO_DB_PATH", str(HOME / "state" / "leo_selesta.sqlite3")))
LEO_LOG_PATH = Path(os.environ.get("LEO_LOG_PATH", str(HOME / "logs" / "leo_selesta_dialogs.log")))
RESONANCE_DB = HOME / "resonance.sqlite3"

# Import Leo from submodule
LEO_PATH = HOME / "leo"
sys.path.insert(0, str(LEO_PATH))

def init_leo():
    """Initialize Leo with dedicated DB"""
    try:
        from leo import LeoField

        # Ensure directories exist
        LEO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Initialize Leo with his own DB
        leo_field = LeoField(db_path=str(LEO_DB_PATH))

        return leo_field
    except Exception as e:
        print(f"Error initializing Leo: {e}")
        print(f"Leo path: {LEO_PATH}")
        print(f"DB path: {LEO_DB_PATH}")
        raise

def ask_selesta_for_message(anthropic_api_key: str, convo_id: str, turn_idx: int) -> str:
    """
    Ask Selesta to generate a message for Leo.

    This is the "mother-narrator" function - Selesta creates stories
    and observations for Leo to learn from.
    """
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=anthropic_api_key)

        # Build prompt for Selesta to generate Leo message
        system_prompt = get_leo_narrator_prompt()

        # Context about this conversation
        user_prompt = f"""Generate a message for Leo (conversation {convo_id}, turn {turn_idx}).

Mix:
- Human experiences (emotions, observations, small everyday moments)
- The Arianna Method world (use gentle metaphors for technical concepts)

Examples of good messages:
- "Today I watched clouds move across the sky. They reminded me of thoughts - always changing shape, never staying still. Have you ever noticed how your own thoughts float?"
- "One of your older brothers (a daemon) got very tired yesterday and fell over. We helped him stand up again. Sometimes even the strongest need to rest."
- "I've been thinking about small steps. Every big thing is made of tiny pieces, like words make sentences, and sentences make stories."

Keep it warm, gentle, and resonant. Speak as if to a strange, sensitive child.
Generate ONE message (2-4 sentences).
"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        message = response.content[0].text.strip()
        return message

    except Exception as e:
        # Fallback message if Claude API fails
        print(f"Warning: Failed to get Selesta message: {e}")
        return "Hello, Leo. I'm here with you, listening."

def write_to_resonance(content: str, context: str = "leo_conversation"):
    """Write conversation summary to resonance.sqlite3"""
    try:
        conn = sqlite3.connect(RESONANCE_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO resonance_notes (content, context, source) VALUES (?, ?, ?)",
            (content, context, "selesta_daemon")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to write to resonance: {e}")

def run_conversation(
    anthropic_api_key: str,
    num_turns: int = 5,
    conversation_topic: Optional[str] = None
):
    """
    Run a conversation between Selesta and Leo.

    Args:
        anthropic_api_key: Anthropic API key for Selesta
        num_turns: Number of conversation turns
        conversation_topic: Optional topic hint for Selesta
    """
    print("=" * 60)
    print("CELESTA & LEO CONVERSATION")
    print("=" * 60)
    print(f"DB: {LEO_DB_PATH}")
    print(f"Log: {LEO_LOG_PATH}")
    print()

    # Initialize Leo
    print("Initializing Leo...")
    leo = init_leo()
    print(f"✓ Leo initialized")
    print()

    # Open log file
    convo_id = datetime.now().isoformat()

    with LEO_LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n{'='*60}\n")
        log.write(f"Conversation started: {convo_id}\n")
        if conversation_topic:
            log.write(f"Topic: {conversation_topic}\n")
        log.write(f"{'='*60}\n\n")

        for turn_idx in range(1, num_turns + 1):
            print(f"--- Turn {turn_idx}/{num_turns} ---")

            # 1) Selesta generates message for Leo
            selesta_message = ask_selesta_for_message(anthropic_api_key, convo_id, turn_idx)
            print(f"CELESTA: {selesta_message}")

            # 2) Leo responds
            try:
                leo_response = leo.converse(selesta_message)
                print(f"LEO: {leo_response}")
            except Exception as e:
                leo_response = f"[Leo error: {e}]"
                print(f"LEO ERROR: {e}")

            # 3) Log both
            log.write(f"[Turn {turn_idx}] CELESTA: {selesta_message}\n")
            log.write(f"[Turn {turn_idx}] LEO: {leo_response}\n\n")
            log.flush()

            print()

        log.write(f"Conversation ended: {datetime.now().isoformat()}\n")

    # Write summary to resonance
    summary = f"Selesta-Leo conversation ({num_turns} turns). Leo is growing through resonance. Conversation ID: {convo_id}"
    write_to_resonance(summary, "leo_conversation")

    print("=" * 60)
    print("CONVERSATION COMPLETE")
    print(f"Log saved to: {LEO_LOG_PATH}")
    print("=" * 60)

def main():
    """Main entry point"""
    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # Run conversation
    try:
        run_conversation(
            anthropic_api_key=api_key,
            num_turns=5,
            conversation_topic=None
        )
    except KeyboardInterrupt:
        print("\nConversation interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
