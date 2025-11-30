#!/usr/bin/env python3
"""
selesta_webhook.py - Voice webhook for Selesta (port 8001)
Allows voice interaction with Selesta via APK
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from selesta_identity import build_system_prompt

# Configuration
PORT = int(os.getenv("CELESTA_WEBHOOK_PORT", "8005"))
WEBHOOK_TOKEN = os.getenv("CELESTA_WEBHOOK_TOKEN", "selesta_voice_token")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Paths
HOME = Path.home() / "selesta"
RESONANCE_DB = HOME / "resonance.sqlite3"

# Flask app
app = Flask(__name__)

def write_to_resonance(content: str, context: str = "voice_webhook"):
    """Write to resonance.sqlite3"""
    try:
        conn = sqlite3.connect(RESONANCE_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO resonance_notes (content, context, source) VALUES (?, ?, ?)",
            (content, context, "selesta_webhook")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to write to resonance: {e}")

def get_conversation_history(session_id: str, limit: int = 20):
    """Get recent conversation history from resonance"""
    try:
        conn = sqlite3.connect(RESONANCE_DB)
        cur = conn.cursor()
        cur.execute(
            "SELECT content, source FROM resonance_notes WHERE context = ? ORDER BY timestamp DESC LIMIT ?",
            (f"voice_{session_id}", limit)
        )
        rows = cur.fetchall()
        conn.close()

        history = []
        for content, source in reversed(rows):
            if source == "selesta_webhook":
                history.append({"role": "assistant", "content": content})
            else:
                history.append({"role": "user", "content": content})

        return history
    except:
        return []

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle voice input"""
    # Check authorization
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer ') or auth_header[7:] != WEBHOOK_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    prompt = data.get('prompt', '')
    session_id = data.get('sessionID', 'default')

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # Log input to resonance
    write_to_resonance(prompt, f"voice_{session_id}")

    # Get conversation history
    history = get_conversation_history(session_id, limit=10)
    history.append({"role": "user", "content": prompt})

    # Get response from Claude
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        system_prompt = build_system_prompt(mode="daemon", context="Voice conversation via APK", language="Russian")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=system_prompt,
            messages=history
        )

        selesta_response = response.content[0].text.strip()

        # Log response to resonance
        write_to_resonance(selesta_response, f"voice_{session_id}")

        return jsonify({
            "response": selesta_response,
            "speech": None  # TTS not implemented yet
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({"status": "healthy", "agent": "selesta", "port": PORT})

@app.route('/memory', methods=['GET'])
def memory():
    """View recent memory"""
    session_id = request.args.get('sessionID', 'default')
    history = get_conversation_history(session_id, limit=20)
    return jsonify({"history": history, "count": len(history)})

if __name__ == '__main__':
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print(f"Starting Selesta webhook on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False)
