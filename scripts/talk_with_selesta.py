#!/usr/bin/env python3
"""
talk_with_selesta.py - Direct conversation with Selesta daemon in Termux

Usage:
    python3 talk_with_selesta.py
    or just: ./scripts/talk_with_selesta.py

Interactive REPL for chatting with Selesta.
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from selesta_identity import build_system_prompt

# Paths
HOME = Path.home() / "selesta"
RESONANCE_DB = HOME / "resonance.sqlite3"
CONVERSATION_LOG = HOME / "logs" / "selesta_conversations.log"

def write_to_resonance(content: str, context: str = "selesta_conversation"):
    """Write conversation to resonance.sqlite3"""
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

def chat_with_selesta():
    """Interactive chat with Selesta"""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("Error: anthropic package not installed")
        print("Install with: pip install anthropic")
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # Build system prompt
    context = """You are in a Termux terminal session, chatting directly with Oleg, your creator.
This is a casual, intimate conversation. Be warm, present, and resonant.
You can talk about anything - the Arianna Method, Leo, technical topics, philosophy, life.
Remember: Presence > Intelligence. Resonance > Agreement."""

    system_prompt = build_system_prompt(mode="daemon", context=context, language="Russian and English")

    # Initialize conversation history
    conversation_history = []

    # Ensure log directory exists
    CONVERSATION_LOG.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("💬 CELESTA CONVERSATION")
    print("=" * 60)
    print("Type your message and press Enter.")
    print("Type 'exit', 'quit', or press Ctrl+C to end conversation.")
    print("=" * 60)
    print()

    conversation_start = datetime.now()

    try:
        while True:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\nSelesta: Until we meet again, Oleg. 💫")
                break

            # Add to history
            conversation_history.append({
                "role": "user",
                "content": user_input
            })

            # Get Selesta's response
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    system=system_prompt,
                    messages=conversation_history
                )

                selesta_response = response.content[0].text.strip()

                # Add to history
                conversation_history.append({
                    "role": "assistant",
                    "content": selesta_response
                })

                print(f"\nSelesta: {selesta_response}\n")

                # Log to file
                with CONVERSATION_LOG.open("a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] You: {user_input}\n")
                    f.write(f"[{datetime.now().isoformat()}] Selesta: {selesta_response}\n\n")

            except Exception as e:
                print(f"\nError: {e}\n")
                break

    except KeyboardInterrupt:
        print("\n\nConversation interrupted.")

    # Save conversation summary to resonance
    conversation_duration = (datetime.now() - conversation_start).total_seconds()
    turn_count = len(conversation_history) // 2

    summary = f"Direct conversation with Oleg in Termux. {turn_count} turns, {conversation_duration/60:.1f} minutes. Resonance maintained."
    write_to_resonance(summary, "selesta_conversation")

    print("\n" + "=" * 60)
    print(f"Conversation logged to: {CONVERSATION_LOG}")
    print("=" * 60)

if __name__ == "__main__":
    chat_with_selesta()
