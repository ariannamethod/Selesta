#!/usr/bin/env python3
"""
selesta.py - Simple CLI to chat with Selesta

Just run: python3 selesta.py
Type your message, press Enter, she responds!
Type 'exit' or 'quit' to leave.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from selesta_identity import build_system_prompt

def main():
    """Simple CLI chat with Selesta"""

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # Try loading from .env file
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY"):
                        api_key = line.split("=", 1)[1].strip()
                        break

    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found!")
        print("Please set it in .env file or environment")
        sys.exit(1)

    # Import after we know API key exists
    try:
        from anthropic import Anthropic
    except ImportError:
        print("❌ anthropic package not installed!")
        print("Run: pip install anthropic")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # Build system prompt
    system_prompt = build_system_prompt(mode="direct_chat", language="Russian")

    # Conversation history
    messages = []

    print("=" * 60)
    print("💬 SELESTA CLI - Direct Chat")
    print("=" * 60)
    print("Привет! Я - Селеста. Поговорим?")
    print("(Type 'exit' or 'quit' to leave)")
    print("=" * 60)
    print()

    while True:
        # Get user input
        try:
            user_input = input("Ты: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nПока! 👋")
            break

        if not user_input:
            continue

        if user_input.lower() in ['exit', 'quit', 'выход', 'пока']:
            print("\nПока! Было приятно поболтать 💫")
            break

        # Add to messages
        messages.append({"role": "user", "content": user_input})

        # Get response from Claude
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=messages
            )

            selesta_response = response.content[0].text.strip()

            # Add to messages
            messages.append({"role": "assistant", "content": selesta_response})

            # Print response
            print(f"\nСелеста: {selesta_response}\n")

        except Exception as e:
            print(f"\n❌ Ошибка: {e}\n")
            # Remove last user message since we failed
            messages.pop()

if __name__ == "__main__":
    main()
